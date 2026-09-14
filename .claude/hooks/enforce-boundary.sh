#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write)
# Hard-blocks cross-app imports between apps/structured/** and apps/unstructured/**.
# This is a MECHANICAL check only — it does not judge whether shared code is
# well-scoped (that's the boundary-guardian agent's job when someone proposes
# adding something to packages/shared-ui). It exists to stop accidental coupling
# before it ever reaches review.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "WARNING: jq not found — enforce-boundary.sh cannot inspect this tool call and is failing open. Install jq to restore this guardrail." >&2
  exit 0
fi

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

# Only care about files inside apps/structured or apps/unstructured
side=""
case "$file_path" in
  */apps/structured/*) side="structured" ;;
  */apps/unstructured/*) side="unstructured" ;;
  apps/structured/*) side="structured" ;;
  apps/unstructured/*) side="unstructured" ;;
  *) exit 0 ;;
esac

if [ "$side" = "structured" ]; then
  forbidden="unstructured"
else
  forbidden="structured"
fi

# Gather everything that could contain new code: Write's content, Edit's new_string
content=$(echo "$input" | jq -r '[.tool_input.content, .tool_input.new_string] | map(select(. != null)) | join("\n")')

# Path-based cross-import: relative traversal, absolute app path, python dotted path,
# JS/TS alias path, or a bare mention of the sibling app's internal dirs (core/, llm/,
# ingestion_pipeline/, aird_stages/) which are the parts that must never be shared.
if echo "$content" | grep -qE "apps/${forbidden}/(core|llm|ingestion_pipeline|aird_stages|db)|apps\\.${forbidden}\\.|from apps import ${forbidden}|\\.\\./${forbidden}/|/${forbidden}/(core|llm|ingestion_pipeline|aird_stages)"; then
  echo "BLOCKED: this edit to apps/${side}/** appears to import from apps/${forbidden}/** internals (core/llm/ingestion_pipeline/aird_stages/db)." >&2
  echo "Cross-app imports are forbidden by CLAUDE.md §3. If this is genuinely shared logic, it belongs in packages/shared-ui (chrome/Help/Support/design tokens only) — route the change through the boundary-guardian agent instead of importing directly." >&2
  exit 2
fi

exit 0

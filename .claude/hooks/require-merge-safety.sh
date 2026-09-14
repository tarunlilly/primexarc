#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash)
# Blocks git commit/push until the merge-safety skill has run within the
# last 30 minutes. Mirrors ARC's existing deploy-safety hook pattern, extended
# to also cover boundary and auth-model checks relevant to the merge.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "WARNING: jq not found — require-merge-safety.sh is failing open." >&2
  exit 0
fi

input=$(cat)
cmd=$(echo "$input" | jq -r '.tool_input.command // empty')

if echo "$cmd" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+)*[[:space:]]+(commit|push)([[:space:]]|$)' \
   && ! echo "$cmd" | grep -q -- '--help'; then
  ts_file=".claude/.last-validated"
  if [ -f "$ts_file" ] && [ $(( $(date +%s) - $(cat "$ts_file") )) -lt 1800 ]; then
    exit 0
  fi
  echo "BLOCKED: run the merge-safety skill before committing or pushing. Invoke it, then retry." >&2
  exit 2
fi

exit 0

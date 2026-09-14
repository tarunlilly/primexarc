#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write)
# Extends ARC's db-security-review gate repo-wide: any change under a db/
# or migrations/ directory, or any new .sql file, in EITHER app requires a
# fresh review stamp before it can be edited/written.
#
# Freshness marker: .claude/.last-db-review (epoch seconds), 30-minute TTL.
# Stamped by the db-security-review agent (structured) or its unstructured
# counterpart once one exists — see CLAUDE.md §3.4.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "WARNING: jq not found — require-db-review.sh is failing open." >&2
  exit 0
fi

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

if echo "$file_path" | grep -qE '(^|/)(db|migrations)/|\.sql$'; then
  ts_file=".claude/.last-db-review"
  if [ -f "$ts_file" ] && [ $(( $(date +%s) - $(cat "$ts_file") )) -lt 1800 ]; then
    exit 0
  fi
  echo "BLOCKED: DB/migration change detected at $file_path." >&2
  echo "Run a db-security-review pass first (Agent tool, subagent_type=db-security-review for apps/structured, or the equivalent reviewer once apps/unstructured has one). On APPROVED it stamps .claude/.last-db-review; this hook allows edits for 30 minutes after that." >&2
  echo "Remember: ARC uses schema 'history_assessment'; PrimeData uses a configurable schema (default 'public'). They must never collide in one Postgres instance — see CLAUDE.md §3.4." >&2
  exit 2
fi

exit 0

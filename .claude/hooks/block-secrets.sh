#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write)
# Blocks writes to real .env files and blocks credential-shaped values from
# landing in tracked example/template files. Repo-wide version of the check
# ARC's deploy-safety skill already runs manually — made deterministic here
# since it costs nothing to run on every write.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "WARNING: jq not found — block-secrets.sh is failing open." >&2
  exit 0
fi

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')
content=$(echo "$input" | jq -r '[.tool_input.content, .tool_input.new_string] | map(select(. != null)) | join("\n")')

base=$(basename -- "$file_path")

# Real .env files (not .env.example / .env.*.example templates)
if echo "$base" | grep -qE '^\.env(\.[A-Za-z0-9_-]+)?$'; then
  echo "BLOCKED: direct write to a real .env file ($file_path) via an agent tool is not allowed. Set environment values through the operator's normal secret flow, not via Claude edits." >&2
  exit 2
fi

# Example/template files must never carry real-looking secrets
if echo "$base" | grep -qE '\.env(\.[^/]+)?\.example$|\.example$'; then
  if echo "$content" | grep -qE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9+/]{32,}'; then
    echo "BLOCKED: $file_path looks like a template/example file but contains a GUID-shaped or 32+-char token value. Replace with a placeholder like 'your-client-id-here'." >&2
    exit 2
  fi
fi

# .gitignore must not re-allow local env files
if [ "$base" = ".gitignore" ] && echo "$content" | grep -qE '^!.*\.env.*\.local|^!\.env$'; then
  echo "BLOCKED: this .gitignore change un-ignores a real .env/.local file pattern. That has caused a credential leak before in one of the source repos — do not repeat it." >&2
  exit 2
fi

exit 0

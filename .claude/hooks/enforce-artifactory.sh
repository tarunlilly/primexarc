#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash|Edit|Write)
# Enforces Lilly's org-wide policy: all packages come from JFrog Artifactory.
# Direct npm/PyPI/DockerHub-without-mirror is prohibited. This is a mechanical
# check for the obvious violations; the artifactory-compliance agent handles
# judgment calls (e.g. "is this base image allowed", "does this lockfile need
# regenerating against Artifactory").

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "WARNING: jq not found — enforce-artifactory.sh is failing open." >&2
  exit 0
fi

input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name // empty')

block() {
  echo "BLOCKED: $1" >&2
  echo "Lilly requires JFrog Artifactory for all package installs (org policy — see 'Artifactory | Developer Platform Front Door'). Route this through the artifactory-compliance agent if you believe this is a false positive." >&2
  exit 2
}

if [ "$tool_name" = "Bash" ]; then
  cmd=$(echo "$input" | jq -r '.tool_input.command // empty')

  # npm/yarn/pnpm install against the public registry with no --registry override
  if echo "$cmd" | grep -qE '\b(npm|npx|yarn|pnpm)\b.*\b(install|ci|add)\b' \
     && ! echo "$cmd" | grep -qE -- '--registry|elilillyco'; then
    # Only block if there's no local .npmrc pointing at Artifactory in the likely cwd.
    if ! find . -maxdepth 3 -name ".npmrc" -exec grep -l "elilillyco" {} \; 2>/dev/null | grep -q .; then
      block "npm/yarn/pnpm install with no Artifactory-scoped .npmrc found and no --registry override in the command."
    fi
  fi

  # pip install against public PyPI with no index override
  if echo "$cmd" | grep -qE '\bpip[0-9]*\b.*\binstall\b' \
     && ! echo "$cmd" | grep -qE -- '--index-url|-i |elilillyco'; then
    if ! find . -maxdepth 3 -iname "pip.conf" -o -iname "pip.ini" 2>/dev/null | xargs grep -l "elilillyco" 2>/dev/null | grep -q .; then
      block "pip install with no Artifactory index-url found and no --index-url override in the command."
    fi
  fi
fi

if [ "$tool_name" = "Edit" ] || [ "$tool_name" = "Write" ]; then
  file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')
  content=$(echo "$input" | jq -r '[.tool_input.content, .tool_input.new_string] | map(select(. != null)) | join("\n")')

  case "$file_path" in
    *.npmrc)
      if echo "$content" | grep -qE 'registry\s*=\s*https?://registry\.npmjs\.org' \
         && ! echo "$content" | grep -q "elilillyco"; then
        block "$file_path points at registry.npmjs.org instead of Artifactory."
      fi
      ;;
    *requirements*.txt|*pip.conf|*pip.ini)
      if echo "$content" | grep -qE 'index-url\s*=?\s*https?://pypi\.org' \
         && ! echo "$content" | grep -q "elilillyco"; then
        block "$file_path points at pypi.org instead of Artifactory."
      fi
      ;;
    *Dockerfile*)
      # Flag unpinned public-registry FROM lines that skip the Artifactory mirror.
      # Escape hatch: a trailing '# artifactory-exempt' comment on the FROM line.
      if echo "$content" | grep -qE '^\s*FROM\s+[a-zA-Z0-9_.-]+(/[a-zA-Z0-9_.-]+)?:latest' \
         && ! echo "$content" | grep -qE 'elilillyco|artifactory-exempt'; then
        block "$file_path pulls an unpinned public-registry base image with no Artifactory mirror and no ':latest' pin review. Use elilillyco-lilly-docker.jfrog.io/<image>:<pinned-tag>, or add '# artifactory-exempt' after review by artifactory-compliance."
      fi
      ;;
  esac
fi

exit 0

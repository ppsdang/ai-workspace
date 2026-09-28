#!/usr/bin/env bash
# Add patterns to a repository's local ignore file (.git/info/exclude), idempotently.
# Local only: nothing is committed and teammates are unaffected.
#
# Usage: exclude-local.sh <repo_dir> <pattern> [pattern ...]
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: $0 <repo_dir> <pattern> [pattern ...]" >&2; exit 64; }
repo="$1"; shift
file="$(git -C "$repo" rev-parse --git-path info/exclude)"
[[ "$file" = /* ]] || file="$repo/$file"
mkdir -p "$(dirname "$file")"
touch "$file"
grep -qxF "# ai-workspace (local)" "$file" || printf '\n# ai-workspace (local)\n' >> "$file"
for pattern in "$@"; do
  [[ "$pattern" == *$'\n'* ]] && { echo "error: pattern contains a newline" >&2; exit 65; }
  if grep -qxF -- "$pattern" "$file"; then
    echo "present: $pattern"
  else
    printf '%s\n' "$pattern" >> "$file"
    echo "added:   $pattern"
  fi
done

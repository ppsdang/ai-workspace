#!/usr/bin/env bash
# Print a one-line git status for every codebase and task worktree in the workspace.
#
# Usage: status.sh <workspace_root> [path ...]
#   With paths (relative to the root), only those are shown, e.g. `status.sh . .` in single-repo mode.
#   Without paths: codebase/*/ and task worktrees under work/*/*/.
set -uo pipefail

root="${1:-.}"
shift || true
cd "$root" || { echo "cannot enter $root" >&2; exit 1; }

if [[ $# -gt 0 ]]; then
  dirs=("$@")
else
  dirs=()
  for d in codebase/*/ work/*/*/; do [[ -e "$d/.git" ]] && dirs+=("${d%/}"); done
fi
if [[ ${#dirs[@]} -eq 0 ]]; then
  echo "no codebases found under $root (expected codebase/<name>/)" >&2
  exit 1
fi

printf '%-36s %-40s %-8s %s\n' PATH BRANCH CHANGES UPSTREAM
for dir in "${dirs[@]}"; do
  if ! git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
    printf '%-36s %s\n' "$dir" "(error: not a readable git repository)"
    continue
  fi
  branch="$(git -C "$dir" symbolic-ref --short -q HEAD \
            || { sha="$(git -C "$dir" rev-parse --short HEAD 2>/dev/null)" && echo "(detached $sha)"; } \
            || echo '?')"
  changes="$(git -C "$dir" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  if upstream="$(git -C "$dir" rev-parse --abbrev-ref '@{u}' 2>/dev/null)"; then
    read -r behind ahead < <(git -C "$dir" rev-list --left-right --count "$upstream...HEAD" 2>/dev/null || echo "? ?")
    sync="$upstream (+$ahead/-$behind)"
  else
    sync="(no upstream)"
  fi
  printf '%-36s %-40s %-8s %s\n' "$dir" "$branch" "$changes" "$sync"
done

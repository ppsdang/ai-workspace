#!/usr/bin/env bash
# Per-task git worktrees, so several tickets can be worked in parallel without touching the main clone.
#
# Usage:
#   worktree.sh add    <clone_dir> <dest_dir> <branch> <base>   create (or reuse) a worktree on <branch>
#   worktree.sh remove <clone_dir> <dest_dir>                   remove it; refuses if dirty or unpushed
#   worktree.sh list   <clone_dir>                              list worktrees of a clone
set -uo pipefail

die() { echo "error: $*" >&2; exit 1; }
[[ $# -ge 2 ]] || { sed -n '4,7p' "$0" >&2; exit 64; }
op="$1"; clone="$2"
[[ -e "$clone/.git" ]] || die "$clone is not a git clone"

case "$op" in
  add)
    [[ $# -eq 5 ]] || die "usage: $0 add <clone_dir> <dest_dir> <branch> <base>"
    dest="$3"; branch="$4"; base="$5"
    [[ "$branch" != -* && "$base" != -* && "$dest" != -* ]] || die "arguments must not start with '-'"
    git check-ref-format --branch "$branch" >/dev/null 2>&1 || die "invalid branch name '$branch'"
    if [[ -e "$dest/.git" ]]; then
      current="$(git -C "$dest" rev-parse --abbrev-ref HEAD)"
      [[ "$current" == "$branch" ]] || die "$dest exists on branch '$current', expected '$branch'"
      echo "reused: $dest ($branch)"; exit 0
    fi
    [[ -e "$dest" ]] && die "$dest exists but is not a worktree"
    git -C "$clone" fetch --quiet origin "$base" || die "could not fetch origin/$base"
    mkdir -p "$(dirname "$dest")"
    dest_abs="$(cd "$(dirname "$dest")" && pwd -P)/$(basename "$dest")"
    if git -C "$clone" show-ref --verify --quiet "refs/heads/$branch"; then
      git -C "$clone" worktree add --quiet "$dest_abs" "$branch" || die "worktree add failed"
    else
      git -C "$clone" worktree add --quiet --no-track -b "$branch" "$dest_abs" "origin/$base" || die "worktree add failed"
    fi
    echo "created: $dest ($branch from origin/$base)"
    ;;
  remove)
    [[ $# -eq 3 ]] || die "usage: $0 remove <clone_dir> <dest_dir>"
    dest="$3"
    [[ -e "$dest/.git" ]] || die "$dest is not a worktree"
    [[ -z "$(git -C "$dest" status --porcelain)" ]] || die "$dest has uncommitted changes; not removing"
    branch="$(git -C "$dest" rev-parse --abbrev-ref HEAD)"
    if upstream="$(git -C "$dest" rev-parse --abbrev-ref '@{u}' 2>/dev/null)"; then
      ahead="$(git -C "$dest" rev-list --count "$upstream..HEAD")"
      [[ "$ahead" == 0 ]] || die "$branch has $ahead unpushed commit(s); not removing"
    else
      git -C "$dest" fetch --quiet origin "$branch" 2>/dev/null \
        && [[ -z "$(git -C "$dest" rev-list "origin/$branch..HEAD" 2>/dev/null)" ]] \
        || die "$branch is not pushed; not removing"
    fi
    git -C "$clone" worktree remove "$dest" || die "worktree remove failed"
    git -C "$clone" worktree prune
    echo "removed: $dest (branch $branch kept)"
    ;;
  list)
    git -C "$clone" worktree list
    ;;
  *) die "unknown operation '$op'" ;;
esac

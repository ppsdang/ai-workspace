#!/usr/bin/env bash
# Clone (or update) one codebase into <workspace>/codebase/<name>.
# Idempotent: re-running fetches instead of re-cloning.
#
# Usage: clone-repo.sh <workspace_root> <name> <url> [branch]
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <workspace_root> <name> <url> [branch]" >&2
  exit 64
fi

root="$1"; name="$2"; url="$3"; branch="${4:-}"

if [[ ! "$name" =~ ^[A-Za-z0-9._-]+$ || "$name" == "." || "$name" == ".." ]]; then
  echo "error: invalid codebase name '$name' (allowed: letters, digits, . _ -)" >&2
  exit 65
fi
if [[ "$url" == -* || "$branch" == -* ]]; then
  echo "error: url and branch must not start with '-'" >&2
  exit 65
fi

# Canonical form for comparing remotes: ssh/https/scp-style and a trailing .git are equivalent.
normalize_url() {
  local u="${1%/}"
  u="${u%.git}"
  u="${u#*://}"                       # drop scheme
  u="${u#*@}"                         # drop user@
  if [[ "$u" != /* && "$u" =~ ^[^/:]+:[^0-9] ]]; then
    u="${u/://}"                      # scp-style host:path -> host/path
  fi
  u="$(printf '%s' "$u" | sed -E 's#^([^/:]+):[0-9]+/#\1/#')"   # drop port
  printf '%s' "$u" | tr '[:upper:]' '[:lower:]'
}

dest="$root/codebase/$name"
mkdir -p "$root/codebase"

if [[ -d "$dest/.git" ]]; then
  current_url="$(git -C "$dest" remote get-url origin 2>/dev/null || true)"
  if [[ "$(normalize_url "$current_url")" != "$(normalize_url "$url")" ]]; then
    echo "error: $dest exists with remote '$current_url', expected '$url'" >&2
    exit 1
  fi
  git -C "$dest" fetch --prune origin
  current="$(git -C "$dest" rev-parse --abbrev-ref HEAD)"
  # Fast-forward the checked-out branch only if it is the base branch and has no local changes.
  base="${branch:-$(git -C "$dest" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')}"
  if [[ -n "$base" && "$current" == "$base" && -z "$(git -C "$dest" status --porcelain)" ]]; then
    git -C "$dest" merge --ff-only --quiet "origin/$base" 2>/dev/null || echo "note: $name/$base could not fast-forward" >&2
  fi
  echo "updated: $name ($current)"
  exit 0
fi

if [[ -e "$dest" ]]; then
  echo "error: $dest exists but is not a git repository" >&2
  exit 1
fi

if [[ -n "$branch" ]]; then
  git clone --branch "$branch" -- "$url" "$dest"
else
  git clone -- "$url" "$dest"
fi
echo "cloned: $name ($(git -C "$dest" rev-parse --abbrev-ref HEAD))"

#!/usr/bin/env bash
# Build a self-contained ai-workspace demo: two small repositories with local "remotes" and a
# markdown backlog. No accounts, tokens or network needed. Requires git, python3; node 18+ for web tests.
#
# Usage: examples/demo/setup.sh [target_dir]      (default: ./ai-workspace-demo)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd -P)"
target="${1:-ai-workspace-demo}"
[[ -e "$target" ]] && { echo "error: $target already exists" >&2; exit 1; }
mkdir -p "$target/remotes"
target="$(cd "$target" && pwd -P)"

for name in api web; do
  git init --quiet --bare --initial-branch=main "$target/remotes/$name.git"
  seed="$(mktemp -d)"
  cp -R "$here/seeds/$name/." "$seed/"
  git -C "$seed" init --quiet --initial-branch=main
  git -C "$seed" add -A
  git -C "$seed" -c user.name="ai-workspace demo" -c user.email="demo@example.invalid" \
    commit --quiet -m "Initial commit"
  git -C "$seed" push --quiet "$target/remotes/$name.git" main
  rm -rf "$seed"
done

ws="$target/shop-workspace"
mkdir -p "$ws"
cp -R "$here/backlog" "$ws/backlog"
cat > "$ws/workspace.yaml" <<YAML
# yaml-language-server: \$schema=https://raw.githubusercontent.com/ppsdang/ai-workspace/main/schema/workspace.schema.json
version: 1
mode: multi
worktrees: false

workspace:
  name: Shop Demo

tracker:
  type: markdown
  path: backlog
  statuses:
    start: in-progress
    review: in-review

git_host:
  type: github            # the demo remotes are local folders, so opening PRs is skipped with a note
  default_branch: main

codebases:
  - name: api
    url: $target/remotes/api.git
  - name: web
    url: $target/remotes/web.git

protected_branches: [main]
YAML

cat <<MSG
Demo ready: $ws

  cd "$ws"
  claude                      # with the ai-workspace plugin installed (or: claude --plugin-dir <plugin>)
  /ai-workspace:init          # clones api + web, detects stacks, writes profiles and rules
  /ai-workspace:task T-1      # quick fix: one approval at the end
  /ai-workspace:task T-2      # cross-repo feature: plan approval, then ship approval

Pushes go to the local folders in $target/remotes; nothing leaves your machine.
MSG

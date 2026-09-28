# {{WORKSPACE_NAME}} — AI Development Workspace

This is an ai-workspace managed by the ai-workspace plugin.
The source of truth for requirements is the task tracker ({{TRACKER}}); for code, the git host ({{GIT_HOST}}).
Files in this workspace are working memory and never override either.

## Codebases

{{CODEBASE_TABLE}}

Each codebase is its own git repository at the path in the table{{WORKTREE_NOTE}}. Never `cd` the
shell into a codebase; use `git -C <path> ...`. Profiles with build/test/lint commands are in
`context/codebases/` — read the relevant profile before building or testing.

## Knowledge

`context/INDEX.md` lists what is known about the product: overview, architecture, features, decisions and
lessons from earlier tasks. Before analysing or changing something, search it:
`python3 <plugin>/scripts/kb.py search "<words>"`, then read only the documents you need. The code wins
when a document disagrees; note the mismatch so it can be fixed.

## Working rules

1. Understand the task and inspect the code before changing anything.
2. Follow each codebase's existing architecture and conventions; do not add dependencies without need.
3. Make the smallest change that satisfies the requirement; do not touch unrelated code.
4. Add or update tests; run the codebase's checks from its profile before calling work done.
5. Never push to protected branches ({{PROTECTED}}) or force-push. Ask before pushing, opening MRs,
   or changing tracker status.
6. If a generated profile disagrees with the code, the code wins — note it so the profile can be refreshed.

## Commands

- `/ai-workspace:task <KEY>` — work a ticket end to end
- `/ai-workspace:status` — git status across codebases
- `/ai-workspace:ci <KEY>` / `/ai-workspace:respond <KEY>` — follow up on a ticket's MRs
- `/ai-workspace:ask "<question>"` — answer a question about the product with references
- `/ai-workspace:learn <feature>` / `/ai-workspace:refresh` — document a feature; update stale documents
- `/ai-workspace:doctor` — check tools, logins and clones
- `/ai-workspace:init` — re-run detection after adding a codebase or when profiles are stale

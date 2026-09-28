---
name: status
description: Show branch, uncommitted changes and upstream sync for every codebase in the ai-workspace. Use when the user asks for workspace or cross-repo git status.
allowed-tools: Bash(bash *status.sh*), Read
---

# Workspace status

> **Paths and tools.** `${CLAUDE_PLUGIN_ROOT}` is this plugin's folder and `${CLAUDE_SKILL_DIR}` the folder
> of this file. If they appear literally (not replaced, e.g. in Cursor), use `$AI_WORKSPACE_PLUGIN_ROOT`
> when it is set, otherwise the folder two levels above this file; for `${CLAUDE_SKILL_DIR}`, this file's
> folder. If there is no AskUserQuestion tool, ask in plain text with numbered options and wait for the answer.

Run from the workspace root (the directory containing `workspace.yaml`):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/status.sh" "<workspace-root>"
```

In `mode: single`, pass the repository and any task worktrees explicitly:
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/status.sh" . . .ai-work/*` (drop `.ai-work/*` if that folder doesn't exist).

Show the table as-is, then point out anything that needs attention: uncommitted changes, codebases on a
protected branch, branches ahead of or behind upstream, codebases listed in `workspace.yaml` but not cloned.
Do not change anything.

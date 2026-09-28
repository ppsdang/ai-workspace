---
name: doctor
description: Check that the machine and the ai-workspace are ready — git, python, gh/glab and their logins, tracker credentials or MCP connection, cloned codebases, generated files. Use when setup fails, before a first task, or when the user asks to check or troubleshoot the workspace.
allowed-tools: Read, Bash(python3 */doctor.py*)
---

# ai-workspace doctor

> **Paths and tools.** `${CLAUDE_PLUGIN_ROOT}` is this plugin's folder and `${CLAUDE_SKILL_DIR}` the folder
> of this file. If they appear literally (not replaced, e.g. in Cursor), use `$AI_WORKSPACE_PLUGIN_ROOT`
> when it is set, otherwise the folder two levels above this file; for `${CLAUDE_SKILL_DIR}`, this file's
> folder. If there is no AskUserQuestion tool, ask in plain text with numbered options and wait for the answer.

1. Read `workspace.yaml` (if present) for `tracker.type`, `tracker.via`, `git_host.type`, `git_host.url`,
   `ci.provider`, `tools` and the codebase names.
2. Run:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --root . --tracker <type> --host <github|gitlab|other|none> [--host-url <git_host.url>] --ci <host|jenkins|custom|none> --tools <claude-code,cursor> --codebases <a,b,c>
   ```

   Omit options you don't have. In single-repo mode pass the codebase as `<name>=.`. The script never
   prints secret values.
3. If the tracker uses an MCP server (`via: mcp`), check that a matching server is connected and
   say which one (or that none is).
4. Report the results grouped as **Must fix** (FAIL), **Should fix** (WARN) and **OK**, with the exact
   command or setting that fixes each problem (e.g. `gh auth login`, `export JIRA_API_TOKEN=…` in the
   shell profile, `/ai-workspace:init`). Don't change anything yourself.

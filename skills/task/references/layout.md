# Workspace layout and paths

Every skill uses these names. Resolve them once per task from `workspace.yaml` and record the result in
`state.md` under `checkouts:`.

## Modes

| `mode` | Workspace root | Codebases |
|---|---|---|
| `multi` (default) | a folder holding `workspace.yaml` | each cloned to `codebase/<name>/` |
| `single` | the repository itself | exactly one codebase, `path: "."` |

In `single` mode the workspace files (`workspace.yaml`, `context/`, `tasks/`, `.ai-work/`, generated rules)
live inside the repository and are excluded locally through `.git/info/exclude`, so they never show up in
the team's diffs unless the team decides to commit them.

## Terms

- **clone path** `<clone>`: where the codebase's main checkout lives: `codebase/<name>` (multi) or `.` (single).
  `path:` is only used in single mode (`"."`).
- **components** (monorepos): a codebase may list parts that are analysed separately:

  ```yaml
  codebases:
    - name: platform
      url: git@github.com:acme/platform.git
      components:
        - { name: api, dir: services/api }
        - { name: web, dir: apps/web }
  ```

  Each component gets its own profile (`context/codebases/<codebase>--<component>.md`), rules scoped to
  `<clone>/<dir>/**`, and its own impact analysis and test commands. **Branches, commits, pushes and
  MRs stay per codebase**: one branch and one MR for the whole repository, however many components change.
- **task checkout** `<repo>`: where the task's branch is checked out and all edits, tests and git
  commands for the task happen:
  - `worktrees: false` (default): `<repo>` = `<clone>`. One task at a time per codebase.
  - `worktrees: true`: `<repo>` = `work/<folder-key>/<name>` (multi) or `.ai-work/<folder-key>` (single),
    created by `scripts/worktree.sh`. Tasks can run in parallel (for example in separate Claude sessions),
    and the main clone stays on its base branch.

**Local only** (`git_host.type: none`): codebases may have no remote at all. Branches, worktrees and
comparisons then use the local base branch instead of `origin/<base>` (the skill calls this `<base-ref>`).

## Commands

Always address a checkout explicitly, never by changing the shell's directory:

- git: `git -C <repo> ...`
- profile commands: the profile writes them from the workspace root as `cd <clone> && ...`. In a
  worktree, substitute `<repo>` for `<clone>` (and add `/<dir>` for a component).
- host CLIs (`gh`, `glab`): in a subshell `( cd <repo> && ... )`.

A fresh worktree has no installed dependencies (`node_modules`, virtualenvs, build caches). Run the
profile's install command in `<repo>` before building or testing there.

## Worktree lifecycle

- **Create** (task Phase 5): `bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree.sh" add <clone> <repo> <branch> <base>`
- **Remove** after the MR is merged or the task is abandoned, only when the user asks or agrees:
  `bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree.sh" remove <clone> <repo>`. It refuses when there are
  uncommitted or unpushed changes; report that instead of forcing it. The branch itself is kept.

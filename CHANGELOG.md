# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.1.0] - 2026-09-28

### Added
- **Local only** (`git_host.type: none`): nothing is pushed; the last approval offers *keep the branch*
  or *merge into my local base branch* (fast-forward). Repositories without a remote work, including
  worktrees; comparisons use the local base branch.
- **Any git server**: `git_host.url` for self-hosted GitLab (e.g. `https://gitlab.yourcompany.com`) and
  GitHub Enterprise; `type: other` for Bitbucket, Gitea, Azure DevOps and others (push, then a link to
  open the PR). init detects the host from the clone URLs and asks GitHub / Other git server / Local only.
- **No CLI required**: on GitLab, MRs open through `git push` options when `glab` isn't installed; on
  GitHub without `gh`, you get the PR link. `gh`/`glab` now add automation instead of being required.
- **CI providers** (`ci.provider`): `host` (GitHub Actions / GitLab CI), `jenkins` (multibranch or single
  jobs, failed stages, console log tail, re-run; `JENKINS_USER`/`JENKINS_TOKEN`), `custom` (your script for
  status/log/rerun), `none`. New `scripts/ci.py`, tested against a mock Jenkins.
- init asks what runs your pipelines; `doctor` checks Jenkins credentials, self-hosted logins and
  local-only repositories.

### Changed
- Missing `gh`/`glab` is a warning with the fallback explained, not a failure.
- The guard asks before CI re-runs through `ci.py`.

## [1.0.1] - 2026-09-28

### Fixed
- `/ai-workspace:init` asks for the tracker in two steps (Jira / GitHub Issues / Trello / Something
  else → markdown, in-house, none). The question prompt holds only four options, so Trello and others
  could previously be left out.

## [1.0.0] - 2026-09-28

First public release.

### Added
- Zero-setup demo (`examples/demo/setup.sh`): two small repositories with local remotes and a markdown
  backlog, so the whole flow can be tried without accounts or network access.
- JSON Schema for `workspace.yaml` (`schema/workspace.schema.json`) with editor hint in the template.
- Documentation: configuration reference, how it works, roadmap; rewritten README.
- GitHub issue forms (bug, feature), PR template, private security reporting link.

### Changed
- State files record each codebase's base branch (`bases:`), used by `/ci` and `/respond`.
- Single-repo mode writes `.claude/settings.local.json` so tracked files stay untouched; `/status`
  handles single-repo workspaces.
- Skill permission patterns match the quoted script paths the skills actually run; unused broad
  permissions removed (`git clone *`).
- GitHub transitions swap status labels; Jira passes `--project` and optional `--acceptance-field`.
- `/ci` and `/respond` stop on secrets findings instead of rewriting pushed history.
- `doctor` understands monorepo component profiles and single-repo settings.
- `docs/PLAN.md` replaced by `docs/roadmap.md`; README rewritten as a user guide.

### Fixed
- Custom tracker commands keep backslashes in Windows paths (`C:\tools\tracker.exe`).
- `worktree.sh`: clearer unpushed-branch check (shellcheck SC2015).
- Demo test accepts Git Bash style paths on Windows.

## [0.5.0] - 2026-09-27

### Added
- **Worktrees** (`worktrees: true`): each task gets its own checkout per codebase under
  `work/<KEY>/<name>` via `scripts/worktree.sh` (add / guarded remove / list), so tickets can run in
  parallel and the main clone stays on its base branch. Path-scoped rules cover worktree paths too.
- **Single-repo mode** (`mode: single`): use an existing repository as the workspace. Nothing is
  committed to it; workspace files are excluded locally (`scripts/exclude-local.sh`), and the team's
  `CLAUDE.md` is left alone (instructions go to a generated rule instead).
- **Monorepo components**: a codebase can list `components: [{name, dir}]`; each gets its own profile,
  rules, impact analysis and test commands, while branches and MRs stay per repository. Init proposes
  components when it detects a monorepo layout.
- SessionStart hook: lists unfinished tasks (phase and next step) when a session opens in a workspace.
- Per-agent `effort` (analyst medium, test runner low on Sonnet, reviewer high).
- Starter behaviour evals in `evals/` for `claude plugin eval` (guard, task and status without a workspace).
- Path model reference (`skills/task/references/layout.md`) shared by all skills; `state.md` records
  each codebase's checkout; cleanup of worktrees after merge.
- `doctor.py` accepts `name=path` codebases (single-repo mode).

### Fixed
- `status.sh` shows the right branch for repositories with no commits or a detached HEAD, and
  includes task worktrees.

## [0.4.0] - 2026-09-27

### Added
- `/ai-workspace:ci <KEY>`: watches MR/PR pipelines (GitHub checks, GitLab pipelines), classifies failures
  (caused by the change / flaky / pre-existing / environment) and fixes only the first kind, capped by
  `ci.max_rounds` (default 2) and a no-progress rule.
- `/ai-workspace:respond <KEY>`: fetches unresolved review threads, triages them (fix / explain / ask),
  drafts replies, and after one approval pushes fixes and posts the replies.
- `/ai-workspace:doctor` and `scripts/doctor.py`: checks tools, gh/glab logins, tracker credentials
  (without printing them), clones and generated files.
- `scripts/scan_secrets.py`: scans the lines a branch adds (not history) for keys, tokens, private
  keys, credentials in URLs and sensitive files; masks values; uses gitleaks too when installed.
- `scripts/review_threads.py`: list unresolved threads, reply, and CI summary for GitHub and GitLab.
- Task flow: pre-ship phase (base-branch drift check with rebase/merge, secrets scan), a single gate for
  quick fixes (`gates.quick_fix`), `blocked` state with a reason, per-codebase MR URLs and CI rounds
  in `state.md`, commit style taken from the repository (never `--no-verify`), lighter resume.
- Guard: raw `gh api`/`glab api` writes, GraphQL mutations, review replies and CI re-runs ask for confirmation.

### Fixed
- Child processes that get no input now have stdin closed, so a CLI waiting for input can't hang a script.

## [0.3.0] - 2026-09-27

### Security
- New Python guard hook (`hooks/guard.py`) replaces the bash push guard. It parses commands with shell
  quoting rules, expands grouped flags, follows `cd`/`sh -c`/wrappers, skips heredoc bodies, and resolves
  the real push target. It denies force/delete/`--all`/`--mirror`/`--prune` pushes, protected-branch
  pushes and merges; asks for confirmation on every push, MR/PR and tracker update, and on commands it
  cannot analyse. It also fixes a hang when the working directory was relative.
- Settings template deny rules now match the `git -C codebase/<name>` form used by the flow.
- Prompt-injection hardening: ticket and repo content marked untrusted in every agent; impact analyst
  no longer has shell access; turn limits on all agents.
- Markdown tracker refuses task files outside its folder.
- `clone-repo.sh` rejects option-like URLs and `.`/`..` names, and passes `--` to git.

### Fixed
- tracker.py: no raw tracebacks; retries on HTTP 429/502/503; clear errors for HTML login pages,
  timeouts and 401/403; literal braces in custom command templates; non-object JSON from custom commands;
  backslashes in statuses.
- Trello comments are sent in the request body, and up to 1000 comments are fetched.
- `status.sh` keeps going when one repository is broken.
- `clone-repo.sh` treats ssh/https/scp URLs of the same repository as equal and fast-forwards a clean
  base branch on update.
- ship reference uses subshells and body files, so the shell's working directory stays correct.

### Added
- Jira `--acceptance-field` (custom field, including Atlassian Document Format) and `--project` check.
- GitHub keys like `owner/repo#42`; status labels replaced on transition.
- `--max-comments` (default 20) to keep context small.
- Pre-approved read-only git commands for the task and init skills.
- CI (tests on Linux/macOS/Windows, shellcheck, plugin validation), SECURITY.md, CONTRIBUTING.md.

## [0.2.0] - 2026-09-27

### Added
- `/ai-workspace:task` flow with impact-analyst, test-runner and reviewer agents.
- Tracker adapters: Jira, GitHub, Trello, markdown, custom, none.

## [0.1.0] - 2026-09-27

### Added
- `/ai-workspace:init`, `/ai-workspace:status`, rule templates, push guard hook.

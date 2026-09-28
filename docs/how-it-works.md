# How ai-workspace works

## The pieces

| Piece | Kind | Job |
|---|---|---|
| `init` | skill | manifest → clone → detect each stack (one Explore agent per repo or component, in parallel) → profiles, path-scoped rules, workspace instructions |
| `task` | skill | the ticket flow below; the main session orchestrates and implements |
| `ci`, `respond` | skills | after the MR: fix CI failures caused by the change (capped); triage and answer review comments |
| `status`, `doctor` | skills | cross-repo git status; readiness checks |
| `impact-analyst` | agent | read-only (no shell), one per unit in parallel: affected files, contracts, tests, risks |
| `test-runner` | agent | runs a unit's checks and returns only pass/fail and the essential failures |
| `reviewer` | agent | fresh context: every acceptance criterion → code → test evidence, then correctness and security |
| `guard.py` | PreToolUse hook | denies destructive git operations, protected-branch pushes and merges; asks before outward-facing actions |
| `session_start.py` | SessionStart hook | lists unfinished tasks when a session opens |
| `scripts/` | deterministic helpers | clone, worktrees, status, tracker adapters, secrets scan, review threads/CI, doctor |

Judgement (reading code, planning, fixing) is left to Claude. Steps that must behave the same every
time (git plumbing, API calls, scanning) are scripts with tests.

## The ticket flow

```
/ai-workspace:task KEY
  0  resolve & resume ─── tasks/KEY/state.md
  1  intake ──────────── tracker adapter → task.json, requirement.md (ticket text quoted as untrusted)
  2  scale ───────────── quick-fix | feature | epic (epics are split first)
  3  impact analysis ─── impact-analyst × units, in parallel → analysis.md
  4  plan ────────────── plan.md, criteria map ─────────────► GATE 1 (skipped for quick fixes)
  5  branches ────────── same branch name per codebase (worktree or main clone)
  6  implement ───────── main session, repo conventions, TDD mode, repo's commit style
  7  test ────────────── test-runner × units → test-results.md (fix loop, max 3)
  8  review ──────────── reviewer → review.md (fix loop, max 2)
  9  pre-ship ────────── base-branch sync (rebase/merge, re-test), secrets scan
 10  ship ────────────── ──────────────────────────────────► GATE 2
                         push → one MR/PR per codebase, cross-linked → tracker comment + status
afterwards: /ai-workspace:ci KEY · /ai-workspace:respond KEY · cleanup of worktrees
```

Every phase writes its artifact under `tasks/<KEY>/` and updates `state.md`, so a task can resume in a
new session (the SessionStart hook reminds you of unfinished tasks) and leaves an audit trail.

## Sources of truth

| Source | Holds | ai-workspace |
|---|---|---|
| Task tracker | requirements, acceptance criteria, status | reads; writes only comments and status changes, after approval |
| Git host | code, branches, MRs | writes only feature branches and MRs, after approval; never merges |
| Workspace | analysis, plans, test results, reviews, state | working memory; rebuildable from `workspace.yaml` + the repos + the tracker |

## Safety layers

1. **Instructions:** gates, untrusted-content rules, scope rules in every skill and agent.
2. **Tool limits:** the analyst has no shell; agents have turn limits; pre-approved commands are read-only.
3. **Guard hook:** parses every shell command and denies or asks, independent of what the model decided.
4. **Settings deny rules:** force-push, hard reset, clean, merges, reading `.env` files.
5. **Server side (yours):** branch protection, required reviews, least-privilege tokens. This is the real boundary.

See [SECURITY.md](../SECURITY.md) for the threat model.

## Context economy

- `CLAUDE.md` stays short; per-language guidance loads only for matching files (path-scoped rules).
- Skills load on demand, and reference files (trackers, shipping, layout) are read only when needed.
- Subagents do the searching, test runs and reviewing, and return summaries rather than logs.
- Tracker comments are capped (latest 20); artifacts are passed between agents as file paths.

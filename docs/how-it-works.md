# How ai-workspace works

## The pieces

| Piece | Kind | Job |
|---|---|---|
| `init` | skill | manifest → clone → detect each stack (one Explore agent per repo or component, in parallel) → profiles, path-scoped rules, workspace instructions |
| `task` | skill | the ticket flow below; the main session orchestrates and implements |
| `ci`, `respond` | skills | after the MR: fix CI failures caused by the change (capped); triage and answer review comments |
| `status`, `doctor` | skills | cross-repo git status; readiness checks |
| `ask`, `learn`, `refresh` | skills | answer product questions with references; document a feature; update stale documents |
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

## Knowledge base

The workspace keeps what it learns in `context/` as markdown documents with a small frontmatter
(`title`, `kind`, `summary`, `tags`, `codebases`, `sources`, `generated_from`):

| Kind | File | Written by |
|---|---|---|
| brief | `product/brief.md` | the user, at setup |
| overview | `product/overview.md` | init (quick pass) |
| architecture | `architecture/system.md` | init (quick pass): calls matched to endpoints across repositories |
| feature | `product/features/<slug>.md` | `/ai-workspace:learn`, or the task flow the first time a ticket changes the feature |
| codebase | `codebases/<name>.md` | init |
| decision, learning | `decisions/`, `learnings/` | the task flow, after shipping |

`scripts/kb.py` keeps it usable:

- **index / search**: a local SQLite FTS5 index (BM25; titles and headings weighted; a pure-Python scorer
  where FTS5 is missing), rebuilt incrementally from the markdown, which stays the source of truth. The
  index file `context/.kb.sqlite` is a cache and isn't committed.
- **index-md**: `context/INDEX.md`, one line per document, the only part loaded into every session.
- **stale**: compares each document's `generated_from` commits with the current code, limited to its
  `sources` paths, so `/ai-workspace:refresh` updates only what changed.
- **check**: frontmatter and size budgets (e.g. 150 lines per feature), so documents stay cheap to read.

In a task, phase 1 searches the knowledge base with the ticket's terms and passes the relevant documents
(as paths) to the impact analysts, who verify them against the code and report mismatches. Phase 11 adds
what the task established: feature documents, pending changes, decisions and learnings.

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

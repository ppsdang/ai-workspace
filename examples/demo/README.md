# Demo workspace

A zero-setup way to try ai-workspace: two tiny repositories (a Python API and a JavaScript web client,
no dependencies) with **local folders as their remotes**, and a markdown backlog. No accounts, tokens or
network access needed.

```bash
examples/demo/setup.sh ~/ai-workspace-demo
cd ~/ai-workspace-demo/shop-workspace
claude --plugin-dir /path/to/ai-workspace     # or install the plugin from its marketplace
```

Then in Claude Code:

| Step | Command | What to look for |
|---|---|---|
| 1 | `/ai-workspace:init` | both repos cloned into `codebase/`, a profile per repo in `context/codebases/`, rules in `.claude/rules/` (approve the writes under `.claude/`) |
| 2 | `/ai-workspace:doctor` | everything OK |
| 3 | `/ai-workspace:task T-1` | a quick fix in `api`: it implements, tests and reviews, then asks you **once** before pushing |
| 4 | `/ai-workspace:task T-2` | a change across `api` and `web`: impact analysis per repo, a plan to approve, API before web, then a ship gate |
| 5 | `/ai-workspace:status` | the task branches in each repo |

Pushes land in `remotes/*.git`. Opening PRs is skipped (the remotes aren't on GitHub), and the flow
saves the PR descriptions under `tasks/<KEY>/` instead. The markdown tickets in `backlog/` get their
status and an activity log updated, just as a Jira or Trello ticket would.

Requirements: git, python3 (3.10+); node 18+ for the web tests.

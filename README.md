# ai-workspace

**Take a ticket from your tracker to reviewed merge requests across all your repositories, with Claude
Code, for any stack, and approve anything that leaves your machine.**

ai-workspace is a Claude Code plugin. It turns a folder into an AI development workspace: your frontend,
backend, mobile app and services side by side (or a single repo, or a monorepo), each keeping its own git
history. Then it works tickets end to end:

```
ticket ─► impact analysis per repo ─► plan ─► implement ─► test ─► independent review ─► sync + secrets scan ─► MRs
                                        ▲                                                                   ▲
                                   you approve                                                        you approve
                               (skipped for quick fixes)
```

- **Any stack.** Each repository is analysed from its build files, CI and code. Guidance for Java,
  Kotlin, TypeScript, Angular, React, Python, Go, PHP, Flutter and C# loads only for matching files.
- **Any tracker.** Jira, GitHub Issues, Trello, plain markdown task files, in-house trackers (through
  your own script or MCP server), or pasted text.
- **GitHub and GitLab** (including self-hosted). One MR/PR per affected repository, cross-linked.
- **After the MR:** fix CI failures caused by the change (with a hard cap), and triage and answer reviewer comments.
- **Safe by default.** A guard hook denies force-pushes, protected-branch pushes and merges, and asks you
  before every push, MR/PR and tracker update. Ticket text and repo files are treated as untrusted.
- **Parallel tickets** with one git worktree per task, and **resumable** tasks with an audit trail.

## Try it in five minutes (no accounts needed)

```bash
git clone https://github.com/ppsdang/ai-workspace
ai-workspace/examples/demo/setup.sh ~/ai-workspace-demo
cd ~/ai-workspace-demo/shop-workspace
claude --plugin-dir ~/ai-workspace        # adjust the path to where you cloned it
```

```text
/ai-workspace:init
/ai-workspace:task T-1
```

The demo has two tiny repositories with local folders as remotes and a markdown backlog. Details in
[examples/demo](examples/demo/README.md).

## Install

```text
/plugin marketplace add ppsdang/ai-workspace
/plugin install ai-workspace@ai-workspace
```

**Requirements:** `git`, `python3` 3.10+ (standard library only), and `gh` or `glab` for opening
MRs/PRs. On Windows, use Git Bash (Windows support is not yet verified in CI).

Works well alongside [Superpowers](https://github.com/obra/superpowers): when it's installed, the task
flow uses its TDD, debugging and verification skills.

## Set up your own workspace

```bash
mkdir payroll-workspace && cd payroll-workspace && claude      # several repositories
# or, inside an existing repository:  cd my-repo && claude       # single-repo mode
```

```text
/ai-workspace:init       # asks for your repos and tracker, writes workspace.yaml, clones, detects stacks
/ai-workspace:doctor     # checks tools, logins, tracker credentials
```

Approve the prompts for writes under `.claude/` on the first run. Result (multi-repo):

```
payroll-workspace/
  workspace.yaml            ← the one file you edit       (reference: docs/configuration.md)
  CLAUDE.md                 ← generated, short
  .claude/settings.json     ← plugin enabled, read-only git pre-approved, destructive commands denied
  .claude/rules/            ← generated, path-scoped per repository and language
  context/codebases/*.md    ← generated profile per repository: stack, commands, layout, integrations
  codebase/<name>/          ← your repositories (own git histories, gitignored here)
  work/<KEY>/<name>/        ← per-task worktrees when worktrees: true
  tasks/<KEY>/              ← requirement, analysis, plan, test results, review, state
```

## Commands

| Command | What it does |
|---|---|
| `/ai-workspace:init [names…]` | Create or refresh the workspace: manifest, clones, stack detection, profiles, rules |
| `/ai-workspace:task <KEY \| file.md \| "text">` | Work a ticket end to end; run it again with the same key to resume |
| `/ai-workspace:ci <KEY>` | Watch the ticket's pipelines; fix failures caused by the change, at most `ci.max_rounds` times |
| `/ai-workspace:respond <KEY>` | Triage unresolved review comments (fix / explain / ask), then fix and reply after one approval |
| `/ai-workspace:status` | Branch, changes and sync state for every repository and task worktree |
| `/ai-workspace:doctor` | Readiness check: tools, logins, tracker credentials, clones |

## Workspace shapes

| Shape | In `workspace.yaml` | Notes |
|---|---|---|
| Several repositories | `codebases` with `url` | cloned into `codebase/<name>/` |
| One existing repository | `mode: single` | nothing is committed to your repo: workspace files are excluded locally, your `CLAUDE.md` is left alone |
| Monorepo | `components: [{name, dir}]` on a codebase | analysis, profiles, rules and tests per component; one branch and MR per repository |
| Parallel tickets | `worktrees: true` | each task in `work/<KEY>/<name>`; your main clones stay on their base branch |

## Trackers

| `tracker.type` | Connects via | Credentials |
|---|---|---|
| `jira` | Atlassian MCP server, or REST API (Cloud and Server/DC) | REST: `JIRA_API_TOKEN` (+ `JIRA_EMAIL` on Cloud) |
| `github` | `gh` | `gh auth login` |
| `trello` | REST API | `TRELLO_API_KEY`, `TRELLO_TOKEN` |
| `markdown` | files such as `backlog/task1.md` | none |
| `custom` | your script (`fetch` / `comment` / `transition`) or an MCP server | whatever your tracker needs |
| `none` | pasted text or a file path | none |

Secrets are read from environment variables only, never from `workspace.yaml`. See
[docs/configuration.md](docs/configuration.md).

## Documentation

- [How it works](docs/how-it-works.md): skills, agents, hooks, the ticket flow, safety layers
- [Configuration reference](docs/configuration.md): every `workspace.yaml` key, with examples
  (a [JSON Schema](schema/workspace.schema.json) gives editor completion)
- [Trackers](skills/task/references/trackers.md) · [Shipping](skills/task/references/ship.md) · [Paths and worktrees](skills/task/references/layout.md)
- [Security](SECURITY.md) · [Roadmap](docs/roadmap.md) · [Changelog](CHANGELOG.md)

## Security

Human approval gates plus a guard hook on every shell command: destructive and protected-branch git
operations and merges are denied; pushes, MRs/PRs and tracker updates need your confirmation. The hook is
a safety net, not a sandbox, so keep server-side branch protection on. Threat model and private
vulnerability reporting: [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome, especially rule templates for more stacks and tracker adapters. See
[CONTRIBUTING.md](CONTRIBUTING.md).

```bash
python3 -m unittest discover tests      # 50+ tests, standard library only
claude plugin validate .
claude plugin eval . --allow-tools Bash Read --trust-plugin    # behaviour evals (uses your Claude quota)
```

## Acknowledgements

Inspired by [Superpowers](https://github.com/obra/superpowers),
[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) and
[workspaces](https://github.com/patricio0312rev/workspaces). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

[MIT](LICENSE)

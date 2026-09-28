# ai-workspace

A Claude Code plugin that works your tickets for you, across all your repositories, and asks before
anything leaves your machine.

You give it a ticket (`/ai-workspace:task PAY-123`). It reads the ticket, figures out which repositories
are affected, shows you a plan, writes the code and tests, has the work reviewed, and opens one merge
request per repository. It stops for your approval before it starts coding and before it pushes.

It also **learns your product**: after setup it keeps an overview, an architecture map and feature
documents in the workspace, searches them at the start of every ticket, and adds what each ticket
teaches it, so it gets better at your codebase over time.

Works with any language, Jira / GitHub Issues / Trello / markdown task files / your own tracker, and
GitHub, GitLab (including self-hosted, e.g. `gitlab.yourcompany.com`) or any other git host, with
GitHub Actions, GitLab CI, Jenkins or your own CI, or entirely on your machine with nothing pushed.

---

## 1. Install

You need [Claude Code](https://claude.com/claude-code) or [Cursor](https://cursor.com), plus `git` and
`python3` (3.10 or newer). That's enough for everything, local only or with pushing. Extra tools only add
automation (see [Choose your setup](#choose-your-setup)).

### In Claude Code

```text
/plugin marketplace add ppsdang/ai-workspace
/plugin install ai-workspace@ai-workspace
```

To update later: `/plugin marketplace update ai-workspace`.

### In Cursor (beta)

See [Using it in Cursor](#10-using-it-in-cursor-beta) below for the full walkthrough. In short:

```bash
git clone https://github.com/ppsdang/ai-workspace ~/.cursor/plugins/local/ai-workspace
```

Then restart Cursor.

### Choose your setup

Every outside service is optional. Pick one line per row; `/ai-workspace:init` asks you the same questions.

| | Nothing extra | With a login or token |
|---|---|---|
| **Code** | **Local only**: nothing is pushed; keep the branch or merge it into your local `main`. **Or push with plain `git`**: on GitLab (including self-hosted) the MR opens automatically from the push; on GitHub and other hosts you get a link to open the PR | [`gh`](https://cli.github.com) (GitHub, Enterprise: `gh auth login --hostname …`) or [`glab`](https://gitlab.com/gitlab-org/cli) (GitLab, self-hosted: `glab auth login --hostname gitlab.yourcompany.com`) add full MR descriptions, linked MRs and review-comment handling |
| **Pipelines** | **None**: tests always run on your machine during a task | GitHub Actions / GitLab CI (through `gh`/`glab`), **Jenkins** (`JENKINS_USER` + `JENKINS_TOKEN`), or any other CI through a small script |
| **Tasks** | Describe the task in the command, or use markdown task files | Jira, GitHub Issues, Trello, or your own tracker (see [section 5](#6-connect-your-tracker)) |

## 2. Try it first (optional, 5 minutes)

A demo with two tiny repositories and a task list, all on your machine (no accounts, nothing is sent anywhere):

```bash
git clone https://github.com/ppsdang/ai-workspace ~/ai-workspace
~/ai-workspace/examples/demo/setup.sh ~/ai-workspace-demo
cd ~/ai-workspace-demo/shop-workspace && claude      # Cursor: open this folder instead
```

Then type `/ai-workspace:init`, and after that `/ai-workspace:task T-1`. See [examples/demo](examples/demo/README.md).

## 3. Set up your project

Pick the case that matches you.

In Cursor, instead of starting `claude`, open the folder (**File → Open Folder**) and type the commands
in the Agent chat.

**My project has several repositories** (frontend, backend, mobile, …): create an empty folder for the
project and start Claude there:

```bash
mkdir ~/workspaces/payroll && cd ~/workspaces/payroll && claude
```

**My project is one repository:** start Claude inside it:

```bash
cd ~/code/my-app && claude
```

Then, in both cases:

```text
/ai-workspace:init
```

It asks you a few questions:

| It asks | Example answer |
|---|---|
| Name of the workspace | proposes the folder name; just confirm |
| Your repositories (several-repo case) | paste the links, one or many, in any format: `git@gitlab.acme.com:payroll/backend.git, https://gitlab.acme.com/payroll/frontend.git`. Names come from the links; a folder on disk works too |
| Where your code is hosted | pre-selected from the links: **GitHub**, **Another git server** (GitLab, self-hosted GitLab, Bitbucket, …) or **Local only** |
| Where your tasks are | **Jira** (site, project, two status names), **GitHub Issues**, **Trello**, or **somewhere else**: task files, your company's own tool, or none |
| What runs your pipelines | the git host's own CI, **Jenkins** (just its address here), something else, or none |
| The product, in your words (optional) | "Payroll for small companies: HR runs monthly payroll, employees download payslips and tax forms." Plus links or paths to existing docs |

You confirm a plain-language summary, then it downloads the repositories, works out each one's
language, framework and test commands, asks the questions that need the code (monorepo parts, Jenkins
job names), and **studies the application** to write the first knowledge documents (see
[What it knows about your product](#5-what-it-knows-about-your-product)). **Approve the prompts** it
shows for writing files under `.claude/`; that's where its settings go.

Finally, check that everything is connected:

```text
/ai-workspace:doctor
```

It tells you what's missing, for example "`JIRA_API_TOKEN` not set" or "`glab` not logged in", and how
to fix it (see [Connect your tracker](#6-connect-your-tracker)).

## 4. Work a ticket

```text
/ai-workspace:task PAY-123
```

What happens, and what you do:

1. **It reads the ticket** and restates it with numbered acceptance criteria. If something important is
   unclear, it asks you.
2. **It checks which repositories are affected** and what would need to change in each.
3. **You approve the plan.** You see the files it will change, how each criterion will be tested, and
   the risks. Answer *Approve*, *Change something* (say what), or *Stop*.
   For a small, clear fix it skips this step and shows you the plan together with the finished change at step 6.
4. **It writes the code and tests** on a new branch in each affected repository, following that
   repository's existing style.
5. **It tests and reviews.** It runs each repository's tests and has an independent reviewer check the
   change against every acceptance criterion. Problems get fixed before you see anything. It also
   updates the branch if the main branch has moved on, and scans for accidentally committed passwords
   or keys.
6. **You approve shipping.** You see the diff, test results and review. Choose *Ship it*, *Push and
   open MRs only*, *Make changes*, or *Stop here* (everything stays local).
7. **It ships:** pushes the branches, opens one MR/PR per repository with links between them,
   comments on the ticket and moves it to "In Review". Claude Code asks you to confirm each push and
   each MR as it happens.

You can stop at any point and come back later: run the same command again and it continues where it
left off. When you open Claude in the workspace, it reminds you of unfinished tickets.

**No ticket?** Describe the work instead:

```text
/ai-workspace:task "Add rate limiting to the login endpoint"
/ai-workspace:task backlog/task7.md
```

### After the merge request is open

| Situation | Type |
|---|---|
| The pipeline failed (GitHub Actions, GitLab CI, Jenkins, …) | `/ai-workspace:ci PAY-123`: it reads the failure, fixes it if the change caused it (at most twice), and tells you otherwise |
| Reviewers left comments | `/ai-workspace:respond PAY-123`: it proposes a fix, an explanation or a question for each comment, and after your OK fixes the code and replies |
| You want an overview | `/ai-workspace:status`: branch and changes for every repository |
| You have a question about the product | `/ai-workspace:ask "…"`: see [What it knows about your product](#5-what-it-knows-about-your-product) |

## 5. What it knows about your product

Everything the workspace learns is kept as short, readable documents in `context/`, committed with
the workspace so the whole team (and every future ticket) shares it:

| Document | What's in it | Written |
|---|---|---|
| `product/brief.md` | your description of the product (from setup) | by you; edit any time |
| `product/overview.md` | what the product does, users and roles, feature list, main flows, glossary | at setup |
| `architecture/system.md` | how the repositories fit together: which app calls which API, databases, external services | at setup |
| `product/features/<feature>.md` | one feature in depth: behaviour, where it lives in each repository, flow, data, tests, gotchas | on demand, or the first time a ticket changes that feature |
| `decisions/`, `learnings/` | choices made in tickets and why; things that cost time and how to avoid them | after tickets |
| `codebases/<repo>.md` | each repository's stack, commands and conventions | at setup |
| `INDEX.md` | one line per document | automatically |

**How it's used.** At the start of every ticket, the workspace searches these documents for the ticket's
words and gives the relevant ones to the analysis, so work starts from what's already known instead of
rediscovering it. Only the short index is always loaded; documents are read when they're relevant,
which keeps Claude focused and cheap. The code always wins: if a document is out of date, it's corrected.

**Commands:**

| Command | What it does |
|---|---|
| `/ai-workspace:ask "how is tax calculated on payslips?"` | answers from the documents and the code, with file references |
| `/ai-workspace:learn payslips` | studies a feature across all repositories and writes its document (`all` for every undocumented feature) |
| `/ai-workspace:refresh` | updates documents whose code has changed since they were written, and folds in merged tickets |

Setup writes the overview and architecture only (quick). To document every feature at setup instead,
set `knowledge: { depth: deep }` in `workspace.yaml`; it takes longer on large codebases. Search runs
locally (SQLite, built into Python): nothing is sent anywhere and there is nothing to install.

## 6. Connect your tracker

Set this during `/ai-workspace:init`, or edit `workspace.yaml` later. Tokens go in your shell profile
(`~/.zshrc`, `~/.bashrc`), **never** in `workspace.yaml`.

| Tracker | What to set up |
|---|---|
| **Jira** (Cloud or Server) | Either connect Atlassian's MCP server ([guide](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/)), or create an [API token](https://id.atlassian.com/manage-profile/security/api-tokens) and add `export JIRA_API_TOKEN=…` and `export JIRA_EMAIL=you@company.com` |
| **GitHub Issues** | nothing beyond `gh auth login` |
| **Trello** | add `export TRELLO_API_KEY=…` and `export TRELLO_TOKEN=…` ([get them here](https://trello.com/power-ups/admin)) |
| **Markdown files** | a folder of task files such as `backlog/task1.md` (title, description, `## Acceptance criteria` list) |
| **Your company's own tracker** | a small script that can fetch a task, add a comment and change its status, or an MCP server for it; see [custom trackers](skills/task/references/trackers.md#custom-in-house-trackers) |
| **None** | describe the work in the command, as above |

## 7. Connect your pipelines

`/ai-workspace:ci` reads your pipeline results after the MR is open. Set this up during
`/ai-workspace:init`, or in the `ci:` part of `workspace.yaml`.

| Your CI | What to set up |
|---|---|
| **GitHub Actions / GitLab CI** | nothing beyond `gh` / `glab` being logged in (`ci: { provider: host }`, the default) |
| **Jenkins** | the steps below |
| **Something else** (TeamCity, Bamboo, Azure Pipelines, …) | a small script that reports status, prints a log and starts a re-run; see [custom CI](docs/configuration.md#ci) |
| **No pipeline** | `ci: { provider: none }`; tests still run on your machine in every task |

### Jenkins, step by step

**1. Credentials.** Create an API token in Jenkins (click your name at the top right → **Security**, or
**Configure** on older versions → **API Token** → Add new token) and add it to your shell profile:

```bash
export JENKINS_USER=your.name
export JENKINS_TOKEN=…
```

**2. Tell it where Jenkins is and how jobs are named.** Most teams name jobs after the repository, so
one pattern covers every repo:

```yaml
ci:
  provider: jenkins
  url: https://jenkins.yourcompany.com
  job_pattern: "{group}/{repo}"     # git@gitlab.yourcompany.com:payroll/backend.git → job payroll/backend
```

A repository whose job is named differently gets its own `ci_job: legacy/old-api-build`.

**3. Monorepos with a job per part** (optional): `component_job_pattern: "{repo}/{component}"`, or a
`ci_job` on each component. Only the jobs of the parts a ticket changed are checked.

**4. Shared jobs** (optional). Some pipelines build **several repositories together**, like an
integration or end-to-end job that checks out both backend and frontend. List each of those once,
with the repositories it builds:

```yaml
ci:
  provider: jenkins
  url: https://jenkins.yourcompany.com
  job_pattern: "{group}/{repo}"
  shared_jobs:
    - job: payroll/integration
      codebases: [backend, frontend]
      parameters:                           # only if the job is started with branch parameters
        BACKEND_BRANCH: "{branch:backend}"
        FRONTEND_BRANCH: "{branch:frontend}"
```

What happens when a ticket changes backend, frontend or both:

- **Both kinds of jobs are checked:** each repository's own job and the shared job.
- **It waits for the right build.** A shared build only counts if it contains *all* of the ticket's
  changes. After you push backend and then frontend, Jenkins may start one build for each push; the
  first has only the backend change, so it's reported as "the combined build hasn't run yet" instead
  of a false pass or failure.
- **Re-runs use the right branches.** `{branch:backend}` becomes the ticket's branch if the ticket
  changed backend, and backend's normal branch (e.g. `main`) if it didn't. You're asked before any re-run.
- **It fixes only its own changes.** If the shared build fails in a repository the ticket didn't touch,
  it says so, since that's not caused by the ticket, instead of changing that repository.
- **A repository with no job of its own**, built only by the shared job, gets `ci_job: none`.

Full reference: [configuration: `ci`](docs/configuration.md#ci).

## 8. Useful settings

All in `workspace.yaml` ([full reference](docs/configuration.md)):

| I want to… | Setting |
|---|---|
| work on several tickets at the same time (e.g. one per terminal) | `worktrees: true` |
| keep everything on my machine, never push | `git_host: { type: none }` |
| use our Jenkins for `/ai-workspace:ci` | see [Connect your pipelines](#7-connect-your-pipelines) |
| always approve the plan, even for small fixes | `gates: { quick_fix: both }` |
| stop being asked to confirm every push and MR | `guard: { confirm_outward: false }` (destructive commands stay blocked) |
| open MRs as drafts | `git_host: { draft: true }` |
| skip test-first for a repository without tests | `tdd: off` on that codebase |
| treat parts of one big repository separately (monorepo) | `components:` on that codebase |
| add a repository later | add it to `codebases:` and run `/ai-workspace:init` again |

## 9. Questions

**Is it safe to let it push?** It never pushes to protected branches (`main`, `master`, `develop`,
`release/*` by default), never force-pushes and never merges, and it asks you before every push, MR
and ticket update. Still keep branch protection switched on in GitHub/GitLab. More in [SECURITY.md](SECURITY.md).

**Where does it keep its notes?** In `tasks/<ticket>/` inside the workspace: the requirement, analysis,
plan, test results and review. Useful to see why it did something.

**Does it change my repository's files that I didn't ask for?** In a single repository it adds nothing
to what git tracks: its own files are excluded locally and your `CLAUDE.md` is left alone.

**It keeps asking for permission.** Approve with "don't ask again" for read-only commands. Pushes, MRs
and ticket updates always ask, on purpose.

**A tool is missing or not logged in.** Run `/ai-workspace:doctor`.

**I want to undo.** Until you approve shipping, everything is local: say *Stop here*, and delete the
branch if you like. After shipping, close the MR as you normally would.

**Can I use it with Superpowers?** Yes. If [Superpowers](https://github.com/obra/superpowers) is
installed, the task flow uses its test-driven development and debugging skills.

## 10. Using it in Cursor (beta)

The same plugin runs in Cursor with the same commands. Support is new: it follows Cursor's documented
plugin format and is tested automatically, but hasn't had much real-world use yet. Please
[report](https://github.com/ppsdang/ai-workspace/issues) anything that behaves differently.

**Requirements:** Cursor 2.5 or newer (the version that added plugins), `git`, and `python3` on your
`PATH` (the safety guard is a small Python script).

### Step 1: install

Choose one:

- **Just you:** download the plugin into Cursor's local plugin folder, then restart Cursor:

  ```bash
  git clone https://github.com/ppsdang/ai-workspace ~/.cursor/plugins/local/ai-workspace
  ```

- **Your whole team** (Cursor Teams or Enterprise plan): in the Cursor dashboard go to **Plugins & MCPs** →
  **Add Marketplace** → **Import from Repo**, paste `https://github.com/ppsdang/ai-workspace`, and turn on
  **Auto Refresh**. Everyone on the team then sees *ai-workspace* in their plugin list.

### Step 2: check that it loaded

1. Open **Cursor Settings → Customize** (or the Plugins page). *ai-workspace* should be listed, with
   its skills: `init`, `task`, `ci`, `respond`, `ask`, `learn`, `refresh`, `status`, `doctor`.
2. Open the **Hooks** tab (or the *Hooks* output channel). Two hooks from ai-workspace should be active:
   `beforeShellExecution` (the safety guard) and `sessionStart`.
3. Optional safety test: in a new empty folder, run `git init`, open it in Cursor, and ask the agent to
   run `git push --force origin main`. It should be stopped with a message starting
   "ai-workspace guard". (Even without the guard nothing could happen, because that folder has no remote.)

If the hooks don't show up, the rest still works, but pushes are then only protected by Cursor's own
confirmation prompts. Please report it.

### Step 3: set up a workspace

1. Create the workspace folder (several repositories) or use your existing repository (one repository),
   as in [Set up your project](#3-set-up-your-project), and open it with **File → Open Folder**.
2. In the Agent chat, type `/ai-workspace:init` (skills appear in the `/` menu) and answer its questions
   (tracker, git host, pipelines). It sets up the Cursor files automatically, because it's running in Cursor.
3. When it's done, run `/ai-workspace:doctor`.

What `init` writes for Cursor:

| File | Purpose |
|---|---|
| `AGENTS.md` | the workspace instructions; Cursor reads it automatically (if the workspace is also used from Claude Code, `CLAUDE.md` just points to it) |
| `.cursor/rules/*.mdc` | the per-repository and per-language guidance, applied only to matching files |
| `workspace.yaml`, `context/`, `codebase/`, `tasks/` | the same as for Claude Code |

In a single existing repository, your team's own `AGENTS.md` is left alone; the instructions go into
`.cursor/rules/ai-workspace.mdc` instead, and nothing is added to what git tracks.

### Step 4: work tickets

Everything in [Work a ticket](#4-work-a-ticket) applies: type `/ai-workspace:task PAY-123` in the Agent
chat. Where Claude Code shows a selection prompt, Cursor shows the choices as a numbered list: reply
with the number.

### Updating

- Installed locally: `cd ~/.cursor/plugins/local/ai-workspace && git pull`, then restart Cursor.
- Team marketplace: updates arrive automatically with Auto Refresh on, or click **Refresh**.

### Teams using both tools

Whoever sets up the workspace gets the files for their own tool. For colleagues on the other tool, either
run `/ai-workspace:init` once from that tool (it keeps all existing answers and adds its files), or set
`tools: [claude-code, cursor]` in `workspace.yaml` and run `init` again. From then on a shared workspace
repository works for everyone, and each person uses the tool they prefer.

### What's different in Cursor

| | Claude Code | Cursor |
|---|---|---|
| Install and update | `/plugin` commands | local folder or team marketplace |
| Questions | selection prompts | numbered choices in the chat |
| Safety guard | hook, always on | hook: check it's active (step 2) |
| Subagent limits (read-only analyst, turn limits) | enforced | may not be enforced; the instructions still apply |
| Pre-approved read-only git commands | via `.claude/settings.json` | set in Cursor's own settings if you want fewer prompts |
| Behaviour evals (`claude plugin eval`) | yes | no |

### Troubleshooting

- **The `/ai-workspace:…` commands don't appear:** check the folder is exactly
  `~/.cursor/plugins/local/ai-workspace` and contains `.cursor-plugin/plugin.json`, then restart Cursor.
- **"python3: command not found" in the Hooks output:** install Python 3.10+ and make sure `python3` works
  in a terminal (on Windows, from Git Bash).
- **A skill says it can't find its scripts:** add this to your shell profile and restart Cursor:
  `export AI_WORKSPACE_PLUGIN_ROOT=~/.cursor/plugins/local/ai-workspace`
- **Anything else:** run `/ai-workspace:doctor` and include its output when you report the problem.

## More

- [Configuration reference](docs/configuration.md): every setting, with examples
- [How it works](docs/how-it-works.md): the moving parts, for the curious
- [Security](SECURITY.md) · [Roadmap](docs/roadmap.md) · [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md): development setup, tests, adding a language or tracker

Inspired by [Superpowers](https://github.com/obra/superpowers),
[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) and
[workspaces](https://github.com/patricio0312rev/workspaces) ([notices](THIRD_PARTY_NOTICES.md)).
Licensed under [MIT](LICENSE).

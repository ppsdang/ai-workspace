# ai-workspace

A Claude Code plugin that works your tickets for you, across all your repositories, and asks before
anything leaves your machine.

You give it a ticket (`/ai-workspace:task PAY-123`). It reads the ticket, figures out which repositories
are affected, shows you a plan, writes the code and tests, has the work reviewed, and opens one merge
request per repository. It stops for your approval before it starts coding and before it pushes.

Works with any language, Jira / GitHub Issues / Trello / markdown task files / your own tracker, and
GitHub, GitLab (including self-hosted, e.g. `gitlab.yourcompany.com`) or any other git host, with
GitHub Actions, GitLab CI, Jenkins or your own CI, or entirely on your machine with nothing pushed.

---

## 1. Install

You need [Claude Code](https://claude.com/claude-code), `git` and `python3` (3.10 or newer). That's
enough for everything, local only or with pushing. Extra tools only add automation (see
[Choose your setup](#choose-your-setup)).

In Claude Code:

```text
/plugin marketplace add ppsdang/ai-workspace
/plugin install ai-workspace@ai-workspace
```

> The repository is private for now: you need read access to it on GitHub for this to work.

To update later: `/plugin marketplace update ai-workspace`.

### Choose your setup

Every outside service is optional. Pick one line per row; `/ai-workspace:init` asks you the same questions.

| | Nothing extra | With a login or token |
|---|---|---|
| **Code** | **Local only**: nothing is pushed; keep the branch or merge it into your local `main`. **Or push with plain `git`**: on GitLab (including self-hosted) the MR opens automatically from the push; on GitHub and other hosts you get a link to open the PR | [`gh`](https://cli.github.com) (GitHub, Enterprise: `gh auth login --hostname …`) or [`glab`](https://gitlab.com/gitlab-org/cli) (GitLab, self-hosted: `glab auth login --hostname gitlab.yourcompany.com`) add full MR descriptions, linked MRs and review-comment handling |
| **Pipelines** | **None**: tests always run on your machine during a task | GitHub Actions / GitLab CI (through `gh`/`glab`), **Jenkins** (`JENKINS_USER` + `JENKINS_TOKEN`), or any other CI through a small script |
| **Tasks** | Describe the task in the command, or use markdown task files | Jira, GitHub Issues, Trello, or your own tracker (see [section 5](#5-connect-your-tracker)) |

## 2. Try it first (optional, 5 minutes)

A demo with two tiny repositories and a task list, all on your machine (no accounts, nothing is sent anywhere):

```bash
git clone https://github.com/ppsdang/ai-workspace ~/ai-workspace
~/ai-workspace/examples/demo/setup.sh ~/ai-workspace-demo
cd ~/ai-workspace-demo/shop-workspace && claude
```

Then type `/ai-workspace:init`, and after that `/ai-workspace:task T-1`. See [examples/demo](examples/demo/README.md).

## 3. Set up your project

Pick the case that matches you.

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
| Name of the workspace | Payroll |
| Where your tasks are | Jira, `https://acme.atlassian.net`, project `PAY` |
| Status names to use | "In Progress" when work starts, "In Review" when MRs are open |
| Where your code is hosted | **GitHub**, **Other git server** (GitLab, self-hosted GitLab such as `https://gitlab.yourcompany.com`, Bitbucket, …), or **Local only** |
| What runs your pipelines | the same as the host, **Jenkins** (e.g. `https://jenkins.yourcompany.com` and a job per repo), other, or none |
| Your repositories (several-repo case) | `backend  git@gitlab.acme.com:payroll/backend.git`, `frontend  …` (a local folder works too) |

It then downloads the repositories, works out each one's language, framework and test commands, and
saves your answers in `workspace.yaml`. **Approve the prompts** it shows for writing files under
`.claude/`; that's where its settings go.

Finally, check that everything is connected:

```text
/ai-workspace:doctor
```

It tells you what's missing, for example "`JIRA_API_TOKEN` not set" or "`glab` not logged in", and how
to fix it (see [Connect your tracker](#5-connect-your-tracker)).

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

## 5. Connect your tracker

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

## 6. Useful settings

All in `workspace.yaml` ([full reference](docs/configuration.md)):

| I want to… | Setting |
|---|---|
| work on several tickets at the same time (e.g. one per terminal) | `worktrees: true` |
| keep everything on my machine, never push | `git_host: { type: none }` |
| use our Jenkins for `/ai-workspace:ci` | `ci: { provider: jenkins, url: https://jenkins.yourcompany.com, job_pattern: "{group}/{repo}" }`; `ci_job:` only for repos that don't follow the pattern |
| always approve the plan, even for small fixes | `gates: { quick_fix: both }` |
| stop being asked to confirm every push and MR | `guard: { confirm_outward: false }` (destructive commands stay blocked) |
| open MRs as drafts | `git_host: { draft: true }` |
| skip test-first for a repository without tests | `tdd: off` on that codebase |
| treat parts of one big repository separately (monorepo) | `components:` on that codebase, optionally with a Jenkins `ci_job` per component |
| add a repository later | add it to `codebases:` and run `/ai-workspace:init` again |

## 7. Questions

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

## More

- [Configuration reference](docs/configuration.md): every setting, with examples
- [How it works](docs/how-it-works.md): the moving parts, for the curious
- [Security](SECURITY.md) · [Roadmap](docs/roadmap.md) · [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md): development setup, tests, adding a language or tracker

Inspired by [Superpowers](https://github.com/obra/superpowers),
[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) and
[workspaces](https://github.com/patricio0312rev/workspaces) ([notices](THIRD_PARTY_NOTICES.md)).
Licensed under [MIT](LICENSE).

# Security

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **"Report a vulnerability"** button
(Security → Advisories) on this repository rather than in a public issue. We aim to respond within 7 days.

## Threat model

ai-workspace lets Claude Code read tickets and repositories and run commands in your workspace. Keep
these limits in mind:

| Risk | What the plugin does | What remains your responsibility |
|---|---|---|
| **Prompt injection** via ticket text, comments or files in cloned repos | Agents treat ticket and repo content as data; ticket text is quoted in an "untrusted" block; the impact analyst has no shell; the flow stops at human approval gates | Review plans and diffs at the gates; only clone repositories you trust |
| **Pushing to the wrong place** | The guard hook denies force-pushes, ref deletion, `--all`/`--mirror`/`--prune`, pushes to protected branches and MR/PR merges, and asks you to confirm every push, MR/PR and tracker update | Keep `protected_branches` accurate; use server-side branch protection as well |
| **Running repository code** | The test runner executes the project's own test/build commands, as a developer would | Don't run `/task` on repositories whose build scripts you don't trust |
| **Secrets** | Tokens come only from environment variables; the settings template denies reading `.env` files | Use least-privilege tokens; never commit secrets to `workspace.yaml` |

**The guard hook is a safety net, not a sandbox.** It parses commands to catch honest mistakes and
injected shortcuts, and asks for confirmation when it cannot analyse a command (`sh -c`, `eval`, command
substitution, git aliases). A process with shell access can still find other ways to act; server-side
protections (protected branches, required reviews, least-privilege tokens) are the real boundary.

Requirements: the guard runs with `python3`. If `python3` is not on `PATH`, the hook fails and Claude
Code continues without it, so make sure it is installed.

# Contributing

Thanks for helping! Small, focused pull requests are easiest to review.

## Setup

```bash
git clone https://github.com/ppsdang/ai-workspace && cd ai-workspace
python3 -m unittest discover tests      # all tests, standard library only
claude plugin validate .                # manifests
claude --plugin-dir .                   # try your changes in a real session
```

Behaviour evals live in `evals/<case>/` (`prompt.md` + `graders/*.md`) and run with
`claude plugin eval . --allow-tools Bash Read --trust-plugin`. They use your Claude quota (the starter set
costs well under $1), compare against a run without the plugin, and aren't run in CI. Add a case when you
change how a skill behaves.

For an end-to-end check, create a scratch workspace with a `markdown` tracker (no accounts needed) and
run `/ai-workspace:init` and `/ai-workspace:task <task-file>`.

## Good first contributions

- **Rule templates** for more stacks in `templates/rules/<stack>.md`: a `{{PATHS}}` frontmatter
  placeholder and 4–6 rules that Claude tends to get wrong for that stack. Defer to the repository's own
  conventions and don't restate what a linter enforces.
- **Tracker adapters** in `scripts/tracker.py`: implement `fetch`, `comment`, `transition`, return the
  normalised ticket, read secrets from environment variables only, and add tests against the mock server
  in `tests/test_tracker.py`.

## Guidelines

- The repository is both a Claude Code plugin (`.claude-plugin/`) and a Cursor plugin (`.cursor-plugin/`,
  hooks in `cursor/hooks.json`). Keep the version the same in both `plugin.json` files (a test checks it),
  and keep hooks working for both input formats.

- Keep the core stack-agnostic: no language-specific instructions in skills or agents.
- Scripts use only the Python standard library, or bash plus git.
- Anything outward-facing (push, MR/PR, tracker writes) must stay behind a human gate.
- Security-sensitive changes (guard hook, tracker auth) need tests for the bypass or failure you fixed.
- Update `CHANGELOG.md` under "Unreleased".

## Credit for borrowed ideas

If you adapt text or code from another project, add a header to the file and the project's licence to
`THIRD_PARTY_NOTICES.md`.

# Roadmap

## Design principles

1. **Three sources of truth.** The task tracker holds requirements and the git host holds code. The
   workspace is working memory only and never overrides either.
2. **One human-written file.** `workspace.yaml`; everything else is generated and rebuildable.
3. **Scripts for deterministic steps, Claude for judgement.**
4. **Stack-agnostic core.** Language guidance lives in rule templates loaded by path.
5. **Humans approve anything outward-facing**, and the guard hook enforces it.
6. **Small context.** Short instructions, skills loaded on demand, subagents return summaries.
7. **Nothing company-specific in this repository.** Company setup lives in each private workspace.

## Released

See [CHANGELOG.md](../CHANGELOG.md). In short: workspace setup (0.1), ticket-to-MR flow with tracker
adapters (0.2), security hardening (0.3), CI and review follow-up, secrets scan, quick-fix gate (0.4),
worktrees, single-repo and monorepo support, evals (0.5), public release (1.0).

## Next

- **`context-refresh`**: update profiles incrementally from the diff since `generated_from`.
- **Learning loop**: after merge, record what worked in `docs/solutions/` and let analysts read it first.
- **Tracker access as a bundled MCP server**: would allow plugin `userConfig` with keychain-stored tokens
  (secret values reach MCP servers but not the scripts the model runs).
- **More adapters**: Linear, Azure Boards; Bitbucket as a git host.
- **More rule templates**: Ruby, Rust, Swift, Vue, Svelte, Elixir.
- **Windows**: verify in CI and remove the non-blocking flag.
- **Headless use**: documented recipes for `claude -p` and the Claude GitHub Action.

Ideas and votes are welcome in the issue tracker.

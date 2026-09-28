---
name: refresh
description: Bring the workspace knowledge base up to date with the code — update documents whose source files changed since they were written, and fold merged task changes into feature documents. Use when the user asks to refresh, update or sync the workspace documentation or knowledge, or after MRs were merged.
allowed-tools: Read, Write, Edit, Glob, Grep, Agent, Bash(python3 *kb.py*), Bash(git -C * fetch*), Bash(git -C * log*), Bash(git -C * diff*), Bash(git -C * rev-parse *), Bash(git -C * merge-base *)
---

# ai-workspace refresh

> **Paths and tools.** `${CLAUDE_PLUGIN_ROOT}` is this plugin's folder and `${CLAUDE_SKILL_DIR}` the folder
> of this file. If they appear literally (not replaced, e.g. in Cursor), use `$AI_WORKSPACE_PLUGIN_ROOT`
> when it is set, otherwise the folder two levels above this file; for `${CLAUDE_SKILL_DIR}`, this file's
> folder. If there is no AskUserQuestion tool, ask in plain text with numbered options and wait for the answer.

1. **Update the main checkouts** so documents describe the base branches: for each codebase,
   `git -C <clone> fetch origin` (skip for local-only repositories). Don't change branches or pull
   into a checkout with local changes; if a clone isn't on its base branch, compare against
   `origin/<base>` instead of `HEAD` and say so.
2. **Find stale documents:**

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py" --root . stale [--ref <codebase>=<base-ref> ...]
   ```

   Pass `--ref` for every codebase whose clone isn't on its base branch (`<base-ref>` = `origin/<base>`).

   Each entry lists the codebases and changed files since the document was written.
3. **Pending changes:** in feature documents, each `## Pending changes` item names a task and its
   MR. If the task's commits are now in the base branch (`git -C <clone> merge-base --is-ancestor
   <commit> <base-ref>`, commits from `tasks/<KEY>/implementation.md`), fold the change into the
   document and remove the item. Leave unmerged ones.
4. **Update**, in parallel (one subagent per stale document, all in one message): give each the
   document, the changed files and `git -C <clone> diff <generated_from>..<base-ref> -- <files>`, and ask
   it to update only what changed, keeping the document's structure and size budget. Then set
   `generated_from` to the new commit and `updated` to today. A document whose sources no longer exist:
   ask the user whether to delete it.
5. **New features:** if the diffs add routes, screens or modules that no document covers, add them to
   the overview's feature list as "(not documented yet)" and mention `/ai-workspace:learn`.
6. **Index:** `kb.py index-md`, `kb.py index`, `kb.py check`.

Report: documents updated, pending changes folded in, new undocumented features, and warnings.

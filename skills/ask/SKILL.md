---
name: ask
description: Answer a question about the product or its code from the workspace knowledge base and the repositories, with references — e.g. "how is tax calculated on payslips", "which service sends emails", "where is login handled". Use when the user asks how something in their application works or where it is.
argument-hint: "\"question\""
allowed-tools: Read, Glob, Grep, Agent, Bash(python3 *kb.py*), Bash(git -C * log*)
---

# ai-workspace ask

> **Paths and tools.** `${CLAUDE_PLUGIN_ROOT}` is this plugin's folder and `${CLAUDE_SKILL_DIR}` the folder
> of this file. If they appear literally (not replaced, e.g. in Cursor), use `$AI_WORKSPACE_PLUGIN_ROOT`
> when it is set, otherwise the folder two levels above this file; for `${CLAUDE_SKILL_DIR}`, this file's
> folder. If there is no AskUserQuestion tool, ask in plain text with numbered options and wait for the answer.

Question: `$ARGUMENTS`.

1. Search the knowledge base with the question's key words (try synonyms if there are few hits):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py" --root . search "<key words>" --limit 6
   ```

2. Read the best-matching sections, then **check them against the code** they point to (a document
   may be out of date; the code wins). If the knowledge base has nothing, search the repositories
   directly (dispatch an Explore subagent for broad questions across several repositories).
3. Answer briefly and concretely, with references: document sections and file paths
   (`codebase/backend/src/payslip/tax.py:42`). Say when something is inferred rather than confirmed.
4. If the answer wasn't in the knowledge base, or a document was wrong, offer to record it: a new or
   corrected section in the right feature document (or `/ai-workspace:learn <feature>` for a whole
   feature). Don't write anything without the user's OK.

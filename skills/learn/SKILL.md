---
name: learn
description: Study part of the application and write it down in the workspace knowledge base — a feature ("payslips"), a flow ("login"), or everything not documented yet. Use when the user asks to document, learn, understand or map a feature, module or flow of the product.
argument-hint: "[feature or flow | all]"
allowed-tools: Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion, Bash(python3 *kb.py*), Bash(git -C * rev-parse *), Bash(git -C * log*)
---

# ai-workspace learn

> **Paths and tools.** `${CLAUDE_PLUGIN_ROOT}` is this plugin's folder and `${CLAUDE_SKILL_DIR}` the folder
> of this file. If they appear literally (not replaced, e.g. in Cursor), use `$AI_WORKSPACE_PLUGIN_ROOT`
> when it is set, otherwise the folder two levels above this file; for `${CLAUDE_SKILL_DIR}`, this file's
> folder. If there is no AskUserQuestion tool, ask in plain text with numbered options and wait for the answer.

Input: `$ARGUMENTS`: a feature or flow name, or `all` for every feature the overview lists as
"not documented yet". Empty: show that list and ask which ones.

Knowledge lives in `context/` (see `context/INDEX.md`). Templates: `${CLAUDE_PLUGIN_ROOT}/templates/knowledge/`.

## 1. Find what's already known

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py" --root . search "<feature words>" --limit 8
```

Read `context/product/brief.md`, `context/product/overview.md`, `context/architecture/system.md` and any
hits. If a feature document already exists, this is an update: keep what is still true.

## 2. Study the code (parallel)

Dispatch one **Explore** subagent per repository (or monorepo part) that the overview or the search
says is involved, all in one message. Brief each with the feature, the known entry points, and:

> Read-only. For the feature "<feature>", find from evidence: the user-facing behaviour and business rules;
> entry points (routes, screens, commands, jobs); the flow through this repository; API endpoints it
> exposes or calls (method, path, purpose, file); data it reads or writes (tables/fields, files, queues);
> tests and what they cover; non-obvious rules and edge cases. Give file paths for every claim. Mark
> guesses as (unverified). Under 500 words.

## 3. Write the document

`context/product/features/<slug>.md` from `templates/knowledge/feature.md`: fill it from the reports,
joining the repositories into one flow; remove the template's guidance comments. Frontmatter: `sources`
lists the folders the feature lives in as `<codebase>:<path>`; `generated_from` maps each codebase to
`git -C <clone> rev-parse --short HEAD`. Stay within 150 lines: describe, point to files, don't copy
code. In the overview, replace the feature's "(not documented yet)" with a link. Add any domain terms
to the overview's glossary.

## 4. Index

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py" --root . index-md && python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py" --root . index
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py" --root . check
```

Report: the documents written or updated, the main facts learned, and anything the code contradicts
in the brief (the code wins; ask the user whether the brief should be corrected).

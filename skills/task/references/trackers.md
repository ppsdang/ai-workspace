# Tracker adapters

Read only the section for the workspace's `tracker.type`. Every adapter gives the same three operations:
**fetch** (→ normalised ticket JSON), **comment**, **transition** (move to a status).

The script is `${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py` (Python 3 standard library only). Pass comment text
on stdin with a quoted heredoc so no shell expansion happens:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type <type> [options] comment <KEY> <<'MSG'
text
MSG
```

Normalised ticket: `key, title, type, status, priority, url, description, acceptance_criteria[], labels[], comments[], source`.

Secrets always come from environment variables. Never put tokens in `workspace.yaml`, in commands, or in files.
If a variable is missing, tell the user which one to export and stop. Don't ask them to paste the token.

`tracker.statuses.start` / `tracker.statuses.review` name the statuses used at Gate 1 and Gate 2. If they
are not set, ask the user once and suggest adding them to `workspace.yaml`.

---

## jira

```yaml
tracker:
  type: jira
  base_url: https://your-site.atlassian.net
  project: SHOP
  via: mcp            # mcp | api  (default: mcp if an Atlassian MCP server is connected, else api)
  acceptance_field: customfield_10042   # optional: custom field holding acceptance criteria
  statuses: { start: "In Progress", review: "In Review" }
```

**via: mcp.** Use the connected Atlassian MCP server's tools to get the issue (summary, description,
status, type, priority, labels, comments), add a comment, and transition the issue. Map the result to the
normalised shape yourself and save it as `task.json`. If no Atlassian MCP server is connected, point
the user to Atlassian's setup guide
(https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/),
or to `via: api`.

**via: api.** Env: `JIRA_API_TOKEN`, plus `JIRA_EMAIL` for Jira Cloud (without it, the token is sent as a
Server/Data Center personal access token).

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type jira --base-url <base_url> --project <project> \
  [--acceptance-field <acceptance_field>] fetch SHOP-123
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type jira --base-url <base_url> transition SHOP-123 "In Review"
```

Transition accepts either the transition name or the target status name. On failure it lists what is available.

## github

```yaml
tracker:
  type: github
  repo: owner/repo
  statuses: { start: "in-progress", review: "in-review" }   # labels; "closed"/"open" close/reopen
```

Uses the `gh` CLI and its existing login. Keys: `42`, `#42` or `owner/repo#42`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type github --repo owner/repo fetch 42
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type github --repo owner/repo \
  --status-labels "<statuses.start>,<statuses.review>" transition 42 "<statuses.review>"
```

## trello

```yaml
tracker:
  type: trello
  statuses: { start: "Doing", review: "Review" }   # list names on the card's board
```

Env: `TRELLO_API_KEY`, `TRELLO_TOKEN` (from https://trello.com/power-ups/admin). Key: the card's short
link (`AbC123`) or its full URL. Checklist items count as acceptance criteria; transition moves the card
to the list with that name.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type trello fetch https://trello.com/c/AbC123/...
```

## markdown

Tasks are markdown files in the workspace, e.g. `backlog/task1.md`:

```yaml
tracker:
  type: markdown
  path: backlog        # relative to the workspace root; don't use tasks/ (that holds AI artifacts)
  statuses: { start: "in-progress", review: "in-review" }
```

Task file format (all frontmatter optional):

```markdown
---
id: T-1
status: todo
priority: high
type: feature
labels: [api, auth]
---
# Title of the task

Description…

## Acceptance criteria
- [ ] First criterion
- [ ] Second criterion
```

Key: the `id`, the file name (`task1`), or a path. **comment** appends to a `## Activity` section and
**transition** sets `status:` in the frontmatter. Both edit the user's file, so do them only at the gates.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type markdown --root . --path backlog fetch task1
```

## custom (in-house trackers)

For any tracker without a built-in adapter. Two options:

**via: command.** The team provides small scripts (any language) that talk to their tracker's API:

```yaml
tracker:
  type: custom
  via: command
  commands:
    fetch: "./tools/tracker fetch {key}"           # stdout: normalised ticket JSON, or markdown/plain text
    comment: "./tools/tracker comment {key}"       # comment text on stdin
    transition: "./tools/tracker move {key} {status}"
  statuses: { start: "In Progress", review: "Code Review" }
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" --type custom --root . \
  --fetch-cmd "<commands.fetch>" --comment-cmd "<commands.comment>" --transition-cmd "<commands.transition>" \
  fetch <KEY>
```

Commands run from the workspace root. Placeholders are substituted per argument (no shell), so keys
cannot inject commands. Pass the templates exactly as written in `workspace.yaml`.

**via: mcp.** The tracker has an MCP server:

```yaml
tracker:
  type: custom
  via: mcp
  mcp_server: acme-tasks      # name of the connected MCP server
  statuses: { start: "In Progress", review: "Code Review" }
```

Use that server's tools to get the task, add a comment and change the status, and map the result to
the normalised shape. If it lacks one of those tools, tell the user which step must be done by hand.

## none (ad-hoc)

`type: none`, or free text / a file path passed to `/task`. Build `task.json` from the text (title =
first line or heading). There is no comment or transition step, and Gate 2 only pushes and opens MRs.

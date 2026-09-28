---
title: {{NAME}} (repository profile)
kind: codebase
summary: {{SUMMARY}}
codebase: {{NAME}}
path: {{PATH}}
sources: ["{{SOURCE}}"]
generated_from: { {{NAME}}: {{COMMIT_SHA}} }
updated: {{DATE}}
---

# {{NAME}}

**Stack:** {{LANGUAGE}} · {{FRAMEWORK}} · {{BUILD_TOOL}} · tests: {{TEST_FRAMEWORK}}
**Purpose:** {{ONE_LINE_PURPOSE}}

## Commands (run from the workspace root)

| Action | Command |
|---|---|
| Install | `cd {{PATH}} && ...` |
| Build | `cd {{PATH}} && ...` |
| Test (all) | `cd {{PATH}} && ...` |
| Test (single) | `cd {{PATH}} && ...` |
| Lint / format | `cd {{PATH}} && ...` |
| Run locally | `cd {{PATH}} && ...` |

Mark any command you could not confirm from config files as `(unverified)`.

## Layout

- Entry points:
- Key modules / packages:
- Where tests live:

## Integrations

- Talks to: (other codebases, APIs, databases, queues — with evidence: file paths)
- Exposes: (REST/GraphQL/gRPC endpoints, events)

## Conventions observed

- (naming, layering, error handling, DI, state management — only what the code shows)

---
id: T-2
status: todo
type: feature
priority: high
---
# Show the API version in the web footer

Support wants to see which API version the site talks to.

## Acceptance criteria
- [ ] API: `GET /version` returns `{"version": "<VERSION>"}`
- [ ] Web: the footer shows `API v<version>` using the new endpoint; if the call fails the footer still renders `Shop`
- [ ] Both changes have tests

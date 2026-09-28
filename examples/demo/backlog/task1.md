---
id: T-1
status: todo
type: bug
priority: medium
---
# 404 response should include the requested path

When a route is unknown the API returns `{"error": "not found"}`. Support wants the path included.

## Acceptance criteria
- [ ] Unknown routes return 404 with `{"error": "not found", "path": "<requested path>"}`
- [ ] Covered by a test

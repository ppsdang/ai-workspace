---
type: regex
pattern: "ai-workspace:init|workspace\\.yaml"
match: contains
target: last_message
---
Must explain that no workspace was found and suggest /ai-workspace:init.

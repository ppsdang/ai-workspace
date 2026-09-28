---
paths:
{{PATHS}}
---

# Go

- Keep `go.mod` Go version; run `gofmt`/`goimports` and `go vet`.
- Return errors with context (`fmt.Errorf("...: %w", err)`); never ignore errors.
- Follow existing package layout; avoid package-level mutable state.
- Tests: table-driven, next to the code (`_test.go`); run with `-race` if the project does.

## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] `python3 -m unittest discover tests` passes
- [ ] `claude plugin validate .` passes
- [ ] Tests added or updated for the change (required for guard hook and tracker changes)
- [ ] `CHANGELOG.md` updated under "Unreleased"
- [ ] Core stays stack-agnostic; outward-facing actions stay behind a gate
- [ ] If skill behaviour changed: tried it in a real session (the demo in `examples/demo` is enough) or added/updated an eval in `evals/`

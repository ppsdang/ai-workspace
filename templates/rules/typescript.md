---
paths:
{{PATHS}}
---

# TypeScript

- Respect `tsconfig` strictness; do not add `any`, `@ts-ignore` or non-null assertions to silence errors.
- Use the package manager implied by the lockfile (npm / yarn / pnpm / bun); never mix lockfiles.
- Follow existing module boundaries, path aliases and barrel-file conventions.
- Run the project's lint and type-check scripts, not just tests.

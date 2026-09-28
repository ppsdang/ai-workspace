---
paths:
{{PATHS}}
---

# Python

- Use the project's environment tool (poetry, uv, pipenv, pip + requirements) and Python version; don't switch.
- Follow existing typing level; add type hints to new public functions if the codebase uses them.
- Respect configured formatters/linters (ruff, black, isort, mypy) and run them.
- Tests: pytest or unittest as already used; reuse existing fixtures.

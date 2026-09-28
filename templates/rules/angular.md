---
paths:
{{PATHS}}
---

# Angular

- Match the project's Angular version and style: standalone components vs NgModules, signals vs RxJS, control-flow syntax.
- Use `ng generate` conventions for file naming and placement.
- Unsubscribe or use `async`/`takeUntilDestroyed`; no manual subscriptions that leak.
- Keep business logic in services, not components. Tests use the configured runner (Karma/Jasmine or Jest).

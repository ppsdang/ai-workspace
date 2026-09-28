---
paths:
{{PATHS}}
---

# Kotlin

- Use the Gradle wrapper and the Kotlin/JVM versions already configured.
- Prefer immutability (`val`, data classes) and null-safety over `!!`.
- Match existing coroutine/reactive style; don't introduce a second concurrency model.
- Tests: follow the existing framework (JUnit 5, Kotest, MockK).

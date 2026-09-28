---
paths:
{{PATHS}}
---

# Java

- Match the existing build tool (Maven `mvnw`/Gradle `gradlew` wrapper if present) and Java version from the build file; do not upgrade either.
- Follow the project's layering (e.g. controller → service → repository) and its DI style; don't mix field and constructor injection in new code if one is dominant.
- Prefer existing utilities (logging, validation, mapping) over new libraries.
- Tests: mirror the package of the class under test; use the framework already present (JUnit 4 vs 5, Mockito, AssertJ, Testcontainers).
- Never swallow exceptions; follow the codebase's error-handling and logging patterns.

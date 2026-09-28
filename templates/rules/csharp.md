---
paths:
{{PATHS}}
---

# C# / .NET

- Keep the target framework and SDK from the project files / `global.json`.
- Follow nullable reference type settings; don't suppress warnings to compile.
- Use the built-in DI, async all the way (no `.Result`/`.Wait()`), and existing logging.
- Tests: xUnit/NUnit/MSTest as configured; run `dotnet test`.

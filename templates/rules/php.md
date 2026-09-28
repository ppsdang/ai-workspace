---
paths:
{{PATHS}}
---

# PHP

- Use Composer and the PHP version from `composer.json`; follow PSR-12 or the configured standard (phpcs/php-cs-fixer).
- Match the framework's conventions (Laravel, Symfony, ...) for routing, DI, validation and migrations.
- Use parameterised queries / the ORM; never interpolate input into SQL.
- Tests: PHPUnit or Pest as already configured.

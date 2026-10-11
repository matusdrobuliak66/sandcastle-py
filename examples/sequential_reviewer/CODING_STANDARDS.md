# Coding Standards

<!-- Customize this file with your project's coding standards. The
     reviewer agent loads it during review via @CODING_STANDARDS.md so
     these standards are enforced without costing tokens during
     implementation. -->

## Style

- Use snake_case for variables and functions, PascalCase for classes.
- Add type hints to every public function signature.

## Testing

- Every public function must have at least one test in `tests/`.
- Use descriptive test names that explain the expected behavior.

## Architecture

- Keep modules focused on a single responsibility.

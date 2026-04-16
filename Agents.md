# Python Instructions

- Use docstrings ONLY when required for framework functionality (e.g., FastAPI/Swagger documentation, Typer CLI help).
- Use the `typing` module for type annotations (e.g., List[str], Dict[str, int]).
- Break down complex functions into smaller, more manageable functions.
- Follow PEP 8 guidelines for code style and formatting.
- Use the standard Python `logging` library for capturing pertinent events. Logs should provide a clear audit trail without cluttering the output.

# General Instructions

- Always prioritize readability and clarity.
- Avoid comments that restate the code. Use comments sparingly to explain "why" over "what."
- Use minimalistic but highly descriptive names for functions, variables, and classes.
- Write concise, efficient, and idiomatic code that is also easily understandable.
- Handle edge cases and write clear exception handling.

# Git Workflow

- **Never push directly to `main`.** All changes must go through a pull request.
- Create a new branch for every change: `git checkout -b <type>/<short-description>` (e.g. `feat/bulk-lookup`, `fix/csv-parse`, `ci/lock-update`).
- Once the work is complete and tests pass, open a PR targeting `main`: `gh pr create --title "..." --body "..."`.
- Use the branch naming convention that matches the commit type (feat, fix, ci, chore, docs, etc.).

# Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/) to drive automated releases and changelog generation. Using the format is recommended but not required — commits that don't follow it are merged normally but won't appear in release notes or trigger version bumps.

Format: `type(scope): description`

| Type | When to use |
|---|---|
| `feat` | A new feature (triggers a version bump) |
| `fix` | A bug fix (triggers a version bump) |
| `perf` | A performance improvement |
| `refactor` | Code restructuring with no behavior change |
| `docs` | Documentation only changes |
| `ci` | CI/CD configuration changes |
| `chore` | Maintenance tasks, dependency updates |

Breaking changes: append `!` after the type (e.g., `feat!: remove legacy flag`) or add `BREAKING CHANGE:` in the commit body.

Examples:
```
feat: add bulk IP lookup command
fix: handle empty rows in CSV import
docs: update install instructions for uv
ci: pin release-please action to v4
chore: bump geoip2 to 4.9.0
```

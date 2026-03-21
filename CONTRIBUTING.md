# Contributing to Demery Bot

Thanks for your interest in contributing! Here's how to get involved.

## Reporting Bugs

Open a [bug report](https://github.com/jnsartwell/demery-bot/issues/new?template=bug_report.md) with:

- What you expected to happen
- What actually happened
- Steps to reproduce

## Requesting Features

Open a [feature request](https://github.com/jnsartwell/demery-bot/issues/new?template=feature_request.md) with a description and motivation.

## Submitting Pull Requests

1. Fork the repo and create a branch from `main`
2. Follow the development workflow below
3. Open a PR using the [PR template](https://github.com/jnsartwell/demery-bot/blob/main/.github/PULL_REQUEST_TEMPLATE.md)
4. PRs require one approving review and all CI checks to pass (`lint`, `test`, `secret-scan`)

### Development Workflow

This project follows a stories-first workflow:

1. **Requirements first** — all feature work starts in `STORIES.md` with user stories and acceptance criteria
2. **Tests from stories** — every story must be covered by tests before implementation
3. **Implementation from tests** — production code is written to satisfy the tests

### Code Style

- **Linter/formatter:** [Ruff](https://docs.astral.sh/ruff/) — `ruff check && ruff format --check` must pass
- **Line length:** 120 characters
- **Config:** `pyproject.toml`

### Pre-Commit Hook

After cloning, enable the pre-commit hook:

```bash
git config core.hooksPath .githooks
```

This runs lint, tests, and secret scanning before every commit. See the [Dev Guide](docs/dev-guide.md) for details.

## Development Setup

For local setup, environment variables, testing, and deploy instructions, see the **[Dev Guide](docs/dev-guide.md)**.

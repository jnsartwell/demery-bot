# Dev Guide

## Stack

- [discord.py](https://discordpy.readthedocs.io/) — slash commands
- [Anthropic](https://docs.anthropic.com/) — `claude-haiku-4-5` for trash talk generation
- [Fly.io](https://fly.io) — persistent worker deployment
- GitHub Actions — CI/CD

## Local Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in values
python bot.py
```

`.env` needs:

| Variable | Notes |
|---|---|
| `DISCORD_BOT_TOKEN` | Bot token from Discord Developer Portal |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `DISCORD_BOT_APPLICATION_ID` | Discord application ID (integer) |
| `DISCORD_GUILD_ID` | Comma-separated guild IDs for instant slash command sync (optional) |
| `DB_PATH` | SQLite path; set to `./brackets.db` locally (defaults to `/data/brackets.db` for Fly.io) |

## Pre-Commit Hook

After cloning, point git at the repo's hooks directory:

```bash
git config core.hooksPath .githooks
```

This runs lint + tests automatically before every commit. If either fails, the commit is blocked.

## Linting

```bash
ruff check              # lint (unused imports, errors, import order)
ruff format --check     # check formatting without changing files
ruff format             # auto-format in place
ruff check --fix        # auto-fix lint issues (e.g. unused imports)
```

- [Ruff](https://docs.astral.sh/ruff/) handles linting and formatting — config in `pyproject.toml`
- Lint + format checks must pass before deploy (enforced by CI)

## Testing

```bash
python -m pytest tests/ -v
```

- **128 tests** covering all user stories and dev stories in `REQUIREMENTS.txt`
- Tests mock all external APIs (Anthropic, ESPN, Discord) — no network access needed
- Each test gets a fresh temp SQLite database (no cleanup required)
- Tests must pass before deploy (enforced by CI)

## Deploy

Trigger manually via **Actions → Deploy to Fly.io → Run workflow**.

The workflow runs lint and tests first — if either fails, the deploy is blocked. On success, it syncs all secrets/vars and deploys a single machine to Fly.io.

### GitHub Secrets & Variables

| Name | Type |
|---|---|
| `DISCORD_BOT_TOKEN` | Secret |
| `ANTHROPIC_API_KEY` | Secret |
| `FLY_AUTH_TOKEN` | Secret |
| `DISCORD_BOT_APPLICATION_ID` | Variable |
| `DISCORD_GUILD_ID` | Variable (comma-separated for multiple servers) |
| `DISCORD_BYPASS_USER_IDS` | Variable (comma-separated; exempt from cooldown + can use `/testdigest`) |
| `TAUNT_HOUR` | Variable (UTC hour 0–23 to post digest; default `21`) |

### First-Time Fly.io Setup

Before the first deploy, create the persistent volume for SQLite:

```bash
flyctl volumes create brackets_data --region iad --size 1
```

Only needs to be done once. The volume is mounted at `/data` and persists across deploys.

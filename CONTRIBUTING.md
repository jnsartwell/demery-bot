# Dev Guide

## Stack

- [discord.py](https://discordpy.readthedocs.io/) — slash commands
- [Anthropic](https://docs.anthropic.com/) — `claude-haiku-4-5` for trash talk generation
- [Fly.io](https://fly.io) — persistent worker deployment
- GitHub Actions — CI/CD

## Local Development

```bash
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

## Deploy

Trigger manually via **Actions → Deploy to Fly.io → Run workflow**.

The workflow creates the Fly.io app on first run, syncs all secrets/vars, and deploys a single machine to Fly.io.

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

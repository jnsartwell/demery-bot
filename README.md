# Demery Bot

A Discord bot that generates March Madness trash talk via Claude, in the style of a former coworker named Demery.

## Usage

```
/taunt @user [intensity]
```

- `intensity`: `mild` / `medium` / `harsh` (default: medium)

## Setup

### GitHub Secrets
| Name | Type | Value |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Secret | Bot token from Discord Developer Portal |
| `ANTHROPIC_API_KEY` | Secret | Anthropic API key |
| `FLY_AUTH_TOKEN` | Secret | Fly.io deploy token |
| `DISCORD_BOT_APPLICATION_ID` | Variable | Discord application ID |
| `DISCORD_GUILD_ID` | Variable | Guild ID for instant slash command sync |

### Deploy

Trigger manually via **Actions → Deploy to Fly.io → Run workflow**.

The workflow creates the Fly.io app on first run, syncs all secrets, and deploys.

## Local Development

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in values
python bot.py
```

`.env` needs: `DISCORD_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `DISCORD_BOT_APPLICATION_ID`, and optionally `DISCORD_GUILD_ID`.

## Stack

- [discord.py](https://discordpy.readthedocs.io/) — slash commands
- [Anthropic](https://docs.anthropic.com/) — `claude-haiku-4-5` for trash talk generation
- [Fly.io](https://fly.io) — persistent worker deployment

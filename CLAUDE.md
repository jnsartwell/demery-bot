# Demery Bot — CLAUDE.md

## Project Summary
Discord bot that generates LLM-powered March Madness trash talk in the style of a former coworker named Demery. Users invoke `/taunt @user [intensity]` and the bot roasts the target's bracket picks.

**GitHub:** https://github.com/jnsartwell/demery-bot
**Fly.io app name:** `demery-bot`

---

## Tech Stack
- **Runtime:** Python 3.12 (docker: `python:3.12-slim`)
- **Discord:** `discord.py >= 2.3` with `app_commands.CommandTree` (slash commands)
- **LLM:** Anthropic `AsyncAnthropic`, model `claude-haiku-4-5-20251001`, prompt caching on system prompt
- **Deploy:** Fly.io (persistent worker, no HTTP service), GitHub Actions CI/CD
- **Config:** `python-dotenv` locally; GitHub secrets/vars → Fly.io secrets in CI

---

## File Structure
```
taunt-bot/
├── bot.py                     # Entry point, DemeryBot client, /taunt command
├── llm.py                     # Anthropic wrapper + Demery system prompt
├── requirements.txt
├── Dockerfile
├── fly.toml
├── .gitignore
└── .github/workflows/
    └── deploy.yml             # Push to main or workflow_dispatch → Fly.io
```

---

## Architecture Notes

### bot.py
- `DemeryBot` subclasses `discord.Client` with `app_commands.CommandTree`
- `setup_hook` syncs slash commands: guild-scoped (instant) if `DISCORD_GUILD_ID` is set, otherwise global (up to 1hr)
- `/taunt` defers immediately (`interaction.response.defer()`) then calls `generate_taunt()` and sends via `followup.send()`
- `intensity` is an optional `app_commands.Choice[str]` (mild/medium/harsh), defaults to `"medium"`

### llm.py
- `anthropic.AsyncAnthropic()` picks up `ANTHROPIC_API_KEY` from environment automatically
- System prompt uses `cache_control: ephemeral` — ~90% token cost reduction after first call
- `max_tokens=150` keeps responses punchy

### deploy.yml
- Triggers: push to `main`, `workflow_dispatch` (manual trigger without a push)
- Syncs all runtime config to Fly.io secrets on every deploy run
- **Secrets** (sensitive): `DISCORD_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `FLY_AUTH_TOKEN`
- **Variables** (non-sensitive): `DISCORD_BOT_APPLICATION_ID`, `DISCORD_GUILD_ID`

### fly.toml
- No `[http_service]` block — bot is a persistent worker process, not a web server
- 256mb shared VM, region `iad`

---

## Environment Variables
| Variable | Source | Notes |
|---|---|---|
| `DISCORD_BOT_TOKEN` | GitHub secret | Bot login token |
| `ANTHROPIC_API_KEY` | GitHub secret | Claude API key |
| `FLY_AUTH_TOKEN` | GitHub secret | Fly.io deploy auth |
| `DISCORD_BOT_APPLICATION_ID` | GitHub var | Discord app ID (integer) |
| `DISCORD_GUILD_ID` | GitHub var | Test server ID; enables instant slash command sync |

---

## Phase 1 Status: Complete
All code is written and committed. The workflow handles secret sync on every deploy.

**One-time manual step** (only needed once, before first deploy):
```bash
flyctl launch --name demery-bot --region iad --no-deploy
```

**To deploy:** push to `main` or trigger workflow manually via GitHub Actions UI.

**To test locally:**
```bash
pip install -r requirements.txt
# create .env with the 4 env vars above (DISCORD_GUILD_ID optional but recommended)
python bot.py
```

---

## Phase 2 — Planned (not started)
- Bracket submission + SQLite storage
- ESPN API integration for real game results
- Scheduled auto-taunts after game results post
- Discord button components: Regenerate / Harsher / Milder

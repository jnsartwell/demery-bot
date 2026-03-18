# Session Summary — 2026-03-18

## What Was Done

### Files Created
- **`bot.py`** — Discord bot entry point with `/taunt @user [intensity]` slash command
- **`llm.py`** — Anthropic async wrapper with Demery system prompt and prompt caching
- **`requirements.txt`**, **`Dockerfile`**, **`fly.toml`** — Runtime/deploy scaffolding
- **`.gitignore`** — Covers `.env`, `__pycache__/`, `*.pyc`
- **`CLAUDE.md`** — Full project context for resuming across sessions
- **`README.md`** — Usage, setup, deploy, and stack docs

### Files Modified
- **`.github/workflows/deploy.yml`** — Two fixes:
  1. Removed automatic `push` trigger — workflow is now `workflow_dispatch` only (manual button)
  2. Added idempotent `flyctl apps create demery-bot --machines 2>/dev/null || true` step before secrets sync, so app is created automatically on first run

---

## Key Architecture Decisions

| Decision | Reason |
|---|---|
| Guild-scoped slash command sync when `DISCORD_GUILD_ID` set | Instant registration vs up to 1hr for global |
| `interaction.response.defer()` + `followup.send()` | Extends response window from 3s to 15min for async LLM call |
| Prompt caching (`cache_control: ephemeral`) on system prompt | ~90% cost reduction after first call |
| `max_tokens=150` | Keeps taunts punchy |
| No `[http_service]` in fly.toml | Bot is a persistent worker, not a web server |
| All secrets flow GitHub → Fly.io on every deploy | No manual secret management needed |

---

## Known Gap
`README.md` references `.env.example` which doesn't exist in the repo. Either create it or remove the reference.

---

## Phase 2 Scope (not started)
- Bracket submission + SQLite storage
- ESPN API integration for real game results
- Scheduled auto-taunts after game results post
- Discord button components: Regenerate / Harsher / Milder

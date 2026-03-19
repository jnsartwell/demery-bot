# Demery Bot — Progress Log

---

## Session 1 — 2026-03-18 (Phase 1 build)

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

### Key Architecture Decisions

| Decision | Reason |
|---|---|
| Guild-scoped slash command sync when `DISCORD_GUILD_ID` set | Instant registration vs up to 1hr for global |
| `interaction.response.defer()` + `followup.send()` | Extends response window from 3s to 15min for async LLM call |
| Prompt caching (`cache_control: ephemeral`) on system prompt | ~90% cost reduction after first call |
| `max_tokens=150` | Keeps taunts punchy |
| No `[http_service]` in fly.toml | Bot is a persistent worker, not a web server |
| All secrets flow GitHub → Fly.io on every deploy | No manual secret management needed |

---

## Session 2 — 2026-03-18 (fixes, rename, polish, public repo prep)

### Bugs Fixed
- **`ValueError: invalid literal for int() with base 10: '...'`** — `DISCORD_BOT_APPLICATION_ID` GitHub Variable was accidentally set to a comma-separated string (both app ID + guild ID). Fixed by correcting the variable to a single integer; guild IDs go in `DISCORD_GUILD_ID`.
- **Bot not picking up new variables after deploy** — Required `flyctl machines restart -a demery-bot` to force the machine to reload secrets.

### Changes Made

#### `bot.py`
- Renamed `/taunt` → `/diss`
- Added `/disshelp` ephemeral slash command — shows usage instructions only to the invoker, no channel clutter
- Added `BYPASS_USER_IDS` env var support for cooldown bypass
- Per-user 2-minute cooldown with ephemeral "chill" response when triggered

#### `llm.py`
- Dialed back ALL CAPS usage in system prompt: `"sometimes ALL CAPS"` → `"rarely ALL CAPS — only when something truly deserves it"`
- System prompt refactored to not assume the bot knows real bracket picks (it doesn't), roasting general vibe/overconfidence instead

#### `.gitignore`
- Added `CLAUDE.md` and `session_summary.md` — internal dev notes, gitignored so they stay local but don't appear in the public repo
- Used `git rm --cached` to untrack already-committed versions

#### `README.md`
- Stripped to user-facing content only
- Fixed stale `/taunt` references → `/diss`
- Added mention of `/disshelp`

#### `CONTRIBUTING.md` (new)
- Created as the dev/deploy guide split from the old README
- Includes local dev setup, GitHub secrets/vars table, and deploy instructions

### Phase 1 Status
All code written, committed, and pushed to `main`. Bot is live on Fly.io.

**Next action (user):** Trigger **Actions → Deploy to Fly.io → Run workflow** to push latest changes (renamed `/diss`, new `/disshelp`, caps prompt tweak) to production.

---

## Phase 2 Scope (not started)
- Bracket submission + SQLite storage
- ESPN API integration for real game results
- Scheduled auto-taunts after game results post
- Discord button components: Regenerate / Harsher / Milder

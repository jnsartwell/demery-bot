REQUIREMENTS — Demery Bot
=========================

Personas
--------
USER   — Any Discord server member who interacts with the bot.
DEV    — A developer/operator listed in DISCORD_BYPASS_USER_IDS.
ADMIN  — A Discord server member with Manage Channels permission.


========================================================================
USER STORIES
========================================================================

US-1  Diss a friend's bracket
----------------------------------------------------------------------
As a USER, I can type `/diss @user [intensity]` to have Demery generate
a trash-talk message roasting the tagged person's March Madness bracket.

Acceptance criteria:
- The command accepts a required `user` argument (Discord member mention)
  and an optional `intensity` choice: mild, medium, or harsh.
- If no intensity is provided, it defaults to medium.
- The response is a public message in the channel that @-mentions the
  target and contains an AI-generated roast in Demery's voice.
- If the target has a stored bracket, the roast references their
  specific picks (champion, Final Four, etc.) and any busted picks or
  survivors based on real tournament results.
- If the target has no stored bracket, the roast is generic March
  Madness trash talk.
- The bot defers the interaction (shows "thinking...") while generating.


US-2  Cooldown on /diss
----------------------------------------------------------------------
As a USER, I am rate-limited to one `/diss` command every 2 minutes so
the bot isn't spammed.

Acceptance criteria:
- After using `/diss`, any subsequent `/diss` within 120 seconds from
  the same user returns an ephemeral message showing the remaining
  cooldown time.
- DEV users (BYPASS_USER_IDS) are exempt from the cooldown.


US-3  Submit a bracket via image upload
----------------------------------------------------------------------
As a USER, I can type `/submitbracket [image]` and upload a screenshot
of my filled-out bracket so Demery knows my actual picks.

Acceptance criteria:
- The command accepts a required `image` argument (Discord attachment).
- The bot uses AI vision (Claude Sonnet) to extract picks from the
  image for all 6 round tiers: round_of_32, sweet_16, elite_eight,
  final_four, championship_game, and champion.
- The bot extracts the user's ORIGINAL PICKS, not actual tournament
  results — even if the screenshot shows eliminated/faded teams.
- After extraction, the bot normalizes team names to match ESPN's
  official displayName format using an LLM matching step.
- On success: the picks are saved to the database (upsert — replaces
  any previous submission for that user in that guild), a public
  Demery-style acknowledgment is posted, and an ephemeral summary of
  the parsed picks is shown to the submitter.
- On failure (unreadable image, incomplete picks): an ephemeral error
  message is shown.


US-4  Submission rate limit
----------------------------------------------------------------------
As a USER, I get 3 bracket submissions per day to correct bad parses
or update my picks, but no more.

Acceptance criteria:
- After 3 submissions in a calendar day (Eastern time), further
  attempts return an ephemeral message saying submissions are exhausted
  for the day.
- The count resets at midnight Eastern.
- DEV users are exempt from this limit.


US-5  Re-submit a bracket (upsert)
----------------------------------------------------------------------
As a USER, if I submit a new bracket image, it replaces my previous
submission rather than creating a duplicate.

Acceptance criteria:
- Only one bracket record exists per (user, guild) pair.
- Submitting again overwrites picks, display name, and timestamp.


US-6  Brackets are per-guild
----------------------------------------------------------------------
As a USER, my bracket submission in one Discord server is independent
from my submission in another server.

Acceptance criteria:
- A user can have different brackets stored in different guilds.
- `/diss` retrieves the target's bracket for the current guild only.
- The daily digest processes brackets per guild independently.


US-7  View help
----------------------------------------------------------------------
As a USER, I can type `/disshelp` to see a usage guide.

Acceptance criteria:
- The response is ephemeral (only visible to the caller).
- It lists all user-facing commands, intensity levels, the submission
  limit, and the cooldown duration.


US-8  View about info
----------------------------------------------------------------------
As a USER, I can type `/about` to learn what Demery Bot is.

Acceptance criteria:
- The response is a public message explaining the bot's purpose, listing
  commands, and describing the daily digest feature.


US-9  Daily digest — automatic bracket recap
----------------------------------------------------------------------
As a USER with a submitted bracket, I receive a daily Demery-style
recap in my server's configured digest channel during the tournament.

Acceptance criteria:
- The digest fires once per day at diss_HOUR (UTC).
- It fetches that day's completed ESPN game results and persists them
  to the `game_results` table in SQLite. On first run (or after data
  loss), it backfills historical dates from tournament start.
- Bracket status is computed against ALL cumulative tournament results,
  not just today's games. A bust from Day 1 remains visible on Day 5.
- The digest distinguishes today's new busts/survivors from cumulative
  status so the narrative focuses on what just happened while
  reflecting overall bracket health.
- For each submitter: busted picks include "picked to reach X, lost
  in Y" context; survivors include the round they're still alive
  through.
- Every bracket holder is mentioned every day — even those with no
  activity that day get a "somehow still intact" treatment.
- If no games were played, the digest acknowledges the off-day.
- The message uses Discord @-mentions (exact <@ID> tags) for each
  submitter.
- The digest posts to the channel configured via `/setchannel` for
  that guild.
- If no channel is configured or no brackets exist for a guild, that
  guild is skipped silently.


US-10  Set the digest channel
----------------------------------------------------------------------
As an ADMIN (Manage Channels permission), I can type
`/setchannel #channel` to configure where daily digests are posted.

Acceptance criteria:
- Accepts a channel mention (<#ID>), a raw channel ID, or a channel
  name.
- If the channel can't be found or the bot can't see it, an ephemeral
  error is returned.
- On success, an ephemeral confirmation is shown.
- The setting is stored per guild and persists across restarts (SQLite).
- Only users with Manage Channels permission can run this command.


US-11  Tone and personality
----------------------------------------------------------------------
As a USER, all bot responses feel like Demery — a sharp, hilarious
March Madness fanatic who loves his friends and busts their chops.

Acceptance criteria:
- disss are 2-3 sentences max, casual and punchy.
- No profanity, slurs, or HR-uncomfortable content.
- Intensity levels produce distinct tones:
  - mild: light, affectionate ribbing
  - medium: sharp and fun
  - harsh: most pointed, but still lands with a wink
- Daily digests read like natural Discord messages — no headers, bold,
  or bullet points.


US-12  Skip digest on non-game days
----------------------------------------------------------------------
As a USER, I do not receive a digest message on mornings after a day
with no NCAA tournament games.

Acceptance criteria:
- A hardcoded set of 2026 NCAA tournament game dates is defined in
  bot.py (First Four through Championship).
- The daily digest checks whether yesterday (Eastern time) is in the
  tournament game dates set before running the full pipeline.
- If yesterday is not a tournament game date, the digest is silently
  skipped (no message posted, no error).
- "Yesterday" is determined in Eastern time, consistent with DS-10.
- DEV commands (/testdigest, /pushdigest) bypass the skip and always
  run the full pipeline.
- A skip logs: "[digest] No tournament games yesterday (YYYYMMDD),
  skipping digest".


US-13  Submit a bracket via URL  [PARKING LOT]
----------------------------------------------------------------------
As a DEV, I can type `/submitbracket-url [url]` and provide a bracket
page URL instead of a screenshot so I can submit brackets more easily
from mobile.

Acceptance criteria:
- The command accepts a required `url` argument (string).
- Gated to BYPASS_USER_IDS; non-DEV users get "Not for you."
  (ephemeral).
- The bot fetches HTML from the URL with a browser User-Agent and 30s
  timeout; non-200 status or non-HTML content type raises a ValueError.
- The bot preprocesses the HTML: extracts embedded JSON from script
  tags, strips noise tags (script, style, noscript, svg, iframe,
  header, footer, nav), removes HTML comments, strips non-semantic
  attributes, isolates bracket subtree by keyword matching, collapses
  whitespace, and truncates to 100,000 chars.
- The bot sends cleaned content to Claude (text, not vision) to
  extract picks in the same 6-round schema as image submission.
- After extraction, picks are normalized and stored identically to
  `/submitbracket` (normalize team names, upsert to DB, public
  Demery-style ack, ephemeral summary).
- On failure (fetch error, parse error, timeout): an ephemeral error
  message is shown.
- The submission rate limit (3/day per user, `_last_submit` dict) is
  shared with `/submitbracket`; a URL submission counts toward the
  same daily quota.
- DEV users are exempt from the rate limit.


US-14  Test digest (preview without broadcasting)
----------------------------------------------------------------------
As a DEV, I can type `/testdigest` to trigger the digest for my guild
immediately and see the result as an ephemeral message, without posting
to the public channel.

Acceptance criteria:
- Gated to BYPASS_USER_IDS; non-DEV users get "Not for you."
- Runs the full digest pipeline (ESPN fetch, bracket comparison, LLM
  generation) for the invoker's guild only.
- Result is ephemeral — not visible to other users and not posted to
  the digest channel.


US-15  Push digest (broadcast on demand)
----------------------------------------------------------------------
As a DEV, I can type `/pushdigest` to trigger and broadcast the digest
to the configured channel immediately.

Acceptance criteria:
- Gated to BYPASS_USER_IDS.
- Runs the full digest pipeline and posts the result to the guild's
  configured digest channel.
- Also sends an ephemeral copy to the invoker.


US-16  Debug guild visibility
----------------------------------------------------------------------
As a DEV, I can type `/debugguild` to see what the bot can access in
the current guild.

Acceptance criteria:
- Gated to BYPASS_USER_IDS.
- Shows: guild name/ID, bot permissions, roles, and a list of visible
  text channels with per-channel view/send permissions.
- Response is ephemeral.


========================================================================
DEV STORIES
========================================================================

DS-1  ESPN scoreboard result caching (in-memory)
----------------------------------------------------------------------
As a DEV, I expect that repeated `/diss` calls within the same process
lifetime do not re-fetch past tournament dates from ESPN.

Acceptance criteria:
- `fetch_tournament_results()` uses an in-memory dict cache keyed by
  date string (YYYYMMDD).
- Past dates (before today) are served from cache after the first
  fetch.
- Today's date is always re-fetched (games may still be in progress).
- Cache is not persisted — it repopulates on bot restart.
- Verification: first `/diss` logs "[espn] Fetching scoreboard for ..."
  for every date; subsequent calls only log today's date.


DS-2  ESPN tournament team name caching
----------------------------------------------------------------------
As a DEV, I expect that tournament team names from ESPN are fetched
once and reused for all subsequent bracket submissions.

Acceptance criteria:
- `fetch_tournament_team_names()` returns cached results after the
  first successful call.
- The cache is a module-level list populated by scanning First Round
  scoreboard dates.
- Cache is not persisted — it repopulates on bot restart.


DS-3  Team name normalization on submission
----------------------------------------------------------------------
As a DEV, I expect bracket picks extracted from images to be normalized
to ESPN's official team displayName format before storage.

Acceptance criteria:
- After image parsing, an LLM call maps user-submitted names (e.g.
  "Duke", "UConn Huskies") to ESPN names (e.g. "Duke Blue Devils",
  "Connecticut Huskies").
- If normalization fails, raw picks are saved as a fallback — the
  submission is not rejected.


DS-4  Prompt caching on system prompt
----------------------------------------------------------------------
As a DEV, I expect the Demery system prompt to use Anthropic's prompt
caching to reduce token costs.

Acceptance criteria:
- All LLM calls that use the Demery system prompt include
  `cache_control: {"type": "ephemeral"}` on the system message block.
- This applies to: generate_diss, generate_submission_ack, and
  generate_digest.


DS-5  Bracket image parsing robustness
----------------------------------------------------------------------
As a DEV, I expect the bracket image parser to handle messy LLM output
gracefully.

Acceptance criteria:
- If the LLM wraps JSON in markdown code fences, the parser strips
  them.
- If the LLM includes text before/after the JSON object, the parser
  extracts the JSON.
- If the response contains `{"error": "..."}`, a ValueError is raised
  with the error message.
- If required round keys are missing, a ValueError is raised listing
  the missing rounds.


DS-6  Guild-scoped slash command sync
----------------------------------------------------------------------
As a DEV, I expect slash commands to sync instantly to configured test
guilds during development.

Acceptance criteria:
- If DISCORD_GUILD_ID is set (comma-separated list), commands are
  copied and synced to each guild individually (instant registration).
- Stale global command registrations are cleared when guild sync is
  active.
- If DISCORD_GUILD_ID is not set, commands sync globally (up to 1 hour
  propagation delay).


DS-7  Database migrations
----------------------------------------------------------------------
As a DEV, I expect schema changes to be handled by a forward migration
system.

Acceptance criteria:
- SQL migration files live in `migrations/` and run in sorted order on
  `init_db()`.
- Each migration runs once; applied migrations are tracked in a
  `schema_migrations` table.
- Down migrations (`.down.sql`) are available and can be applied via
  `rollback_migration()`.


DS-8  Round-to-tier mapping
----------------------------------------------------------------------
As a DEV, I expect ESPN round names from game results to map correctly
to the bracket picks schema tiers.

Acceptance criteria:
- ROUND_NAME_TO_TIER maps ESPN headline round names (e.g. "1st Round",
  "Sweet 16") to picks dict keys (e.g. "round_of_32", "elite_eight").
- The mapping accounts for the offset: "1st Round" results determine
  Round of 32 survivors, "Sweet 16" results determine Elite Eight
  survivors, etc.
- Alternate/fallback round name forms are included.
- Play-in round names that don't appear in the mapping are silently
  skipped.


DS-9  Bust and survivor computation
----------------------------------------------------------------------
As a DEV, I expect `_compute_bracket_status()` to correctly identify
busted and surviving picks.

Acceptance criteria:
- A bust is recorded when a losing team was picked to advance in the
  current round or any later round. The bust includes which round the
  team was picked to reach (furthest tier) and which round they
  actually lost in.
- A survivor is recorded when a winning team was picked to advance in
  the current round or any later round.
- Teams not in the user's picks for the relevant tiers are ignored.


DS-10  Eastern time for game dates
----------------------------------------------------------------------
As a DEV, I expect all date calculations for game fetching to use
Eastern time, not UTC.

Acceptance criteria:
- The daily digest uses `datetime.datetime.now(EASTERN)` to determine
  "today" when fetching ESPN results.
- This prevents UTC midnight offset issues where late-night Eastern
  games would be fetched under the wrong date.


US-18  Digest includes real game context
----------------------------------------------------------------------
As a USER, the daily digest references what actually happened in
yesterday's games so the roasts feel grounded in reality, not just
abstract pick data.

Acceptance criteria:
- Yesterday's completed game results (winner, loser, scores) are
  included in the digest prompt as a compact game summary.
- The LLM can reference upsets, blowouts, or close finishes to make
  roasts more specific and timely.
- Scores are extracted from the ESPN scoreboard API (already fetched);
  no additional API calls required.

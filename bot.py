import datetime
import os
import random
import re
import time
import traceback
import zoneinfo

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import db
import espn
from constants import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_TYPES,
    ROUND_NAME_TO_TIER,
    ROUND_TIER_ORDER,
    SUPPORTED_IMAGE_FORMATS_LABEL,
    TOURNAMENT_GAME_DATES,
)
from llm import (
    generate_digest,
    generate_diss,
    generate_submission_ack,
    normalize_team_names,
    parse_bracket_image,
)

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_BOT_APPLICATION_ID = int(os.environ["DISCORD_BOT_APPLICATION_ID"])
DISCORD_GUILD_IDS = [guild_id.strip() for guild_id in os.getenv("DISCORD_GUILD_ID", "").split(",") if guild_id.strip()]
BYPASS_USER_IDS = {int(uid.strip()) for uid in os.getenv("DISCORD_BYPASS_USER_IDS", "").split(",") if uid.strip()}
diss_HOUR = int(os.getenv("diss_HOUR") or "12")
EASTERN = zoneinfo.ZoneInfo("America/New_York")

COOLDOWN_SECONDS = 120
_last_used: dict[int, float] = {}
_last_submit: dict[int, tuple[str, int]] = {}  # user_id → (YYYYMMDD, count)
MAX_SUBMIT_PER_DAY = 3


class DemeryBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents, application_id=DISCORD_BOT_APPLICATION_ID)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if DISCORD_GUILD_IDS:
            for guild_id in DISCORD_GUILD_IDS:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"Synced {len(synced)} commands to guild {guild_id}")

            # Remove stale global registrations (guild syncs already done above)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            print("Cleared stale global commands")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} commands globally")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        for guild in self.guilds:
            me = guild.me
            perms = me.guild_permissions
            print(
                f"Guild '{guild.name}' ({guild.id}): "
                f"view_channel={perms.view_channel} send_messages={perms.send_messages} "
                f"roles=[{', '.join(r.name for r in me.roles)}] "
                f"text_channels_visible={len(guild.text_channels)}"
            )
        db.init_db()
        if not daily_digest_task.is_running():
            daily_digest_task.start()

    async def on_error(self, event: str, *args, **kwargs):
        print(f"Unhandled error in event '{event}':")
        traceback.print_exc()


client = DemeryBot()


@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    cmd = interaction.command.name if interaction.command else "unknown"
    print(f"Command error in '{cmd}': {type(error).__name__}: {error}")


# --- scheduled task ---


@tasks.loop(time=datetime.time(hour=diss_HOUR, tzinfo=datetime.timezone.utc))
async def daily_digest_task():
    try:
        yesterday = (datetime.datetime.now(EASTERN) - datetime.timedelta(days=1)).strftime("%Y%m%d")
        if yesterday not in TOURNAMENT_GAME_DATES:
            print(f"[digest] No tournament games yesterday ({yesterday}), skipping digest")
            return
        await _run_digest()
    except Exception:
        print("Digest error:")
        traceback.print_exc()


@daily_digest_task.before_loop
async def before_digest():
    await client.wait_until_ready()


# --- commands ---


@client.tree.command(name="diss", description="Have Demery roast someone's bracket picks")
@app_commands.describe(user="The victim")
async def diss(
    interaction: discord.Interaction,
    user: discord.Member,
):
    if await _check_diss_cooldown(interaction):
        return

    await interaction.response.defer()
    bracket_data = db.get_bracket(user.id, interaction.guild_id)
    results = None
    if bracket_data:
        games = await espn.fetch_tournament_results()
        if games:
            results = _compute_bracket_status(bracket_data, games)
    diss_text = await generate_diss(user.mention, bracket_data, results)
    await interaction.followup.send(diss_text)


@client.tree.command(
    name="submitbracket",
    description=f"Upload a screenshot of your bracket ({SUPPORTED_IMAGE_FORMATS_LABEL})",
)
@app_commands.describe(image=f"A screenshot of your filled-out bracket ({SUPPORTED_IMAGE_FORMATS_LABEL})")
async def submit_bracket(interaction: discord.Interaction, image: discord.Attachment):
    # Validate file type before doing any work
    content_type = image.content_type or ""
    filename = (image.filename or "").lower()
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""

    type_ok = content_type.split(";")[0].strip() in ALLOWED_IMAGE_TYPES
    ext_ok = ext in ALLOWED_IMAGE_EXTENSIONS

    if not type_ok and not ext_ok:
        await interaction.response.send_message(
            "That doesn't look like a supported image. "
            f"Please upload a **{SUPPORTED_IMAGE_FORMATS_LABEL}** screenshot of your bracket.",
            ephemeral=True,
        )
        return

    if await _check_submit_rate_limit(interaction):
        return

    await interaction.response.defer()

    try:
        picks = await parse_bracket_image(image.url)
    except ValueError as e:
        await interaction.followup.send(f"Couldn't read your bracket from that image: {e}", ephemeral=True)
        return
    except Exception as e:
        print(f"Unexpected error parsing bracket image: {e}")
        await interaction.followup.send(
            "Something went wrong while reading your bracket. "
            f"Make sure you're uploading a clear screenshot ({SUPPORTED_IMAGE_FORMATS_LABEL}) and try again.",
            ephemeral=True,
        )
        return

    try:
        espn_names = await espn.fetch_tournament_team_names()
        if espn_names:
            picks = await normalize_team_names(picks, espn_names)
    except Exception as e:
        print(f"Team name normalization failed, saving raw picks: {e}")

    db.upsert_bracket(interaction.user.id, interaction.guild_id, interaction.user.display_name, picks)
    ack = await generate_submission_ack(interaction.user.mention, picks)
    await interaction.followup.send(ack)

    lines = [
        f"**Champion:** {picks['champion']}",
        f"**Championship:** {', '.join(picks['championship_game'])}",
        f"**Final Four:** {', '.join(picks['final_four'])}",
        f"**Elite Eight:** {', '.join(picks['elite_eight'])}",
        f"**Sweet 16:** {', '.join(picks['sweet_16'])}",
        f"**Round of 32:** {', '.join(picks['round_of_32'])}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@client.tree.command(name="disshelp", description="How to use Demery Bot")
async def disshelp(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Demery Bot** — March Madness trash talk, powered by AI.\n\n"
        "**`/diss @user`**\n"
        "Tag someone and Demery will roast their bracket picks.\n"
        "If they've submitted a bracket, the roast gets specific.\n\n"
        "**`/submitbracket [image]`**\n"
        "Upload a screenshot of your filled-out bracket so Demery knows your actual picks. "
        "You get 3 submissions per day — use them to correct a bad parse or swap picks.\n\n"
        "There's a 2-minute cooldown between uses.",
        ephemeral=True,
    )


@client.tree.command(name="about", description="What is Demery Bot?")
async def about(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Demery Bot** — March Madness trash talk, powered by AI and channeling "
        "the energy of Demery, who never lets a bad bracket pick slide.\n\n"
        "Demery watches your bracket, tracks every bust, and delivers the roasts "
        "you deserve.\n\n"
        "**Commands:**\n"
        "- `/diss @user` — Demery roasts someone's bracket picks\n"
        "- `/submitbracket [image]` — upload a bracket screenshot so Demery knows your picks\n"
        "- `/setchannel #channel` — set the digest channel *(Manage Channels permission required)*\n"
        "- `/disshelp` — full usage guide\n\n"
        "**Daily Digest:** Every morning after tournament games, Demery posts a recap "
        "calling out busted picks and praising survivors across all submitted brackets."
    )


@client.tree.command(name="setchannel", description="Set the channel for daily bracket digest posts")
@app_commands.describe(channel="Tag the text channel (e.g. #march-madness)")
@app_commands.default_permissions(manage_channels=True)
async def setchannel(interaction: discord.Interaction, channel: str):
    # Accept channel mention (<#ID>), raw ID, or channel name
    mention_match = re.match(r"<#(\d+)>", channel.strip())
    if mention_match:
        channel_id = int(mention_match.group(1))
    elif channel.strip().isdigit():
        channel_id = int(channel.strip())
    else:
        found = discord.utils.get(interaction.guild.text_channels, name=channel.strip().lstrip("#"))
        if not found:
            await interaction.response.send_message(
                f"Couldn't find a text channel called `{channel}`. Try tagging it like #channel-name.",
                ephemeral=True,
            )
            return
        channel_id = found.id

    target = interaction.guild.get_channel(channel_id)
    if not target:
        await interaction.response.send_message(
            "I can't see that channel — make sure I have access to it.", ephemeral=True
        )
        return

    print(f"setchannel called: guild={interaction.guild_id} channel_id={channel_id} channel_name={target.name}")
    db.set_guild_channel(interaction.guild_id, channel_id)
    await interaction.response.send_message(f"Got it — daily digests will post to <#{channel_id}>.", ephemeral=True)


@client.tree.command(name="debugguild", description="[Dev] Show what the bot can see in this guild")
async def debugguild(interaction: discord.Interaction):
    if await _reject_non_dev(interaction):
        return

    guild = interaction.guild
    bot_member = guild.me
    lines = [
        f"**Guild:** {guild.name} (`{guild.id}`)",
        f"**Bot permissions:** {bot_member.guild_permissions.value}",
        f"**View Channels:** {bot_member.guild_permissions.view_channel}",
        f"**Send Messages:** {bot_member.guild_permissions.send_messages}",
        f"**Bot roles:** {', '.join(r.name for r in bot_member.roles)}",
        f"**Text channels visible ({len(guild.text_channels)}):**",
    ]
    for ch in guild.text_channels[:20]:
        perms = ch.permissions_for(bot_member)
        lines.append(f"- #{ch.name} (`{ch.id}`) view={perms.view_channel} send={perms.send_messages}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@client.tree.command(name="testdigest", description="[Dev] Trigger the daily digest now")
async def testdigest(interaction: discord.Interaction):
    if await _reject_non_dev(interaction):
        return

    await interaction.response.defer(ephemeral=True)
    try:
        message = await _run_digest(broadcast=False, guild_id=interaction.guild_id)
        if message:
            chunks = _split_message(message)
            await interaction.followup.send(f"Digest preview:\n{chunks[0]}", ephemeral=True)
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk, ephemeral=True)
        else:
            await interaction.followup.send(
                "Nothing to post — no completed games today or no brackets on file.",
                ephemeral=True,
            )
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)


@client.tree.command(name="pushdigest", description="[Dev] Broadcast the daily digest to the channel now")
async def pushdigest(interaction: discord.Interaction):
    if await _reject_non_dev(interaction):
        return

    await interaction.response.defer(ephemeral=True)
    try:
        message = await _run_digest(guild_id=interaction.guild_id)
        if message:
            chunks = _split_message(message)
            await interaction.followup.send(f"Digest pushed to channel:\n{chunks[0]}", ephemeral=True)
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk, ephemeral=True)
        else:
            await interaction.followup.send(
                "Nothing to post — no completed games today or no brackets on file.",
                ephemeral=True,
            )
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)


# --- orchestration helpers ---


async def _run_digest(broadcast: bool = True, guild_id: int | None = None) -> str | None:
    """
    Core digest logic. Generates a per-guild digest message.
    If guild_id is given, only process that guild.
    broadcast=True posts to the configured channel; False returns the message only.
    """
    guild_channels = db.get_all_guild_channels()
    if not guild_channels:
        print("No guild channels configured — skipping digest")
        return None

    if guild_id is not None:
        guild_channels = [gc for gc in guild_channels if gc["guild_id"] == guild_id]
        if not guild_channels:
            return None

    today_games, today_str = await _fetch_and_persist_today_games()
    today_date = datetime.datetime.strptime(today_str, "%Y%m%d").date()
    await _backfill_historical_games(today_date)

    all_results = db.get_all_game_results()
    all_games = [
        {
            "winner": r["winner"],
            "loser": r["loser"],
            "round": r["round"],
            "winner_seed": r.get("winner_seed"),
            "loser_seed": r.get("loser_seed"),
            "region": r.get("region"),
        }
        for r in all_results
    ]
    print(f"[digest] {len(all_games)} total cumulative games in DB")

    for game in today_games:
        tier = ROUND_NAME_TO_TIER.get(game["round"])
        print(f"[digest]   Today: {game['winner']} beat {game['loser']} | round='{game['round']}' → tier={tier}")

    today_losers = {g["loser"] for g in today_games}
    last_message = None
    for guild_channel in guild_channels:
        submitters = _build_submitters_for_guild(guild_channel["guild_id"], all_games, today_losers)
        if not submitters:
            print(f"[digest] Guild {guild_channel['guild_id']}: no submitters, skipping")
            continue

        print(f"[digest] Guild {guild_channel['guild_id']}: sending to LLM with {len(submitters)} submitters")
        message = await generate_digest(submitters, today_games)
        if broadcast:
            channel = client.get_channel(guild_channel["channel_id"])
            if channel:
                for chunk in _split_message(message):
                    await channel.send(chunk)
        last_message = message

    return last_message


async def _fetch_and_persist_today_games() -> tuple[list[dict], str]:
    """Fetch today's ESPN results and persist to DB. Returns (games, date_str)."""
    today_str = datetime.datetime.now(EASTERN).strftime("%Y%m%d")
    print(f"[digest] Fetching games for {today_str} (Eastern)")
    today_games = await espn.fetch_today_results(today_str)
    db.save_game_results(today_str, today_games)
    print(f"[digest] ESPN returned {len(today_games)} completed games for today")
    return today_games, today_str


async def _backfill_historical_games(today_date: datetime.date) -> None:
    """Backfill missing historical dates and re-fetch any dates lacking seed data."""
    tournament_start = datetime.date(2026, 3, 17)  # First Four
    existing_dates = db.get_game_result_dates()
    seedless_dates = db.get_seedless_game_dates()
    d = tournament_start
    while d < today_date:
        date_str = d.strftime("%Y%m%d")
        if date_str not in existing_dates:
            print(f"[digest] Backfilling {date_str}")
            historical_games = await espn.fetch_today_results(date_str)
            db.save_game_results(date_str, historical_games)
        elif date_str in seedless_dates:
            print(f"[digest] Re-fetching {date_str} for seed data")
            historical_games = await espn.fetch_today_results(date_str)
            db.save_game_results(date_str, historical_games)
        d += datetime.timedelta(days=1)


def _build_submitters_for_guild(
    guild_id: int, all_games: list[dict], today_losers: set[str] | None = None
) -> list[dict]:
    """Load guild brackets and compute bracket status for each submitter."""
    today_losers = today_losers or set()
    guild_brackets = db.get_guild_brackets(guild_id)
    print(f"[digest] Guild {guild_id}: {len(guild_brackets)} brackets on file")
    submitters = []
    for entry in guild_brackets:
        picks = entry["picks"]
        status = _compute_bracket_status(picks, all_games)
        survivors = _enrich_survivors(status["survivors"], picks)
        sorted_busts = sorted(
            status["busts"],
            key=lambda b: ROUND_TIER_ORDER.index(b["pick"]) if b["pick"] in ROUND_TIER_ORDER else -1,
            reverse=True,
        )
        new_busts = [b for b in sorted_busts if b["team"] in today_losers]
        prior_busts = [b for b in sorted_busts if b["team"] not in today_losers]
        print(
            f"[digest]   {entry['display_name']}: "
            f"{len(new_busts)} new busts, {len(prior_busts)} prior busts, {len(survivors)} alive"
        )
        submitters.append(
            {
                "mention": f"<@{entry['discord_user_id']}>",
                "new_busts": new_busts,
                "prior_busts": prior_busts,
                "survivors": survivors,
            }
        )
    random.shuffle(submitters)
    return submitters


def _enrich_survivors(survivors: list[dict], picks: dict) -> list[dict]:
    """Add pick depth to survivors, filter cashed-out, sort by deepest pick first."""
    enriched = []
    for s in survivors:
        farthest = _find_farthest_picked_round(s["team"], picks)
        if not farthest:
            continue
        thru_tier = ROUND_NAME_TO_TIER.get(s["thru"])
        if not thru_tier:
            continue
        farthest_idx = ROUND_TIER_ORDER.index(farthest)
        thru_idx = ROUND_TIER_ORDER.index(thru_tier)
        if farthest_idx <= thru_idx:
            continue
        s["farthest_pick"] = farthest
        enriched.append(s)
    enriched.sort(key=lambda s: ROUND_TIER_ORDER.index(s["farthest_pick"]), reverse=True)
    return enriched


# --- message helpers ---


def _split_message(text: str, limit: int = 1990) -> list[str]:
    """Split text into chunks that fit within Discord's message limit.
    Prefers splitting on paragraph breaks, falls back to newlines, then hard cuts.
    Continuation chunks are prefixed with '(cont) '.
    """
    if len(text) <= limit:
        return [text]

    CONT = "(cont) "
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        # Skip over the continuation prefix when searching for a split point
        # so the space inside "(cont) " is never chosen as a separator.
        search_start = len(CONT) if remaining.startswith(CONT) else 0
        for sep in ("\n\n", "\n", " "):
            split_at = remaining.rfind(sep, search_start, limit)
            if split_at > search_start:
                chunks.append(remaining[:split_at])
                remaining = CONT + remaining[split_at + len(sep) :].lstrip()
                break
        else:
            # Hard cut
            chunks.append(remaining[:limit])
            remaining = CONT + remaining[limit:]

    return chunks


# --- guard helpers ---


async def _reject_non_dev(interaction: discord.Interaction) -> bool:
    """Send 'Not for you.' and return True if user is not a dev. Return False if they passed."""
    if interaction.user.id not in BYPASS_USER_IDS:
        await interaction.response.send_message("Not for you.", ephemeral=True)
        return True
    return False


async def _check_diss_cooldown(interaction: discord.Interaction) -> bool:
    """Check cooldown and send rejection if on cooldown. Return True if rejected, False if clear."""
    caller_id = interaction.user.id
    if caller_id in BYPASS_USER_IDS:
        return False
    now = time.monotonic()
    last = _last_used.get(caller_id, 0)
    remaining = COOLDOWN_SECONDS - (now - last)
    if remaining > 0:
        await interaction.response.send_message(f"Chill — you can diss again in {int(remaining) + 1}s.", ephemeral=True)
        return True
    _last_used[caller_id] = now
    return False


async def _check_submit_rate_limit(interaction: discord.Interaction) -> bool:
    """Check daily submission limit and send rejection if exceeded. Return True if rejected, False if clear."""
    if interaction.user.id in BYPASS_USER_IDS:
        return False
    today = datetime.datetime.now(EASTERN).strftime("%Y%m%d")
    last_date, count = _last_submit.get(interaction.user.id, ("", 0))
    if last_date == today and count >= MAX_SUBMIT_PER_DAY:
        await interaction.response.send_message(
            f"You've used all {MAX_SUBMIT_PER_DAY} submissions for today. Try again tomorrow.",
            ephemeral=True,
        )
        return True
    _last_submit[interaction.user.id] = (today, count + 1 if last_date == today else 1)
    return False


# --- computation helpers ---


def _compute_bracket_status(picks: dict, games: list[dict]) -> dict:
    """Returns {"busts": [...], "survivors": [...]} for one user's picks against game results."""
    busts, survivors = [], []
    for game in games:
        tier = ROUND_NAME_TO_TIER.get(game["round"])
        if not tier:
            continue
        idx = ROUND_TIER_ORDER.index(tier)
        tiers_at_or_beyond = ROUND_TIER_ORDER[idx:]
        picked_teams = set()
        for t in tiers_at_or_beyond:
            picked_teams.update(_get_picks_for_tier(picks, t))
        if game["loser"] in picked_teams:
            furthest = _find_farthest_picked_round(game["loser"], picks) or tier
            busts.append(
                {
                    "team": game["loser"],
                    "pick": furthest,
                    "lost": game["round"],
                    "seed": game.get("loser_seed"),
                    "region": game.get("region"),
                }
            )
        if game["winner"] in picked_teams:
            survivors.append(
                {
                    "team": game["winner"],
                    "thru": game["round"],
                    "seed": game.get("winner_seed"),
                }
            )

    # Deduplicate survivors — keep only the latest round per team
    seen = {}
    for s in survivors:
        tier = ROUND_NAME_TO_TIER.get(s["thru"])
        idx = ROUND_TIER_ORDER.index(tier) if tier else -1
        if s["team"] not in seen or idx > seen[s["team"]][1]:
            seen[s["team"]] = (s, idx)
    survivors = [entry for entry, _ in seen.values()]

    return {"busts": busts, "survivors": survivors}


def _get_picks_for_tier(picks: dict, tier: str) -> set[str]:
    """Return the set of team names picked for a given tier, handling str vs list."""
    val = picks.get(tier, [])
    if isinstance(val, str):
        return {val}
    return set(val)


def _find_farthest_picked_round(team: str, picks: dict) -> str | None:
    """Find the furthest round a team was picked to reach, searching from championship down."""
    for tier in reversed(ROUND_TIER_ORDER):
        if team in _get_picks_for_tier(picks, tier):
            return tier
    return None


if __name__ == "__main__":
    client.run(DISCORD_BOT_TOKEN)

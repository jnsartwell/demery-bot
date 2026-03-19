import datetime
import os
import time

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import db
import espn
from llm import generate_digest, generate_submission_ack, generate_taunt, parse_bracket_image

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_BOT_APPLICATION_ID = int(os.environ["DISCORD_BOT_APPLICATION_ID"])
DISCORD_GUILD_IDS = [
    gid.strip()
    for gid in os.getenv("DISCORD_GUILD_ID", "").split(",")
    if gid.strip()
]
BYPASS_USER_IDS = {
    int(uid.strip())
    for uid in os.getenv("DISCORD_BYPASS_USER_IDS", "").split(",")
    if uid.strip()
}
TAUNT_HOUR = int(os.getenv("TAUNT_HOUR") or "12")

COOLDOWN_SECONDS = 120
_last_used: dict[int, float] = {}
_last_submit: dict[int, tuple[str, int]] = {}  # user_id → (YYYYMMDD, count)
MAX_SUBMIT_PER_DAY = 3

ROUND_TIER_ORDER = [
    "round_of_32", "sweet_16", "elite_eight",
    "final_four", "championship_game", "champion",
]
ROUND_NAME_TO_TIER = {
    "First Round":  "round_of_32",
    "Second Round": "sweet_16",
    "Sweet 16":     "elite_eight",
    "Elite Eight":  "final_four",
    "Final Four":   "championship_game",
    "Championship": "champion",
}


class DemeryBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents, application_id=DISCORD_BOT_APPLICATION_ID)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if DISCORD_GUILD_IDS:
            for gid in DISCORD_GUILD_IDS:
                guild = discord.Object(id=int(gid))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        db.init_db()
        if not daily_digest_task.is_running():
            daily_digest_task.start()


client = DemeryBot()


# --- digest helpers ---

async def _run_digest(force: bool = False) -> str | None:
    """
    Core digest logic. Posts to every configured guild channel.
    Returns the posted message, or None if skipped.
    force=True bypasses the already-posted guard and skips marking as posted.
    """
    guild_channels = db.get_all_guild_channels()
    if not guild_channels:
        print("No guild channels configured — skipping digest")
        return None

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    state_key = f"digest_{today}"

    if not force and db.get_digest_state(state_key):
        return None  # already posted today

    games = await espn.fetch_today_results(today)
    all_brackets = db.get_all_brackets()
    submitters = []
    for entry in all_brackets:
        picks = entry["picks"]
        busts, survivors = [], []
        for game in games:
            tier = ROUND_NAME_TO_TIER.get(game["round"])
            if not tier:
                continue  # play-in or unrecognized round — skip
            idx = ROUND_TIER_ORDER.index(tier)
            tiers_at_or_beyond = ROUND_TIER_ORDER[idx:]
            # collect all teams user picked to survive this round or further
            picked_teams = set()
            for t in tiers_at_or_beyond:
                val = picks.get(t, [])
                picked_teams.update([val] if isinstance(val, str) else val)
            if game["loser"] in picked_teams:
                # find furthest tier they had the loser reaching
                furthest = next(
                    (t for t in reversed(ROUND_TIER_ORDER) if game["loser"] in (
                        [picks[t]] if isinstance(picks.get(t), str) else picks.get(t, [])
                    )),
                    tier,
                )
                busts.append({
                    "team": game["loser"],
                    "picked_to_reach": furthest,
                    "lost_in": game["round"],
                })
            if game["winner"] in picked_teams:
                survivors.append({
                    "team": game["winner"],
                    "still_alive_through": game["round"],
                })
        submitters.append({
            "mention": f"<@{entry['discord_user_id']}>",
            "name": entry["display_name"],
            "busts": busts,
            "survivors": survivors,
        })

    if not submitters:
        return None

    message = await generate_digest(submitters)
    for gc in guild_channels:
        channel = client.get_channel(gc["channel_id"])
        if channel:
            await channel.send(message)
    if not force:
        db.set_digest_state(state_key, "posted")

    return message


# --- scheduled task ---

@tasks.loop(
    time=datetime.time(hour=TAUNT_HOUR, tzinfo=datetime.timezone.utc)
)
async def daily_digest_task():
    try:
        await _run_digest()
    except Exception as e:
        print(f"Digest error: {e}")


@daily_digest_task.before_loop
async def before_digest():
    await client.wait_until_ready()


# --- commands ---

@client.tree.command(name="diss", description="Have Demery roast someone's bracket picks")
@app_commands.describe(
    user="The victim",
    intensity="How hard to go (default: medium)",
)
@app_commands.choices(intensity=[
    app_commands.Choice(name="mild", value="mild"),
    app_commands.Choice(name="medium", value="medium"),
    app_commands.Choice(name="harsh", value="harsh"),
])
async def taunt(
    interaction: discord.Interaction,
    user: discord.Member,
    intensity: app_commands.Choice[str] = None,
):
    intensity_value = intensity.value if intensity else "medium"

    caller_id = interaction.user.id
    if caller_id not in BYPASS_USER_IDS:
        now = time.monotonic()
        last = _last_used.get(caller_id, 0)
        remaining = COOLDOWN_SECONDS - (now - last)
        if remaining > 0:
            await interaction.response.send_message(
                f"Chill — you can taunt again in {int(remaining) + 1}s.", ephemeral=True
            )
            return
        _last_used[caller_id] = now

    await interaction.response.defer()
    bracket_data = db.get_bracket(user.id)
    taunt_text = await generate_taunt(user.display_name, intensity_value, bracket_data)
    await interaction.followup.send(f"{user.mention} {taunt_text}")


@client.tree.command(
    name="submitbracket",
    description="Upload a screenshot of your bracket so Demery knows your picks",
)
@app_commands.describe(image="A screenshot of your filled-out bracket")
async def submit_bracket(interaction: discord.Interaction, image: discord.Attachment):
    if interaction.user.id not in BYPASS_USER_IDS:
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        last_date, count = _last_submit.get(interaction.user.id, ("", 0))
        if last_date == today and count >= MAX_SUBMIT_PER_DAY:
            await interaction.response.send_message(
                f"You've used all {MAX_SUBMIT_PER_DAY} submissions for today. Try again tomorrow.",
                ephemeral=True,
            )
            return
        _last_submit[interaction.user.id] = (today, count + 1 if last_date == today else 1)

    await interaction.response.defer()

    try:
        picks = await parse_bracket_image(image.url)
    except ValueError as e:
        await interaction.followup.send(
            f"Couldn't read your bracket from that image: {e}", ephemeral=True
        )
        return

    db.upsert_bracket(interaction.user.id, interaction.user.display_name, picks)
    ack = await generate_submission_ack(interaction.user.display_name, picks)
    await interaction.followup.send(f"{interaction.user.mention} {ack}")

    if interaction.user.id in BYPASS_USER_IDS:
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
        "**`/diss @user [intensity]`**\n"
        "Tag someone and Demery will roast their bracket picks.\n"
        "If they've submitted a bracket, the roast gets specific.\n\n"
        "**`/submitbracket [image]`**\n"
        "Upload a screenshot of your filled-out bracket so Demery knows your actual picks. "
        "You get 3 submissions per day — use them to correct a bad parse or swap picks.\n\n"
        "**Intensity levels:**\n"
        "- `mild` — light ribbing, almost affectionate\n"
        "- `medium` — sharp but fun *(default)*\n"
        "- `harsh` — the most pointed, lands with a wink\n\n"
        "There's a 2-minute cooldown between uses.",
        ephemeral=True,
    )


@client.tree.command(name="setchannel", description="Set the channel for daily bracket digest posts")
@app_commands.describe(channel="The text channel where Demery will post daily results")
@app_commands.default_permissions(manage_guild=True)
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    db.set_guild_channel(interaction.guild_id, channel.id)
    await interaction.response.send_message(
        f"Got it — daily digests will post to {channel.mention}.", ephemeral=True
    )


@client.tree.command(name="testdigest", description="[Dev] Trigger the daily digest now")
async def testdigest(interaction: discord.Interaction):
    if interaction.user.id not in BYPASS_USER_IDS:
        await interaction.response.send_message("Not for you.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        message = await _run_digest(force=True)
        if message:
            await interaction.followup.send(
                f"Digest posted:\n{message}", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Nothing to post — no completed games today or no brackets on file.",
                ephemeral=True,
            )
    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)


client.run(DISCORD_BOT_TOKEN)

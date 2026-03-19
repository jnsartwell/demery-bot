import datetime
import os
import time

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import db
import espn
from llm import generate_digest, generate_submission_ack, generate_taunt

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
TAUNT_HOUR = int(os.getenv("TAUNT_HOUR", "12"))

COOLDOWN_SECONDS = 120
_last_used: dict[int, float] = {}


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

def _all_bracket_teams(picks: dict) -> set[str]:
    teams: set[str] = set()
    for key in ("champion", "championship_game", "final_four", "elite_eight"):
        val = picks.get(key, [])
        teams.update([val] if isinstance(val, str) else val)
    return teams


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
    if not games:
        return None  # no completed games today

    all_brackets = db.get_all_brackets()
    submitters = []
    for entry in all_brackets:
        bracket_teams = _all_bracket_teams(entry["picks"])
        wins = [
            f"{g['winner']} advances"
            for g in games
            if g["winner"] in bracket_teams
        ]
        losses = [
            f"{g['loser']} eliminated"
            for g in games
            if g["loser"] in bracket_teams
        ]
        if wins or losses:
            submitters.append(
                {
                    "mention": f"<@{entry['discord_user_id']}>",
                    "name": entry["display_name"],
                    "wins": wins,
                    "losses": losses,
                }
            )

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
    description="Submit your ESPN bracket so Demery knows your actual picks",
)
@app_commands.describe(espn_url="Your ESPN Tournament Challenge bracket URL")
async def submit_bracket(interaction: discord.Interaction, espn_url: str):
    await interaction.response.defer(ephemeral=True)

    entry_id = espn.parse_entry_id(espn_url)
    if not entry_id:
        await interaction.followup.send(
            "Couldn't find an entry ID in that URL. "
            "Make sure you're pasting your ESPN Tournament Challenge bracket URL.",
            ephemeral=True,
        )
        return

    try:
        picks = await espn.fetch_bracket(entry_id)
    except Exception as e:
        await interaction.followup.send(
            f"Couldn't fetch your bracket from ESPN: {e}", ephemeral=True
        )
        return

    db.upsert_bracket(interaction.user.id, interaction.user.display_name, picks)
    ack = await generate_submission_ack(interaction.user.display_name, picks)
    await interaction.followup.send(ack, ephemeral=True)


@client.tree.command(name="disshelp", description="How to use Demery Bot")
async def disshelp(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Demery Bot** — March Madness trash talk, powered by AI.\n\n"
        "**`/diss @user [intensity]`**\n"
        "Tag someone and Demery will roast their bracket picks.\n"
        "If they've submitted a bracket, the roast gets specific.\n\n"
        "**`/submitbracket [espn_url]`**\n"
        "Paste your ESPN Tournament Challenge bracket URL so Demery knows your actual picks.\n\n"
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

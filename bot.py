import os
import time
import discord
from discord import app_commands
from dotenv import load_dotenv
from llm import generate_taunt

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


client = DemeryBot()


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
    taunt_text = await generate_taunt(user.display_name, intensity_value)
    await interaction.followup.send(f"{user.mention} {taunt_text}")


@client.tree.command(name="disshelp", description="How to use Demery Bot")
async def disshelp(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Demery Bot** — March Madness trash talk, powered by AI.\n\n"
        "**`/diss @user [intensity]`**\n"
        "Tag someone and Demery will roast their bracket picks.\n\n"
        "**Intensity levels:**\n"
        "- `mild` — light ribbing, almost affectionate\n"
        "- `medium` — no mercy, full roast *(default)*\n"
        "- `harsh` — scorched earth\n\n"
        "There's a 2-minute cooldown between uses.",
        ephemeral=True,
    )


client.run(DISCORD_BOT_TOKEN)

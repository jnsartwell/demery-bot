import os
import discord
from discord import app_commands
from dotenv import load_dotenv
from llm import generate_taunt

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_BOT_APPLICATION_ID = int(os.environ["DISCORD_BOT_APPLICATION_ID"])
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")


class DemeryBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents, application_id=DISCORD_BOT_APPLICATION_ID)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")


client = DemeryBot()


@client.tree.command(name="taunt", description="Have Demery roast someone's bracket picks")
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
    await interaction.response.defer()
    taunt_text = await generate_taunt(user.display_name, intensity_value)
    await interaction.followup.send(f"{user.mention} {taunt_text}")


client.run(DISCORD_BOT_TOKEN)

"""
Tests for /setchannel command — covers:
  US-10: Set the digest channel
"""

from unittest.mock import MagicMock

import pytest

import bot
import db


class TestSetChannelCommand:
    @pytest.mark.asyncio
    async def test_mention_format(self, make_interaction):
        interaction = make_interaction(guild_id=9001)
        target_channel = MagicMock()
        target_channel.name = "march-madness"
        target_channel.id = 5001
        interaction.guild.get_channel = MagicMock(return_value=target_channel)

        await bot.setchannel.callback(interaction, channel="<#5001>")

        channels = db.get_all_guild_channels()
        assert len(channels) == 1
        assert channels[0]["guild_id"] == 9001
        assert channels[0]["channel_id"] == 5001

    @pytest.mark.asyncio
    async def test_raw_id(self, make_interaction):
        interaction = make_interaction(guild_id=9001)
        target_channel = MagicMock()
        target_channel.name = "march-madness"
        interaction.guild.get_channel = MagicMock(return_value=target_channel)

        await bot.setchannel.callback(interaction, channel="5001")

        channels = db.get_all_guild_channels()
        assert channels[0]["channel_id"] == 5001

    @pytest.mark.asyncio
    async def test_channel_name_lookup(self, make_interaction):
        interaction = make_interaction(guild_id=9001)

        ch = MagicMock()
        ch.name = "march-madness"
        ch.id = 5001
        interaction.guild.text_channels = [ch]
        interaction.guild.get_channel = MagicMock(return_value=ch)

        # discord.utils.get should find it by name
        await bot.setchannel.callback(interaction, channel="march-madness")

        channels = db.get_all_guild_channels()
        assert channels[0]["channel_id"] == 5001

    @pytest.mark.asyncio
    async def test_channel_not_found(self, make_interaction):
        interaction = make_interaction(guild_id=9001)
        interaction.guild.text_channels = []

        await bot.setchannel.callback(interaction, channel="nonexistent")

        msg = interaction.response.send_message.call_args[0][0]
        assert "Couldn't find" in msg
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_bot_cant_see_channel(self, make_interaction):
        interaction = make_interaction(guild_id=9001)
        interaction.guild.get_channel = MagicMock(return_value=None)

        await bot.setchannel.callback(interaction, channel="<#5001>")

        msg = interaction.response.send_message.call_args[0][0]
        assert "can't see" in msg.lower() or "access" in msg.lower()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_success_confirmation_ephemeral(self, make_interaction):
        interaction = make_interaction(guild_id=9001)
        target_channel = MagicMock()
        target_channel.name = "march-madness"
        interaction.guild.get_channel = MagicMock(return_value=target_channel)

        await bot.setchannel.callback(interaction, channel="<#5001>")

        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        msg = interaction.response.send_message.call_args[0][0]
        assert "digest" in msg.lower()

    @pytest.mark.asyncio
    async def test_persists_across_calls(self, make_interaction):
        interaction = make_interaction(guild_id=9001)
        target = MagicMock()
        target.name = "ch"
        interaction.guild.get_channel = MagicMock(return_value=target)

        await bot.setchannel.callback(interaction, channel="<#5001>")

        # Verify persisted in DB
        channels = db.get_all_guild_channels()
        assert any(c["guild_id"] == 9001 and c["channel_id"] == 5001 for c in channels)

    @pytest.mark.asyncio
    async def test_channel_name_with_hash(self, make_interaction):
        """Channel name prefixed with # should still work."""
        interaction = make_interaction(guild_id=9001)
        ch = MagicMock()
        ch.name = "march-madness"
        ch.id = 5001
        interaction.guild.text_channels = [ch]
        interaction.guild.get_channel = MagicMock(return_value=ch)

        await bot.setchannel.callback(interaction, channel="#march-madness")

        channels = db.get_all_guild_channels()
        assert channels[0]["channel_id"] == 5001

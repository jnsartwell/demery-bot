"""
Tests for slash commands in bot.py — covers:
  US-1:  Diss a friend's bracket
  US-2:  Cooldown on /diss
  US-3:  Submit a bracket via image upload
  US-4:  Submission rate limit
  US-7:  View help
  US-8:  View about info
  US-14: Test digest (preview)
  US-15: Push digest (broadcast)
  US-16: Debug guild visibility
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import bot
import db
import espn

# ---------------------------------------------------------------------------
# US-1: Diss a friend's bracket
# ---------------------------------------------------------------------------


class TestDissCommand:
    @pytest.mark.asyncio
    async def test_defers_interaction(self, make_interaction, make_member, bypass_user, mock_anthropic, monkeypatch):
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        interaction = make_interaction(user_id=bypass_user)
        target = make_member()
        await bot.diss.callback(interaction, user=target, intensity=None)
        interaction.response.defer.assert_called_once()

    @pytest.mark.asyncio
    async def test_mentions_target(self, make_interaction, make_member, bypass_user, mock_anthropic, monkeypatch):
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        mock_gen = AsyncMock(return_value="roast")
        monkeypatch.setattr(bot, "generate_diss", mock_gen)
        interaction = make_interaction(user_id=bypass_user)
        target = make_member(user_id=2001)
        await bot.diss.callback(interaction, user=target, intensity=None)
        assert mock_gen.call_args[0][0] == "<@2001>"

    @pytest.mark.asyncio
    async def test_default_intensity_medium(
        self, make_interaction, make_member, bypass_user, mock_anthropic, monkeypatch
    ):
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        mock_gen = AsyncMock(return_value="roast")
        monkeypatch.setattr(bot, "generate_diss", mock_gen)
        interaction = make_interaction(user_id=bypass_user)
        target = make_member()
        await bot.diss.callback(interaction, user=target, intensity=None)
        assert mock_gen.call_args[0][1] == "medium"

    @pytest.mark.asyncio
    async def test_intensity_passed_through(
        self, make_interaction, make_member, make_intensity, bypass_user, mock_anthropic, monkeypatch
    ):
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        mock_gen = AsyncMock(return_value="roast")
        monkeypatch.setattr(bot, "generate_diss", mock_gen)
        interaction = make_interaction(user_id=bypass_user)
        target = make_member()
        await bot.diss.callback(interaction, user=target, intensity=make_intensity("harsh"))
        assert mock_gen.call_args[0][1] == "harsh"

    @pytest.mark.asyncio
    async def test_with_bracket_passes_picks(
        self, make_interaction, make_member, bypass_user, sample_picks, mock_anthropic, monkeypatch
    ):
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        mock_gen = AsyncMock(return_value="roast")
        monkeypatch.setattr(bot, "generate_diss", mock_gen)
        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        target = make_member(user_id=2001)
        db.upsert_bracket(2001, 9001, "Victim", sample_picks)

        await bot.diss.callback(interaction, user=target, intensity=None)
        assert mock_gen.call_args[0][2] is not None  # bracket_data

    @pytest.mark.asyncio
    async def test_without_bracket_no_picks(
        self, make_interaction, make_member, bypass_user, mock_anthropic, monkeypatch
    ):
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        mock_gen = AsyncMock(return_value="roast")
        monkeypatch.setattr(bot, "generate_diss", mock_gen)
        interaction = make_interaction(user_id=bypass_user)
        target = make_member()

        await bot.diss.callback(interaction, user=target, intensity=None)
        assert mock_gen.call_args[0][2] is None  # bracket_data
        assert mock_gen.call_args[0][3] is None  # results

    @pytest.mark.asyncio
    async def test_with_bracket_and_results(
        self, make_interaction, make_member, bypass_user, sample_picks, mock_anthropic, monkeypatch
    ):
        """When bracket exists and games have been played, results are computed and passed."""
        games = [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=games))
        mock_gen = AsyncMock(return_value="roast")
        monkeypatch.setattr(bot, "generate_diss", mock_gen)
        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        target = make_member(user_id=2001)
        db.upsert_bracket(2001, 9001, "Victim", sample_picks)

        await bot.diss.callback(interaction, user=target, intensity=None)
        results = mock_gen.call_args[0][3]
        assert results is not None
        assert "busts" in results
        assert "survivors" in results


# ---------------------------------------------------------------------------
# US-2: Cooldown on /diss
# ---------------------------------------------------------------------------


class TestDissCooldown:
    @pytest.mark.asyncio
    async def test_cooldown_blocks_second_call(self, make_interaction, make_member, mock_anthropic, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        interaction1 = make_interaction(user_id=5001)
        interaction2 = make_interaction(user_id=5001)
        target = make_member()

        await bot.diss.callback(interaction1, user=target, intensity=None)
        await bot.diss.callback(interaction2, user=target, intensity=None)

        interaction2.response.send_message.assert_called_once()
        msg = interaction2.response.send_message.call_args[0][0]
        assert "Chill" in msg

    @pytest.mark.asyncio
    async def test_cooldown_shows_remaining_time(self, make_interaction, make_member, mock_anthropic, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        interaction1 = make_interaction(user_id=5001)
        interaction2 = make_interaction(user_id=5001)
        target = make_member()

        await bot.diss.callback(interaction1, user=target, intensity=None)
        await bot.diss.callback(interaction2, user=target, intensity=None)

        msg = interaction2.response.send_message.call_args[0][0]
        assert "s." in msg  # contains seconds

    @pytest.mark.asyncio
    async def test_cooldown_ephemeral(self, make_interaction, make_member, mock_anthropic, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        interaction1 = make_interaction(user_id=5001)
        interaction2 = make_interaction(user_id=5001)
        target = make_member()

        await bot.diss.callback(interaction1, user=target, intensity=None)
        await bot.diss.callback(interaction2, user=target, intensity=None)

        kwargs = interaction2.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_bypass_user_exempt(self, make_interaction, make_member, bypass_user, mock_anthropic, monkeypatch):
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))
        interaction1 = make_interaction(user_id=bypass_user)
        interaction2 = make_interaction(user_id=bypass_user)
        target = make_member()

        await bot.diss.callback(interaction1, user=target, intensity=None)
        await bot.diss.callback(interaction2, user=target, intensity=None)

        # Both should have deferred (no cooldown block)
        assert interaction1.response.defer.call_count == 1
        assert interaction2.response.defer.call_count == 1

    @pytest.mark.asyncio
    async def test_cooldown_expires(self, make_interaction, make_member, mock_anthropic, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        monkeypatch.setattr(espn, "fetch_tournament_results", AsyncMock(return_value=[]))

        fake_time = [1000.0]
        monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])

        interaction1 = make_interaction(user_id=5001)
        target = make_member()
        await bot.diss.callback(interaction1, user=target, intensity=None)

        # Advance past cooldown
        fake_time[0] = 1000.0 + 121
        interaction2 = make_interaction(user_id=5001)
        await bot.diss.callback(interaction2, user=target, intensity=None)

        # Second call should defer (not be blocked)
        interaction2.response.defer.assert_called_once()


# ---------------------------------------------------------------------------
# US-3: Submit a bracket via image upload
# ---------------------------------------------------------------------------


class TestSubmitBracketCommand:
    def _valid_picks(self):
        return {
            "round_of_32": ["A"] * 32,
            "sweet_16": ["A"] * 16,
            "elite_eight": ["A"] * 8,
            "final_four": ["A"] * 4,
            "championship_game": ["A", "B"],
            "champion": "A",
        }

    def _mock_submit_deps(self, monkeypatch, picks=None):
        if picks is None:
            picks = self._valid_picks()
        monkeypatch.setattr(bot, "parse_bracket_image", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Nice."))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=["A", "B"]))

    @pytest.mark.asyncio
    async def test_success_saves_to_db(self, make_interaction, bypass_user, monkeypatch):
        picks = self._valid_picks()
        self._mock_submit_deps(monkeypatch, picks)

        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/image.png"

        await bot.submit_bracket.callback(interaction, image=attachment)

        saved = db.get_bracket(bypass_user, 9001)
        assert saved is not None
        assert saved["champion"] == "A"

    @pytest.mark.asyncio
    async def test_posts_public_ack(self, make_interaction, bypass_user, monkeypatch):
        picks = self._valid_picks()
        monkeypatch.setattr(bot, "parse_bracket_image", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Nice bracket."))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=[]))

        interaction = make_interaction(user_id=bypass_user)
        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/image.png"

        await bot.submit_bracket.callback(interaction, image=attachment)

        # First followup is public ack
        first_call = interaction.followup.send.call_args_list[0]
        assert "Nice bracket." in first_call[0][0]

    @pytest.mark.asyncio
    async def test_posts_ephemeral_summary(self, make_interaction, bypass_user, monkeypatch):
        picks = self._valid_picks()
        monkeypatch.setattr(bot, "parse_bracket_image", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Nice."))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=[]))

        interaction = make_interaction(user_id=bypass_user)
        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/image.png"

        await bot.submit_bracket.callback(interaction, image=attachment)

        # Second followup is ephemeral summary
        second_call = interaction.followup.send.call_args_list[1]
        assert second_call.kwargs.get("ephemeral") is True
        assert "Champion" in second_call[0][0]

    @pytest.mark.asyncio
    async def test_parse_failure_shows_error(self, make_interaction, bypass_user, monkeypatch):
        monkeypatch.setattr(bot, "parse_bracket_image", AsyncMock(side_effect=ValueError("Bad image")))

        interaction = make_interaction(user_id=bypass_user)
        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/image.png"

        await bot.submit_bracket.callback(interaction, image=attachment)

        call = interaction.followup.send.call_args
        assert "Bad image" in call[0][0]
        assert call.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_normalization_failure_saves_raw(self, make_interaction, bypass_user, monkeypatch):
        picks = self._valid_picks()
        monkeypatch.setattr(bot, "parse_bracket_image", AsyncMock(return_value=picks))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=["X"]))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(side_effect=Exception("LLM error")))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Ok."))

        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/image.png"

        await bot.submit_bracket.callback(interaction, image=attachment)

        saved = db.get_bracket(bypass_user, 9001)
        assert saved is not None  # raw picks saved despite normalization failure


# ---------------------------------------------------------------------------
# US-4: Submission rate limit
# ---------------------------------------------------------------------------


class TestSubmitRateLimit:
    def _setup_mocks(self, monkeypatch):
        picks = {
            "round_of_32": ["A"] * 32,
            "sweet_16": ["A"] * 16,
            "elite_eight": ["A"] * 8,
            "final_four": ["A"] * 4,
            "championship_game": ["A", "B"],
            "champion": "A",
        }
        monkeypatch.setattr(bot, "parse_bracket_image", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Ok."))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=[]))

    @pytest.mark.asyncio
    async def test_blocks_after_3_submissions(self, make_interaction, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        self._setup_mocks(monkeypatch)

        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/image.png"

        for i in range(3):
            interaction = make_interaction(user_id=5001)
            await bot.submit_bracket.callback(interaction, image=attachment)

        # 4th attempt
        interaction = make_interaction(user_id=5001)
        await bot.submit_bracket.callback(interaction, image=attachment)

        msg = interaction.response.send_message.call_args[0][0]
        assert "submissions" in msg.lower() or "3" in msg

    @pytest.mark.asyncio
    async def test_bypass_user_no_limit(self, make_interaction, bypass_user, monkeypatch):
        self._setup_mocks(monkeypatch)

        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/image.png"

        for i in range(5):
            interaction = make_interaction(user_id=bypass_user)
            await bot.submit_bracket.callback(interaction, image=attachment)
            # All should defer (not be rate-limited)
            interaction.response.defer.assert_called_once()


# ---------------------------------------------------------------------------
# US-7: View help
# ---------------------------------------------------------------------------


class TestDissHelpCommand:
    @pytest.mark.asyncio
    async def test_ephemeral(self, make_interaction):
        interaction = make_interaction()
        await bot.disshelp.callback(interaction)
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_content_mentions_commands(self, make_interaction):
        interaction = make_interaction()
        await bot.disshelp.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "/diss" in msg
        assert "/submitbracket" in msg

    @pytest.mark.asyncio
    async def test_content_mentions_intensity(self, make_interaction):
        interaction = make_interaction()
        await bot.disshelp.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "mild" in msg
        assert "medium" in msg
        assert "harsh" in msg

    @pytest.mark.asyncio
    async def test_content_mentions_cooldown(self, make_interaction):
        interaction = make_interaction()
        await bot.disshelp.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "2-minute" in msg or "cooldown" in msg.lower()

    @pytest.mark.asyncio
    async def test_content_mentions_submission_limit(self, make_interaction):
        interaction = make_interaction()
        await bot.disshelp.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "3" in msg


# ---------------------------------------------------------------------------
# US-8: View about info
# ---------------------------------------------------------------------------


class TestAboutCommand:
    @pytest.mark.asyncio
    async def test_not_ephemeral(self, make_interaction):
        interaction = make_interaction()
        await bot.about.callback(interaction)
        kwargs = interaction.response.send_message.call_args.kwargs
        # about is public — no ephemeral=True
        assert kwargs.get("ephemeral") is not True

    @pytest.mark.asyncio
    async def test_content(self, make_interaction):
        interaction = make_interaction()
        await bot.about.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "Demery" in msg
        assert "/diss" in msg
        assert "/submitbracket" in msg
        assert "Daily Digest" in msg or "digest" in msg.lower()


# ---------------------------------------------------------------------------
# US-14: Test digest (preview)
# ---------------------------------------------------------------------------


class TestTestDigestCommand:
    @pytest.mark.asyncio
    async def test_bypass_only(self, make_interaction, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        interaction = make_interaction(user_id=5001)
        await bot.testdigest.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "Not for you" in msg

    @pytest.mark.asyncio
    async def test_no_results(self, make_interaction, bypass_user, monkeypatch, mock_anthropic):
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        db.set_guild_channel(9001, 5001)
        # No brackets on file
        await bot.testdigest.callback(interaction)
        msg = interaction.followup.send.call_args[0][0]
        assert "Nothing to post" in msg

    @pytest.mark.asyncio
    async def test_ephemeral_no_broadcast(
        self, make_interaction, bypass_user, sample_picks, monkeypatch, mock_anthropic
    ):
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(2001, 9001, "Alice", sample_picks)

        await bot.testdigest.callback(interaction)

        kwargs = interaction.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# US-15: Push digest (broadcast)
# ---------------------------------------------------------------------------


class TestPushDigestCommand:
    @pytest.mark.asyncio
    async def test_bypass_only(self, make_interaction, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        interaction = make_interaction(user_id=5001)
        await bot.pushdigest.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "Not for you" in msg

    @pytest.mark.asyncio
    async def test_broadcasts_to_channel(
        self, make_interaction, bypass_user, sample_picks, monkeypatch, mock_anthropic
    ):
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(2001, 9001, "Alice", sample_picks)

        mock_channel = AsyncMock()
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: mock_channel if cid == 5001 else None)

        await bot.pushdigest.callback(interaction)

        mock_channel.send.assert_called_once()


# ---------------------------------------------------------------------------
# US-16: Debug guild visibility
# ---------------------------------------------------------------------------


class TestDebugGuildCommand:
    @pytest.mark.asyncio
    async def test_bypass_only(self, make_interaction, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        interaction = make_interaction(user_id=5001)
        await bot.debugguild.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "Not for you" in msg

    @pytest.mark.asyncio
    async def test_shows_guild_info(self, make_interaction, bypass_user):
        interaction = make_interaction(user_id=bypass_user)
        guild = interaction.guild
        guild.name = "Test Guild"
        guild.id = 9001
        guild.me = MagicMock()
        guild.me.guild_permissions = MagicMock()
        guild.me.guild_permissions.value = 8
        guild.me.guild_permissions.view_channel = True
        guild.me.guild_permissions.send_messages = True
        role1 = MagicMock()
        role1.name = "@everyone"
        role2 = MagicMock()
        role2.name = "Bot"
        guild.me.roles = [role1, role2]

        ch = MagicMock()
        ch.name = "general"
        ch.id = 1234
        ch.permissions_for = MagicMock(return_value=MagicMock(view_channel=True, send_messages=True))
        guild.text_channels = [ch]

        await bot.debugguild.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "Test Guild" in msg
        assert "9001" in msg
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

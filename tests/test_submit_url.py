"""
Tests for /submitbracket-url command in bot.py — covers:
  US-13: Submit a bracket via URL
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import bot
import db
import espn


class TestSubmitBracketUrlCommand:
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
        monkeypatch.setattr(bot, "fetch_html", AsyncMock(return_value="<html>bracket</html>"))
        monkeypatch.setattr(bot, "preprocess_html", MagicMock(return_value="bracket content"))
        monkeypatch.setattr(bot, "parse_bracket_html", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Nice."))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=["A", "B"]))

    @pytest.mark.asyncio
    async def test_non_bypass_blocked(self, make_interaction, monkeypatch):
        monkeypatch.setattr(bot, "BYPASS_USER_IDS", set())
        interaction = make_interaction(user_id=5001)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")
        msg = interaction.response.send_message.call_args[0][0]
        assert "Not for you" in msg

    @pytest.mark.asyncio
    async def test_defers_interaction(self, make_interaction, bypass_user, monkeypatch):
        self._mock_submit_deps(monkeypatch)
        interaction = make_interaction(user_id=bypass_user)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")
        interaction.response.defer.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_saves_to_db(self, make_interaction, bypass_user, monkeypatch):
        picks = self._valid_picks()
        self._mock_submit_deps(monkeypatch, picks)

        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")

        saved = db.get_bracket(bypass_user, 9001)
        assert saved is not None
        assert saved["champion"] == "A"

    @pytest.mark.asyncio
    async def test_posts_public_ack(self, make_interaction, bypass_user, monkeypatch):
        self._mock_submit_deps(monkeypatch)
        interaction = make_interaction(user_id=bypass_user)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")

        first_call = interaction.followup.send.call_args_list[0]
        assert "Nice." in first_call[0][0]

    @pytest.mark.asyncio
    async def test_posts_ephemeral_summary(self, make_interaction, bypass_user, monkeypatch):
        self._mock_submit_deps(monkeypatch)
        interaction = make_interaction(user_id=bypass_user)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")

        second_call = interaction.followup.send.call_args_list[1]
        assert second_call.kwargs.get("ephemeral") is True
        assert "Champion" in second_call[0][0]

    @pytest.mark.asyncio
    async def test_fetch_failure_shows_error(self, make_interaction, bypass_user, monkeypatch):
        monkeypatch.setattr(bot, "fetch_html", AsyncMock(side_effect=ValueError("Connection refused")))

        interaction = make_interaction(user_id=bypass_user)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")

        call = interaction.followup.send.call_args
        assert "Connection refused" in call[0][0]
        assert call.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_parse_failure_shows_error(self, make_interaction, bypass_user, monkeypatch):
        monkeypatch.setattr(bot, "fetch_html", AsyncMock(return_value="<html>stuff</html>"))
        monkeypatch.setattr(bot, "preprocess_html", MagicMock(return_value="stuff"))
        monkeypatch.setattr(bot, "parse_bracket_html", AsyncMock(side_effect=ValueError("No bracket found")))

        interaction = make_interaction(user_id=bypass_user)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")

        call = interaction.followup.send.call_args
        assert "No bracket found" in call[0][0]
        assert call.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_normalization_failure_saves_raw(self, make_interaction, bypass_user, monkeypatch):
        picks = self._valid_picks()
        monkeypatch.setattr(bot, "fetch_html", AsyncMock(return_value="<html>bracket</html>"))
        monkeypatch.setattr(bot, "preprocess_html", MagicMock(return_value="bracket content"))
        monkeypatch.setattr(bot, "parse_bracket_html", AsyncMock(return_value=picks))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=["X"]))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(side_effect=Exception("LLM error")))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Ok."))

        interaction = make_interaction(user_id=bypass_user, guild_id=9001)
        await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")

        saved = db.get_bracket(bypass_user, 9001)
        assert saved is not None  # raw picks saved despite normalization failure


class TestSubmitUrlBypassOnly:
    """Since /submitbracket-url is DEV-gated, only bypass users can access it.
    Rate limiting is not applicable (bypass users are exempt from rate limits)."""

    def _setup_url_mocks(self, monkeypatch):
        picks = {
            "round_of_32": ["A"] * 32,
            "sweet_16": ["A"] * 16,
            "elite_eight": ["A"] * 8,
            "final_four": ["A"] * 4,
            "championship_game": ["A", "B"],
            "champion": "A",
        }
        monkeypatch.setattr(bot, "fetch_html", AsyncMock(return_value="<html>bracket</html>"))
        monkeypatch.setattr(bot, "preprocess_html", MagicMock(return_value="content"))
        monkeypatch.setattr(bot, "parse_bracket_html", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "normalize_team_names", AsyncMock(return_value=picks))
        monkeypatch.setattr(bot, "generate_submission_ack", AsyncMock(return_value="Ok."))
        monkeypatch.setattr(espn, "fetch_tournament_team_names", AsyncMock(return_value=[]))

    @pytest.mark.asyncio
    async def test_bypass_user_can_submit_unlimited(self, make_interaction, bypass_user, monkeypatch):
        self._setup_url_mocks(monkeypatch)

        for _ in range(5):
            interaction = make_interaction(user_id=bypass_user)
            await bot.submit_bracket_url.callback(interaction, url="https://example.com/bracket")
            interaction.response.defer.assert_called_once()

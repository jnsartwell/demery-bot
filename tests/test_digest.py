"""
Tests for _run_digest in bot.py — covers:
  US-9:  Daily digest — automatic bracket recap
  DS-13: Eastern time for game dates
"""

import datetime
from unittest.mock import AsyncMock, patch

import pytest

import bot
import db
import espn

# ---------------------------------------------------------------------------
# US-9: Daily digest
# ---------------------------------------------------------------------------


class TestRunDigest:
    @pytest.mark.asyncio
    async def test_fetches_espn_and_calls_llm(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)

        games = [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=games))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        result = await bot._run_digest(broadcast=False, guild_id=9001)
        assert result is not None

    @pytest.mark.asyncio
    async def test_broadcasts_to_channel(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))

        mock_channel = AsyncMock()
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: mock_channel if cid == 5001 else None)

        await bot._run_digest(broadcast=True, guild_id=9001)
        mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_guild_without_channel(self, monkeypatch, mock_anthropic):
        """Guild with no set_guild_channel is skipped."""
        result = await bot._run_digest(broadcast=False)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_guild_without_brackets(self, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        result = await bot._run_digest(broadcast=False, guild_id=9001)
        # No brackets → generate_digest not called → no message
        assert result is None

    @pytest.mark.asyncio
    async def test_all_submitters_included(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        db.upsert_bracket(2001, 9001, "Bob", sample_picks)
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="digest msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            names = {s["name"] for s in submitters}
            assert "Alice" in names
            assert "Bob" in names

    @pytest.mark.asyncio
    async def test_bust_context_passed(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        games = [{"winner": "Saint Peter's Peacocks", "loser": "Kentucky Wildcats", "round": "1st Round"}]
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=games))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            alice = submitters[0]
            assert len(alice["busts"]) > 0
            bust = alice["busts"][0]
            assert "picked_to_reach" in bust
            assert "lost_in" in bust

    @pytest.mark.asyncio
    async def test_survivor_context_passed(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        games = [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=games))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            alice = submitters[0]
            assert len(alice["survivors"]) > 0
            surv = alice["survivors"][0]
            assert "still_alive_through" in surv

    @pytest.mark.asyncio
    async def test_no_games_empty_busts_survivors(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            assert submitters[0]["busts"] == []
            assert submitters[0]["survivors"] == []

    @pytest.mark.asyncio
    async def test_single_guild_filter(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.set_guild_channel(9002, 5002)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        db.upsert_bracket(2001, 9002, "Bob", sample_picks)
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            names = {s["name"] for s in submitters}
            assert "Alice" in names
            assert "Bob" not in names

    @pytest.mark.asyncio
    async def test_mentions_use_discord_tags(self, sample_picks, monkeypatch, mock_anthropic):
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=[]))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            assert submitters[0]["mention"] == "<@1001>"


# ---------------------------------------------------------------------------
# DS-13: Eastern time for game dates
# ---------------------------------------------------------------------------


class TestEasternTime:
    @pytest.mark.asyncio
    async def test_digest_uses_eastern_date(self, sample_picks, monkeypatch, mock_anthropic):
        """At 11pm ET (which is next day in UTC), digest should use Eastern date."""
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)

        # 11pm ET on March 19 = 3am UTC on March 20
        et_time = datetime.datetime(2026, 3, 19, 23, 0, 0, tzinfo=bot.EASTERN)

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return et_time

        monkeypatch.setattr(bot.datetime, "datetime", MockDatetime)

        fetched_dates = []

        async def capture_fetch(date_str):
            fetched_dates.append(date_str)
            return []

        monkeypatch.setattr(espn, "fetch_today_results", capture_fetch)
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        await bot._run_digest(broadcast=False, guild_id=9001)

        # Should fetch March 19 (Eastern), not March 20 (UTC)
        assert "20260319" in fetched_dates
        assert "20260320" not in fetched_dates

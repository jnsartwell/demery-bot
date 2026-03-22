"""
Tests for _run_digest in bot.py — covers:
  US-9:  Daily digest — automatic bracket recap
  US-12: Skip digest on non-game days
  DS-10: Eastern time for game dates
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
            assert "pick" in bust
            assert "lost" in bust

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
            assert "thru" in surv

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
# US-9: Cumulative tournament results in digest
# ---------------------------------------------------------------------------


class TestCumulativeDigest:
    @pytest.mark.asyncio
    async def test_digest_uses_cumulative_results(self, sample_picks, monkeypatch, mock_anthropic):
        """Busts from previous days appear in cumulative status, not just today's."""
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)

        # Yesterday: Kentucky busted (pre-populated in DB)
        db.save_game_results(
            "20260319", [{"winner": "Saint Peter's Peacocks", "loser": "Kentucky Wildcats", "round": "1st Round"}]
        )

        # Today: Gonzaga busted
        today_games = [{"winner": "Some Team", "loser": "Gonzaga Bulldogs", "round": "2nd Round"}]
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=today_games))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            alice = submitters[0]

            # Cumulative busts include BOTH yesterday's and today's
            bust_teams = {b["team"] for b in alice["busts"]}
            assert "Kentucky Wildcats" in bust_teams
            assert "Gonzaga Bulldogs" in bust_teams

    @pytest.mark.asyncio
    async def test_digest_distinguishes_today_from_cumulative(self, sample_picks, monkeypatch, mock_anthropic):
        """today_busts contains only today's new busts, not historical ones."""
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)

        # Yesterday's bust already in DB
        db.save_game_results(
            "20260319", [{"winner": "Saint Peter's Peacocks", "loser": "Kentucky Wildcats", "round": "1st Round"}]
        )

        # Today: Gonzaga busts
        today_games = [{"winner": "Some Team", "loser": "Gonzaga Bulldogs", "round": "2nd Round"}]
        monkeypatch.setattr(espn, "fetch_today_results", AsyncMock(return_value=today_games))
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        with patch.object(bot, "generate_digest", new_callable=AsyncMock, return_value="msg") as mock_gen:
            await bot._run_digest(broadcast=False, guild_id=9001)
            submitters = mock_gen.call_args[0][0]
            alice = submitters[0]

            # Today's busts: only Gonzaga
            today_bust_teams = {b["team"] for b in alice["today_busts"]}
            assert "Gonzaga Bulldogs" in today_bust_teams
            assert "Kentucky Wildcats" not in today_bust_teams

    @pytest.mark.asyncio
    async def test_digest_persists_today_results(self, sample_picks, monkeypatch, mock_anthropic):
        """After running digest, today's games are saved to game_results table."""
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)

        # Fix date to March 19 so backfill only covers March 17-18
        et_time = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=bot.EASTERN)

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return et_time

        monkeypatch.setattr(bot.datetime, "datetime", MockDatetime)

        today_games = [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]

        async def mock_fetch(date_str):
            if date_str == "20260319":
                return today_games
            return []

        monkeypatch.setattr(espn, "fetch_today_results", mock_fetch)
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        await bot._run_digest(broadcast=False, guild_id=9001)

        # Verify today's games were persisted
        results = db.get_all_game_results()
        today_results = [r for r in results if r["game_date"] == "20260319"]
        assert len(today_results) == 1
        assert today_results[0]["winner"] == "Duke Blue Devils"

    @pytest.mark.asyncio
    async def test_digest_backfills_missing_dates(self, sample_picks, monkeypatch, mock_anthropic):
        """On first run with empty DB, digest backfills historical dates from ESPN."""
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)

        # Mock: today is March 19, tournament started March 17
        et_time = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=bot.EASTERN)

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return et_time

        monkeypatch.setattr(bot.datetime, "datetime", MockDatetime)

        fetched_dates = []

        async def capture_fetch(date_str):
            fetched_dates.append(date_str)
            if date_str == "20260317":
                return [{"winner": "A", "loser": "B", "round": "First Four"}]
            if date_str == "20260318":
                return [{"winner": "C", "loser": "D", "round": "First Four"}]
            if date_str == "20260319":
                return [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]
            return []

        monkeypatch.setattr(espn, "fetch_today_results", capture_fetch)
        monkeypatch.setattr(bot.client, "get_channel", lambda cid: AsyncMock())

        await bot._run_digest(broadcast=False, guild_id=9001)

        # Should have fetched today + backfilled March 17 and 18
        assert "20260319" in fetched_dates
        assert "20260317" in fetched_dates
        assert "20260318" in fetched_dates

        # All dates should be persisted
        stored_dates = db.get_game_result_dates()
        assert "20260317" in stored_dates
        assert "20260318" in stored_dates
        assert "20260319" in stored_dates

    @pytest.mark.asyncio
    async def test_digest_skips_backfill_when_history_exists(self, sample_picks, monkeypatch, mock_anthropic):
        """If historical dates already exist in DB, backfill does not re-fetch them."""
        db.set_guild_channel(9001, 5001)
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)

        # Pre-populate historical dates
        db.save_game_results("20260317", [{"winner": "A", "loser": "B", "round": "First Four"}])
        db.save_game_results("20260318", [{"winner": "C", "loser": "D", "round": "First Four"}])

        et_time = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=bot.EASTERN)

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

        # Only today should be fetched, not the backfill dates
        assert "20260319" in fetched_dates
        assert "20260317" not in fetched_dates
        assert "20260318" not in fetched_dates


# ---------------------------------------------------------------------------
# DS-10: Eastern time for game dates
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


# ---------------------------------------------------------------------------
# US-12: Skip digest on non-game days
# ---------------------------------------------------------------------------


class TestSkipNonGameDays:
    """Tests for daily_digest_task() skipping on non-tournament days.

    The skip logic lives in daily_digest_task (not _run_digest), so
    /testdigest and /pushdigest inherently bypass it.
    """

    @pytest.mark.asyncio
    async def test_daily_task_skips_on_non_game_day(self, monkeypatch):
        """Digest should not run when yesterday has no tournament games."""
        # March 24 8am ET — yesterday is March 23, a gap day (no tournament games)
        et_time = datetime.datetime(2026, 3, 24, 8, 0, 0, tzinfo=bot.EASTERN)

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return et_time

        monkeypatch.setattr(bot.datetime, "datetime", MockDatetime)

        with patch.object(bot, "_run_digest", new_callable=AsyncMock) as mock_digest:
            await bot.daily_digest_task()
            mock_digest.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_task_runs_on_game_day(self, monkeypatch):
        """Digest should run when yesterday is a tournament game day."""
        # March 20 8am ET — yesterday is March 19, Round of 64
        et_time = datetime.datetime(2026, 3, 20, 8, 0, 0, tzinfo=bot.EASTERN)

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return et_time

        monkeypatch.setattr(bot.datetime, "datetime", MockDatetime)

        with patch.object(bot, "_run_digest", new_callable=AsyncMock) as mock_digest:
            await bot.daily_digest_task()
            mock_digest.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_task_uses_eastern_for_yesterday(self, monkeypatch):
        """Yesterday should be computed in Eastern time, not UTC.

        At 9pm ET on March 23 (= 1am UTC March 24), yesterday in Eastern
        is March 22 (Round of 32 — a game day), not March 23 (a gap day).
        The digest should run.
        """
        et_time = datetime.datetime(2026, 3, 23, 21, 0, 0, tzinfo=bot.EASTERN)

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return et_time

        monkeypatch.setattr(bot.datetime, "datetime", MockDatetime)

        with patch.object(bot, "_run_digest", new_callable=AsyncMock) as mock_digest:
            await bot.daily_digest_task()
            mock_digest.assert_called_once()

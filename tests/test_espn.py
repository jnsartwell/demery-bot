"""
Tests for espn.py — covers:
  DS-1: ESPN scoreboard result caching
  DS-2: ESPN tournament team name caching
"""

import datetime
import re

import pytest
from aioresponses import aioresponses

import espn

ESPN_URL_PATTERN = re.compile(r".*scoreboard.*")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _espn_event(winner_name, loser_name, round_name="1st Round", completed=True, winner_score=75, loser_score=60):
    """Build a minimal ESPN event dict."""
    return {
        "name": f"{winner_name} vs {loser_name}",
        "status": {"type": {"completed": completed, "name": "STATUS_FINAL" if completed else "STATUS_IN_PROGRESS"}},
        "competitions": [
            {
                "competitors": [
                    {"winner": True, "team": {"displayName": winner_name}, "score": str(winner_score)},
                    {"winner": False, "team": {"displayName": loser_name}, "score": str(loser_score)},
                ],
                "notes": [{"headline": f"NCAA Men's Basketball Championship - East Region - {round_name}"}],
                "type": {"text": "tournament"},
            }
        ],
    }


def _espn_event_incomplete(name="Game"):
    return {
        "name": name,
        "status": {"type": {"completed": False, "name": "STATUS_IN_PROGRESS"}},
        "competitions": [
            {
                "competitors": [
                    {"winner": False, "team": {"displayName": "Team A"}},
                    {"winner": False, "team": {"displayName": "Team B"}},
                ],
                "notes": [],
                "type": {"text": "tournament"},
            }
        ],
    }


# ---------------------------------------------------------------------------
# fetch_today_results
# ---------------------------------------------------------------------------


class TestFetchTodayResults:
    @pytest.mark.asyncio
    async def test_returns_completed_games(self):
        with aioresponses() as m:
            m.get(
                ESPN_URL_PATTERN,
                payload={
                    "events": [
                        _espn_event("Duke Blue Devils", "Vermont Catamounts"),
                    ]
                },
            )
            results = await espn.fetch_today_results("20260319")
        assert len(results) == 1
        assert results[0]["winner"] == "Duke Blue Devils"
        assert results[0]["loser"] == "Vermont Catamounts"
        assert results[0]["round"] == "1st Round"

    @pytest.mark.asyncio
    async def test_returns_scores(self):
        with aioresponses() as m:
            m.get(
                ESPN_URL_PATTERN,
                payload={
                    "events": [
                        _espn_event("Duke Blue Devils", "Vermont Catamounts", winner_score=82, loser_score=55),
                    ]
                },
            )
            results = await espn.fetch_today_results("20260319")
        assert results[0]["winner_score"] == 82
        assert results[0]["loser_score"] == 55

    @pytest.mark.asyncio
    async def test_skips_incomplete_games(self):
        with aioresponses() as m:
            m.get(
                ESPN_URL_PATTERN,
                payload={
                    "events": [
                        _espn_event("Duke Blue Devils", "Vermont Catamounts"),
                        _espn_event_incomplete(),
                    ]
                },
            )
            results = await espn.fetch_today_results("20260319")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_round_from_headline(self):
        with aioresponses() as m:
            m.get(
                ESPN_URL_PATTERN,
                payload={
                    "events": [
                        _espn_event("Duke Blue Devils", "Vermont Catamounts", "Sweet 16"),
                    ]
                },
            )
            results = await espn.fetch_today_results("20260319")
        assert results[0]["round"] == "Sweet 16"

    @pytest.mark.asyncio
    async def test_round_fallback_to_type_text(self):
        """When notes headline has no ' - ', fall back to competition type text."""
        event = _espn_event("Duke Blue Devils", "Vermont Catamounts")
        event["competitions"][0]["notes"] = []
        with aioresponses() as m:
            m.get(ESPN_URL_PATTERN, payload={"events": [event]})
            results = await espn.fetch_today_results("20260319")
        assert results[0]["round"] == "tournament"

    @pytest.mark.asyncio
    async def test_empty_events(self):
        with aioresponses() as m:
            m.get(ESPN_URL_PATTERN, payload={"events": []})
            results = await espn.fetch_today_results("20260319")
        assert results == []


# ---------------------------------------------------------------------------
# DS-1: fetch_tournament_results caching
# ---------------------------------------------------------------------------


def _make_mock_date(frozen_today):
    """Create a datetime.date subclass with a frozen today()."""

    class MockDate(datetime.date):
        @classmethod
        def today(cls):
            return frozen_today

    return MockDate


class TestFetchTournamentResults:
    @pytest.mark.asyncio
    async def test_caches_past_dates(self, monkeypatch):
        """Past dates are fetched once; second call uses cache."""
        monkeypatch.setattr(espn.datetime, "date", _make_mock_date(datetime.date(2026, 3, 19)))

        call_count = 0

        async def counting_fetch(date_str):
            nonlocal call_count
            call_count += 1
            return [{"winner": "A", "loser": "B", "round": "1st Round"}]

        monkeypatch.setattr(espn, "fetch_today_results", counting_fetch)

        # First call: fetches all 3 dates (17, 18, 19)
        await espn.fetch_tournament_results()
        assert call_count == 3

        # Second call: only today (19) re-fetched
        call_count = 0
        await espn.fetch_tournament_results()
        assert call_count == 1  # only today

    @pytest.mark.asyncio
    async def test_always_refetches_today(self, monkeypatch):
        """Today's date is always re-fetched even if cached."""
        monkeypatch.setattr(espn.datetime, "date", _make_mock_date(datetime.date(2026, 3, 17)))

        fetch_dates = []

        async def tracking_fetch(date_str):
            fetch_dates.append(date_str)
            return []

        monkeypatch.setattr(espn, "fetch_today_results", tracking_fetch)

        await espn.fetch_tournament_results()
        await espn.fetch_tournament_results()

        # March 17 (today) should appear twice
        assert fetch_dates.count("20260317") == 2

    @pytest.mark.asyncio
    async def test_accumulates_all_dates(self, monkeypatch):
        """Results from all dates are combined."""
        monkeypatch.setattr(espn.datetime, "date", _make_mock_date(datetime.date(2026, 3, 19)))

        async def one_game_per_date(date_str):
            return [{"winner": f"W-{date_str}", "loser": f"L-{date_str}", "round": "1st Round"}]

        monkeypatch.setattr(espn, "fetch_today_results", one_game_per_date)

        results = await espn.fetch_tournament_results()
        assert len(results) == 3  # 17, 18, 19


# ---------------------------------------------------------------------------
# DS-2: ESPN tournament team name caching
# ---------------------------------------------------------------------------


class TestFetchTournamentTeamNames:
    @pytest.mark.asyncio
    async def test_fetches_and_caches(self):
        event = {
            "competitions": [
                {
                    "competitors": [
                        {"team": {"displayName": "Duke Blue Devils"}},
                        {"team": {"displayName": "Vermont Catamounts"}},
                    ],
                }
            ],
        }
        with aioresponses() as m:
            # Two first-round dates — use repeat so both requests match
            m.get(ESPN_URL_PATTERN, payload={"events": [event]}, repeat=True)
            names = await espn.fetch_tournament_team_names()

        assert "Duke Blue Devils" in names
        assert "Vermont Catamounts" in names

    @pytest.mark.asyncio
    async def test_second_call_uses_cache(self, monkeypatch):
        # Pre-populate cache
        monkeypatch.setattr(espn, "_cached_team_names", ["Duke Blue Devils", "Kansas Jayhawks"])
        names = await espn.fetch_tournament_team_names()
        assert names == ["Duke Blue Devils", "Kansas Jayhawks"]
        # No HTTP calls needed — would fail if aiohttp tried to connect

    @pytest.mark.asyncio
    async def test_deduplicates_names(self):
        event = {
            "competitions": [
                {
                    "competitors": [
                        {"team": {"displayName": "Duke Blue Devils"}},
                        {"team": {"displayName": "Duke Blue Devils"}},
                    ],
                }
            ],
        }
        with aioresponses() as m:
            m.get(ESPN_URL_PATTERN, payload={"events": [event]}, repeat=True)
            names = await espn.fetch_tournament_team_names()
        assert names.count("Duke Blue Devils") == 1

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        """If one date fails, the other still works."""
        event = {
            "competitions": [
                {
                    "competitors": [
                        {"team": {"displayName": "Duke Blue Devils"}},
                        {"team": {"displayName": "Vermont Catamounts"}},
                    ],
                }
            ],
        }
        with aioresponses() as m:
            m.get(ESPN_URL_PATTERN, exception=Exception("API down"))
            m.get(ESPN_URL_PATTERN, payload={"events": [event]})
            names = await espn.fetch_tournament_team_names()
        assert "Duke Blue Devils" in names

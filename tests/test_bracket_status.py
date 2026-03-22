"""
Tests for _compute_bracket_status and _compute_shared_busts — covers:
  DS-8: Round-to-tier mapping
  DS-9: Bust and survivor computation
  US-17: Cross-bracket shared busts
"""

from bot import _compute_bracket_status, _compute_shared_busts
from constants import ROUND_NAME_TO_TIER, ROUND_TIER_ORDER

# ---------------------------------------------------------------------------
# DS-8: Round-to-tier mapping
# ---------------------------------------------------------------------------


class TestRoundNameToTier:
    def test_primary_mappings(self):
        assert ROUND_NAME_TO_TIER["1st Round"] == "round_of_32"
        assert ROUND_NAME_TO_TIER["2nd Round"] == "sweet_16"
        assert ROUND_NAME_TO_TIER["Sweet 16"] == "elite_eight"
        assert ROUND_NAME_TO_TIER["Elite 8"] == "final_four"
        assert ROUND_NAME_TO_TIER["Final Four"] == "championship_game"
        assert ROUND_NAME_TO_TIER["National Championship"] == "champion"

    def test_alternate_mappings(self):
        assert ROUND_NAME_TO_TIER["First Round"] == "round_of_32"
        assert ROUND_NAME_TO_TIER["Second Round"] == "sweet_16"
        assert ROUND_NAME_TO_TIER["Elite Eight"] == "final_four"
        assert ROUND_NAME_TO_TIER["Championship"] == "champion"

    def test_unknown_round_returns_none(self):
        assert ROUND_NAME_TO_TIER.get("First Four") is None
        assert ROUND_NAME_TO_TIER.get("Play-In") is None
        assert ROUND_NAME_TO_TIER.get("") is None

    def test_tier_order_complete(self):
        assert ROUND_TIER_ORDER == [
            "round_of_32",
            "sweet_16",
            "elite_eight",
            "final_four",
            "championship_game",
            "champion",
        ]


# ---------------------------------------------------------------------------
# DS-9: Bust and survivor computation
# ---------------------------------------------------------------------------


class TestComputeBracketStatus:
    def _picks(self, **overrides):
        """Minimal picks dict with overrides."""
        base = {
            "round_of_32": [],
            "sweet_16": [],
            "elite_eight": [],
            "final_four": [],
            "championship_game": [],
            "champion": "",
        }
        base.update(overrides)
        return base

    def test_bust_basic(self):
        picks = self._picks(round_of_32=["Kentucky Wildcats"])
        games = [{"winner": "Saint Peter's Peacocks", "loser": "Kentucky Wildcats", "round": "1st Round"}]
        result = _compute_bracket_status(picks, games)
        assert len(result["busts"]) == 1
        assert result["busts"][0]["team"] == "Kentucky Wildcats"

    def test_bust_furthest_round(self):
        """Bust should report the latest tier the team was picked in."""
        picks = self._picks(
            round_of_32=["Kentucky Wildcats"],
            sweet_16=["Kentucky Wildcats"],
            elite_eight=["Kentucky Wildcats"],
        )
        games = [{"winner": "Saint Peter's Peacocks", "loser": "Kentucky Wildcats", "round": "1st Round"}]
        result = _compute_bracket_status(picks, games)
        assert result["busts"][0]["pick"] == "elite_eight"

    def test_bust_lost_in_round(self):
        picks = self._picks(round_of_32=["Kentucky Wildcats"])
        games = [{"winner": "Saint Peter's Peacocks", "loser": "Kentucky Wildcats", "round": "1st Round"}]
        result = _compute_bracket_status(picks, games)
        assert result["busts"][0]["lost"] == "1st Round"

    def test_survivor_basic(self):
        picks = self._picks(round_of_32=["Duke Blue Devils"])
        games = [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]
        result = _compute_bracket_status(picks, games)
        assert len(result["survivors"]) == 1
        assert result["survivors"][0]["team"] == "Duke Blue Devils"

    def test_survivor_still_alive_through(self):
        picks = self._picks(sweet_16=["Duke Blue Devils"])
        games = [{"winner": "Duke Blue Devils", "loser": "Someone", "round": "2nd Round"}]
        result = _compute_bracket_status(picks, games)
        assert result["survivors"][0]["thru"] == "2nd Round"

    def test_team_not_in_picks_ignored(self):
        picks = self._picks(round_of_32=["Duke Blue Devils"])
        games = [{"winner": "Gonzaga Bulldogs", "loser": "Memphis Tigers", "round": "1st Round"}]
        result = _compute_bracket_status(picks, games)
        assert result["busts"] == []
        assert result["survivors"] == []

    def test_multiple_games_multiple_busts(self):
        picks = self._picks(
            round_of_32=["Kentucky Wildcats", "Baylor Bears"],
            sweet_16=["Kentucky Wildcats", "Baylor Bears"],
        )
        games = [
            {"winner": "A", "loser": "Kentucky Wildcats", "round": "1st Round"},
            {"winner": "B", "loser": "Baylor Bears", "round": "1st Round"},
        ]
        result = _compute_bracket_status(picks, games)
        assert len(result["busts"]) == 2

    def test_champion_pick_bust(self):
        """Champion pick that loses should show picked_to_reach='champion'."""
        picks = self._picks(
            round_of_32=["Duke Blue Devils"],
            sweet_16=["Duke Blue Devils"],
            elite_eight=["Duke Blue Devils"],
            final_four=["Duke Blue Devils"],
            championship_game=["Duke Blue Devils"],
            champion="Duke Blue Devils",
        )
        games = [{"winner": "Underdog U", "loser": "Duke Blue Devils", "round": "1st Round"}]
        result = _compute_bracket_status(picks, games)
        assert result["busts"][0]["pick"] == "champion"

    def test_play_in_round_skipped(self):
        picks = self._picks(round_of_32=["Duke Blue Devils"])
        games = [{"winner": "Duke Blue Devils", "loser": "Someone", "round": "First Four"}]
        result = _compute_bracket_status(picks, games)
        assert result["busts"] == []
        assert result["survivors"] == []

    def test_bust_and_survivor_same_game(self):
        """A game can produce both a bust (loser picked) and survivor (winner picked)."""
        picks = self._picks(
            round_of_32=["Duke Blue Devils", "Kentucky Wildcats"],
        )
        games = [{"winner": "Duke Blue Devils", "loser": "Kentucky Wildcats", "round": "1st Round"}]
        result = _compute_bracket_status(picks, games)
        assert len(result["busts"]) == 1
        assert len(result["survivors"]) == 1
        assert result["busts"][0]["team"] == "Kentucky Wildcats"
        assert result["survivors"][0]["team"] == "Duke Blue Devils"

    def test_empty_games_no_results(self):
        picks = self._picks(round_of_32=["Duke Blue Devils"])
        result = _compute_bracket_status(picks, [])
        assert result == {"busts": [], "survivors": []}

    def test_later_round_bust(self):
        """A team picked for Sweet 16 that loses in the 2nd Round is a bust."""
        picks = self._picks(
            sweet_16=["Duke Blue Devils"],
            elite_eight=["Duke Blue Devils"],
        )
        games = [{"winner": "Upset U", "loser": "Duke Blue Devils", "round": "2nd Round"}]
        result = _compute_bracket_status(picks, games)
        assert len(result["busts"]) == 1
        assert result["busts"][0]["pick"] == "elite_eight"
        assert result["busts"][0]["lost"] == "2nd Round"


# ---------------------------------------------------------------------------
# US-17: _compute_shared_busts
# ---------------------------------------------------------------------------


class TestComputeSharedBusts:
    def test_shared_bust_found(self):
        submitters = [
            {"mention": "<@1>", "busts": [{"team": "Kentucky Wildcats", "pick": "sweet_16", "lost": "1st Round"}]},
            {"mention": "<@2>", "busts": [{"team": "Kentucky Wildcats", "pick": "elite_eight", "lost": "1st Round"}]},
        ]
        shared = _compute_shared_busts(submitters)
        assert len(shared) == 1
        assert shared[0]["team"] == "Kentucky Wildcats"
        assert "<@1>" in shared[0]["mentions"]
        assert "<@2>" in shared[0]["mentions"]

    def test_no_shared_busts(self):
        submitters = [
            {"mention": "<@1>", "busts": [{"team": "Duke Blue Devils", "pick": "sweet_16", "lost": "1st Round"}]},
            {"mention": "<@2>", "busts": [{"team": "Kentucky Wildcats", "pick": "elite_eight", "lost": "1st Round"}]},
        ]
        shared = _compute_shared_busts(submitters)
        assert shared == []

    def test_empty_busts(self):
        submitters = [
            {"mention": "<@1>", "busts": []},
            {"mention": "<@2>", "busts": []},
        ]
        shared = _compute_shared_busts(submitters)
        assert shared == []

    def test_single_submitter_no_shared(self):
        submitters = [
            {"mention": "<@1>", "busts": [{"team": "Duke Blue Devils", "pick": "champion", "lost": "1st Round"}]},
        ]
        shared = _compute_shared_busts(submitters)
        assert shared == []

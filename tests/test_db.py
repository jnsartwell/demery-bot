"""
Tests for db.py — covers:
  US-5:  Re-submit a bracket (upsert)
  US-6:  Brackets are per-guild
  DS-10: Database migrations
"""

import sqlite3

import db

# ---------------------------------------------------------------------------
# DS-10: Database migrations
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_creates_brackets_table(self, tmp_db):
        with sqlite3.connect(tmp_db) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "brackets" in tables

    def test_creates_guild_settings_table(self, tmp_db):
        with sqlite3.connect(tmp_db) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "guild_settings" in tables

    def test_creates_schema_migrations_table(self, tmp_db):
        with sqlite3.connect(tmp_db) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "schema_migrations" in tables

    def test_migration_recorded(self, tmp_db):
        with sqlite3.connect(tmp_db) as con:
            rows = con.execute("SELECT filename FROM schema_migrations").fetchall()
        filenames = [r[0] for r in rows]
        assert "20260319_001_add_guild_id_to_brackets.sql" in filenames

    def test_migration_runs_once(self, tmp_db):
        """Calling init_db a second time does not re-run migrations."""
        db.init_db()  # second call
        with sqlite3.connect(tmp_db) as con:
            rows = con.execute("SELECT filename FROM schema_migrations").fetchall()
        # Should still have exactly one entry for each migration
        filenames = [r[0] for r in rows]
        assert filenames.count("20260319_001_add_guild_id_to_brackets.sql") == 1


# ---------------------------------------------------------------------------
# US-5: Re-submit a bracket (upsert)
# ---------------------------------------------------------------------------


class TestUpsertBracket:
    def test_insert_and_retrieve(self, tmp_db, sample_picks):
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        result = db.get_bracket(1001, 9001)
        assert result is not None
        assert result["champion"] == "Duke Blue Devils"

    def test_upsert_replaces_picks(self, tmp_db, sample_picks):
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        new_picks = {**sample_picks, "champion": "Kansas Jayhawks"}
        db.upsert_bracket(1001, 9001, "Alice", new_picks)
        result = db.get_bracket(1001, 9001)
        assert result["champion"] == "Kansas Jayhawks"

    def test_upsert_updates_display_name(self, tmp_db, sample_picks):
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        db.upsert_bracket(1001, 9001, "Alice_New", sample_picks)
        rows = db.get_guild_brackets(9001)
        assert len(rows) == 1
        assert rows[0]["display_name"] == "Alice_New"

    def test_upsert_updates_timestamp(self, tmp_db, sample_picks):
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        with sqlite3.connect(tmp_db) as con:
            ts1 = con.execute(
                "SELECT submitted_at FROM brackets WHERE discord_user_id=1001 AND guild_id=9001"
            ).fetchone()[0]
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        with sqlite3.connect(tmp_db) as con:
            ts2 = con.execute(
                "SELECT submitted_at FROM brackets WHERE discord_user_id=1001 AND guild_id=9001"
            ).fetchone()[0]
        assert ts2 >= ts1


# ---------------------------------------------------------------------------
# US-6: Brackets are per-guild
# ---------------------------------------------------------------------------


class TestPerGuildBrackets:
    def test_same_user_different_guilds(self, tmp_db, sample_picks):
        picks_a = {**sample_picks, "champion": "Duke Blue Devils"}
        picks_b = {**sample_picks, "champion": "Kansas Jayhawks"}
        db.upsert_bracket(1001, 9001, "Alice", picks_a)
        db.upsert_bracket(1001, 9002, "Alice", picks_b)

        assert db.get_bracket(1001, 9001)["champion"] == "Duke Blue Devils"
        assert db.get_bracket(1001, 9002)["champion"] == "Kansas Jayhawks"

    def test_get_bracket_returns_correct_guild(self, tmp_db, sample_picks):
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        assert db.get_bracket(1001, 9002) is None

    def test_get_guild_brackets_filters_by_guild(self, tmp_db, sample_picks):
        db.upsert_bracket(1001, 9001, "Alice", sample_picks)
        db.upsert_bracket(2001, 9001, "Bob", sample_picks)
        db.upsert_bracket(3001, 9002, "Carol", sample_picks)

        guild_a = db.get_guild_brackets(9001)
        guild_b = db.get_guild_brackets(9002)
        assert len(guild_a) == 2
        assert len(guild_b) == 1
        assert guild_b[0]["display_name"] == "Carol"


# ---------------------------------------------------------------------------
# Guild channel settings
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# US-9: Game results persistence
# ---------------------------------------------------------------------------


class TestGameResults:
    def test_creates_game_results_table(self, tmp_db):
        with sqlite3.connect(tmp_db) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "game_results" in tables

    def test_save_and_load(self, tmp_db):
        games = [
            {"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"},
            {"winner": "Kansas Jayhawks", "loser": "Norfolk State Spartans", "round": "1st Round"},
        ]
        db.save_game_results("20260319", games)
        results = db.get_all_game_results()
        assert len(results) == 2
        winners = {r["winner"] for r in results}
        assert "Duke Blue Devils" in winners
        assert "Kansas Jayhawks" in winners

    def test_save_multiple_dates(self, tmp_db):
        day1 = [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]
        day2 = [{"winner": "Kansas Jayhawks", "loser": "Norfolk State Spartans", "round": "2nd Round"}]
        db.save_game_results("20260319", day1)
        db.save_game_results("20260320", day2)
        results = db.get_all_game_results()
        assert len(results) == 2
        dates = {r["game_date"] for r in results}
        assert dates == {"20260319", "20260320"}

    def test_save_idempotent(self, tmp_db):
        games = [{"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"}]
        db.save_game_results("20260319", games)
        db.save_game_results("20260319", games)  # same data again
        results = db.get_all_game_results()
        assert len(results) == 1

    def test_get_game_result_dates(self, tmp_db):
        db.save_game_results("20260319", [{"winner": "A", "loser": "B", "round": "1st Round"}])
        db.save_game_results("20260320", [{"winner": "C", "loser": "D", "round": "2nd Round"}])
        dates = db.get_game_result_dates()
        assert dates == {"20260319", "20260320"}

    def test_empty_games_list(self, tmp_db):
        db.save_game_results("20260319", [])
        results = db.get_all_game_results()
        assert results == []

    def test_results_ordered_by_date(self, tmp_db):
        db.save_game_results("20260320", [{"winner": "B", "loser": "D", "round": "2nd Round"}])
        db.save_game_results("20260319", [{"winner": "A", "loser": "C", "round": "1st Round"}])
        results = db.get_all_game_results()
        assert results[0]["game_date"] == "20260319"
        assert results[1]["game_date"] == "20260320"


# ---------------------------------------------------------------------------
# Guild channel settings
# ---------------------------------------------------------------------------


class TestGuildChannelSettings:
    def test_set_and_get(self, tmp_db):
        db.set_guild_channel(9001, 5001)
        channels = db.get_all_guild_channels()
        assert len(channels) == 1
        assert channels[0]["guild_id"] == 9001
        assert channels[0]["channel_id"] == 5001

    def test_upsert_overwrites(self, tmp_db):
        db.set_guild_channel(9001, 5001)
        db.set_guild_channel(9001, 5002)
        channels = db.get_all_guild_channels()
        assert len(channels) == 1
        assert channels[0]["channel_id"] == 5002

    def test_multiple_guilds(self, tmp_db):
        db.set_guild_channel(9001, 5001)
        db.set_guild_channel(9002, 5002)
        channels = db.get_all_guild_channels()
        assert len(channels) == 2

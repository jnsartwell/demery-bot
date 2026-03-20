import os
import sqlite3

# Set dummy env vars BEFORE any project imports (bot.py reads them at import time)
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("DISCORD_BOT_APPLICATION_ID", "123456")
os.environ.setdefault("DISCORD_GUILD_ID", "")
os.environ.setdefault("DISCORD_BYPASS_USER_IDS", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import bot
import db
import espn
import llm


# ---------------------------------------------------------------------------
# Database — every test gets a fresh in-memory SQLite DB
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    return db_path


# ---------------------------------------------------------------------------
# Reset module-level caches between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_caches(monkeypatch):
    monkeypatch.setattr(espn, "_cached_results", {})
    monkeypatch.setattr(espn, "_cached_team_names", [])
    monkeypatch.setattr(bot, "_last_used", {})
    monkeypatch.setattr(bot, "_last_submit", {})


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_picks():
    return {
        "round_of_32": [
            "Duke Blue Devils", "Kansas Jayhawks", "Gonzaga Bulldogs",
            "Houston Cougars", "Arizona Wildcats", "Purdue Boilermakers",
            "North Carolina Tar Heels", "UCLA Bruins", "Tennessee Volunteers",
            "Baylor Bears", "Kentucky Wildcats", "Marquette Golden Eagles",
            "Alabama Crimson Tide", "Indiana Hoosiers", "Saint Mary's Gaels",
            "Creighton Bluejays", "Texas Longhorns", "Miami Hurricanes",
            "Xavier Musketeers", "Iowa State Cyclones", "Connecticut Huskies",
            "TCU Horned Frogs", "Michigan State Spartans", "Arkansas Razorbacks",
            "Memphis Tigers", "Florida Atlantic Owls", "San Diego State Aztecs",
            "Nevada Wolf Pack", "Charleston Cougars", "Oral Roberts Golden Eagles",
            "Vermont Catamounts", "Colgate Raiders",
        ],
        "sweet_16": [
            "Duke Blue Devils", "Kansas Jayhawks", "Gonzaga Bulldogs",
            "Houston Cougars", "Arizona Wildcats", "Purdue Boilermakers",
            "North Carolina Tar Heels", "UCLA Bruins", "Tennessee Volunteers",
            "Baylor Bears", "Kentucky Wildcats", "Marquette Golden Eagles",
            "Alabama Crimson Tide", "Indiana Hoosiers", "Saint Mary's Gaels",
            "Creighton Bluejays",
        ],
        "elite_eight": [
            "Duke Blue Devils", "Kansas Jayhawks", "Gonzaga Bulldogs",
            "Houston Cougars", "Arizona Wildcats", "Purdue Boilermakers",
            "North Carolina Tar Heels", "UCLA Bruins",
        ],
        "final_four": [
            "Duke Blue Devils", "Kansas Jayhawks",
            "Gonzaga Bulldogs", "Houston Cougars",
        ],
        "championship_game": ["Duke Blue Devils", "Kansas Jayhawks"],
        "champion": "Duke Blue Devils",
    }


@pytest.fixture
def sample_games():
    return [
        {"winner": "Duke Blue Devils", "loser": "Vermont Catamounts", "round": "1st Round"},
        {"winner": "Kansas Jayhawks", "loser": "Norfolk State Spartans", "round": "1st Round"},
        {"winner": "Saint Peter's Peacocks", "loser": "Kentucky Wildcats", "round": "1st Round"},
    ]


# ---------------------------------------------------------------------------
# Mock Anthropic client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_anthropic(monkeypatch):
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Demery says something witty")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(llm, "client", mock_client)
    return mock_client


# ---------------------------------------------------------------------------
# Mock Discord interaction factory
# ---------------------------------------------------------------------------

@pytest.fixture
def make_interaction():
    def _make(user_id=1001, guild_id=9001, display_name="TestUser"):
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = user_id
        interaction.user.display_name = display_name
        interaction.user.mention = f"<@{user_id}>"
        interaction.guild_id = guild_id
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = guild_id
        interaction.guild.text_channels = []
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.command = MagicMock()
        interaction.command.name = "test"
        return interaction
    return _make


@pytest.fixture
def make_member():
    def _make(user_id=2001, display_name="Victim"):
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.display_name = display_name
        member.mention = f"<@{user_id}>"
        return member
    return _make


@pytest.fixture
def make_intensity():
    def _make(value="medium"):
        choice = MagicMock()
        choice.value = value
        return choice
    return _make


@pytest.fixture
def bypass_user(monkeypatch):
    monkeypatch.setattr(bot, "BYPASS_USER_IDS", {1001})
    return 1001

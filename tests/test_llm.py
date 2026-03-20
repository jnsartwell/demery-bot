"""
Tests for llm.py — covers:
  US-11: Tone and personality (system prompt verification)
  DS-6:  Team name normalization
  DS-7:  Prompt caching on system prompt
  DS-8:  Bracket image parsing robustness
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aioresponses import aioresponses

import llm

# ---------------------------------------------------------------------------
# US-11: Tone and personality — system prompt content
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_contains_character_name(self):
        assert "Demery" in llm.SYSTEM_PROMPT

    def test_contains_sentence_limit(self):
        assert "2-3 sentences" in llm.SYSTEM_PROMPT

    def test_contains_clean_language_rule(self):
        assert "no profanity" in llm.SYSTEM_PROMPT

    def test_contains_intensity_mild(self):
        assert "mild" in llm.SYSTEM_PROMPT

    def test_contains_intensity_medium(self):
        assert "medium" in llm.SYSTEM_PROMPT

    def test_contains_intensity_harsh(self):
        assert "harsh" in llm.SYSTEM_PROMPT

    def test_contains_friend_tone(self):
        assert "roasting friends, not strangers" in llm.SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# DS-7: Prompt caching on system prompt
# ---------------------------------------------------------------------------


class TestPromptCaching:
    @pytest.mark.asyncio
    async def test_generate_taunt_uses_cache_control(self, mock_anthropic):
        await llm.generate_taunt("Alice", "medium")
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        system = call_kwargs["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_generate_submission_ack_uses_cache_control(self, mock_anthropic):
        await llm.generate_submission_ack("Alice", {"champion": "Duke Blue Devils"})
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        system = call_kwargs["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_generate_digest_uses_cache_control(self, mock_anthropic):
        submitters = [{"mention": "<@1>", "name": "A", "busts": [], "survivors": []}]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        system = call_kwargs["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# generate_taunt
# ---------------------------------------------------------------------------


class TestGenerateTaunt:
    @pytest.mark.asyncio
    async def test_passes_system_prompt(self, mock_anthropic):
        await llm.generate_taunt("Alice", "medium")
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["system"][0]["text"] == llm.SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_includes_target_name(self, mock_anthropic):
        await llm.generate_taunt("Alice", "harsh")
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Alice" in user_content
        assert "harsh" in user_content

    @pytest.mark.asyncio
    async def test_includes_bracket_data(self, mock_anthropic, sample_picks):
        await llm.generate_taunt("Alice", "medium", bracket_data=sample_picks)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Duke Blue Devils" in user_content
        assert "Champion" in user_content

    @pytest.mark.asyncio
    async def test_includes_results_busts(self, mock_anthropic, sample_picks):
        results = {
            "busts": [{"team": "Kentucky Wildcats", "picked_to_reach": "elite_eight", "lost_in": "1st Round"}],
            "survivors": [],
        }
        await llm.generate_taunt("Alice", "medium", bracket_data=sample_picks, results=results)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Kentucky Wildcats" in user_content
        assert "Busted bracket picks" in user_content

    @pytest.mark.asyncio
    async def test_includes_results_survivors(self, mock_anthropic, sample_picks):
        results = {
            "busts": [],
            "survivors": [{"team": "Duke Blue Devils", "still_alive_through": "1st Round"}],
        }
        await llm.generate_taunt("Alice", "medium", bracket_data=sample_picks, results=results)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Survivors still alive" in user_content

    @pytest.mark.asyncio
    async def test_no_bracket_no_picks_in_prompt(self, mock_anthropic):
        await llm.generate_taunt("Alice", "medium")
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Champion" not in user_content

    @pytest.mark.asyncio
    async def test_returns_response_text(self, mock_anthropic):
        result = await llm.generate_taunt("Alice", "medium")
        assert result == "Demery says something witty"


# ---------------------------------------------------------------------------
# generate_submission_ack
# ---------------------------------------------------------------------------


class TestGenerateSubmissionAck:
    @pytest.mark.asyncio
    async def test_includes_champion(self, mock_anthropic):
        await llm.generate_submission_ack("Alice", {"champion": "Duke Blue Devils"})
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Duke Blue Devils" in user_content

    @pytest.mark.asyncio
    async def test_returns_text(self, mock_anthropic):
        result = await llm.generate_submission_ack("Alice", {"champion": "Duke Blue Devils"})
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_digest
# ---------------------------------------------------------------------------


class TestGenerateDigest:
    @pytest.mark.asyncio
    async def test_includes_all_submitters(self, mock_anthropic):
        submitters = [
            {"mention": "<@1>", "name": "Alice", "busts": [], "survivors": []},
            {"mention": "<@2>", "name": "Bob", "busts": [], "survivors": []},
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "<@1>" in user_content
        assert "<@2>" in user_content

    @pytest.mark.asyncio
    async def test_no_activity_context(self, mock_anthropic):
        """When all submitters have no busts/survivors, context says no games."""
        submitters = [{"mention": "<@1>", "name": "A", "busts": [], "survivors": []}]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "No games have been played yet" in user_content

    @pytest.mark.asyncio
    async def test_activity_context_with_today(self, mock_anthropic):
        """When there are today's busts, context focuses on today's events."""
        submitters = [
            {
                "mention": "<@1>",
                "name": "A",
                "busts": [{"team": "X", "picked_to_reach": "sweet_16", "lost_in": "1st Round"}],
                "survivors": [],
                "today_busts": [{"team": "X", "picked_to_reach": "sweet_16", "lost_in": "1st Round"}],
                "today_survivors": [],
            }
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "how everyone's bracket is looking" in user_content

    @pytest.mark.asyncio
    async def test_activity_context_cumulative_only(self, mock_anthropic):
        """When there's cumulative history but no today activity, context acknowledges both."""
        submitters = [
            {
                "mention": "<@1>",
                "name": "A",
                "busts": [{"team": "X", "picked_to_reach": "sweet_16", "lost_in": "1st Round"}],
                "survivors": [],
                "today_busts": [],
                "today_survivors": [],
            }
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "already done some damage" in user_content

    @pytest.mark.asyncio
    async def test_prompt_requests_natural_style(self, mock_anthropic):
        submitters = [{"mention": "<@1>", "name": "A", "busts": [], "survivors": []}]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "no headers, no bold, no bullets" in user_content


# ---------------------------------------------------------------------------
# DS-8: Bracket image parsing robustness
# ---------------------------------------------------------------------------


class TestParseBracketImage:
    def _mock_response(self, text):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=text)]
        return mock_resp

    def _valid_picks_json(self):
        return json.dumps(
            {
                "round_of_32": ["A"] * 32,
                "sweet_16": ["A"] * 16,
                "elite_eight": ["A"] * 8,
                "final_four": ["A"] * 4,
                "championship_game": ["A", "B"],
                "champion": "A",
            }
        )

    @pytest.mark.asyncio
    async def test_valid_json_returns_picks(self, monkeypatch):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(self._valid_picks_json()))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG fake image data")
            result = await llm.parse_bracket_image("https://cdn.discord.com/image.png")

        assert result["champion"] == "A"
        assert len(result["round_of_32"]) == 32

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self, monkeypatch):
        wrapped = f"```json\n{self._valid_picks_json()}\n```"
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(wrapped))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG")
            result = await llm.parse_bracket_image("https://cdn.discord.com/image.png")

        assert result["champion"] == "A"

    @pytest.mark.asyncio
    async def test_extracts_json_from_surrounding_text(self, monkeypatch):
        wrapped = f"Here are the picks:\n{self._valid_picks_json()}\nHope that helps!"
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(wrapped))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG")
            result = await llm.parse_bracket_image("https://cdn.discord.com/image.png")

        assert result["champion"] == "A"

    @pytest.mark.asyncio
    async def test_error_key_raises_valueerror(self, monkeypatch):
        error_json = json.dumps({"error": "Cannot read this bracket"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(error_json))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG")
            with pytest.raises(ValueError, match="Cannot read this bracket"):
                await llm.parse_bracket_image("https://cdn.discord.com/image.png")

    @pytest.mark.asyncio
    async def test_missing_keys_raises_valueerror(self, monkeypatch):
        incomplete = json.dumps({"round_of_32": ["A"], "champion": "A"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(incomplete))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG")
            with pytest.raises(ValueError, match="missing rounds"):
                await llm.parse_bracket_image("https://cdn.discord.com/image.png")

    @pytest.mark.asyncio
    async def test_unparseable_response_raises(self, monkeypatch):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=self._mock_response("I can't read this image at all, sorry!")
        )
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG")
            with pytest.raises(ValueError, match="Could not parse"):
                await llm.parse_bracket_image("https://cdn.discord.com/image.png")


# ---------------------------------------------------------------------------
# DS-6: Team name normalization
# ---------------------------------------------------------------------------


class TestNormalizeTeamNames:
    @pytest.mark.asyncio
    async def test_maps_names_correctly(self, monkeypatch):
        mapping = {"Duke": "Duke Blue Devils", "UConn Huskies": "Connecticut Huskies"}
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=json.dumps(mapping))]))
        monkeypatch.setattr(llm, "client", mock_client)

        picks = {
            "round_of_32": ["Duke", "Kansas Jayhawks"],
            "sweet_16": ["Duke"],
            "elite_eight": [],
            "final_four": [],
            "championship_game": [],
            "champion": "Duke",
        }
        result = await llm.normalize_team_names(picks, ["Duke Blue Devils", "Kansas Jayhawks"])
        assert result["champion"] == "Duke Blue Devils"
        assert result["round_of_32"][0] == "Duke Blue Devils"

    @pytest.mark.asyncio
    async def test_empty_espn_list_noop(self):
        picks = {
            "round_of_32": ["Duke"],
            "champion": "Duke",
            "sweet_16": [],
            "elite_eight": [],
            "final_four": [],
            "championship_game": [],
        }
        result = await llm.normalize_team_names(picks, [])
        assert result == picks

    @pytest.mark.asyncio
    async def test_malformed_response_returns_raw(self, monkeypatch):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text="not json at all")]))
        monkeypatch.setattr(llm, "client", mock_client)

        picks = {
            "round_of_32": ["Duke"],
            "champion": "Duke",
            "sweet_16": [],
            "elite_eight": [],
            "final_four": [],
            "championship_game": [],
        }
        result = await llm.normalize_team_names(picks, ["Duke Blue Devils"])
        assert result == picks

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self, monkeypatch):
        mapping = {"Duke": "Duke Blue Devils"}
        wrapped = f"```json\n{json.dumps(mapping)}\n```"
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=wrapped)]))
        monkeypatch.setattr(llm, "client", mock_client)

        picks = {
            "round_of_32": ["Duke"],
            "champion": "Duke",
            "sweet_16": [],
            "elite_eight": [],
            "final_four": [],
            "championship_game": [],
        }
        result = await llm.normalize_team_names(picks, ["Duke Blue Devils"])
        assert result["champion"] == "Duke Blue Devils"

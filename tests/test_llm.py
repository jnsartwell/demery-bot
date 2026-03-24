"""
Tests for llm.py — covers:
  US-11: Tone and personality (system prompt verification)
  DS-3:  Team name normalization
  DS-4:  Prompt caching on system prompt
  DS-5:  Bracket image parsing robustness
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aioresponses import aioresponses

import llm

# ---------------------------------------------------------------------------
# DS-4: Prompt caching on system prompt
# ---------------------------------------------------------------------------


class TestPromptCaching:
    @pytest.mark.asyncio
    async def test_generate_diss_uses_cache_control(self, mock_anthropic):
        await llm.generate_diss("Alice")
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
        submitters = [{"mention": "<@1>", "busts": []}]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        system = call_kwargs["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# generate_diss
# ---------------------------------------------------------------------------


class TestGeneratediss:
    @pytest.mark.asyncio
    async def test_passes_system_prompt(self, mock_anthropic):
        await llm.generate_diss("Alice")
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["system"][0]["text"] == llm.SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_includes_target_name(self, mock_anthropic):
        await llm.generate_diss("Alice")
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Alice" in user_content

    @pytest.mark.asyncio
    async def test_includes_bracket_data(self, mock_anthropic, sample_picks):
        await llm.generate_diss("Alice", bracket_data=sample_picks)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Duke Blue Devils" in user_content

    @pytest.mark.asyncio
    async def test_includes_results_busts(self, mock_anthropic, sample_picks):
        results = {
            "busts": [{"team": "Kentucky Wildcats", "pick": "elite_eight", "lost": "1st Round"}],
            "survivors": [],
        }
        await llm.generate_diss("Alice", bracket_data=sample_picks, results=results)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Kentucky Wildcats" in user_content

    @pytest.mark.asyncio
    async def test_includes_results_survivors(self, mock_anthropic, sample_picks):
        results = {
            "busts": [],
            "survivors": [{"team": "Duke Blue Devils", "thru": "1st Round"}],
        }
        await llm.generate_diss("Alice", bracket_data=sample_picks, results=results)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Duke Blue Devils" in user_content

    @pytest.mark.asyncio
    async def test_no_bracket_no_picks_in_prompt(self, mock_anthropic):
        await llm.generate_diss("Alice")
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Champion" not in user_content

    @pytest.mark.asyncio
    async def test_returns_response_text(self, mock_anthropic):
        result = await llm.generate_diss("Alice")
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
            {"mention": "<@1>", "new_busts": [], "prior_busts": [], "survivors": []},
            {"mention": "<@2>", "new_busts": [], "prior_busts": [], "survivors": []},
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "<@1>" in user_content
        assert "<@2>" in user_content

    @pytest.mark.asyncio
    async def test_includes_new_bust_data_in_prompt(self, mock_anthropic):
        submitters = [
            {
                "mention": "<@1>",
                "new_busts": [{"team": "Kentucky Wildcats", "pick": "elite_eight", "lost": "1st Round", "seed": "4"}],
                "prior_busts": [],
                "survivors": [],
            },
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Kentucky Wildcats" in user_content
        assert "NEW:" in user_content

    @pytest.mark.asyncio
    async def test_prior_busts_show_count_only(self, mock_anthropic):
        """Prior busts show just the count, no details, to save tokens for humor."""
        submitters = [
            {
                "mention": "<@1>",
                "new_busts": [],
                "prior_busts": [{"team": "Kentucky Wildcats", "pick": "elite_eight", "lost": "1st Round", "seed": "4"}],
                "survivors": [],
            },
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "PRIOR: 1 more" in user_content
        assert "Kentucky Wildcats" not in user_content  # details omitted

    @pytest.mark.asyncio
    async def test_includes_survivor_data_in_prompt(self, mock_anthropic):
        submitters = [
            {
                "mention": "<@1>",
                "new_busts": [],
                "prior_busts": [],
                "survivors": [
                    {"team": "Duke Blue Devils", "thru": "2nd Round", "seed": "1", "farthest_pick": "champion"}
                ],
            },
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Duke Blue Devils" in user_content
        assert "Alive:" in user_content
        assert "Champ-pick" in user_content

    @pytest.mark.asyncio
    async def test_summary_includes_severity_callouts(self, mock_anthropic):
        """Summary line highlights worst bust and best survivor."""
        submitters = [
            {
                "mention": "<@1>",
                "new_busts": [{"team": "Kentucky Wildcats", "pick": "elite_eight", "lost": "1st Round", "seed": "4"}],
                "prior_busts": [],
                "survivors": [
                    {"team": "Duke Blue Devils", "thru": "1st Round", "seed": "1", "farthest_pick": "champion"},
                    {"team": "Kansas Jayhawks", "thru": "1st Round", "seed": "1", "farthest_pick": "final_four"},
                ],
            },
        ]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "1 busted" in user_content
        assert "worst: E8 pick" in user_content
        assert "2 alive" in user_content
        assert "best: Champ-pick" in user_content

    @pytest.mark.asyncio
    async def test_calibration_prompt_mentions_severity(self, mock_anthropic):
        submitters = [{"mention": "<@1>", "new_busts": [], "prior_busts": [], "survivors": []}]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "SEVERITY" in user_content
        assert "seeds" in user_content.lower()

    @pytest.mark.asyncio
    async def test_includes_game_results_in_prompt(self, mock_anthropic):
        submitters = [{"mention": "<@1>", "new_busts": [], "prior_busts": [], "survivors": []}]
        yesterday_games = [
            {
                "winner": "Duke Blue Devils",
                "loser": "Vermont Catamounts",
                "round": "1st Round",
                "winner_score": 82,
                "loser_score": 55,
            },
        ]
        await llm.generate_digest(submitters, yesterday_games=yesterday_games)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Duke Blue Devils" in user_content
        assert "82" in user_content
        assert "55" in user_content

    @pytest.mark.asyncio
    async def test_zero_busts_shows_count(self, mock_anthropic):
        submitters = [{"mention": "<@1>", "new_busts": [], "prior_busts": [], "survivors": []}]
        await llm.generate_digest(submitters)
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "0 busted" in user_content


# ---------------------------------------------------------------------------
# DS-5: Bracket image parsing robustness
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
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG fake image data", content_type="image/png")
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
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG", content_type="image/png")
            result = await llm.parse_bracket_image("https://cdn.discord.com/image.png")

        assert result["champion"] == "A"

    @pytest.mark.asyncio
    async def test_extracts_json_from_surrounding_text(self, monkeypatch):
        wrapped = f"Here are the picks:\n{self._valid_picks_json()}\nHope that helps!"
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(wrapped))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG", content_type="image/png")
            result = await llm.parse_bracket_image("https://cdn.discord.com/image.png")

        assert result["champion"] == "A"

    @pytest.mark.asyncio
    async def test_error_key_raises_valueerror(self, monkeypatch):
        error_json = json.dumps({"error": "Cannot read this bracket"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(error_json))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG", content_type="image/png")
            with pytest.raises(ValueError, match="Cannot read this bracket"):
                await llm.parse_bracket_image("https://cdn.discord.com/image.png")

    @pytest.mark.asyncio
    async def test_missing_keys_raises_valueerror(self, monkeypatch):
        incomplete = json.dumps({"round_of_32": ["A"], "champion": "A"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._mock_response(incomplete))
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG", content_type="image/png")
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
            m.get("https://cdn.discord.com/image.png", body=b"\x89PNG", content_type="image/png")
            with pytest.raises(ValueError, match="No JSON object found"):
                await llm.parse_bracket_image("https://cdn.discord.com/image.png")

    @pytest.mark.asyncio
    async def test_unsupported_media_type_raises(self, monkeypatch):
        mock_client = AsyncMock()
        monkeypatch.setattr(llm, "client", mock_client)

        with aioresponses() as m:
            m.get("https://cdn.discord.com/file.bmp", body=b"BM", content_type="image/bmp")
            with pytest.raises(ValueError, match="Unsupported image format"):
                await llm.parse_bracket_image("https://cdn.discord.com/file.bmp")

        # Claude API should never have been called
        mock_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# DS-3: Team name normalization
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


# ---------------------------------------------------------------------------
# DS-5: Bracket picks extraction/validation (shared helper)
# ---------------------------------------------------------------------------


class TestExtractAndValidatePicks:
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

    def test_valid_json_returns_picks(self):
        result = llm._extract_and_validate_picks(self._valid_picks_json())
        assert result["champion"] == "A"
        assert len(result["round_of_32"]) == 32

    def test_strips_markdown_fences(self):
        wrapped = f"```json\n{self._valid_picks_json()}\n```"
        result = llm._extract_and_validate_picks(wrapped)
        assert result["champion"] == "A"

    def test_extracts_from_surrounding_text(self):
        wrapped = f"Here are the picks:\n{self._valid_picks_json()}\nDone!"
        result = llm._extract_and_validate_picks(wrapped)
        assert result["champion"] == "A"

    def test_error_key_raises(self):
        with pytest.raises(ValueError, match="Cannot read"):
            llm._extract_and_validate_picks('{"error": "Cannot read this bracket"}')

    def test_missing_keys_raises(self):
        with pytest.raises(ValueError, match="missing rounds"):
            llm._extract_and_validate_picks('{"round_of_32": ["A"], "champion": "A"}')

    def test_unparseable_raises(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            llm._extract_and_validate_picks("This is not JSON at all")

import base64
import datetime
import json
import re

import aiohttp
import anthropic

from constants import (
    ALLOWED_IMAGE_TYPES,
    PICKS_ROUND_KEYS,
    REQUIRED_PICKS_KEYS,
    SUPPORTED_IMAGE_FORMATS_LABEL,
    TIER_DISPLAY_NAMES,
    TOURNAMENT_GAME_DATES,
)
from prompts import (
    NORMALIZE_TEAM_NAMES_PROMPT,
    PARSE_BRACKET_IMAGE_PROMPT,
    SYSTEM_PROMPT,
)

client = anthropic.AsyncAnthropic()

HUMOR_MODEL = "claude-opus-4-6"
OCR_MODEL = "claude-sonnet-4-6"


async def generate_diss(
    target_mention: str,
    bracket_data: dict | None = None,
    results: dict | None = None,
    roast_angle: str | None = None,
    joke_style: str | None = None,
) -> str:
    content = f"Roast {target_mention}'s bracket picks with a creative zinger. 1-2 sentences max."
    if roast_angle:
        content += f"\nANGLE: {roast_angle}"
    if joke_style:
        content += f"\nSTYLE: {joke_style}"
    if bracket_data or results:
        data_lines = []
        if bracket_data:
            data_lines.append(
                f"Picks: champ={bracket_data['champion']}"
                f" | final={', '.join(bracket_data['championship_game'])}"
                f" | F4={', '.join(bracket_data['final_four'])}"
                f" | E8={', '.join(bracket_data['elite_eight'])}"
                f" | S16={', '.join(bracket_data['sweet_16'])}"
                f" | R32={', '.join(bracket_data['round_of_32'])}"
            )
        if results:
            if results["busts"]:
                data_lines.append(f"Busts: {_fmt_busts(results['busts'])}")
            if results["survivors"]:
                data_lines.append(f"Alive: {_fmt_survs(results['survivors'])}")
        content += "\n\n<data>\n" + "\n".join(data_lines) + "\n</data>"
    response = await client.messages.create(
        model=HUMOR_MODEL,
        max_tokens=400,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


async def generate_submission_ack(mention: str, picks: dict) -> str:
    champion = picks.get("champion", "somebody")
    content = (
        "One-liner. You just got handed ammo and you know it. "
        "Make it funny — a real zinger, not just an acknowledgement. "
        "Stick the landing.\n\n"
        f"<data>\n{mention} just submitted their bracket — they picked {champion} to win it all.\n</data>"
    )
    response = await client.messages.create(
        model=HUMOR_MODEL,
        max_tokens=120,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


async def parse_bracket_image(image_url: str) -> dict:
    """
    Fetch image from Discord CDN and use Claude Vision to extract bracket picks.
    Returns picks dict with keys: round_of_32, sweet_16, elite_eight, final_four,
    championship_game (lists), and champion (string).
    Raises ValueError if image is unreadable or picks are incomplete.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as resp:
            resp.raise_for_status()
            image_bytes = await resp.read()
            content_type = resp.content_type or "image/png"

    # Strip parameters (e.g. "image/png; charset=utf-8" -> "image/png")
    media_type = content_type.split(";")[0].strip()
    if media_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError(f"Unsupported image format ({media_type}). Please use {SUPPORTED_IMAGE_FORMATS_LABEL}.")

    image_b64 = base64.standard_b64encode(image_bytes).decode()

    response = await client.messages.create(
        model=OCR_MODEL,
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": PARSE_BRACKET_IMAGE_PROMPT},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    print(f"parse_bracket_image raw response ({len(raw)} chars): {raw[:200]}")
    return _extract_and_validate_picks(raw)


async def normalize_team_names(picks: dict, espn_names: list[str]) -> dict:
    """
    Normalize team names in picks to match ESPN's exact displayName values.
    Uses Haiku to resolve abbreviations, nicknames, and minor differences.
    """
    if not espn_names:
        return picks

    all_pick_names = []
    for key in PICKS_ROUND_KEYS:
        all_pick_names.extend(picks.get(key, []))
    if picks.get("champion"):
        all_pick_names.append(picks["champion"])
    unique_picks = list(set(all_pick_names))

    prompt = NORMALIZE_TEAM_NAMES_PROMPT.format(
        espn_names=json.dumps(sorted(espn_names)),
        unique_picks=json.dumps(unique_picks),
    )

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    try:
        name_map = json.loads(_extract_json_from_text(raw))
    except ValueError:
        print(f"normalize_team_names: failed to parse response, skipping. Raw: {raw[:200]}")
        return picks

    if not isinstance(name_map, dict):
        print(f"normalize_team_names: expected dict, got {type(name_map).__name__}, skipping")
        return picks

    def _apply_mapping(name):
        val = name_map.get(name, name)
        return val if isinstance(val, str) else name

    normalized = {}
    for key in PICKS_ROUND_KEYS:
        normalized[key] = [_apply_mapping(t) for t in picks.get(key, [])]
    normalized["champion"] = _apply_mapping(picks.get("champion", ""))

    changed = {k: v for k, v in name_map.items() if k != v and isinstance(v, str)}
    if changed:
        print(f"normalize_team_names: corrected {len(changed)} names: {changed}")

    return normalized


async def generate_digest(
    submitters: list[dict],
    yesterday_games: list[dict] | None = None,
) -> str:
    """
    submitters: [{mention, new_busts: [...], prior_busts: [...], survivors: [...]}]
    yesterday_games: [{winner, loser, round, winner_score, loser_score}]
    Returns a single message roasting everyone's bracket.
    """
    data_lines = []
    if yesterday_games:
        games_str = "; ".join(
            f"{g['winner']} {g.get('winner_score', '?')}-{g.get('loser_score', '?')} {g['loser']}"
            for g in yesterday_games
        )
        data_lines.append(f"Yesterday's results: {games_str}")
    data_lines.append("")
    for s in submitters:
        new_busts = s.get("new_busts", [])
        prior_busts = s.get("prior_busts", [])
        survivors = s.get("survivors", [])
        all_busts = new_busts + prior_busts
        summary = _build_summary(all_busts, survivors)
        line = s["mention"] + " | " + summary
        if new_busts:
            line += "\n  NEW: " + _fmt_busts(new_busts)
        if prior_busts:
            line += "\n  PRIOR: " + _fmt_busts(prior_busts)
        if survivors:
            line += "\n  Alive: " + _fmt_survs(survivors)
        if s.get("roast_angle"):
            line += f"\n  ANGLE: {s['roast_angle']}"
        if s.get("joke_style"):
            line += f"\n  STYLE: {s['joke_style']}"
        data_lines.append(line)

    last_game = max(TOURNAMENT_GAME_DATES)
    tournament_over = datetime.date.today() > datetime.datetime.strptime(last_game, "%Y%m%d").date()
    if tournament_over:
        tense = "The tournament is over — use past tense."
    else:
        tense = "The tournament is still going — use present tense. Brackets ARE a disaster, not WERE."

    content = (
        "Roast everyone's bracket in one continuous monologue. "
        f"{tense} "
        "Calibrate by SEVERITY, not count — losing a champion or Final Four pick is devastating; "
        "losing R32 picks is minor. Lead with yesterday's NEW busts — that's the fresh material. "
        "PRIOR busts are context, don't repeat the same jokes about them. "
        "Use seeds when they make the joke funnier (a 1-seed losing in R1 is inherently hilarious). "
        "Mention each Discord tag exactly once. Stay under 2000 characters."
    )
    content += "\n\n<data>\n" + "\n".join(data_lines) + "\n</data>"
    print(f"[digest-llm] Prompt ({len(content)} chars): {content[:500]}")
    response = await client.messages.create(
        model=HUMOR_MODEL,
        max_tokens=1200,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": content}],
    )
    print(f"[digest-llm] Response ({len(response.content[0].text)} chars): {response.content[0].text[:200]}")
    return response.content[0].text


# --- helpers ---


def _build_summary(all_busts: list[dict], survivors: list[dict]) -> str:
    """Build a compact severity-aware summary line for one submitter."""
    bust_count = len(all_busts)
    alive_count = len(survivors)
    summary = f"{bust_count} busted"
    if all_busts:
        worst = TIER_DISPLAY_NAMES.get(all_busts[0]["pick"], all_busts[0]["pick"])
        summary += f" (worst: {worst} pick)"
    summary += f" / {alive_count} alive"
    if survivors:
        best = TIER_DISPLAY_NAMES.get(survivors[0].get("farthest_pick", ""), "")
        summary += f" (best: {best}-pick)"
    return summary


def _fmt_busts(busts: list[dict]) -> str:
    """Format bust list as compact semicolon-delimited string."""
    parts = []
    for b in busts:
        seed = f"({b['seed']}) " if b.get("seed") else ""
        beaten = ""
        if b.get("beaten_by"):
            by_seed = f"({b['beaten_by_seed']}) " if b.get("beaten_by_seed") else ""
            beaten = f" → lost to {by_seed}{b['beaten_by']}"
        parts.append(f"{seed}{b['team']}{beaten} (pick={b['pick']}, lost={b['lost']})")
    return "; ".join(parts)


def _fmt_survs(survs: list[dict]) -> str:
    """Format survivor list as compact semicolon-delimited string with pick depth."""
    parts = []
    for s in survs:
        seed = f"({s['seed']}) " if s.get("seed") else ""
        pick_label = TIER_DISPLAY_NAMES.get(s.get("farthest_pick", ""), s.get("farthest_pick", ""))
        parts.append(f"{seed}{s['team']} {pick_label}-pick thru={s['thru']}")
    return "; ".join(parts)


def _extract_json_from_text(raw: str) -> str:
    """
    Extract a JSON object string from raw LLM output.
    Handles markdown fences and searches for JSON boundaries.
    Raises ValueError if no JSON object is found.
    """
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    if raw.startswith("{"):
        return raw

    start = raw.find("{")
    if start != -1:
        candidate = raw[start:]
        for end in range(len(candidate), 0, -1):
            if candidate[end - 1] == "}":
                try:
                    json.loads(candidate[:end])
                    return candidate[:end]
                except json.JSONDecodeError:
                    continue

    raise ValueError(f"No JSON object found in text: {raw[:200]}")


def _extract_and_validate_picks(raw: str) -> dict:
    """
    Extract and validate bracket picks JSON from raw LLM response text.
    Raises ValueError on parse failure, error responses, or missing rounds.
    """
    json_str = _extract_json_from_text(raw)

    try:
        picks = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse bracket JSON: {e}") from e

    if "error" in picks:
        raise ValueError(f"Claude could not read bracket: {picks['error']}")

    missing = REQUIRED_PICKS_KEYS - picks.keys()
    if missing:
        raise ValueError(f"Bracket picks missing rounds: {missing}")

    return picks

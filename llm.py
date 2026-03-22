import base64
import json
import re

import aiohttp
import anthropic

from constants import PICKS_ROUND_KEYS, REQUIRED_PICKS_KEYS
from prompts import (
    NORMALIZE_TEAM_NAMES_PROMPT,
    PARSE_BRACKET_IMAGE_PROMPT,
    SYSTEM_PROMPT,
)

client = anthropic.AsyncAnthropic()


async def generate_diss(
    target_mention: str,
    intensity: str,
    bracket_data: dict | None = None,
    results: dict | None = None,
) -> str:
    content = f"Taunt {target_mention} at {intensity} intensity."
    if bracket_data:
        content += (
            f"\n\nTheir actual bracket picks:"
            f"\n- Champion: {bracket_data['champion']}"
            f"\n- Championship game: {', '.join(bracket_data['championship_game'])}"
            f"\n- Final Four: {', '.join(bracket_data['final_four'])}"
            f"\n- Elite Eight: {', '.join(bracket_data['elite_eight'])}"
            f"\n- Sweet 16: {', '.join(bracket_data['sweet_16'])}"
            f"\n- Round of 32: {', '.join(bracket_data['round_of_32'])}"
            f"\n\nMake the roast specific to their picks where it's funny."
        )
    if results:
        if results["busts"]:
            bust_lines = [
                f"- {b['team']} (picked to reach {b['picked_to_reach']}, lost in {b['lost_in']})"
                for b in results["busts"]
            ]
            content += "\n\nBusted bracket picks so far:\n" + "\n".join(bust_lines)
        if results["survivors"]:
            surv_lines = [
                f"- {s['team']} (still alive through {s['still_alive_through']})" for s in results["survivors"]
            ]
            content += "\n\nSurvivors still alive:\n" + "\n".join(surv_lines)
        content += (
            "\n\nUse the tournament results — the bigger the gap between expectation and reality, the funnier it is."
        )
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
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
        f"{mention} just submitted their bracket — they picked {champion} to win it all. "
        "Give a one-line playful Demery reaction at mild intensity, like you just got handed ammo to use later."
    )
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
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

    image_b64 = base64.standard_b64encode(image_bytes).decode()

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": content_type,
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


async def generate_digest(submitters: list[dict]) -> str:
    """
    submitters: [{mention, name, busts: [{team, picked_to_reach, lost_in}],
                  survivors: [{team, still_alive_through}]}]
    Returns a single message roasting/praising everyone.
    """
    lines = _format_submitter_lines(submitters)
    _log_digest_data(submitters)
    context = _determine_digest_context(submitters)

    content = (
        f"{context} Bracket status:\n\n" + "\n".join(lines) + "\n\nWrite a Demery-style daily bracket update. "
        "Write it like a real person in a Discord channel — no headers, no bold, no bullets. "
        "Natural flowing text, varied openers. "
        "Mention each person using their EXACT Discord tag (e.g. <@123456>) — copy verbatim. "
        "Today's busts are the headline — roast the gap between where they picked a team to go "
        "and where they actually got bounced. Older busts are background damage, not the main event. "
        "Survivors get begrudging credit. No-activity people get a backhanded acknowledgement. "
        "One or two punchy sentences per person. Everyone gets mentioned. "
        "Use medium intensity. Be funny. Be specific. Be Demery."
    )
    print(f"[digest-llm] Prompt ({len(content)} chars): {content[:500]}")
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
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
    print(f"[digest-llm] Response ({len(response.content[0].text)} chars): {response.content[0].text[:200]}")
    return response.content[0].text


# --- helpers ---


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


def _format_submitter_lines(submitters: list[dict]) -> list[str]:
    """Build pipe-delimited status lines for each submitter."""
    lines = []
    for s in submitters:
        parts = [s["mention"]]
        today_busts = s.get("today_busts", [])
        today_survivors = s.get("today_survivors", [])
        if today_busts:
            bust_strs = [
                f"{b['team']} (picked to reach {b['picked_to_reach']}, lost in {b['lost_in']})" for b in today_busts
            ]
            parts.append("TODAY'S BUSTS: " + "; ".join(bust_strs))
        if today_survivors:
            surv_strs = [f"{sv['team']} (still alive through {sv['still_alive_through']})" for sv in today_survivors]
            parts.append("TODAY'S SURVIVORS: " + "; ".join(surv_strs))
        if s["busts"]:
            bust_strs = [
                f"{b['team']} (picked to reach {b['picked_to_reach']}, lost in {b['lost_in']})" for b in s["busts"]
            ]
            parts.append("ALL BUSTS (cumulative): " + "; ".join(bust_strs))
        if s["survivors"]:
            survivor_strs = [f"{sv['team']} (still alive through {sv['still_alive_through']})" for sv in s["survivors"]]
            parts.append("ALL SURVIVORS (cumulative): " + "; ".join(survivor_strs))
        if not s["busts"] and not s["survivors"]:
            parts.append("No bracket activity yet")
        lines.append(" | ".join(parts))
    return lines


def _determine_digest_context(submitters: list[dict]) -> str:
    """Return the context sentence for the digest based on today's activity."""
    today_quiet = all(not s.get("today_busts") and not s.get("today_survivors") for s in submitters)
    has_history = any(s["busts"] or s["survivors"] for s in submitters)
    if today_quiet and not has_history:
        return "No games have been played yet — brackets are untouched."
    if today_quiet and has_history:
        return (
            "Today's games haven't finished yet (or there are none today), but the tournament "
            "has already done some damage. Here's where everyone's bracket stands so far."
        )
    return (
        "Here's how everyone's bracket is looking. Focus the narrative on TODAY'S new busts "
        "and survivors, but use the cumulative status for overall context."
    )


def _log_digest_data(submitters: list[dict]) -> None:
    """Print debug info about digest submitters."""
    for s in submitters:
        today_b = len(s.get("today_busts", []))
        today_s = len(s.get("today_survivors", []))
        print(
            f"Digest data: {s['name']} — busts={len(s['busts'])} (today={today_b}) "
            f"survivors={len(s['survivors'])} (today={today_s})"
        )
        for b in s["busts"]:
            print(f"  BUST: {b}")
        for sv in s["survivors"]:
            print(f"  SURV: {sv}")

    print(f"[digest-llm] Submitters: {len(submitters)}")
    for s in submitters:
        print(f"[digest-llm]   {s['name']}: {len(s['busts'])} busts, {len(s['survivors'])} survivors")

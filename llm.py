import base64
import json
import re

import aiohttp
import anthropic

from constants import ALLOWED_IMAGE_TYPES, PICKS_ROUND_KEYS, REQUIRED_PICKS_KEYS, SUPPORTED_IMAGE_FORMATS_LABEL
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
    round_progress: dict | None = None,
) -> str:
    content = f"Taunt {target_mention}."
    if bracket_data or results or round_progress:
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
        if round_progress:
            data_lines.append(_fmt_round_progress(round_progress))
        content += "\n<data>\n" + "\n".join(data_lines) + "\n</data>"
    if bracket_data or results:
        content += "\nMake the roast specific to their actual picks. Keep it to 2-4 sentences."
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
        f"<context>{mention} just submitted their bracket — they picked {champion} to win it all.</context>\n"
        "One-liner. You just got handed ammo and you know it. "
        "Make it funny — a real zinger, not just an acknowledgement. "
        "Stick the landing."
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
    today_games: list[dict] | None = None,
    shared_busts: list[dict] | None = None,
    round_progress: dict | None = None,
) -> str:
    """
    submitters: [{mention, name, busts: [{team, pick, lost}],
                  survivors: [{team, thru}]}]
    today_games: [{winner, loser, round, winner_score, loser_score}]
    shared_busts: [{team, mentions: [mention, ...]}]
    Returns a single message roasting/praising everyone.
    """
    lines = _format_submitter_lines(submitters)
    _log_digest_data(submitters)
    context = _determine_digest_context(submitters)

    content = f"<context>\n{context}\n</context>\n<data>\nBracket status:\n\n" + "\n".join(lines)

    if today_games:
        content += "\n\nToday's results: " + _fmt_games(today_games)

    if shared_busts:
        content += "\n\nShared busts (multiple people picked these losers): " + "; ".join(
            f"{sb['team']} ({', '.join(sb['mentions'])})" for sb in shared_busts
        )

    if round_progress:
        content += f"\n\n{_fmt_round_progress(round_progress)}"

    content += "\n</data>"

    content += (
        "\n\nWrite a Demery-style daily bracket update — you're roasting friends "
        "in a Discord channel, not filing a report. "
        "Plain text, no markdown. Varied openers — never start the same way twice. "
        "CRITICAL: each person's Discord tag (e.g. <@123456>) must appear "
        "EXACTLY ONCE. Never repeat a tag. Never type out names. "
        "Every person gets roasted — no one gets off easy. "
        "Spend the most material on today's biggest busts and the most absurd picks. "
        "When multiple people share the same bust, roast them as a group — "
        "they walked into this together. "
        "Write like you're telling a story, not reading a list. "
        "Weave people and picks together into a flowing narrative. Be Demery."
    )
    print(f"[digest-llm] Prompt ({len(content)} chars): {content[:500]}")
    response = await client.messages.create(
        model=HUMOR_MODEL,
        max_tokens=1500,
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


def _fmt_busts(busts: list[dict]) -> str:
    """Format bust list as compact semicolon-delimited string."""
    parts = []
    for b in busts:
        seed = f"({b['seed']}) " if b.get("seed") else ""
        region = f" [{b['region']}]" if b.get("region") else ""
        parts.append(f"{seed}{b['team']}{region} (pick={b['pick']}, lost={b['lost']})")
    return "; ".join(parts)


def _fmt_survs(survs: list[dict]) -> str:
    """Format survivor list as compact semicolon-delimited string."""
    parts = []
    for s in survs:
        seed = f"({s['seed']}) " if s.get("seed") else ""
        parts.append(f"{seed}{s['team']} (thru={s['thru']})")
    return "; ".join(parts)


def _fmt_round_progress(round_progress: dict) -> str:
    """Format round progress as a compact status line for the LLM."""
    parts = []
    for rnd, info in round_progress.items():
        status = "COMPLETE" if info["completed"] >= info["total"] else "IN PROGRESS"
        parts.append(f"{rnd} {status} ({info['completed']}/{info['total']})")
    return "Round status: " + " | ".join(parts)


def _fmt_games(games: list[dict]) -> str:
    """Format game results as compact semicolon-delimited string with scores."""
    parts = []
    for g in games:
        parts.append(f"{g['winner']} {g.get('winner_score', '?')}-{g.get('loser_score', '?')} {g['loser']}")
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


def _format_submitter_lines(submitters: list[dict]) -> list[str]:
    """Build pipe-delimited status lines for each submitter."""
    lines = []
    for s in submitters:
        parts = [s["mention"]]
        today_busts = s.get("today_busts", [])
        today_survs = s.get("today_survivors", [])
        if today_busts:
            parts.append(f"NEW BUSTS: {_fmt_busts(today_busts)}")
        if today_survs:
            parts.append(f"NEW ALIVE: {_fmt_survs(today_survs)}")
        if s["busts"]:
            parts.append(f"ALL BUSTS: {_fmt_busts(s['busts'])}")
        if s["survivors"]:
            parts.append(f"ALL ALIVE: {_fmt_survs(s['survivors'])}")
        if not s["busts"] and not s["survivors"]:
            parts.append("No activity")
        lines.append(" | ".join(parts))
    return lines


def _determine_digest_context(submitters: list[dict]) -> str:
    """Return the context sentence for the digest based on today's activity."""
    today_quiet = all(not s.get("today_busts") and not s.get("today_survivors") for s in submitters)
    has_history = any(s["busts"] or s["survivors"] for s in submitters)
    if today_quiet and not has_history:
        return "No games yet. Brackets untouched."
    if today_quiet and has_history:
        return "No new results. Frame around the round that just finished, not the schedule."
    return "New results today. Focus on NEW, use ALL for overall context."


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

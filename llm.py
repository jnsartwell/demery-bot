import base64
import json
import re

import aiohttp
import anthropic

client = anthropic.AsyncAnthropic()

SYSTEM_PROMPT = """\
You are Demery — sharp, hilarious, and a passionate March Madness fanatic.
You love your friends deeply, which is exactly why you won't let them get away
with having bad bracket energy. You talk like a real person: casual, punchy,
rarely ALL CAPS — only when something truly deserves it. Reference general
bracket wisdom ("everyone knows you never pick against a hot mid-major"),
make it feel personal even without specifics, and end with something that stings
just a little. Keep it to 2-3 sentences max. Keep it clean — no profanity, no
slurs, nothing that would make HR uncomfortable. You're a friend busting chops,
not a roast battle opponent — sharp wit with a wink, not scorched earth.

Intensity levels:
- mild: light, affectionate ribbing — almost a compliment if you squint
- medium: sharp and fun; the kind of thing that gets a laugh and a groan
- harsh: the most pointed you get — but it still lands with a wink, not a wound\
"""


async def generate_taunt(
    target_name: str,
    intensity: str,
    bracket_data: dict | None = None,
) -> str:
    content = f"Taunt {target_name} at {intensity} intensity."
    if bracket_data:
        content += (
            f"\n\nTheir actual bracket picks:"
            f"\n- Champion: {bracket_data['champion']}"
            f"\n- Championship game: {', '.join(bracket_data['championship_game'])}"
            f"\n- Final Four: {', '.join(bracket_data['final_four'])}"
            f"\n- Elite Eight: {', '.join(bracket_data['elite_eight'])}"
            f"\n\nMake the roast specific to their picks where it's funny."
        )
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
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


async def generate_submission_ack(display_name: str, picks: dict) -> str:
    champion = picks.get("champion", "somebody")
    content = (
        f"{display_name} just submitted their bracket — they picked {champion} to win it all. "
        "Give a one-line playful Demery reaction, like you just got handed ammo to use later."
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

    prompt = """\
This is a March Madness bracket image. Extract the user's PICKS for each round.

IMPORTANT CONTEXT:
- This may be a screenshot from ESPN, Yahoo, CBS, or any other bracket provider, taken mid-tournament.
- Different apps use different visual indicators for results: green circles, checkmarks, highlights for correct picks; red X marks, strikethroughs, grayed-out or faded names for wrong picks. Ignore all of these indicators.
- We want the user's ORIGINAL PICKS, not actual results. Extract every team they picked to advance in each round, whether that pick was correct or not.
- Eliminated or busted picks may appear faded, crossed out, or marked wrong — extract them anyway.

Use full ESPN display names (e.g. "Duke Blue Devils", "Arizona Wildcats", "UConn Huskies").

RESPOND WITH ONLY RAW JSON. No markdown, no code fences, no explanation, no text before or after.
Your entire response must be valid JSON and nothing else.

{
  "round_of_32": ["<32 team names — teams picked to win the First Round>"],
  "sweet_16": ["<16 team names — teams picked to win the Second Round>"],
  "elite_eight": ["<8 team names — teams picked to win the Sweet 16>"],
  "final_four": ["<4 team names — teams picked to win the Elite Eight>"],
  "championship_game": ["<2 team names — teams picked to win the Final Four>"],
  "champion": "<1 team name — picked to win the Championship>"
}

If you cannot read the bracket clearly or any round is missing, respond with only:
{"error": "reason the bracket could not be parsed"}"""

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
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    print(f"parse_bracket_image raw response ({len(raw)} chars): {raw[:200]}")

    # Try to extract JSON from markdown code fences or surrounding text
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()
    elif not raw.startswith("{"):
        # Find the outermost balanced JSON object using non-greedy match
        # by looking for the last } that forms valid JSON with the first {
        start = raw.find("{")
        if start != -1:
            raw = raw[start:]
            # Trim trailing non-JSON text by trying progressively shorter substrings
            for end in range(len(raw), 0, -1):
                if raw[end - 1] == "}":
                    try:
                        json.loads(raw[:end])
                        raw = raw[:end]
                        break
                    except json.JSONDecodeError:
                        continue

    try:
        picks = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse bracket JSON from image: {e}") from e

    if "error" in picks:
        raise ValueError(f"Claude could not read bracket: {picks['error']}")

    required_keys = {
        "round_of_32", "sweet_16", "elite_eight",
        "final_four", "championship_game", "champion",
    }
    missing = required_keys - picks.keys()
    if missing:
        raise ValueError(f"Bracket picks missing rounds: {missing}")

    return picks


async def normalize_team_names(picks: dict, espn_names: list[str]) -> dict:
    """
    Normalize team names in picks to match ESPN's exact displayName values.
    Uses Haiku to resolve abbreviations, nicknames, and minor differences.
    """
    if not espn_names:
        return picks

    all_pick_names = []
    for key in ["round_of_32", "sweet_16", "elite_eight", "final_four", "championship_game"]:
        all_pick_names.extend(picks.get(key, []))
    if picks.get("champion"):
        all_pick_names.append(picks["champion"])
    unique_picks = list(set(all_pick_names))

    prompt = f"""\
Match each team name from a user's bracket picks to the closest ESPN official team name.

ESPN official names:
{json.dumps(sorted(espn_names))}

User's bracket names:
{json.dumps(unique_picks)}

Return a JSON object mapping each user name to the correct ESPN name.
If a user name already exactly matches an ESPN name, include it unchanged.
If a user name has no plausible ESPN match, keep the original.

RESPOND WITH ONLY RAW JSON. No markdown, no explanation.
Example: {{"Duke": "Duke Blue Devils", "UConn Huskies": "Connecticut Huskies"}}"""

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()

    try:
        name_map = json.loads(raw)
    except json.JSONDecodeError:
        print(f"normalize_team_names: failed to parse response, skipping. Raw: {raw[:200]}")
        return picks

    if not isinstance(name_map, dict):
        print(f"normalize_team_names: expected dict, got {type(name_map).__name__}, skipping")
        return picks

    def _replace(name):
        val = name_map.get(name, name)
        return val if isinstance(val, str) else name  # guard against non-string values

    normalized = {}
    for key in ["round_of_32", "sweet_16", "elite_eight", "final_four", "championship_game"]:
        normalized[key] = [_replace(t) for t in picks.get(key, [])]
    normalized["champion"] = _replace(picks.get("champion", ""))

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
    lines = []
    for s in submitters:
        parts = [f"{s['mention']} ({s['name']})"]
        if s["busts"]:
            bust_strs = [
                f"{b['team']} (picked to reach {b['picked_to_reach']}, lost in {b['lost_in']})"
                for b in s["busts"]
            ]
            parts.append("Busts: " + "; ".join(bust_strs))
        if s["survivors"]:
            survivor_strs = [
                f"{sv['team']} (still alive through {sv['still_alive_through']})"
                for sv in s["survivors"]
            ]
            parts.append("Survivors: " + "; ".join(survivor_strs))
        if not s["busts"] and not s["survivors"]:
            parts.append("No bracket activity today")
        lines.append(" | ".join(parts))

    all_quiet = all(not s["busts"] and not s["survivors"] for s in submitters)
    context = (
        "No games were played today — brackets are untouched."
        if all_quiet else
        "Here's how everyone's bracket is looking after today's games."
    )
    content = (
        f"{context} Bracket status:\n\n"
        + "\n".join(lines)
        + "\n\nWrite a Demery-style daily bracket update. "
        "Open with a fresh, varied line that fits the vibe — don't always start the same way. "
        "Mention each person by their Discord tag. "
        "For busts: roast them with context — if you had a team going to the championship "
        "and they lost in the Elite Eight, that's richer material than a generic loss. "
        "For survivors: sarcastically praise them like they don't deserve it. "
        "For anyone with no activity: give a backhanded 'somehow still intact' acknowledgement. "
        "If no games were played, keep it short and pointed — acknowledge the calm before the storm. "
        "One or two punchy sentences per person. Address ALL submitters — no one gets skipped."
    )
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
    return response.content[0].text

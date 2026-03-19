import base64
import json

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
This is a March Madness bracket image. Extract all picks by round and return them as JSON.

Use full ESPN display names (e.g. "Duke Blue Devils", "Arizona Wildcats", "UConn Huskies").

Return ONLY valid JSON in exactly this format:
{
  "round_of_32": ["<32 team names — teams that won the First Round>"],
  "sweet_16": ["<16 team names — teams that won the Second Round>"],
  "elite_eight": ["<8 team names — teams that won the Sweet 16>"],
  "final_four": ["<4 team names — teams that won the Elite Eight>"],
  "championship_game": ["<2 team names — teams that won the Final Four>"],
  "champion": "<1 team name — winner of the Championship>"
}

If you cannot read the bracket clearly or any round is missing, return:
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
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

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

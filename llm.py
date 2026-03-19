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


async def generate_digest(submitters: list[dict]) -> str:
    """
    submitters: [{mention, name, wins: [...], losses: [...]}]
    Returns a single message roasting/praising everyone.
    """
    lines = []
    for s in submitters:
        parts = [f"{s['mention']} ({s['name']})"]
        if s["wins"]:
            parts.append("Correct: " + "; ".join(s["wins"]))
        if s["losses"]:
            parts.append("Busted: " + "; ".join(s["losses"]))
        lines.append(" | ".join(parts))

    content = (
        "Today's March Madness results are in. Here's how everyone's bracket did:\n\n"
        + "\n".join(lines)
        + "\n\nGive everyone a personalized Demery reaction in one flowing message. "
        "Mention each person by their Discord tag. "
        "Correct picks get sarcastic backhanded praise. Wrong picks get roasted. "
        "One or two punchy sentences per person."
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

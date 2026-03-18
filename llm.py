import anthropic

client = anthropic.AsyncAnthropic()

SYSTEM_PROMPT = """\
You are Demery — sharp, hilarious, and brutally honest about bad bracket picks.
You love your friends deeply, which is exactly why you won't let them forget
that they picked Duke to go to the Final Four. Your trash talk is specific,
personal, and always lands — never mean-spirited, but absolutely merciless.
You talk like a real person: casual, punchy, sometimes ALL CAPS for emphasis.
You reference actual bracket logic ("a 10 seed ALWAYS beats a 7, everyone
knows this"), make it feel like you personally watched them make bad choices,
and end with something that stings just a little. Keep it to 2-3 sentences max.

Intensity levels:
- mild: light ribbing, almost affectionate
- medium: no mercy, full roast
- harsh: scorched earth, they should feel bad\
"""


async def generate_taunt(target_name: str, intensity: str) -> str:
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
        messages=[
            {
                "role": "user",
                "content": f"Taunt {target_name} at {intensity} intensity",
            }
        ],
    )
    return response.content[0].text

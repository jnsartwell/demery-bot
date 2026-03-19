import asyncio
import aiohttp
from urllib.parse import urlparse, parse_qs

ESPN_BRACKET_API = (
    "https://fantasy.espn.com/tournament-challenge-bracket/2026/en/api/v3/entry"
)
ESPN_TEAMS_API = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/teams"
)
ESPN_SCOREBOARD_API = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/scoreboard"
)

# pickString slot ranges (0-indexed, 63 total slots):
#   0-31  : Round of 64 winners  → advance to Round of 32
#   32-47 : Round of 32 winners  → advance to Sweet 16
#   48-55 : Sweet 16 winners     → advance to Elite 8
#   56-59 : Elite 8 winners      → advance to Final Four
#   60-61 : Final Four winners   → advance to Championship
#   62    : Championship winner  → Champion


def parse_entry_id(url: str) -> str | None:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    for key in ("entryID", "entryId", "entryid"):
        if key in params:
            return params[key][0]
    return None


async def _get_json(
    session: aiohttp.ClientSession, url: str, params: dict = None
) -> dict:
    async with session.get(url, params=params) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


async def _build_team_map(session: aiohttp.ClientSession) -> dict[str, str]:
    data = await _get_json(session, ESPN_TEAMS_API, {"limit": 500})
    teams: dict[str, str] = {}
    for sport in data.get("sports", []):
        for league in sport.get("leagues", []):
            for item in league.get("teams", []):
                t = item.get("team", item)
                teams[str(t["id"])] = t.get("displayName", t.get("name", "Unknown"))
    return teams


def _find_pick_string(data: dict) -> str:
    """Search the ESPN response for a 63-slot pipe-delimited pick string."""
    candidates = [
        data.get("bpi"),
        data.get("e", {}).get("bpi"),
        data.get("pickString"),
        data.get("e", {}).get("pickString"),
    ]
    for c in candidates:
        if isinstance(c, str) and c.count("|") >= 62:
            return c

    # Last resort: walk the whole response tree
    def _search(obj) -> str:
        if isinstance(obj, dict):
            for v in obj.values():
                r = _search(v)
                if r:
                    return r
        elif isinstance(obj, str) and obj.count("|") >= 62:
            return obj
        return ""

    return _search(data)


async def fetch_bracket(entry_id: str) -> dict:
    """Fetch ESPN bracket picks; return decoded team names by round."""
    async with aiohttp.ClientSession() as session:
        data, team_map = await asyncio.gather(
            _get_json(session, ESPN_BRACKET_API, {"entryID": entry_id}),
            _build_team_map(session),
        )

    pick_string = _find_pick_string(data)
    if not pick_string:
        raise ValueError("Could not find pick string in ESPN response")

    picks = [p.strip() for p in pick_string.split("|")]
    if len(picks) < 63:
        raise ValueError(f"Expected ≥63 picks, got {len(picks)}")

    def name(idx: int) -> str:
        return team_map.get(picks[idx], f"Team#{picks[idx]}")

    return {
        "champion": name(62),
        "championship_game": [name(60), name(61)],
        "final_four": [name(i) for i in range(56, 60)],
        "elite_eight": [name(i) for i in range(48, 56)],
    }


async def fetch_today_results(date_str: str) -> list[dict]:
    """
    Fetch completed games for *date_str* (YYYYMMDD).
    Returns [{winner: str, loser: str, round: str}, ...].
    """
    async with aiohttp.ClientSession() as session:
        data = await _get_json(session, ESPN_SCOREBOARD_API, {"dates": date_str})

    results = []
    for event in data.get("events", []):
        if not event.get("status", {}).get("type", {}).get("completed"):
            continue
        competition = event.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        winner = next((c for c in competitors if c.get("winner")), None)
        loser = next((c for c in competitors if not c.get("winner")), None)
        if not winner or not loser:
            continue
        results.append(
            {
                "winner": winner["team"]["displayName"],
                "loser": loser["team"]["displayName"],
                "round": competition.get("type", {}).get("text", "tournament"),
            }
        )
    return results

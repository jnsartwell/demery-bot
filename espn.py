import aiohttp

ESPN_SCOREBOARD_API = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/scoreboard"
)


async def _get_json(
    session: aiohttp.ClientSession, url: str, params: dict = None
) -> dict:
    async with session.get(url, params=params) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


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

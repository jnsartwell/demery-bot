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


_cached_team_names: list[str] = []


async def fetch_tournament_team_names() -> list[str]:
    """
    Fetch all team displayNames from the tournament by scanning scoreboard
    data from the First Four through First Round (all 64+ teams appear).
    Results are cached in memory for the lifetime of the process.
    """
    global _cached_team_names
    if _cached_team_names:
        return _cached_team_names

    # 2026 NCAA Tournament First Round dates — all 64 teams play these two days
    FIRST_ROUND_DATES = ["20260319", "20260320"]

    teams = set()
    async with aiohttp.ClientSession() as session:
        for date_str in FIRST_ROUND_DATES:
            try:
                data = await _get_json(session, ESPN_SCOREBOARD_API, {"dates": date_str})
            except Exception:
                continue
            for event in data.get("events", []):
                for comp in event.get("competitions", []):
                    for c in comp.get("competitors", []):
                        name = c.get("team", {}).get("displayName")
                        if name:
                            teams.add(name)

    _cached_team_names = sorted(teams)
    print(f"Cached {len(_cached_team_names)} ESPN tournament team names")
    return _cached_team_names


async def fetch_today_results(date_str: str) -> list[dict]:
    """
    Fetch completed games for *date_str* (YYYYMMDD).
    Returns [{winner: str, loser: str, round: str}, ...].
    """
    print(f"[espn] Fetching scoreboard for {date_str}")
    async with aiohttp.ClientSession() as session:
        data = await _get_json(session, ESPN_SCOREBOARD_API, {"dates": date_str})

    total_events = len(data.get("events", []))
    results = []
    for event in data.get("events", []):
        completed = event.get("status", {}).get("type", {}).get("completed")
        if not completed:
            name = event.get("name", "unknown")
            status = event.get("status", {}).get("type", {}).get("name", "unknown")
            print(f"[espn]   Skipping incomplete: {name} (status={status})")
            continue
        competition = event.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        winner = next((c for c in competitors if c.get("winner")), None)
        loser = next((c for c in competitors if not c.get("winner")), None)
        if not winner or not loser:
            continue
        # Round name: prefer notes headline, fall back to type.text
        # ESPN headline format: "NCAA Men's Basketball Championship - East Region - 1st Round"
        notes = competition.get("notes", [])
        headline = notes[0].get("headline", "") if notes else ""
        round_name = headline.rsplit(" - ", 1)[-1] if " - " in headline else ""
        if not round_name:
            round_name = competition.get("type", {}).get("text", "tournament")

        results.append(
            {
                "winner": winner["team"]["displayName"],
                "loser": loser["team"]["displayName"],
                "round": round_name,
            }
        )
    print(f"[espn] {total_events} events, {len(results)} completed games returned")
    return results

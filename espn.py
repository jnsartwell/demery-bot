import datetime

import aiohttp

ESPN_SCOREBOARD_API = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"


async def _get_json(session: aiohttp.ClientSession, url: str, params: dict = None) -> dict:
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
            teams.update(_extract_team_names_from_events(data.get("events", [])))

    _cached_team_names = sorted(teams)
    print(f"Cached {len(_cached_team_names)} ESPN tournament team names")
    return _cached_team_names


_cached_results: dict[str, list[dict]] = {}


async def fetch_tournament_results() -> list[dict]:
    """Fetch all completed tournament games from start through today."""
    start = datetime.date(2026, 3, 17)  # First Four
    today = datetime.date.today()
    all_games = []
    d = start
    while d <= today:
        date_str = d.strftime("%Y%m%d")
        if date_str in _cached_results and d < today:
            all_games.extend(_cached_results[date_str])
        else:
            games = await fetch_today_results(date_str)
            _cached_results[date_str] = games
            all_games.extend(games)
        d += datetime.timedelta(days=1)
    return all_games


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
        game = _parse_game_result(event)
        if game:
            results.append(game)
        else:
            name = event.get("name", "unknown")
            status = event.get("status", {}).get("type", {}).get("name", "unknown")
            print(f"[espn]   Skipping: {name} (status={status})")
    print(f"[espn] {total_events} events, {len(results)} completed games returned")
    return results


# --- helpers ---


def _parse_game_result(event: dict) -> dict | None:
    """Parse a single ESPN event into {winner, loser, round} or None if incomplete."""
    completed = event.get("status", {}).get("type", {}).get("completed")
    if not completed:
        return None

    competition = event.get("competitions", [{}])[0]
    competitors = competition.get("competitors", [])
    winner = next((c for c in competitors if c.get("winner")), None)
    loser = next((c for c in competitors if not c.get("winner")), None)
    if not winner or not loser:
        return None

    round_name = _parse_round_name(competition)

    winner_score = int(winner.get("score", 0))
    loser_score = int(loser.get("score", 0))

    return {
        "winner": winner["team"]["displayName"],
        "loser": loser["team"]["displayName"],
        "round": round_name,
        "winner_score": winner_score,
        "loser_score": loser_score,
    }


def _parse_round_name(competition: dict) -> str:
    """Extract round name from competition notes headline, falling back to type.text."""
    # ESPN headline format: "NCAA Men's Basketball Championship - East Region - 1st Round"
    notes = competition.get("notes", [])
    headline = notes[0].get("headline", "") if notes else ""
    if " - " in headline:
        return headline.rsplit(" - ", 1)[-1]
    return competition.get("type", {}).get("text", "tournament")


def _extract_team_names_from_events(events: list[dict]) -> set[str]:
    """Extract all team displayNames from a list of ESPN events."""
    teams = set()
    for event in events:
        for comp in event.get("competitions", []):
            for competitor in comp.get("competitors", []):
                name = competitor.get("team", {}).get("displayName")
                if name:
                    teams.add(name)
    return teams

CREATE TABLE IF NOT EXISTS game_results (
    game_date   TEXT NOT NULL,
    winner      TEXT NOT NULL,
    loser       TEXT NOT NULL,
    round       TEXT NOT NULL,
    PRIMARY KEY (game_date, winner, loser)
);

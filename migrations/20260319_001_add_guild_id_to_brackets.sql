-- Add guild_id to brackets table (existing data dropped — users must re-submit)

DROP TABLE IF EXISTS brackets;

CREATE TABLE brackets (
    discord_user_id INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    display_name    TEXT NOT NULL,
    picks_json      TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    PRIMARY KEY (discord_user_id, guild_id)
);

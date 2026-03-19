-- Add guild_id to brackets table, copy existing rows to all configured guilds
-- Depends on: guild_settings table already existing

CREATE TABLE brackets_new (
    discord_user_id INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    display_name    TEXT NOT NULL,
    picks_json      TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    PRIMARY KEY (discord_user_id, guild_id)
);

INSERT OR IGNORE INTO brackets_new (discord_user_id, guild_id, display_name, picks_json, submitted_at)
    SELECT b.discord_user_id, g.guild_id, b.display_name, b.picks_json, b.submitted_at
    FROM brackets b
    CROSS JOIN guild_settings g;

DROP TABLE brackets;
ALTER TABLE brackets_new RENAME TO brackets;

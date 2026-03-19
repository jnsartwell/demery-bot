-- Revert guild_id addition: collapse back to single-user brackets (keeps last submission per user)

CREATE TABLE brackets_old (
    discord_user_id INTEGER PRIMARY KEY,
    display_name    TEXT NOT NULL,
    picks_json      TEXT NOT NULL,
    submitted_at    TEXT NOT NULL
);

INSERT OR REPLACE INTO brackets_old (discord_user_id, display_name, picks_json, submitted_at)
    SELECT discord_user_id, display_name, picks_json, submitted_at
    FROM brackets
    ORDER BY submitted_at DESC;

DROP TABLE brackets;
ALTER TABLE brackets_old RENAME TO brackets;

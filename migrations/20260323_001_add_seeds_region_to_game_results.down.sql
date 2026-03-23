-- SQLite does not support DROP COLUMN on older versions; recreate table without seed/region columns
CREATE TABLE game_results_backup AS SELECT game_date, winner, loser, round FROM game_results;
DROP TABLE game_results;
ALTER TABLE game_results_backup RENAME TO game_results;

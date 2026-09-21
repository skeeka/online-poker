CREATE TABLE users(
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    pwd_hash TEXT NOT NULL,
    in_use INTEGER NOT NULL,
    total_bb_input INTEGER DEFAULT 0,
    total_bb_output INTEGER DEFAULT 0,
    hands_played INTEGER DEFAULT 0,
    hands_won INTEGER DEFAULT 0,
    hands_lost INTEGER DEFAULT 0,
    vpip_count INTEGER DEFAULT 0,
    pfr_count INTEGER DEFAULT 0,
    aggro_count INTEGER DEFAULT 0,
    passive_count INTEGER DEFAULT 0,
    three_bet_count INTEGER DEFAULT 0
);

CREATE TABLE games(
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    num_players INTEGER,
    name TEXT,
    small_blind INTEGER,
    big_blind INTEGER,
    created_at TEXT
);

CREATE TABLE game_players(
    game_id INTEGER,
    user_id INTEGER,
    starting_chips INTEGER,
    final_chips INTEGER,
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    PRIMARY KEY (game_id,user_id)
);

CREATE TABLE rounds(
    game_id INTEGER,
    round_num INTEGER,
    comm_cards TEXT,
    total_pot INTEGER,
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    PRIMARY KEY (game_id,round_num)
);

CREATE TABLE players_in_round(
    game_id INTEGER,
    round_num INTEGER,
    user_id INTEGER,
    cards TEXT,
    starting_chips INTEGER,
    ending_chips INTEGER,
    FOREIGN KEY (game_id,round_num) REFERENCES rounds(game_id,round_num),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    PRIMARY KEY (game_id,round_num,user_id)
);
# Poker NEA

A multiplayer poker project with an asynchronous Python server, a Pygame client, and SQLite storage for accounts, game history, and statistics.

## Run on Windows

Run commands from the project root. The original source uses Windows-style paths for the SQL setup and poker hand lookup file.

Python 3.12 is suggested, matching the cached interpreter files in the original submission. The original Pygame version was not recorded; `requirements.txt` lists the dependency without inventing a version pin.

```powershell
python -m pip install -r requirements.txt
python main.py
```

In a separate terminal, launch each player client:

```powershell
python client.py
```

To connect to a server on another computer:

```powershell
python client.py --ip <server-ip>
```

The server listens on TCP port 5001. The client connects to `127.0.0.1` by default. Optional client logging: `python client.py --debug`.

## Project files

- `main.py`: starts the server.
- `client.py`: Pygame client.
- `poker/`: game logic, hand evaluator, lookup data, configuration, and database schema.
- `client_assets/`: background and playing-card assets from the original submission.

## Database behaviour

The server creates `poker_game.db` in the working directory if it does not exist. If the `users` table is absent, it runs `poker/setup.sql` to create the application tables. Existing databases are reused, and user login flags are reset at server startup.

All games share this database. Each started game gets a new game record and ID; rounds and player records refer to that ID.

Local database files are intentionally excluded from version control because they contain accounts, password hashes, statistics, and game history. The original `poker_game1.db` is an unused older copy and is not required to run the project.

To reset the data, stop the server and back up or delete `poker_game.db`. The next server start creates a fresh database; users must sign up again.

## Source preservation

The original Python, SQL, lookup data, and assets are preserved. Repository documentation, dependency listing, and ignore rules were added. The NEA PDF is not included.

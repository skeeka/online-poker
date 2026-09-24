# Poker Project

A multiplayer poker project with an asynchronous Python server, a Pygame client, and SQLite storage for accounts, game history, and statistics.

## Run on Windows

Run the commands below from the project root.

You will need Python and Pygame. Install the dependency, then start the server:

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
- `client_assets/`: background and playing-card images.

## Database behaviour

The server creates `poker_game.db` in the working directory if it does not exist. If the `users` table is absent, it runs `poker/setup.sql` to create the application tables. Existing databases are reused, and user login flags are reset at server startup.

All games share this database. Each started game gets a new game record and ID; rounds and player records refer to that ID.

Database files are generated locally and excluded from version control.

To reset the data, stop the server and back up or delete `poker_game.db`. The next server start creates a fresh database; users must sign up again.

from poker.game import *
from poker.player import *
import traceback
import logging
import sys
import sqlite3
import hashlib
from poker.gameconfig import GAME_CONFIG

from poker.logger_config import setup_logger

logger = setup_logger(__name__)

class Server:
    """The server is what hosts the games, and what players will connect to to join games."""
    def __init__(self):
        self.__player_dict = dict() # Tracks writer to player mapping
        self.__player_game_dict = dict() # Tracks which game each player is in
        self.__active_games = {} # Tracks all the currently active games
        self.__db_setup()

        self.__queries = {
            "PERSONAL": """
                SELECT
                    username,
                    hands_played,
                    hands_won,
                    ROUND(CAST(hands_won AS FLOAT) / NULLIF(hands_played,0) * 100, 2) as win_rate,
                    ROUND(CAST(vpip_count AS FLOAT) / NULLIF(hands_played,0) * 100, 2) as vpip,
                    ROUND(CAST(pfr_count AS FLOAT) / NULLIF(hands_played,0) * 100, 2) as pfr,
                    ROUND(CAST(aggro_count AS FLOAT) / NULLIF(passive_count,0), 2) as aggression
                FROM users
                WHERE user_id = ?""",
            "LEADERBOARD": """
                SELECT
                    username,
                    hands_played,
                    ROUND(CAST(hands_won AS FLOAT) / NULLIF(hands_played,0) * 100, 2) as win_rate,
                    ROUND(SUM(gp.final_chips - gp.starting_chips) / NULLIF(g.big_blind,0),2) as total_bb_profit
                FROM users as u
                INNER JOIN game_players as gp ON u.user_id = gp.user_id
                INNER JOIN games as g ON gp.game_id = g.game_id
                WHERE u.hands_played > 0
                    AND gp.starting_chips IS NOT NULL
                    AND gp.final_chips IS NOT NULL
                GROUP BY u.user_id
                ORDER BY win_rate DESC, total_bb_profit DESC
                """,
            "GLOBAL": """
                SELECT
                    (SELECT COUNT(*) FROM games) as total_games,
                    (SELECT COUNT(*) FROM users) as total_players,
                    ROUND(AVG(CAST(hands_won AS FLOAT) / NULLIF(hands_played,0) * 100), 2) as avg_win_rate,
                    MAX(hands_played) as most_hands_played
                FROM users
                WHERE hands_played > 0
                """
                        }

    def __db_setup(self):
        """Connects to the database, and creates the cursor"""
        self.__db_conn = sqlite3.connect("poker_game.db")
        self.__db_cursor = self.__db_conn.cursor() # Cursor used to interact with db
        self.__init_db()

    def __init_db(self):
        """Creates the database if it doesn't exist."""
        self.__db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'") # Checks if users table (and by extension the other tables) exist
        if self.__db_cursor.fetchone() is None:
            with open("poker\\setup.sql","r") as setup_file:
                setup = setup_file.read()
                self.__db_cursor.executescript(setup)
        self.__db_cursor.execute("UPDATE users SET in_use = 0") # Marks all the users as inactive, so they can be signed into
        self.__db_conn.commit()

    def json_message(self, message):
        """Format for most communications between client and server"""
        return {"type": "message-state",
                "message": message}

    async def remove_player(self, player):
        """Closes the client connection"""
        writer = player.writer
        writer.close()
        await writer.wait_closed()

    async def shut_down(self,game):
        """Shuts down a game by closing all the clients connected, and removing them from the game"""
        for player in game.get_players():
            game.get_rid_of(player)
            await self.remove_player(player)

        self.__db_cursor.execute("SELECT round_num,comm_cards FROM rounds WHERE game_id = ? ORDER BY round_num DESC",(game.get_game_id(),))
        result = self.__db_cursor.fetchone()
        if result:
            round_num,comm_cards = result
        else:
            round_num,comm_cards = None,None
        if round_num:
            if comm_cards is None:
                self.__db_cursor.execute("DELETE FROM rounds WHERE game_id = ? AND round_num = ?",(game.get_game_id(),round_num))
                self.__db_cursor.execute("DELETE FROM players_in_round WHERE game_id = ? AND round_num = ?",(game.get_game_id(),round_num))
        self.__db_conn.commit()

    async def send_message(self, player, data):
        """Sends a message to a certain player"""
        message = json.dumps(data)
        writer = player.writer
        message += "\n"
        writer.write(message.encode())
        logger.debug(f"sent {message}")
        await writer.drain()

    async def send_all(self,game, message, exclude=None):
        """Sends the same message to all players, with the option to exclude a player"""
        for player in game.get_players():
            if player != exclude:
                await self.send_message(player, message)

    async def __send_writer(self,writer,data):
        """Similar to send message, but passes writer directly instead of player object"""
        message = json.dumps(self.json_message(data))
        message += "\n"
        writer.write(message.encode())
        logger.debug(f"sent {message}")
        await writer.drain()

    def json_query_result(self,result,type):
        """Message to be sent to client as the result of a db query"""
        return {"type":"query-result",
                "result":result,
                "req":type}

    async def __choose_game_action(self,reader,writer,player):
        """Once a player is signed in, they can decide to create or join a game."""
        finished = False
        while not finished:
            await self.__send_writer(writer,"Create (C) or Join (J) a game, or view some stats: ")
            data = await reader.readline()
            input = json.loads(data.decode())
            if input.get("type","none") == "query":
                result = self.db_execute_query(self.__queries[input["req"]],input["params"])
                await self.send_message(player,self.json_query_result(result,input["req"]))
            else:
                try:
                    choice = input["message"].strip().upper()
                except ValueError:
                    choice = ""

                if choice == "C":
                    finished = True
                    return await self.__create_new_game(reader,writer,player)
                elif choice == "J":
                    finished = True
                    return await self.__join_existing_game(reader,writer,player)

    def __validate_game_name(self,game_name):
        """Ensures the game name is suitable (length and type) and is not currently in use"""
        return game_name.isalnum() and len(game_name) in range(5,21) and game_name not in self.__active_games

    def __validate_username(self,username):
        """Validates the username selected by the player, ensuring it is of a suitable length and type"""
        return bool(re.match(r"^[a-zA-Z]{1}[a-zA-Z0-9_]{3,9}$",username)) # Name between 4 and 10 characters, cannot start with _ or 0-9

    async def __get_num_players(self,reader,writer):
        """If creating a game, this function ensures a suitable number of players is entered"""
        await self.__send_writer(writer,"Input number players (2-8): ")
        while True:
            data = await reader.readline()
            value = json.loads(data.decode())["message"].strip()
            try:
                if int(value) in range(2,9):
                    return int(value)
                else:
                    raise ValueError
            except ValueError:
                await self.__send_writer(writer,f"Invalid input, must be 2-8 players. Try again: ")

    async def __create_new_game(self,reader,writer,player):
        """If the player opts to create a game this function facilitates the creation."""
        try:
            await self.__send_writer(writer, "Enter game name (5-20 characters): ")
            data = await reader.readline()
            game_name = json.loads(data.decode())["message"].strip()
            while not self.__validate_game_name(game_name):
                await self.__send_writer(writer, "Game name either already exists or is invalid. Enter game name (5-20 characters): ")
                data = await reader.readline()
                game_name = json.loads(data.decode())["message"].strip()

            num_players = await self.__get_num_players(reader,writer)

            game = Game(game_name,num_players,server=self) # Creates the game object
            self.__active_games[game_name] = game # Adds the game to the active games
            started = await game.add_new_player(player)

            await self.__send_writer(writer, f"Game created successfully: {game_name}. Waiting...") # Informs player of success
            return game
        except Exception as e:
            logger.error(f"Error creating game: {e}")
            return self.__create_new_game(reader,writer,player)

    def db_start_round_update(self,game_id,round_num,players):
        """Before each round, the database is update with information about the upcoming round"""
        self.__db_cursor.execute("INSERT INTO rounds(game_id,round_num) VALUES (?,?)",(game_id,round_num))

        for player in players:
            player_id = player.get_id()
            player_chips = player.get_chips()
            self.__db_cursor.execute("INSERT INTO players_in_round(game_id,round_num,user_id,starting_chips,ending_chips) VALUES (?,?,?,?,?)",(game_id,round_num,player_id,player_chips,0))
        self.__db_conn.commit()

    def request_starting_chips(self,game_id,round_num,player):
        """Database request for starting chips of a player in a given game and round"""
        self.__db_cursor.execute("SELECT starting_chips FROM players_in_round WHERE game_id = ? AND round_num = ? AND user_id = ?",(game_id,round_num,player.get_id()))
        starting_chips = self.__db_cursor.fetchone()[0]
        return starting_chips

    def db_end_round_update(self,game_id,round_num,comm_cards,total_pot,players,win_dict):
        """After each round, we complete the database update for that round, adding any new information"""
        comm_list = [str(card) for card in comm_cards]
        comm_str = "".join(comm_list)
        self.__db_cursor.execute("UPDATE rounds SET comm_cards = ?,total_pot = ? WHERE game_id = ? AND round_num = ?",(comm_str,total_pot,game_id,round_num))

        for player in players:
            player_id = player.get_id()
            chips = player.get_chips()
            cards = player.get_hand()
            card_list = [str(card) for card in cards]
            card_str = "".join(card_list)
            self.__db_cursor.execute("UPDATE players_in_round SET cards = ?,ending_chips = ? WHERE game_id=? AND round_num=? AND user_id=?",(card_str,chips,game_id,round_num,player_id))
            if win_dict[player_id] > 0:
                self.__db_cursor.execute("UPDATE users SET hands_played = hands_played + 1,hands_won = hands_won + 1 WHERE user_id = ?",(player_id,))
            elif win_dict[player_id] < 0:
                self.__db_cursor.execute("UPDATE users SET hands_played = hands_played + 1,hands_lost = hands_lost + 1 WHERE user_id = ?",(player_id,))
            else:
                self.__db_cursor.execute("UPDATE users SET hands_played = hands_played + 1 WHERE user_id = ?",(player_id,))

        self.__db_conn.commit()

    def increment_vpip(self,player):
        """Voluntary Put In Pot i.e., limps, calls or raises preflop"""
        player_id = player.get_id()
        self.__db_cursor.execute("UPDATE users SET vpip_count = vpip_count + 1 WHERE user_id = ?",(player_id,))
        self.__db_conn.commit()

    def increment_pfr(self,player,vpip):
        """Pre-Flop Raise i.e., raises preflop, and can count towards VPIP"""
        player_id = player.get_id()
        if not vpip:
            self.increment_vpip(player)
        self.__db_cursor.execute("UPDATE users SET pfr_count = pfr_count + 1 WHERE user_id = ?",(player_id,))
        self.__db_conn.commit()

    def increment_aggro(self,player):
        """Aggressive actions i.e., raises"""
        player_id = player.get_id()
        self.__db_cursor.execute("UPDATE users SET aggro_count = aggro_count + 1 WHERE user_id = ?",(player_id,))
        self.__db_conn.commit()

    def increment_passive(self,player):
        """Passive actions i.e., calls or checks"""
        player_id = player.get_id()
        self.__db_cursor.execute("UPDATE users SET passive_count = passive_count + 1 WHERE user_id = ?",(player_id,))
        self.__db_conn.commit()

    def increment_3bet(self,player):
        """A re-raise preflop (specifically the 3rd bet where BB counts as the 1st)"""
        player_id = player.get_id()
        self.__db_cursor.execute("UPDATE users SET three_bet_count = three_bet_count + 1 WHERE user_id = ?",(player_id,))
        self.__db_conn.commit()

    def db_insert_game(self,game):
        """When a game is begins, the database is updated to include the new game"""
        num = game.get_max_players()
        name = game.get_game_name()
        sb = game.get_sb()
        bb = game.get_bb()
        time = game.get_start_time()
        self.__db_cursor.execute("INSERT INTO games(num_players,name,small_blind,big_blind,created_at) VALUES (?,?,?,?,?)",(num,name,sb,bb,time))
        game_id = self.__db_cursor.lastrowid
        game.set_game_id(game_id)
        for player in game.get_players():
            player_id = player.get_id()
            chips = player.get_chips()
            big_blinds = chips / bb
            self.__db_cursor.execute("UPDATE users SET total_bb_input = total_bb_input + ? WHERE user_id = ?",(big_blinds,player_id))
            self.__db_cursor.execute("INSERT INTO game_players(game_id,user_id,starting_chips,final_chips) VALUES (?,?,?,?)",(game_id,player_id,chips,0))
        self.__db_conn.commit()

    def db_execute_query(self,query,params):
        """Executes a given query with the given parameters"""
        self.__db_cursor.execute(query,params)
        return self.__db_cursor.fetchall()

    async def __join_existing_game(self,reader,writer,player):
        """If a player decides to join a game, this function aids them in that, ensuring they enter a name of an active game"""
        while True:
            await self.__send_writer(writer, "Enter name of game to join: ")
            data = await reader.readline()
            game_name = json.loads(data.decode())["message"].strip()

            if game_name in self.__active_games:
                game = self.__active_games[game_name]
                if not game.check_full():
                    started = await game.add_new_player(player)
                    await self.__send_writer(writer, f"You have joined: {game_name}")
                    if started:
                        self.db_insert_game(game)
                    return game
                else:
                    await self.__send_writer(writer,"Game full, please try a different game.")
            else:
                await self.__send_writer(writer,"Game not found, please try a different game.")

    def json_login(self,player):
        """Confirmation that a user has logged in, allowing them to begin viewing stats"""
        return {"type":"login-confirm",
                "id":player.get_id()}

    async def __handle_client(self, reader, writer):
        """
        This is the main function that handles a client, and any new connection will call this function.
        It continuously listens for incoming messages from clients, then has the relevant game handle the message.
        """
        user_client = None
        try:
            (id,name) = await self.__handle_new_player(reader, writer)
            user_client = Player(reader, writer, id, name,GAME_CONFIG["GAME"]["CHIPS"])
            self.__player_dict[writer] = user_client
            await self.send_message(user_client,self.json_login(user_client))

            game = await self.__choose_game_action(reader,writer,user_client)
            self.__player_game_dict[user_client] = game

            while not user_client.get_player_eliminated():
                data = await reader.readline()
                if not data:
                    break

                message = data.decode()

                if user_client.get_player_eliminated():
                    break
                elif json.loads(message)["message"].strip() == "exit":
                    raise Exception("Client requested exit")
                else:
                    await self.__player_game_dict[user_client].evaluate_message(user_client, message)

            logger.info(f"Client Eliminated: {user_client.get_name()}")
            raise Exception("Client Eliminated")

        except Exception as e:
            logger.debug(f"Client excepted {e}")

        finally:
            await self.__handle_client_cleanup(user_client)



    async def __handle_client_cleanup(self,user_client):
        """When a client is eliminated from the game, or for some unexpected reason they exit the game, this handles their departure"""
        if user_client and user_client in self.__player_game_dict:
            game = self.__player_game_dict[user_client]

            """Here we update the database to account for their departure"""
            if game.get_started():
                final_bb = user_client.get_chips()/game.get_bb()
                self.__db_cursor.execute("UPDATE users SET in_use = 0,total_bb_output=total_bb_output+? WHERE user_id = ?",(final_bb,user_client.get_id()))
                self.__db_cursor.execute("UPDATE game_players SET final_chips = ? WHERE user_id = ?",(user_client.get_chips(),user_client.get_id()))
                if len(game.get_players()) > 1:
                    await game.send_all_game_states()
                else:
                    for player in game.get_players():
                        final_bb = player.get_chips()/game.get_bb()
                        self.__db_cursor.execute("UPDATE users SET in_use = 0,total_bb_output=total_bb_output+? WHERE user_id = ?",(player.get_id(),final_bb))
                        self.__db_cursor.execute("UPDATE game_players SET final_chips = ? WHERE user_id = ?",(player.get_chips(),player.get_id()))
                    await self.shut_down(game)

            if game in self.__active_games.values():
                self.__active_games.pop(game.get_game_name())

        if user_client:
            self.__db_cursor.execute("UPDATE users SET in_use = 0 WHERE user_id = ?",(user_client.get_id(),))
        self.__db_conn.commit()
        if user_client and user_client.writer:
            user_client.writer.close()
            await user_client.writer.wait_closed()

    async def __handle_new_player(self, reader, writer):
        """Handles whether a new player wishes to sign up or log in"""
        await self.__send_writer(writer,"Login (L) or Signup (S): ")

        while True:
            data = await reader.readline()
            if not data:
                break

            choice = json.loads(data.decode())["message"].strip()

            if choice.upper() == "L":
                return await self.__login_user(reader,writer)
            elif choice.upper() == "S":
                return await self.__signup_user(reader,writer)
            else:
                await self.__send_writer(writer,"Invalid choice, please enter 'L' or 'S': ")

    async def __login_user(self,reader,writer):
        """Handles the login of an existing user"""
        await self.__send_writer(writer,"Enter username: ")
        username_data = await reader.readline()
        username = json.loads(username_data.decode())["message".strip()]

        await self.__send_writer(writer,"Enter password: ")
        password_data = await reader.readline()
        password = json.loads(password_data.decode())["message".strip()]

        self.__db_cursor.execute("SELECT * FROM users WHERE username = ?",(username,))
        result = self.__db_cursor.fetchone()

        if result and result[2] == hashlib.sha256(password.encode()).hexdigest() and not result[3]:
            self.__db_cursor.execute("UPDATE users SET in_use = 1 WHERE username = ?",(username,))
            self.__db_conn.commit()
            await self.__send_writer(writer,f"Welcome back, {username}!")
            logger.info(f"login {result,result[0]}")
            return (result[0],username)
        else:
            return await self.__handle_new_player(reader,writer)

    async def __signup_user(self,reader,writer):
        """Handles the sign up of a new user"""
        await self.__send_writer(writer,"Enter username (4-10 chars): ")
        username_data = await reader.readline()
        username = json.loads(username_data.decode())["message".strip()]
        while not self.__validate_username(username): # Validate username to prevent injection
            await self.__send_writer(writer,"Invalid username. Enter username (4-10 chars): ")
            username_data = await reader.readline()
            username = json.loads(username_data.decode())["message".strip()]

        await self.__send_writer(writer,"Enter password: ") 
        password_data = await reader.readline()
        password = json.loads(password_data.decode())["message".strip()]

        self.__db_cursor.execute("SELECT username FROM users WHERE username = ?",(username,))
        if self.__db_cursor.fetchone():
            await self.__send_writer(writer,"Username already exists. Please try again.")
            return await self.__handle_new_player(reader,writer)

        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        self.__db_cursor.execute("INSERT INTO users (username, pwd_hash,in_use) VALUES (?, ?, ?)", (username, pwd_hash,1))
        self.__db_conn.commit()

        self.__db_cursor.execute("SELECT user_id FROM users WHERE username = ?",(username,))
        user_id = self.__db_cursor.fetchone()[0]

        await self.__send_writer(writer, f"Successfully registered. Welcome {username}!")
        return (user_id,username)

    async def main(self):
        server = await asyncio.start_server(self.__handle_client, "0.0.0.0", 5001)

        addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        logger.info(f"Serving on: {addrs}")

        async with server:
            await server.serve_forever()
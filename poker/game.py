import asyncio
import json
import re
import logging
import sys
from datetime import datetime
from enum import Enum

from poker.evaluator import *
from poker.deck import *
from poker.lookup import *
from poker.pot import *
from poker.gameconfig import GAME_CONFIG
from poker.structs import Queue
from poker.logger_config import setup_logger

logger = setup_logger(__name__)

class GameState(Enum):
    JOINING = "JOINING"
    WAITING = "WAITING"
    PLAYING = "PLAYING"
    ENDED = "ENDED"

class Game:
    """The Game class is what runs all the game logic and handles messages"""
    def __init__(self,name,num_players,server):
        # Info about the game and its status
        self.__state = GameState.JOINING
        self.__max_players = num_players
        self.__game_name = name
        self.__started = False
        self.__start_time = datetime.now().isoformat()
        self.__game_id = 0

        # Setting up the server methods
        self.__server = server
        self.__setup_server_methods()

        # Evaluator used in hand evaluation
        self.__evaluator = HandEvaluator(LookupManager())

        # Lists of players used for various purposes
        self.__players = [] # All the players in the game
        self.__active_players = [] # The players still active in a given hand
        self.__all_in_players = []
        self.__all_in_queue = []
        self.__dealer_queue = []
        self.__player_turn = 3

        # Game Info
        self.__sb = GAME_CONFIG["GAME"]["SMALL_BLIND"]
        self.__bb = GAME_CONFIG["GAME"]["BIG_BLIND"]
        self.__phase = 0
        self.__highest_bet = 0
        self.__last_raise = self.__bb # Initialised to bb, to set the min raise
        self.__raise_counter = 0 # Used to detect 3bets
        self.__table = []
        self.__pass_count = 0 # Used to tell if a round is over ("passes" vs num players)
        self.__round_num = 0

        # Input tracker
        self.__input_complete = asyncio.Event()

    def get_max_players(self):
        return self.__max_players

    def get_game_name(self):
        return self.__game_name

    def get_start_time(self):
        return self.__start_time

    def get_sb(self):
        return self.__sb

    def get_bb(self):
        return self.__bb

    def __reset_game(self):
        """Resets betweens hands, i.e., people have won/lost chips and are about to be dealt new hands"""
        self.__table = []
        self.__phase = 0
        self.__all_in_players = []
        self.__all_in_queue = []
        self.__player_turn = 3 % len(self.__dealer_queue)

        for player in self.__players:
            player.set_vpip_in_round(False)
            player.set_raised_in_round(False)

    def __reset_phase(self):
        """Resets all the variables used to track various things between phases"""
        for player in self.__players:
            player.set_bet(0)
            player.set_last_action("")

        self.__raise_counter = 0
        self.__player_turn = 1
        self.__highest_bet = 0
        self.__last_raise = self.__bb
        self.__pass_count = 0
        self.__all_in_queue = []

    def get_players(self):
        return self.__players

    def get_game_id(self):
        return self.__game_id

    def set_game_id(self,id):
        self.__game_id = id

    def get_started(self):
        return self.__started

    def __setup_server_methods(self):
        """Server methods to allow game to make changes easily"""
        self.__send_message = self.__server.send_message
        self.__send_all = self.__server.send_all
        self.__shut_down = self.__server.shut_down
        self.__db_start_round_update = self.__server.db_start_round_update
        self.__db_end_round_update = self.__server.db_end_round_update
        self.__increment_vpip = self.__server.increment_vpip
        self.__increment_pfr = self.__server.increment_pfr
        self.__increment_aggro = self.__server.increment_aggro
        self.__increment_passive = self.__server.increment_passive
        self.__increment_3bet = self.__server.increment_3bet
        self.request_starting_chips = self.__server.request_starting_chips

    def get_state(self):
        return self.__state

    def get_game_over_state(self,win_dict,current_player):
        """Game over state sent once the game ends to all players, with info about the other players and their hands"""
        try:
            state = {
                "type": "game-over",
                "winners": self.__process_win_dict(win_dict,current_player),
                "hands": {int(player.get_id()):[card.printable() for card in player.get_hand()] for player in self.__dealer_queue if player != current_player}
            }
        except Exception as e:
            logger.error(f"Error occured in game over state: {e}")

        return state

    def __process_win_dict(self,win_dict,player):
        try:
            temp = win_dict.copy()
            if player.get_id() in temp:
                temp.pop(player.get_id())
        except Exception as e:
            logger.error(f"error processing win dict {e}")
        return temp

    def __get_game_state(self, current_player):
        """
        Game state for a given player, that contains info specifically for them, such as their hand and chips,
        as well as some public info about other players, such as chips or last action.
        """
        try:
            state = {
                "type": "game-state",
                "name": "",
                "pos": -1,
                "id": current_player.get_id(),
                "players": [],
                "order": [],
                "community": [],
                "hand": [],
                "total": 0,
                "current_bet": 0,
                "min_raise": 0,
                "current_player": -1,
                "available_actions": [],
                "chips": 0,
                "game_over": self.__state == GameState.ENDED
            }

            state["name"] = current_player.get_player_name()
            state["self"] = current_player.get_player_state()
            state["players"] = [player.get_player_state() for player in self.__players if player != current_player]
            state["order"] = [player.get_id() for player in self.__dealer_queue]
            state["pos"] = self.__dealer_queue.index(current_player)
            state["community"] = [card.json_rep() for card in self.__table]
            state["hand"] = [card.json_rep() for card in current_player.get_hand()]
            state["total"] = self.__get_total_pot()
            state["current_bet"] = self.__highest_bet
            state["min_raise"] = self.__highest_bet + self.__last_raise
            state["current_player"] = self.__dealer_queue[self.__player_turn % len(self.__dealer_queue)].get_id()
            state["available_actions"] = ["fold", "raise"] + ["check" if self.__can_check(current_player) else "call"]
            state["chips"] = current_player.get_chips()

            return state

        except Exception as e:
            return json.dumps({"type": "error", "message": "Failed to create game state."})

    def get_rid_of(self,player):
        """Removes any instances of a given player from a game"""
        if player in self.__players:
            self.__players.remove(player)
        logger.debug(f"get rid {self.__dealer_queue,player,player.get_id()}")
        if player in self.__dealer_queue:
            self.__dealer_queue.remove(player)
        if player in self.__active_players:
            self.__active_players.remove(player)
        if player in self.__all_in_players:
            self.__all_in_players.remove(player)
        if player in self.__all_in_queue:
            self.__all_in_queue.remove(player)

        if self.__dealer_queue:
            self.__player_turn = self.__player_turn % len(self.__dealer_queue)

    async def send_game_state(self, player):
        """Sends a game state to a certain player"""
        msg = self.__get_game_state(player)
        await self.__send_message(player, msg)

    async def send_all_game_states(self):
        """Sends a game state to all players"""
        for player in self.__players:
            await self.send_game_state(player)
        await asyncio.sleep(0.01)

    async def __send_all_game_overs(self,win_dict):
        """Sends the game over message to all players"""
        for player in self.__players:
            await self.__send_message(player,self.get_game_over_state(win_dict,player))

    def check_full(self):
        """Checks if the game is full."""
        return len(self.__players) >= self.__max_players

    def __check_named(self):
        """Checks all the players have names i.e., their name attribute is not None"""
        return all(obj.get_player_name() is not None for obj in self.__players)

    async def add_new_player(self, player):
        """Adds a new player to the game, and if the game is now full, it starts the game"""

        if player not in self.__players:
            self.__players.append(player)

        if self.check_full() and self.__check_named():
            self.__state = GameState.WAITING
            try:
                asyncio.create_task(self.__begin_play())
                return True
            except Exception as e:
                logger.error(f"Unexpected error during game startup: {e}")
                return False
        return False

    def __place_blinds(self):
        """Place bets on behalf of the SB and BB, using the raise manager"""
        self.__raise_manager(self.__dealer_queue[1], self.__sb)
        self.__raise_manager(self.__dealer_queue[2 % len(self.__dealer_queue)], self.__bb)

    def __start_round_update(self):
        """Updates database when round begins"""
        self.__db_start_round_update(self.__game_id,self.__round_num,self.__players)

    def __get_total_pot(self):
        """Returns the sum of the amounts in each pot"""
        total = 0
        for pot in self.__pots.view_queue():
            total += pot.get_pot_amount()
        return total

    def __end_round_update(self,total_pot,win_dict):
        """Updates database when round ends"""
        self.__db_end_round_update(self.__game_id,self.__round_num,self.__table,total_pot,self.__players,win_dict)

    def prep_deck_and_pots(self):
        """Initialises the deck and the pots queue for the game, and makes the first pot"""
        self.__deck = Deck()
        self.__pots = Queue(len(self.__players))
        self.__pots.enqueue(Pot())

    async def __begin_play(self):
        """Prepares the game to begin, creates the "dealer queue", which is the order in which players will become the dealer, and starts the game"""
        self.prep_deck_and_pots()
        self.__started = True
        self.__round_num += 1
        self.__active_players = self.__players.copy()
        self.__start_round_update()
        if self.__dealer_queue:
            self.__dealer_queue.append(self.__dealer_queue.pop(0))
        else:
            self.__dealer_queue = self.__active_players.copy()
            random.shuffle(self.__dealer_queue)
        await asyncio.gather(self.__play())

    async def evaluate_message(self, player, data):
        """Will evaluate a given message based upon its state"""
        try:
            data = json.loads(data)
            message = data["message"]
        except Exception as e:
            logging.error(f"Couldn't load player input: {e}")
            message = ""

        if self.__state == GameState.JOINING:
            pass
        elif self.__state == GameState.PLAYING:
            if self.__dealer_queue[self.__player_turn] == player:
                action_options = ["fold"]
                if self.__can_check(player):
                    action_options += ["check"]
                else:
                    action_options += ["call"]

                if message:
                    action = message.strip().lower()
                    if action in action_options or bool(re.fullmatch(r"^raise [0-9]+", action)): # Regular expression checks for raise formatting
                        await self.__player_action(player, action)
                        await self.send_all_game_states()
                    else:
                        await self.__send_message(player, self.__json_message("Invalid Action. Try again!"))
            else:
                pass

        elif self.__state == GameState.ENDED:
            if player == self.__players[0]:
                if message.strip().lower() == "play":
                    try:
                        self.__input_complete.set()
                        self.__reset_game()
                        asyncio.create_task(self.__begin_play())
                    except Exception as e:
                        logger.error(f"Unexpected error during play again: {e}")
                elif message.strip().lower() == "quit":
                    await self.__send_all(self,self.__json_message("Game Over"))
                    await self.__shut_down(self)
                else:
                    pass
            else:
                pass
        else:
            pass

        if self.__started:
            await self.send_all_game_states()

    def __deal_hands(self):
        """Deals two cards to each player"""
        for player in self.__players:
            player.deal_hand(self.__deck.deal(2))

    def __check_game_over(self):
        """Checks if a game is over based upon the phase and number of players remaining"""
        return self.__phase == 4 or len(self.__active_players) <= 1

    def __evaluate_winner(self):
        """Evaluates the hands of each player, and creates a dictionary with the player and their hand rank"""
        rank_dict = dict()
        for player in self.__active_players + self.__all_in_players:
            temp = self.__table + player.get_hand()
            rank, hand = self.__evaluator.evaluate_hand(temp)
            rank_dict[player] = (rank,hand)

        return rank_dict

    async def __update_chip_stacks(self, ranks):
        """
        Using the player-rank dictionary, the chips from each pot are allocated
        to the lowest (or split between joint lowest) hand rank from the eligible players for that pot
        """
        win_dict = dict()
        if ranks:
            while not self.__pots.check_empty():
                pot = self.__pots.dequeue()
                logger.debug(f"POT {pot.get_pot_amount()}, {pot.get_pot_contributions()}")
                winner = []
                best_rank = 7463 # Worst hand is ranked at 7462, so will still be lower
                for player in pot.get_eligible_players():
                    rank = ranks[player][0]
                    if rank < best_rank:
                        best_rank = rank
                        winner = [player]
                    elif rank == best_rank:
                        winner.append(player) # There could be multiple winners, in the case of a draw (e.g., best hand on table)
                    else:
                        pass

                # If there are multiple winners i.e., it is a draw, then the chips will be split between the players
                for player in winner:
                    player.set_chips((pot.get_pot_amount() // len(winner)))
        else:
            while not self.__pots.check_empty():
                pot = self.__pots.dequeue()
                player = (self.__active_players + self.__all_in_players)[0]
                player.set_chips(pot.get_pot_amount())


        # Chip change is the net change in chips for a round, as even if a player "wins chips", they might not actually have profited
        for player in self.__players:
            """Chip change accoutns for the chips a player put in, as it compares starting and ending chips."""
            initial_chips = self.request_starting_chips(self.__game_id,self.__round_num,player)
            final_chips = player.get_chips()
            chip_change = final_chips-initial_chips
            win_dict[player.get_id()] = chip_change
        return win_dict

    def __check_win_by_default(self):
        """Win by default occurs if only one player remains in the game"""
        return len(self.__active_players + self.__all_in_players) == 1 # Just makes chip redistribution simpler

    async def __finish_dealing(self):
        """
        If all players are all in, then all the necessary remaining cards will be dealt without waiting for further actions from users.
        Otherwise, once all players are all in, there is no way to progress through phases and reveal new cards, making it impossible to determine a winner.
        """
        while self.__phase < 4:
            await self.__reveal_cards()
            self.__phase += 1

    async def __play(self):
        """
        A hand follows a repetition of revealing cards, playing out the phase, and processing the phase (such as all ins)
        After each phase (e.g., flop) we reset and make sure game is not over (e.g., everyone except one has folded)
        """
        self.__state = GameState.PLAYING
        self.__deal_hands()
        game_over = False
        self.__place_blinds()
        while not game_over and self.__state == GameState.PLAYING:
            await self.__reveal_cards()
            await self. __play_phase()
            await self.__process_all_ins()
            self.__reset_phase()
            game_over = self.__check_game_over()

        await self.__game_over()

    async def __game_over(self):
        """
        Handles a game ending, if all players are all in, it makes sure to finish dealing the cards,
        and it also gets rid of any players without chips after they have been redistributed.
        """
        self.__state = GameState.ENDED
        if len(self.__table) < 5:
                await self.__finish_dealing()

        if self.__check_win_by_default():
            ranks = None
        else:
            ranks = self.__evaluate_winner()
        total_pots = self.__get_total_pot()
        win_dict = await self.__update_chip_stacks(ranks)
        self.__end_round_update(total_pots,win_dict)

        await self.send_all_game_states()
        await self.__send_all_game_overs(win_dict)
        await self.__clean_up_players()
        if len(self.__players) > 1:
            await self.__send_message(self.__players[0], self.__json_message("Send 'play' to play again, or 'quit' to end the game:"))
            await self.__send_all(self,self.__json_message("GAME OVER"),self.__players[0])
        elif len(self.__players) == 1:
            await self.close_final_player()
        self.__input_complete.clear()

    async def close_final_player(self):
        """When only one player remains (i.e., the winner), we tell them they are the winner and then remove them too."""
        player = self.__players[0]
        await self.__send_message(player,self.__json_message("Congratulations! You won! Please close your client."))
        player.set_eliminated()
        self.get_rid_of(player)

    async def __clean_up_players(self):
        """Gets rid of players without chips, as they are no longer in the game"""
        to_remove = []
        for player in self.__players:
            if player.get_chips() <= 0:
                to_remove.append(player)

        while to_remove:
            player_to_remove = to_remove[0]
            await self.__send_message(player_to_remove,self.__json_message("You have been eliminated from the game. Please close your client."))
            player_to_remove.set_eliminated()
            self.get_rid_of(player_to_remove)
            to_remove.remove(player_to_remove)

    def __json_message(self, message):
        """JSON serialisable format for messages to be sent to the client."""
        return {
            "type": "message-state",
            "message": message
        }

    async def __play_phase(self):
        """A phase follows an order of having the player act, incrementing the player, and checking if the given phase is over"""
        await self.send_all_game_states()
        phase_over = False
        while not phase_over:

            # Mod to loop around if we overflow
            self.__player_turn = self.__player_turn % len(self.__dealer_queue)
            next_player = self.__dealer_queue[self.__player_turn]
            # Here, we are making sure that the player we land upon is not folded (i.e., still actively in this hand)
            while next_player not in self.__active_players:
                self.__player_turn = (self.__player_turn + 1) % len(self.__dealer_queue)
                next_player = self.__dealer_queue[self.__player_turn]

            await self.send_all_game_states()

            player = self.__dealer_queue[self.__player_turn]

            # Waiting for the player to act
            await self.__player_act(player)

            phase_over = self.check_phase_over()
            # Increments turn, then skips until a non-folded player is found
            self.__player_turn = (self.__player_turn + 1) % len(self.__dealer_queue)
            next_player = self.__dealer_queue[self.__player_turn]

            # Make sure that phase is not over, as we might get stuck in an infinite loop
            if not phase_over:
                while next_player not in self.__active_players:
                    self.__player_turn = (self.__player_turn + 1) % len(self.__dealer_queue)
                    next_player = self.__dealer_queue[self.__player_turn]


            await self.send_all_game_states()

        self.__phase += 1

    def check_phase_over(self):
        """
        Similar check as for game over, but also considers the number of "passes" (checks or calls),
        as once a certain proportion have "passed", the round must be over
        """
        return self.__pass_count >= len(self.__active_players+self.__all_in_queue) or len(self.__active_players + self.__all_in_queue) <= 1

    async def __player_act(self, player):
        """Handles a player's turn, informing everyone of whose turn it is and then waiting for the input"""
        await self.__send_message(player, self.__json_message("Your Turn: "))
        await self.__send_all(self,self.__json_message(f"{player.get_player_name()}'s turn."),player)
        self.__input_complete.clear()
        await self.__input_complete.wait()

    async def __player_action(self, player, action):
        """Handles a player's action, taking their input and calling the necessary functions"""
        if action == "fold":
            self.__active_players.remove(player)
            for pot in self.__pots.view_queue():
                pot.remove_eligible_player(player)
            player.folded = True
            player.set_last_action("fold")
            self.__input_complete.set()
        elif action == "check":
            player.set_last_action("check")
            self.__pass_count += 1
            self.__input_complete.set()
        elif action == "call":
            player.set_last_action("call ")
            self.__call_manager(player)
            self.__pass_count += 1
            self.__input_complete.set()
            if self.__phase == 0 and not player.get_vpip_in_round():
                self.__increment_vpip(player)
                player.set_vpip_in_round(True)
            self.__increment_passive(player)
        elif action.strip()[:5] == "raise": # Ensures the right format - the player wishes to raise
            try:
                try:
                    amount = int(action.strip().split()[1])
                except ValueError as e:
                    logger.erorr(f"Error when extracting raise amount: {e}")
                    amount = -1
                if self.__validate_raise(player, amount):
                    self.__pass_count = 1 + len(self.__all_in_queue)
                    self.__raise_counter += 1
                    player.set_last_action("raise ")
                    amount = self.__raise_manager(player, amount)
                    self.__input_complete.set()
                    if self.__phase == 0 and not player.get_raised_in_round():
                        self.__increment_pfr(player,player.get_vpip_in_round())
                        player.set_raised_in_round(True)
                        if self.__raise_counter == 2:
                            self.__increment_3bet(player)
                    self.__increment_aggro(player)
                else:
                    await self.__send_message(player, self.__json_message(f"Raise too low! Must raise to at least: {self.__highest_bet + self.__last_raise}"))
            except Exception as e:
                logging.error(f"Failed on player action: {e}")
        
        await self.send_all_game_states()

    def __validate_raise(self, player, amount):
        """Ensures the raise is a valid amount"""
        player_stack = player.get_chips()
        minimum = self.__highest_bet + self.__last_raise
        return not (amount < minimum and amount < player_stack)

    def __call_manager(self, player):
        """Manages a player calling the current raise, and can account for calling into an all in"""
        player_stack = player.get_chips()
        amount = self.__highest_bet
        if amount >= player_stack+player.get_bet():
            self.__all_in_manager(player)
        else:
            self.__place_bet(player, amount)

    def __raise_manager(self, player, amount):
        """Manages a player raising, accounting for whether the player raises into an all in"""
        if amount >= player.get_chips()+player.get_bet():
            self.__all_in_manager(player)
        else:
            self.__place_bet(player, amount)
        return amount

    def __all_in_manager(self, player):
        """
        If a player calls into an all in, it is handled here in the short term
        Player all ins will be handled later in 'process_all_ins', but here we merely place in an all-in queue and place the bet
        """
        self.__all_in_queue.append(player)
        self.__active_players.remove(player)
        self.__place_bet(player, player.get_chips()+player.get_bet())

    async def __process_all_ins(self):
        """All ins are processed at the end of each phase, and pots updated where needed"""
        try:
            self.__all_in_queue.sort(key=lambda p: self.__pots.queue_peek().get_player_contribution(p))
            for allin in self.__all_in_queue:
                self.__all_in_players.append(allin)
                new_pot = Pot() # This is the sidepot for the current allin player, containing all the chips they can possibly win
                amount = self.__pots.queue_peek().get_player_contribution(allin)

                if amount < 0:
                    raise ValueError(f"Player contribution is negative: {amount}")
                
                eligible = self.__pots.queue_peek().get_eligible_players()

                for player in self.__pots.queue_peek().get_pot_contributions().keys():
                    if player not in eligible:
                        player_amount = min(amount,self.__pots.queue_peek().get_player_contribution(player))
                        self.__pots.queue_peek().add_to_pot(player,-player_amount)
                        self.__pots.queue_peek().remove_eligible_player(player)
                        new_pot.add_to_pot(player,player_amount)
                        new_pot.remove_eligible_player(player)

                for player in eligible:
                    self.__pots.queue_peek().add_to_pot(player, -amount) # Removing the player's contribution from the pot
                    new_pot.add_to_pot(player, amount) # Adding that contribution to the side pot
                self.__pots.queue_peek().clean_up()
                self.__pots.enqueue(new_pot)

        except ValueError as e:
            logger.error(f"Error processing all ins {e}")
        except Exception as e:
            logging.error(f"Unexpected error processing all ins: {e}")

    def __place_bet(self, player, amount):
        """Places a player's bet, updating some attributes where needed"""
        bet_amount = amount - player.get_bet()
        player.set_chips(-bet_amount)
        self.__pots.queue_peek().add_to_pot(player,bet_amount)
        if amount > self.__highest_bet:
            if amount - self.__highest_bet > self.__last_raise:
                self.__last_raise = amount - self.__highest_bet
            self.__highest_bet = amount
        player.set_bet(amount)
        player.set_last_action(player.get_last_action() + str(amount))

    def __can_check(self,player):
        """Checks if a player can check"""
        return self.__highest_bet == 0 or player.get_bet() == self.__highest_bet

    async def __reveal_cards(self, phase=None):
        """Reveals the necessary amount of cards, depending on the current phase"""
        if self.__phase == 0:
            pass
        elif self.__phase == 1:
            self.__table += self.__deck.deal(3)
        else:
            self.__table += self.__deck.deal(1)
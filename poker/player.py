from poker.logger_config import setup_logger

logger = setup_logger(__name__)

class Player:
    """Player object is used server-side for game processing."""
    def __init__(self, reader, writer, id, name, chips=1000):
        # Used in client-server communications
        self.reader = reader
        self.writer = writer

        # Unique ID for each player, and the name of each player
        self.__id = id
        self.__name = name

        # Details of the player and their actions
        self.__hand = []
        self.__chips = chips
        self.__bet = 0 # The amount the player has contributed so far, used to check if they can "check"
        self.__last_action = ""
        self.__raised_in_round = False
        self.__vpip_in_round = False
        self.__player_eliminated = False
        self.__folded = False

    def get_raised_in_round(self):
        return self.__raised_in_round

    def get_vpip_in_round(self):
        return self.__vpip_in_round

    def set_raised_in_round(self,value):
        if type(value) is bool:
            self.__raised_in_round = value
            self.set_vpip_in_round(value)

    def set_vpip_in_round(self,value):
        if type(value) is bool:
            self.__vpip_in_round = value

    def get_chips(self):
        return self.__chips

    def get_last_action(self):
        return self.__last_action

    def set_last_action(self,action):
        self.__last_action = action

    def get_bet(self):
        return self.__bet

    def set_bet(self,amount):
        self.__bet = amount

    def set_chips(self,amount):
        self.__chips += amount
        if self.__chips < 0:
            self.__chips = 0

    def get_hand(self):
        return self.__hand

    def set_eliminated(self):
        self.__player_eliminated = True

    def deal_hand(self, cards):
        self.__hand = cards

    def get_id(self): return self.__id
    def get_player_eliminated(self): return self.__player_eliminated
    def get_player_name(self): return self.__name

    def get_player_state(self):
        """JSON serialisable storage of the player data, to be transmitted"""
        state = {
            "player_id": self.__id,
            "chips": self.__chips,
            "name": self.__name,
            "last_action": self.__last_action
        }
        return state

    def __repr__(self):
        return f"{self.__name}"
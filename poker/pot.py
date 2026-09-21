from poker.logger_config import setup_logger

logger = setup_logger(__name__)

class Pot:
    """Though most games will have a single pot, there are often situations with multiple pots."""
    def __init__(self):
        """
        A pot stores some key data which each serves a purpose:
            Amount - the chips in the pot i.e., what there is to win
            Contributions - how much each player has contributed to the pot
            Eligible Players - those eligible to win the pot, and not always the same as contributions, as a player may contribute and fold
            Largest Contribution - the amount that any player wishing to win the pot must have contributed
        """
        self.__amount = 0
        self.__contributions = {}
        self.__eligible_players = set()
        self.__largest_contribution = 0

    def get_pot_amount(self): return max(0,self.__amount)
    def get_pot_contributions(self): return self.__contributions
    def get_largest_contribution(self): return self.__largest_contribution
    def get_eligible_players(self): return self.__eligible_players

    def change_amount(self,value):
        """Updating the amount of the pot, utilised when creating side pots"""
        self.__amount += int(value)
        if self.__amount < 0:
            self.__amount = 0

    def add_to_pot(self, player, amount):
        """Updates the necessary attributes. If it is the first time a player is contributing to the pot, they are added to the contributions dictionary."""
        self.__contributions.setdefault(player, 0)
        self.__largest_contribution = max(self.__largest_contribution, amount + self.__contributions[player])
        self.change_amount(amount)
        self.__contributions[player] += amount
        self.__eligible_players.add(player)

    def get_player_contribution(self, player):
        try:
            return self.__contributions[player]
        except KeyError as e:
            return 0

    def set_player_contribution(self, player, amount):
        self.__contributions[player] += amount
        if self.__contributions[player] < 0:
            self.__contributions[player] = 0

    def remove_eligible_player(self, player):
        self.__eligible_players.discard(player)

    def clean_up(self):
        self.__eligible_players = {player for player in self.__eligible_players if self.__contributions[player] > 0}

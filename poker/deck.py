import random

class Card:
    # Maps the numerical values to the strings counterparts, changing to letters where necessary
    RANK_VALUES = {
        0: "2",
        1: "3",
        2: "4",
        3: "5",
        4: "6",
        5: "7",
        6: "8",
        7: "9",
        8: "10",
        9: "J",
        10: "Q",
        11: "K",
        12: "A"
    }

    # Maps the suits to numbers for encoding
    SUIT_VALUES = {
        "clubs": 0,
        "diamonds": 1,
        "hearts": 2,
        "spades": 3
    }

    # A list of the first 13 primes, used in the evaluation
    PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41]

    # Maps the suits to unicode to be printed nicely
    SUIT_VISUALS = {
        "clubs": "\u2663",
        "diamonds": "\u2666",
        "hearts": "\u2665",
        "spades": "\u2660"
    }

    def __init__(self, rank, suit=None):
        """
        Suit is optional - for when we are creating the lookup tables.
        However, a suit is specified when creating the main deck.
        """
        self.__suit = suit
        self.__rank = rank
        self.__pretty_rank = self.RANK_VALUES[rank]

        if suit:
            self.__pretty_suit = self.SUIT_VISUALS[suit]
        else:
            self.__pretty_suit = "-"
        self.__rep = self.gen_number(rank, suit)

    def printable(self):
        # Looks nicer when printed
        return f"{self.__pretty_rank}{self.__pretty_suit}"

    def json_rep(self):
        """Encodes the rank and suit to be sent via JSON"""
        # The files are 2-14, so adding 2 to make up the difference
        return {"rank": self.__rank + 2,
                "suit": self.__suit}

    def gen_number(self, rank, suit=None):
        """Generates the binary number that is used in Cactus Kev's Algorithm, encoding the key info."""
        r = rank
        if suit:
            s = self.SUIT_VALUES[suit]
            bin_suit = 2**(15 - s)
        else:
            # If no suit was specified, as when lookup tables are generated.
            bin_suit = 0
        bin_card = 2**(16 + r)
        bin_rank = r << 8
        bin_prime = self.PRIMES[r]

        #Binary OR operations used to join the four sections of the number
        return bin_card | bin_suit | bin_rank | bin_prime

    def get_rep(self):
        return self.__rep

    def pretty(self):
        print(f"{self.__pretty_rank}{self.__pretty_suit}")

    def __str__(self):
        return f"{self.__pretty_rank}{self.__pretty_suit}"

    def __repr__(self):
        return self.__json_rep()

class Deck:
    """Deck of cards to be used in the game, and used to build the lookup tables for hand evaluation."""
    def __init__(self,deck=None,seed=None):
        self.__seed = seed
        if deck:
            self.__deck = deck
        else:
            self.__deck = self.__assemble()

        random.shuffle(self.__deck)

    def remove(self,value):
        if value in self.__deck:
            self.__deck.remove(value)

    def __assemble(self):
        """Builds the deck by appending 52 card objects, one for each in a standard deck."""
        temp_deck = []
        for suit in ["clubs", "diamonds", "hearts", "spades"]:
            for rank in range(13):
                temp_deck.append(Card(rank, suit))

        random.Random(self.__seed).shuffle(temp_deck)

        return temp_deck

    def deal(self, num):
        """Deals a certain number of cards"""
        temp = []
        for i in range(num):
            if self.__deck:
                temp.append(self.__deck.pop())

        return temp

    def copy(self):
        """Returns a copy of the deck, so that changes can be made to the duplicate without affecting the original."""
        return Deck(self.__deck)

    def shuffle_deck(self):
        random.shuffle(self.__deck)
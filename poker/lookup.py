from poker.deck import *
from poker.logger_config import setup_logger

logger = setup_logger(__name__)
"""
The lookup tables act like hash tables - there is a time complexity of O(1) for data retrieval.
The index is generated based on a mathematical function
"""
class LookupTable:
    """Base class for Lookup Tables, used in the hand evaluation process"""

    deck = [Card(r) for r in range(13)] # Suit is abstracted when creating the lookup table

    rank_values = {
        "2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5, "8": 6,
        "9": 7, "T": 8, "J": 9, "Q": 10, "K": 11, "A": 12
    }

    rank_map = dict() # Stores the binary representation of each card

    for k in rank_values.keys():
        rank_map[k] = deck[rank_values[k]].get_rep()

    def __init__(self):
        self._table = []

    def get_table(self):
        return self._table

    def add_to_lookup(self):
        pass

class StandardLookup(LookupTable):
    """Both the Flush lookup and the Unique lookup are structurally the same, so can use the same class."""

    def __init__(self):
        """Maximum length known, can use static array."""
        self._table = [0] * 7937

    def add_to_lookup(self, comb):
        """Adds a given hand to the lookup table, as given by the handslist."""
        pos = comb[0]
        cards = comb[1]
        ind = 0
        for card in cards:
            ind = ind | self.rank_map[card]
        ind = ind >> 16
        self._table[ind] = int(pos)

class PrimeProductLookup(LookupTable):
    """
    This table is used for anything that is not a Flush and has repeated cards.
    It technically has two "parallel" tables, where the values in matching indices in each are related.
    """
    def __init__(self):
        self.__prime = []
        self.__score = []
        self.__setup = [] # Used in the creation of the other two lists

    def add_to_lookup(self, comb):
        """Adds a given hand to the lookup table, as given by the handslist."""
        mask = 255
        pos = comb[0]
        cards = comb[1]
        prime_product = 1
        for card in cards:
            prime = self.rank_map[card] & mask
            prime_product *= prime
        self.__setup.append((prime_product, pos))

    def __merge_sort(self,data,value=0):
        """Used to sort the prime product lookup table"""
        if len(data) == 1:
            return data

        mid = len(data) // 2
        left = self.__merge_sort(data[:mid],value)
        right = self.__merge_sort(data[mid:],value)
        return self.__merge(left,right,value)

    def __merge(self,left,right,value):
        """Used as part of the merge sort algorithm"""
        merged = []
        while len(left) > 0 and len(right) > 0:
            if left[0][value] < right[0][value]:
                merged.append(left.pop(0))
            else:
                merged.append(right.pop(0))

        if len(left) > 0:
            merged = merged + left
        elif len(right) > 0:
            merged = merged + right

        return merged

    def sort_setup(self):
        """Sorting the items by the prime product allows for lookup with merge sort in the future."""
        self.__setup = self.__merge_sort(self.__setup,0)

    def create_lookup(self):
        """"Once the setup list has been completed, we can create the prime product and score tables"""
        for row in self.__setup:
            self.__prime.append(int(row[0]))
            self.__score.append(int(row[1]))

    def get_prime_table(self):
        return self.__prime

    def get_score_table(self):
        return self.__score

class LookupManager:
    def __init__(self):
        self.__ranked_hands = self.__rank_hands()
        self.__flush_lookup = StandardLookup()
        self.__unique_lookup = StandardLookup()
        self.__prime_lookup = PrimeProductLookup()
        self.__build_lookups()

    def __rank_hands(self):
        file = open("poker\\handlist.txt", "r")
        ranked_hands = []
        lines = [x.split() for x in file.readlines()]
        for line in lines:
            comb = (line[0], "".join(line[5:10]), line[10])
            ranked_hands.append(comb)
        return ranked_hands

    def get_flush_lookup(self):
        return self.__flush_lookup.get_table()

    def get_unique_lookup(self):
        return self.__unique_lookup.get_table()

    def get_prime_product_lookup(self):
        return self.__prime_lookup.get_prime_table()

    def get_prime_score_lookup(self):
        return self.__prime_lookup.get_score_table()

    def __build_lookups(self):
        """Going through the handslist file and building the lookup tables."""
        for hand in self.__ranked_hands:
            if hand[2] in ["F", "SF"]:
                self.__flush_lookup.add_to_lookup(hand)
            elif hand[2] in ["S", "HC"]:
                self.__unique_lookup.add_to_lookup(hand)
            else:
                self.__prime_lookup.add_to_lookup(hand)

        self.__prime_lookup.sort_setup()
        self.__prime_lookup.create_lookup()
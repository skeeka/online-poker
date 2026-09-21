from itertools import combinations

class HandEvaluator:
    def __init__(self, lookup):
        self.__lookup = lookup

    def evaluate_hand(self, cards):
        """Evaluates the given cards, by finding all the combinations of 5 cards and evaluating each."""
        best_ranking = 7463  # The highest rank (worst hand) is 7462
        combs = list(combinations(cards, 5))
        for c in combs:
            ranking = self.__evaluate(c)
            if ranking < best_ranking:
                best_ranking = ranking

        return (best_ranking, self.__name_hand(best_ranking))

    def __evaluate(self, combination):
        """Evaluates a given combination of 5 cards, by checking the 3 lookup tables in order."""
        if self.__check_flush(combination) > 0:
            return self.__find_flush(combination)
        elif self.__find_unique(combination) > 0:
            return self.__find_unique(combination)
        else:
            return self.__find_prime(combination)

    def __name_hand(self, ranking):
        """All poker hands divided into 7462 unique hands."""
        if ranking == 1:
            return "Royal Flush"
        elif ranking < 11:
            return "Straight Flush"
        elif ranking < 167:
            return "Four of a Kind"
        elif ranking < 323:
            return "Full House"
        elif ranking < 1600:
            return "Flush"
        elif ranking < 1610:
            return "Straight"
        elif ranking < 2468:
            return "Three of a Kind"
        elif ranking < 3326:
            return "Two Pair"
        elif ranking < 6186:
            return "Pair"
        else:
            return "High Card"

    def __find_flush(self, combination):
        """Lookup in flush table"""
        ind = 0
        for c in combination:
            ind = ind | c.get_rep()

        ind = ind >> 16

        return self.__lookup.get_flush_lookup()[ind]

    def __find_unique(self, combination):
        """Lookup in "unique" table"""
        ind = 0
        for c in combination:
            ind = ind | c.get_rep()

        ind = ind >> 16

        return self.__lookup.get_unique_lookup()[ind]

    def __binary_search(self,values,item,lower,upper):
        """Binary search used to find the index of a given item in a list of values."""
        if lower <= upper:
            mid = (lower + upper) // 2

            if values[mid] == item:
                return mid

            elif values[mid] > item:
                return self.__binary_search(values,item,lower,mid-1)

            else:
                return self.__binary_search(values,item,mid+1,upper)

        else:
            return -1

    def __search(self,values,item):
        return self.__binary_search(values,item,0,len(values)-1)

    def __find_prime(self, combination):
        """Lookup in the "primes" table using the prime product, the key advantage of Cactus Kev's Algorithm."""

        mask = 255 # Bit mask used to extract relevant information
        prod = 1
        for c in combination:
            prod *= (c.get_rep() & mask) # Multiplying to get prime product

        """We must find the index of the prime product, and then look in the related table for the score."""
        try:
            ind = self.__search(self.__lookup.get_prime_product_lookup(),prod)
        except ValueError as e:
            ind = None

        try:
            return self.__lookup.get_prime_score_lookup()[ind]
        except IndexError as e:
            return 7462

    def __check_flush(self, combination):
        """Checks if the current combination is a flush, based upon a bitmask applied to the representation of the cards."""
        mask = 61440
        result = mask
        for c in combination:
            result = result & c.get_rep()

        if result:
            return True
        else:
            return False
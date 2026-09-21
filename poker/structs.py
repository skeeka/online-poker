from poker.logger_config import setup_logger

logger = setup_logger(__name__)

class Queue:
    def __init__(self,max):
        self.__queue = [None] * (max+1)
        self.__fp = 0
        self.__rp = -1
        self.__max_size = max

    def enqueue(self,value):
        try:
            if not self.check_full():
                self.__rp += 1
                self.__queue[self.__rp] = value
        except KeyError:
            logger.error(f"Rear pointer out of range, {self.__rp}")
            self.__rp -= 1

    def dequeue(self):
        try:
            if not self.check_empty():
                item = self.__queue[self.__fp]
                self.__fp += 1
                return item
            else:
                return None
        except KeyError:
                return None
        
    def queue_peek(self):
        if not self.check_empty():
            logger.info(f"PEEKING {self.__fp} , {self.__queue}")
            try:
                return self.__queue[self.__fp]
            except KeyError:
                return None

    def check_full(self):
        return self.__rp == self.__max_size
    
    def check_empty(self):
        return self.__fp > self.__rp
    
    def clear_queue(self):
        self.__queue = [None] * (self.__max_size+1)
        self.__rp = -1
        self.__fp = 0

    def view_queue(self):
        try:
            return self.__queue[self.__fp:self.__rp+1]
        except KeyError:
            return [None]
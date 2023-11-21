import time


class Utils:
    def __init__(self) -> None:
        pass

    @staticmethod
    def seconds_to_now(timestamp):
        current_time = time.time()
        seconds_passed = int(current_time - timestamp)
        return seconds_passed

    @staticmethod
    def current_timestamp():
        return int(time.time())

    @staticmethod
    def current_time():
        return time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())
   
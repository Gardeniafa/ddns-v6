import time
import builtins
import datetime
import ipaddress


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

    @staticmethod
    def ip_compare(target, rule):
        if '/' in rule:
            ip, mask = rule.split('/')
            if '.' in mask:
                mask = ipaddress.IPv4Network('0.0.0.0/' + mask).prefixlen
            network = ipaddress.ip_network(f'{ip}/{mask}', strict=False)
            target = ipaddress.ip_address(target)
            return target in network
        else:
            return target == rule


class Printer:
    def __init__(self, write_log: bool = False, log_sender: str = ''):
        self.__log_name = (f'{datetime.datetime.now().strftime("%y-%m-%d %H.%M.%S")}'
                           f'{f"({log_sender})" if log_sender else log_sender}.log')
        self.__write_log = write_log

    def print(self, *args, **kwargs):
        if self.__write_log:
            with open(self.__log_name, 'a') as f:
                builtins.print(*args, file=f, **kwargs)
        builtins.print(*args, **kwargs)

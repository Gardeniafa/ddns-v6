import hashlib
import json
import subprocess
import re
import time
import requests
import yaml
import os
import threading
from utils import Utils
from utils import Printer


class Client:
    def __init__(self, config_path: str) -> None:
        with open(config_path) as cfg:
            config = yaml.safe_load(cfg)
            self.__my_name = config['info']['name']
            self.__ttl = config['info']['ttl_seconds']
            self.__secret = config['server_config']['secret']
            self.__api = config['server_config']['api']
            self.__scan_time_seconds = config['time_policy']['scan_time_seconds']
            self.__min_report_time_seconds = config['time_policy']['min_report_time_seconds']
            self.__v6_address = None
            self.__timer = self.__min_report_time_seconds
            self.__utils = Utils()
            self.__printer = Printer(config['functions']['log']['write_log_file'], log_sender='client')
            self.__print = self.__printer.print
            if self.__ttl <= self.__timer or self.__ttl <= self.__scan_time_seconds:
                self.__print(f"[Attention] {self.__utils.current_time()}  The report time gap should smaller than ttl.")
            self.update_v6_address()
            self.report()

    def update_v6_address(self):
        output = subprocess.check_output('ipconfig' if os.name == 'nt' else 'ifconfig',
                                         shell=True).decode('gbk' if os.name == 'nt' else 'utf-8')
        ipv6_pattern = (r'(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,'
                        r'6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,'
                        r'4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,'
                        r'4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]'
                        r'{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,'
                        r'1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|'
                        r'([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|'
                        r'1{0,1}[0-9]){0,1}[0-9]))')
        ipv6_addresses = re.findall(ipv6_pattern, output)
        result = [address[0] for address in ipv6_addresses]
        nl = []
        for i in result:
            if len(i) > 20:
                nl.append(i)
        res = nl[0]
        for i in nl:
            if len(res) > len(i):
                res = i
        self.__v6_address = res

    def sign(self, params: dict):
        new_params = params.copy()
        new_params['secret'] = self.__secret
        sorted_params = sorted(new_params.items())
        param_str = '&'.join(f'{k}={v}' for k, v in sorted_params)
        md5 = hashlib.md5(param_str.encode()).hexdigest()
        return md5[::-1]

    def report(self):
        dat = {
            'name': self.__my_name,
            'value': self.__v6_address,
            'type': 'AAAA',
            'ttl': self.__ttl,
            'timestamp': self.__utils.current_time()
        }
        try:
            dat['identify'] = self.sign(dat)
            response = requests.post(self.__api, json=dat, timeout=2)
            res = json.loads(response.text)
            if res['code'] != 200:
                raise ValueError(
                    f'[Error] {self.__utils.current_time()}  Return code {res["code"]} with message: {res["message"]}')
        except Exception as e:
            self.__print(e)
        else:
            self.__timer = self.__min_report_time_seconds

    def check_v6_address_change(self):
        self.__print(f'[Info] {self.__utils.current_time()}  address listener start...')
        while True:
            time.sleep(self.__scan_time_seconds)
            previous_add = self.__v6_address
            self.update_v6_address()
            if previous_add != self.__v6_address:
                self.__print(f'[Info] {self.__utils.current_time()}  Detect IPv6 address changed, report it')
                self.__print(f'        From `{previous_add}` to `{self.__v6_address}`')
                self.report()

    def ensure_min_report(self):
        self.__print(f'[Info] {self.__utils.current_time()}  report keeper start...')
        while True:
            time.sleep(1)
            if self.__timer <= 0:
                self.__print(f'[Info] {self.__utils.current_time()}  The max report gap touch, force to report...')
                self.report()
            else:
                self.__timer += -1

    def run(self):
        check_v6_change_thread = threading.Thread(target=self.check_v6_address_change)
        ensure_min_report_thread = threading.Thread(target=self.ensure_min_report)
        check_v6_change_thread.start()
        ensure_min_report_thread.start()
        check_v6_change_thread.join()
        ensure_min_report_thread.join()


def main(config: str = './config.client.yaml'):
    client = Client(config)
    try:
        client.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f'[Fatal] error occurs, program exit with error:')
        print(e)
    print('[Program exit]')


if __name__ == '__main__':
    main()

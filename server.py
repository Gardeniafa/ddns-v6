import dns.query
import dns.message
import dns.rcode
import socket
import threading
import json
import hashlib
from dns.rdatatype import A, AAAA
from dns.rdataclass import IN
from dns.exception import DNSException
from wsgiref.simple_server import make_server
from urllib.parse import parse_qs
import yaml
from utils import Utils
from utils import Printer


class DNSServer:
    def __init__(self, config_path: str) -> None:
        with open(config_path) as cfg:
            config = yaml.safe_load(cfg)
            self.__secret = config['secret']
            self.__allow_addresses = config['addresses']
            self.__listening_host = config['listening']['http_api']['host']
            self.__listening_port = config['listening']['http_api']['port']
            self.__dns_tcp_host = config['listening']['dns']['tcp']['host']
            self.__dns_tcp_port = config['listening']['dns']['tcp']['port']
            self.__dns_udp_host = config['listening']['dns']['udp']['host']
            self.__dns_udp_port = config['listening']['dns']['udp']['port']
            self.__expire_time = config['record']['expire_time_seconds']
            self.__poll_period = config['record']['poll_period_seconds']
            self.__utils = Utils()
            self.__records_min_ttl = None
            self.__last_time_flush = None
            self.__records = []
            self.__lock = threading.Lock()
            self.__printer = Printer(config['functions']['log']['write_log_file'], log_sender='server')
            self.__print = self.__printer.print

    def sign(self, params: dict):
        new_params = params.copy()
        new_params['secret'] = self.__secret
        sorted_params = sorted(new_params.items())
        param_str = '&'.join(f'{k}={v}' for k, v in sorted_params)
        md5 = hashlib.md5(param_str.encode()).hexdigest()
        return md5[::-1]

    def add_api_handel(self, environ, start_response):
        try:
            method = environ['REQUEST_METHOD']
            path = environ['PATH_INFO']
            if method == 'POST' and path == '/':
                content_length = int(environ['CONTENT_LENGTH'])
                post_data = environ['wsgi.input'].read(content_length)
                data = parse_qs(post_data.decode())
                if not data:
                    data = json.loads(post_data)
                if data['name'] not in self.__allow_addresses:
                    raise ValueError('Not allowed')
                for record in self.__records:
                    if record['name'] == data['name']:
                        if data['timestamp'] <= record['update_timestamp']:
                            raise ValueError('Timestamp error')
                identify = data.pop('identify')
                if identify == self.sign(data):
                    self.__lock.acquire()
                    for record in self.__records:
                        if record['name'] == data['name']:
                            self.__records.remove(record)
                    self.__records.append({
                        'name': data['name'],
                        'value': data['value'],
                        'type': {'A': A, 'AAAA': AAAA}[data['type']],
                        'type_str': data['type'],
                        'ttl': data['ttl'],
                        'update_timestamp': data['timestamp'],
                        'update_time': self.__utils.current_time()
                    })
                    if self.__records_min_ttl is None or data['ttl'] < self.__records_min_ttl:
                        self.__records_min_ttl = data['ttl']
                    if self.__last_time_flush is None:
                        self.__last_time_flush = self.__utils.current_timestamp()
                    self.__print(
                        f"[Info] {self.__records[-1]['update_time']}  Record update: {self.__records[-1]['name']}=="
                        f"{self.__records[-1]['value']}(type={self.__records[-1]['type_str']}, "
                        f"ttl={self.__records[-1]['ttl']})")
                    self.__lock.release()
                    status = '200 OK'
                    headers = [('Content-type', 'application/json')]
                    start_response(status, headers)
                    response_data = {
                        "code": 200,
                        "message": "success"
                    }
                    return [json.dumps(response_data).encode()]
            raise ValueError('Not allowed method or path')
        except Exception as ex:
            self.__print(f"[Error] http api error {self.__utils.current_time()}  {ex}")
            status = '404 Not Found'
            headers = [('Content-type', 'application/json')]
            start_response(status, headers)
            response_data = {
                "code": 404,
                "message": "Not Found"
            }
            return [json.dumps(response_data).encode()]

    def add_api_server(self):
        self.__print(
            f'[Info] {self.__utils.current_time()}  Add record api server start at `{self.__listening_host}:'
            f'{self.__listening_port}`')
        httpd = make_server(self.__listening_host, int(self.__listening_port), self.add_api_handel)
        httpd.serve_forever()

    def dns_response(self, qname, qtype):
        qname = qname[:-1] if qname[-1] == '.' else qname
        self.dns_record_flush()
        self.__lock.acquire()
        for record in self.__records:
            if record['name'] == qname and record['type'] == qtype:
                self.__print(f'   result for `{qname}({record["type_str"]})` is `{record["value"]}`, '
                             f'ttl={record["ttl"]}')
                self.__lock.release()
                return record['ttl'], record['value']
        self.__lock.release()
        raise DNSException()

    def handle_dns_query(self, request, src_address=''):
        q = request.question[0]
        qname = q.name.to_text()
        qtype = q.rdtype
        self.__print(
            f'[Log] {self.__utils.current_time()}  host `{src_address}` standard query name `{qname}` '
            f'with type `{qtype}`')
        response = dns.message.make_response(request)
        try:
            ttl, resp = self.dns_response(qname, qtype)
            rrs = dns.rrset.from_text(qname, ttl, IN, qtype, resp)
        except DNSException:
            response.set_rcode(dns.rcode.NXDOMAIN)
            self.__print(f'   [Error] {self.__utils.current_time()}  query name {qname}, type {qtype} not exist')
        else:
            response.answer.append(rrs)
        finally:
            return response

    def dns_udp_server(self):
        self.__print(
            f'[Info] {self.__utils.current_time()}  DNS UDP server start at '
            f'`{self.__dns_udp_host}:{self.__dns_udp_port}`')
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.__dns_udp_host, self.__dns_udp_port))
        while True:
            try:
                request, *_, address, = dns.query.receive_udp(sock)
                response = self.handle_dns_query(request, address)
            except Exception as ex:
                self.__print(ex)
            else:
                dns.query.send_udp(sock, response, address)

    def dns_tcp_server(self):
        self.__print(
            f'[Info] {self.__utils.current_time()}  DNS TCP server start at '
            f'`{self.__dns_tcp_host}:{self.__dns_tcp_port}`')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.__dns_tcp_host, self.__dns_tcp_port))
        sock.listen(5)
        while True:
            client_socket, address = sock.accept()
            data = client_socket.recv(512)
            try:
                request = dns.message.from_wire(data)
                response = self.handle_dns_query(request, address)
            except Exception as e:
                self.__print(e)
            else:
                client_socket.send(response.to_wire())
            finally:
                client_socket.close()

    def dns_record_flush(self):
        self.__lock.acquire()
        if self.__records_min_ttl is None or self.__last_time_flush is None:
            self.__lock.acquire()
            return
        last_flush_to_now = self.__utils.seconds_to_now(self.__last_time_flush)
        if last_flush_to_now < self.__records_min_ttl and last_flush_to_now < self.__poll_period:
            self.__lock.release()
            return
        self.__print(f'[Info] {self.__utils.current_time()}  DNS ttl scan triggered...')
        min_ttl = self.__records[0]['ttls']
        for record in self.__records:
            record_update_to_now = self.__utils.seconds_to_now(record['update_timestamp'])
            if record_update_to_now > record['ttl'] or record_update_to_now > self.__expire_time:
                self.__records.remove(record)
                self.__print(f'[Info] {self.__utils.current_time()}  record {record} has been removed...')
            else:
                if record['ttl'] < min_ttl:
                    min_ttl = record['ttl']
        if self.__records_min_ttl != min_ttl:
            self.__records_min_ttl = min_ttl
            self.__print(f"[Info] {self.__utils.current_time()}  min ttl update to {min_ttl}")
        self.__last_time_flush = self.__utils.current_timestamp()
        self.__lock.release()


def main(config: str = './config.server.yaml'):
    try:
        server = DNSServer(config)
        http_add_api_thread = threading.Thread(target=server.add_api_server)
        dns_udp_server = threading.Thread(target=server.dns_udp_server)
        dns_tcp_server = threading.Thread(target=server.dns_tcp_server)
        http_add_api_thread.start()
        dns_udp_server.start()
        dns_tcp_server.start()
        http_add_api_thread.join()
        dns_udp_server.join()
        dns_tcp_server.join()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("[Fatal] error occurs, program exit with error:")
        print(e)
    print("[Program exit]")


if __name__ == '__main__':
    main()

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
import time
import yaml
from utils import Utils
 

class DNS_Server:
    def __init__(self, config_path: str='./config.server.yaml') -> None:
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
            self.__records = []
            self.__utils = Utils()
            self.__lock = threading.Lock()

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
                identify = data.pop('identify')
                if identify == self.sign(data):
                    for record in self.__records:
                        if record['name'] == data['name']:
                            self.__records.remove(record)
                    self.__lock.acquire()
                    self.__records.append({
                        'name': data['name'],
                        'value': data['value'],
                        'type': {'A': A, 'AAAA': AAAA}[data['type']],
                        'update_timestamp': self.__utils.current_timestamp(),
                        'update_time': self.__utils.current_time()
                    })
                    self.__lock.release()
                    status = '200 OK'
                    headers = [('Content-type', 'application/json')]
                    start_response(status, headers)
                    response_data = {
                        "code": 200,
                        "message": "success"
                    }
                    return [json.dumps(response_data).encode()]
            raise
        except Exception as _:
            status = '404 Not Found'
            headers = [('Content-type', 'application/json')]
            start_response(status, headers)
            response_data = {
                "code": 404,
                "message": "Not Found"
            } 
            return [json.dumps(response_data).encode()]
        
    def add_api_server(self):
        print(f'[Info] {self.__utils.current_time()}  Add record api server start at `{self.__listening_host}:{self.__listening_port}`')
        httpd = make_server(self.__listening_host, int(self.__listening_port), self.add_api_handel)
        httpd.serve_forever()

    def dns_response(self, qname, qtype):
        qname = qname[:-1] if qname[-1] == '.' else qname
        self.__lock.acquire()
        for record in self.__records:
            if record['name'] == qname and record['type'] == qtype:
                print(f'   result for `{qname}` is `{record["value"]}`')
                self.__lock.release()
                return record['value']
        self.__lock.release()
        raise DNSException()

    def handle_dns_query(self, request, src_address=''):
        q = request.question[0]
        qname = q.name.to_text()
        qtype = q.rdtype
        print(f'[Log] {self.__utils.current_time()}  host `{src_address}` standard query name `{qname}` with type `{qtype}`')
        response = dns.message.make_response(request)
        try:
            rrs = dns.rrset.from_text(qname, 600, IN, qtype, self.dns_response(qname, qtype))
        except DNSException:
            response.set_rcode(dns.rcode.NXDOMAIN)
            print(f'   [Error] {self.__utils.current_time()}  query name {qname}, type {qtype} not exist')
        else:
            response.answer.append(rrs)
        finally:
            return response

    def dns_udp_server(self):
        print(f'[Info] {self.__utils.current_time()}  DNS UDP server start at `{self.__dns_udp_host}:{self.__dns_udp_port}`')
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.__dns_udp_host, self.__dns_udp_port))
        while True:
            request, *_, address, = dns.query.receive_udp(sock)
            try:
                response = self.handle_dns_query(request, address)
            except Exception as ex:
                print(ex)
            else:
                dns.query.send_udp(sock, response, address)

    def dns_tcp_server(self):
        print(f'[Info] {self.__utils.current_time()}  DNS TCP server start at `{self.__dns_tcp_host}:{self.__dns_tcp_port}`')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.__dns_tcp_host, self.__dns_tcp_port))
        sock.listen(5)
        while True:
            client_socket, address = sock.accept()
            data = client_socket.recv(512)
            request = dns.message.from_wire(data)
            try:
                response = self.handle_dns_query(request, address)
            except Exception as e:
                print(e)
            else:
                client_socket.send(response.to_wire())
            finally:
                client_socket.close()

    def dns_record_flush(self):
        print(f'[Info] {self.__utils.current_time()}  DNS ttl flush service start...')
        while True:
            time.sleep(self.__poll_period)
            print(f'[Info] {self.__utils.current_time()}  DNS ttl scan start...')
            self.__lock.acquire()
            for record in self.__records:
                if self.__utils.seconds_to_now(record['update_timestamp']) > self.__expire_time:
                    self.__records.remove(record)
                    print(f'[Info] {self.__utils.current_time}  record {record} has been removed...')
            self.__lock.release()
        

def main():
    try:
        server = DNS_Server()
        http_add_api_thread = threading.Thread(target=server.add_api_server)
        dns_udp_server = threading.Thread(target=server.dns_udp_server)
        dns_tcp_server = threading.Thread(target=server.dns_tcp_server)
        dns_record_flush = threading.Thread(target=server.dns_record_flush)
        http_add_api_thread.start()
        dns_udp_server.start()
        dns_tcp_server.start()
        dns_record_flush.start()
        http_add_api_thread.join()
        dns_udp_server.join()
        dns_tcp_server.join()
        dns_record_flush.join()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("[Fatal] error occurs, program exit with error:")
        print(e)
    print("[Program exit]")


if __name__ == '__main__':
    main()

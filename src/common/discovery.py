"""Small LAN discovery service. Gameplay itself always uses TCP.

Only explicit discovery requests receive a reply. A random nonce rejects stale
responses. No subnet scan or third-party service is used.
"""
from __future__ import annotations
import json
import socket
import threading
import time
import uuid
from pathlib import Path
from .config import APP_VERSION, DISCOVERY_PORT
from .protocol import ProtocolError
from .networking import validate_endpoint, check_connection


def _ignore_udp_resets(sock):
    """Windows quirk: after sending UDP to a port nobody is listening on, the next recvfrom
    fails with WinError 10054 ("connection forcibly closed"). Turn that behaviour off."""
    if hasattr(socket, 'SIO_UDP_CONNRESET'):
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass


class DiscoveryResponder:
    def __init__(self, info, port=DISCOVERY_PORT):
        self.info, self.port = info, port
        self.sock = None
        self.thread = None
        self.running = threading.Event()

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('0.0.0.0', self.port))
            sock.settimeout(.2)
            _ignore_udp_resets(sock)
        except OSError:
            sock.close()
            raise
        self.sock, self.port = sock, sock.getsockname()[1]
        self.running.set()
        self.thread = threading.Thread(target=self._run, args=(sock,), daemon=True, name='lan-discovery')
        self.thread.start()

    def _run(self, sock):
        while self.running.is_set():
            try:
                data, address = sock.recvfrom(2048)
                request = json.loads(data)
                if not isinstance(request, dict) or request.get('type') != 'dupme_discover':
                    continue
                nonce = request.get('nonce')
                if not isinstance(nonce, str) or len(nonce) != 32:
                    continue
                reply = dict(self.info(), type='dupme_server', app='Dup Me', version=APP_VERSION, nonce=nonce)
                sock.sendto(json.dumps(reply).encode('utf-8'), address)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue  # a searcher closed before our reply arrived; keep answering others
            except (ValueError, UnicodeError, TypeError):
                continue
            except OSError:
                break

    def close(self):
        self.running.clear()
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=.5)
        self.thread = None


def discover_servers(timeout=1.5, discovery_port=DISCOVERY_PORT):
    nonce = uuid.uuid4().hex
    packet = json.dumps({'type': 'dupme_discover', 'nonce': nonce}).encode('utf-8')
    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('0.0.0.0', 0))
        _ignore_udp_resets(sock)
        end, next_send = time.monotonic() + timeout, 0
        while time.monotonic() < end:
            now = time.monotonic()
            if now >= next_send:
                for address in ('255.255.255.255', '127.0.0.1'):
                    try:
                        sock.sendto(packet, (address, discovery_port))
                    except OSError:
                        pass
                next_send = now + .4
            sock.settimeout(min(.2, max(.01, end - now)))
            try:
                data, address = sock.recvfrom(4096)
                row = json.loads(data)
                if not isinstance(row, dict) or row.get('type') != 'dupme_server' or row.get('app') != 'Dup Me' or row.get('nonce') != nonce:
                    continue
                host, port = validate_endpoint(address[0], row.get('port'))
                identifier = row.get('server_id')
                if not isinstance(identifier, str) or len(identifier) != 32 or not isinstance(row.get('name'), str):
                    continue
                row.update(host=host, port=port, name=row['name'][:60])
                # Prefer the LAN address to loopback if both reach the same server.
                if identifier not in found or not host.startswith('127.'):
                    found[identifier] = row
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue  # stray "port unreachable" from one probe; keep listening for real hosts
            except (ValueError, UnicodeError, TypeError):
                continue
    return sorted(found.values(), key=lambda row: (row['name'], row['host'], row['port']))


def save_connection_file(path, addresses, port, name='Dup Me host'):
    endpoints = [validate_endpoint(host, port) for host in dict.fromkeys(addresses)]
    if not endpoints:
        raise ValueError('No LAN address found. Connect the host to Wi-Fi first.')
    payload = {'app': 'Dup Me', 'version': APP_VERSION, 'name': name,
               'addresses': [host for host, _ in endpoints], 'port': port}
    Path(path).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')


def load_connection_file(path):
    file = Path(path)
    if file.stat().st_size > 8192:
        raise ValueError('This connection file is too large.')
    data = json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('app') != 'Dup Me' or data.get('version') != APP_VERSION:
        raise ValueError('Use a connection file saved by this version of the host.')
    addresses = data.get('addresses')
    if not isinstance(addresses, list) or not 1 <= len(addresses) <= 16 or not all(isinstance(a, str) for a in addresses):
        raise ValueError('The connection file has no valid server addresses.')
    return [validate_endpoint(host, data.get('port')) for host in addresses]


def resolve_connection_file(endpoints):
    for host, port in endpoints:
        try:
            check_connection(host, port, timeout=1)
            return host, port
        except (OSError, ValueError, ProtocolError):
            continue
    raise ValueError('The saved host is not reachable. Keep the host running on the same network and save a new connection file if its network changed.')

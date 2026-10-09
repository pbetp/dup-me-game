"""Shared address validation and a non-player connection check."""
from __future__ import annotations
import errno
import ipaddress
import socket
from .config import APP_VERSION, SERVER_PORT
from .protocol import ProtocolError, receive_message, send_message


def validate_endpoint(host: str, port: object) -> tuple[str, int]:
    host = host.strip()
    if not host or any(c.isspace() for c in host) or any(c in host for c in '/:@\\'):
        raise ValueError('Enter an IPv4 address or hostname, without http:// or a port.')
    try:
        number = int(str(port).strip())
    except (TypeError, ValueError):
        raise ValueError('Port must be a whole number from 1 to 65535.') from None
    if not 1 <= number <= 65535:
        raise ValueError('Port must be from 1 to 65535.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_unspecified or address.is_multicast or str(address) == '255.255.255.255'):
        raise ValueError('Use the server computer\'s IPv4 address. 0.0.0.0 is only a listening address.')
    return host, number


def local_ip_addresses() -> list[str]:
    """Best-effort candidates, not a guarantee of reachability from another PC."""
    addresses = []
    # UDP connect selects a route without sending data or requiring internet access.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('192.0.2.1', 9))
            addresses.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        addresses.extend(row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return list(dict.fromkeys(ip for ip in addresses if not ip.startswith('127.') and ip != '0.0.0.0'))


def connection_error(host: str, port: int, exc: Exception) -> str:
    if isinstance(exc, socket.gaierror):
        detail = 'Address not found. Find games again or load a fresh host connection file.'
    elif isinstance(exc, (TimeoutError, socket.timeout)):
        detail = 'Timed out. Check the address, incoming Python/TCP firewall access, and Wi-Fi device isolation.'
    elif isinstance(exc, ConnectionRefusedError) or getattr(exc, 'errno', None) == errno.ECONNREFUSED:
        detail = 'Connection refused. Start the server and check that both ports match.'
    else:
        detail = str(exc) or 'Connection closed.'
    if host in ('localhost', '127.0.0.1'):
        detail += ' This address means THIS computer. Find games again when joining another computer.'
    return f'{host}:{port}: {detail}'


def listen_error(port: int, exc: OSError) -> str:
    return (f'Could not host on TCP port {port}: {exc}. '
            'If a server is already running, choose Join a game and Find Games, '
            'or close the previous server before hosting again.')


def check_connection(host: str, port: int = SERVER_PORT, timeout: float = 3.0) -> str:
    host, port = validate_endpoint(host, port)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        send_message(sock, {'type': 'ping'})
        reply = receive_message(sock)
    if reply.get('type') != 'pong' or reply.get('app') != 'Dup Me':
        raise ProtocolError('This port is not running the updated Dup Me server. Use the same new folder on both computers.')
    if reply.get('version') != APP_VERSION:
        raise ProtocolError('Server version differs. Use the same new folder on both computers.')
    return f'Dup Me server reached at {host}:{port}. Ready to join.'

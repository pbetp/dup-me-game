"""Run on either computer to check the game protocol without joining a match."""
import argparse
from src.common.config import SERVER_PORT
from src.common.networking import check_connection, connection_error
from src.common.protocol import ProtocolError


def main() -> int:
    parser = argparse.ArgumentParser(description='Check reachability of a Dup Me server')
    parser.add_argument('host', help='Server IPv4 address or hostname')
    parser.add_argument('--port', type=int, default=SERVER_PORT)
    args = parser.parse_args()
    try:
        print(check_connection(args.host, args.port))
        return 0
    except (OSError, ValueError, ProtocolError) as exc:
        print(connection_error(args.host, args.port, exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

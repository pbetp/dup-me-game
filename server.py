"""Optional separate server. The Host and play mode already starts a server."""
from __future__ import annotations
import argparse
import time
from src.common.config import DEFAULT_ROUNDS, ROUND_OPTIONS, SERVER_BIND_HOST, SERVER_PORT
from src.common.networking import listen_error, local_ip_addresses
from src.server.server import DupMeServer


def main() -> int:
    parser = argparse.ArgumentParser(description='Dup Me standalone server')
    parser.add_argument('--host', default=SERVER_BIND_HOST, help='Listening address (default: all IPv4 interfaces)')
    parser.add_argument('--port', type=int, default=SERVER_PORT)
    parser.add_argument('--headless', action='store_true', help='Run without the server dashboard')
    parser.add_argument('--rounds', type=int, choices=ROUND_OPTIONS, default=DEFAULT_ROUNDS)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be from 1 to 65535.')
    if not args.headless:
        try:
            from src.server.server_ui import run_server_app
            run_server_app(args.host, args.port, args.rounds)
        except ImportError as exc:
            print(f'Tkinter unavailable: {exc}. Use --headless or install Python with Tkinter.')
            return 1
        return 0
    server = DupMeServer(host=args.host, port=args.port, total_rounds=args.rounds)
    try:
        server.start()
        print(f'Dup Me listening on {args.host}:{server.port}', flush=True)
        print(f'Host IP candidates: {", ".join(local_ip_addresses()) or "check network settings"}', flush=True)
        while server.running.is_set():
            time.sleep(0.5)
    except OSError as exc:
        print(listen_error(args.port, exc))
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

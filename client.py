"""Open this file in PyCharm or VS Code, or run python client.py."""
from __future__ import annotations
import argparse
from src.common.config import DEFAULT_ROUNDS, INSTRUMENTS, ROUND_OPTIONS, SERVER_PORT


def main() -> int:
    parser = argparse.ArgumentParser(description='Dup Me: host, join, or play with AI')
    parser.add_argument('--preview', action='store_true', help='Try the design offline')
    parser.add_argument('--mode', choices=('join', 'host', 'solo'), default='join')
    parser.add_argument('--host', default=None, help='Optional developer-configured endpoint; normal players use discovery')
    parser.add_argument('--port', type=int, default=SERVER_PORT)
    parser.add_argument('--nickname', default='')
    parser.add_argument('--rounds', type=int, choices=ROUND_OPTIONS, default=DEFAULT_ROUNDS, help='Round count for Host or AI mode')
    parser.add_argument('--instrument', choices=INSTRUMENTS, default=INSTRUMENTS[0])
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be from 1 to 65535.')
    if args.host is not None:
        from src.common.networking import validate_endpoint
        try:
            args.host, args.port = validate_endpoint(args.host, args.port)
        except ValueError as exc:
            parser.error(str(exc))
    try:
        from src.client.client_ui import run_client_app
        run_client_app(preview=args.preview, mode=args.mode, host=args.host, port=args.port, nickname=args.nickname, total_rounds=args.rounds, instrument=args.instrument)
    except ImportError as exc:
        print(f'Cannot open the game window: {exc}. Use Python with Tkinter installed.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

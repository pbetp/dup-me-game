"""One entry point for all play modes. No separate server is needed in Host mode."""
from client import main

if __name__ == '__main__':
    raise SystemExit(main())

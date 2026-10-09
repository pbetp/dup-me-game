# Version 4.0 — rubric implementation and demo readiness

- Normal joining discovers hosts automatically through UDP; connection-file save/load provides a fallback without manual IP/port entry.
- Host and play opens a dashboard attached to its actual server, with online count/list, Reset Game and endpoint export. SERV reopens a hidden dashboard.
- Explicit Welcome, WIN/LOST/DRAW and REMATCH labels.
- Standard mode is fixed at two rounds; longer matches are a separate Extended mode.
- Creation keeps its full 10-second deadline even when all 20 slots are filled. Empty patterns produce zero points without automatically inserted notes.
- Missing/stale phase tokens are rejected. Heartbeats detect stale peers and allow a clean retry after a lost network.
- Completed-match review and CSV export show positional correctness and final scores.
- Preserves the 17-key piano, four instruments, offline preview, adaptive bot and existing game design for later UI work.
- Expanded automated suite from 45 to 61 tests; real two-client GUI workflow passes.
- Replaced old setup instructions with a run/test guide, professor Q&A, architecture, current protocol and rubric mapping.

The protocol version is 4.0. Use this release on both computers, including any separately started server or bot. Older clients are rejected clearly.

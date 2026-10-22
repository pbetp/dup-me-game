# Looping soundtrack update — 10 October 2026

- Added the supplied Arrival at Zenith recording as an automatic, two-minute looping soundtrack.
- Crossfaded the track's ending into its opening to soften the repeat transition.
- Music has a separate volume slider, initially 18%; zero silences music while preserving piano notes.
- Master mute covers both piano and music. Opening Settings preserves mute.
- Music continues between screens and stops when the game closes; piano notes use their existing player independently.
- Native playback on macOS/Windows; Linux streams through aplay. No new Python runtime dependencies.
- Network rules, protocol, and existing selection highlights are preserved.

# Selection visibility update — 10 October 2026

- Selected AI difficulty, rounds, practice level, melody count, and instrument now have a bright cyan fill, dark text, and a checkmark.
- Defaults are marked immediately; the selected option stays highlighted while hovering and updates when the value changes.
- Uses the same themed controls on macOS, Windows, and Linux and retains keyboard focus feedback.
- Verified on macOS: all 70 regression tests and the GUI smoke check passed, including selection changes and layouts at 960×700 and 1280×800.
- Run `play.py` as before. No additional dependencies or protocol changes.

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

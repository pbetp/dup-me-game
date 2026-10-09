"""Shared defaults; players find games or load a host connection file."""

SERVER_BIND_HOST = "0.0.0.0"

# Low-level client default. The launcher uses discovery for remote joining.
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 55000

DISCOVERY_PORT = 55001
APP_VERSION = "4.1"
HEARTBEAT_INTERVAL = 3.0
HEARTBEAT_TIMEOUT = 15.0
MAX_MESSAGE_BYTES = 64 * 1024
MAX_NICKNAME_LENGTH = 20
MAX_PATTERN_STEPS = 20
CREATE_SECONDS = 10
REPEAT_SECONDS = 20
PHASE_RESULT_SECONDS = 2.0

DEFAULT_ROUNDS = 2
ROUND_OPTIONS = (2, 4, 6, 8, 10, 12)

# Chromatic C4–E5. Black keys sit after the given white-key index.
# (note ID, computer key, MIDI pitch, display color, white-key index, black)
PIANO_KEYS = (
    ("c4", "z", 60, "#ff7c96", 0, False),
    ("cs4", "s", 61, "#f39acb", 0, True),
    ("d4", "x", 62, "#ffb36b", 1, False),
    ("ds4", "d", 63, "#fbd77a", 1, True),
    ("e4", "c", 64, "#ffe781", 2, False),
    ("f4", "v", 65, "#b5ed8d", 3, False),
    ("fs4", "g", 66, "#7ee5bb", 3, True),
    ("g4", "b", 67, "#82e5dd", 4, False),
    ("gs4", "h", 68, "#72d7f7", 4, True),
    ("a4", "n", 69, "#8cb9ff", 5, False),
    ("as4", "j", 70, "#abacff", 5, True),
    ("b4", "m", 71, "#c6a2ff", 6, False),
    ("c5", ",", 72, "#e5a0ed", 7, False),
    ("cs5", "l", 73, "#ffa1cd", 7, True),
    ("d5", ".", 74, "#ffa6ae", 8, False),
    ("ds5", ";", 75, "#ffc98e", 8, True),
    ("e5", "/", 76, "#fff0a3", 9, False),
)
WHITE_KEYS = tuple(note for note in PIANO_KEYS if not note[5])
BLACK_KEYS = tuple(note for note in PIANO_KEYS if note[5])
# Keep the wire field named "color"; its value is now a musical note ID.
COLORS = tuple((note[0], note[3]) for note in PIANO_KEYS)
COLOR_NAMES = tuple(name for name, _hex in COLORS)
KEY_TO_COLOR = {note[1]: note[0] for note in PIANO_KEYS}
KEYSYM_TO_KEY = {"comma": ",", "period": ".", "slash": "/", "semicolon": ";"}
NOTE_FREQUENCIES = {note[0]: 440.0 * 2 ** ((note[2] - 69) / 12) for note in PIANO_KEYS}
INSTRUMENTS = ("Classic Piano", "Synthesizer", "Electric Piano", "Organ")

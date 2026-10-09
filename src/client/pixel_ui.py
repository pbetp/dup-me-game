"""Resolution-independent pixel artwork and the live game board.

All art is drawn locally with Tk Canvas. No downloaded fonts, image files,
web browser, or extra packages are needed. Edit PALETTE to change the theme.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable

from src.common.config import (BLACK_KEYS, COLORS, DEFAULT_ROUNDS, INSTRUMENTS,
                               KEY_TO_COLOR, MAX_PATTERN_STEPS, PIANO_KEYS, WHITE_KEYS)


PALETTE = {
    "background": "#050b22", "panel": "#07132f", "panel_light": "#0b2048",
    "border": "#2456ad", "blue": "#1677eb", "cyan": "#70e9ff",
    "pink": "#ff82d3", "yellow": "#ffdf65", "green": "#b0f77b",
    "text": "#eaf2ff", "muted": "#90abd2", "danger": "#ff819b",
}
COLOR_HEX = dict(COLORS)
KEY_LABELS = {color: key.upper() for key, color in KEY_TO_COLOR.items()}

# Original 5x7 bitmap alphabet, drawn as rectangles so the headings remain
# genuinely pixelated on every operating system.
GLYPHS = {
    "A": "01110/10001/10001/11111/10001/10001/10001",
    "B": "11110/10001/10001/11110/10001/10001/11110",
    "C": "01111/10000/10000/10000/10000/10000/01111",
    "D": "11110/10001/10001/10001/10001/10001/11110",
    "E": "11111/10000/10000/11110/10000/10000/11111",
    "F": "11111/10000/10000/11110/10000/10000/10000",
    "G": "01111/10000/10000/10111/10001/10001/01111",
    "H": "10001/10001/10001/11111/10001/10001/10001",
    "I": "11111/00100/00100/00100/00100/00100/11111",
    "J": "00111/00010/00010/00010/10010/10010/01100",
    "K": "10001/10010/10100/11000/10100/10010/10001",
    "L": "10000/10000/10000/10000/10000/10000/11111",
    "M": "10001/11011/10101/10101/10001/10001/10001",
    "N": "10001/11001/10101/10011/10001/10001/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110",
    "P": "11110/10001/10001/11110/10000/10000/10000",
    "Q": "01110/10001/10001/10001/10101/10010/01101",
    "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110",
    "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "10001/10001/10001/10001/10001/10001/01110",
    "V": "10001/10001/10001/10001/10001/01010/00100",
    "W": "10001/10001/10001/10101/10101/10101/01010",
    "X": "10001/10001/01010/00100/01010/10001/10001",
    "Y": "10001/10001/01010/00100/00100/00100/00100",
    "Z": "11111/00001/00010/00100/01000/10000/11111",
    "0": "01110/10001/10011/10101/11001/10001/01110",
    "1": "00100/01100/00100/00100/00100/00100/01110",
    "2": "01110/10001/00001/00010/00100/01000/11111",
    "3": "11110/00001/00001/01110/00001/00001/11110",
    "4": "00010/00110/01010/10010/11111/00010/00010",
    "5": "11111/10000/10000/11110/00001/00001/11110",
    "6": "01110/10000/10000/11110/10001/10001/01110",
    "7": "11111/00001/00010/00100/01000/01000/01000",
    "8": "01110/10001/10001/01110/10001/10001/01110",
    "9": "01110/10001/10001/01111/00001/00001/01110",
    ":": "00000/00100/00100/00000/00100/00100/00000",
    "-": "00000/00000/00000/11111/00000/00000/00000",
    "/": "00001/00001/00010/00100/01000/10000/10000",
    "?": "01110/10001/00001/00010/00100/00000/00100",
    "+": "00000/00100/00100/11111/00100/00100/00000",
    "!": "00100/00100/00100/00100/00100/00000/00100",
    ".": "00000/00000/00000/00000/00000/00100/00100",
    ",": "00000/00000/00000/00000/00110/00100/01000",
    ";": "00000/00110/00110/00000/00110/00100/01000",
    " ": "00000/00000/00000/00000/00000/00000/00000",
    "'": "00100/00100/01000/00000/00000/00000/00000",
    "%": "11001/11010/00010/00100/01000/01011/10011",
}

# Pixel icons for the top-right controls, drawn like the glyphs above.
ICONS = {
    "gear": ("00001110000/00101110100/01111111110/00111111100/11110001111/11100000111/"
             "11110001111/00111111100/01111111110/00101110100/00001110000"),
    "speaker": ("000000100000000/000001100001000/000011100000100/111111100100010/111111100010010/"
                "111111100010010/111111100100010/000011100000100/000001100001000/000000100000000"),
    "book": ("011111000111110/100000101000001/101110101011101/100000101000001/101110101011101/"
             "100000101000001/101110101011101/100000111000001/011111101111110"),
    "fullscreen": ("11110000001111/11110000001111/11000000000011/11000000000011/00000000000000/"
                   "00000000000000/11000000000011/11000000000011/11110000001111/11110000001111"),
    "exit": ("1111111000000/1000001000000/1000001000100/1000001000110/1001001111111/"
             "1000001000110/1000001000100/1000001000000/1111111000000"),
    "speaker_off": ("000000100000000/000001100000000/000011100000000/111111100000000/111111100000000/"
                    "111111100000000/111111100000000/000011100000000/000001100000000/000000100000000"),
}


@dataclass
class BoardState:
    round_number: int = 1
    total_rounds: int = DEFAULT_ROUNDS
    phase: str = "create"
    role: str = "creator"
    remaining: int = 10
    scores: list[dict] = field(default_factory=list)
    pattern: list[str] = field(default_factory=list)
    feedback: list[bool] = field(default_factory=list)
    pattern_length: int = 0
    enabled: bool = False
    complete: bool = False
    instruction: str = "Create a pattern - up to 20 notes"
    status: str = ""
    preview: bool = False
    welcome_name: str = ""

    def begin(self, event: dict) -> None:
        self.round_number = int(event.get("round", 1))
        self.total_rounds = int(event.get("total_rounds", self.total_rounds))
        self.phase = event.get("phase", "create")
        self.role = event.get("role", "creator")
        self.remaining = int(event.get("duration", 0))
        self.scores = event.get("scores", self.scores)
        # Never retain the creator's visible sequence during repetition.
        self.pattern = []
        self.feedback = []
        self.pattern_length = int(event.get("pattern_length", 0))
        self.complete = False
        self.status = ""
        self.enabled = (self.phase, self.role) in {("create", "creator"), ("repeat", "repeater")}
        if self.phase == "create":
            self.instruction = (f"Create a pattern - up to {MAX_PATTERN_STEPS} notes" if self.role == "creator"
                                else "Watch the keyboard and memorize")
        else:
            self.instruction = (f"Repeat all {self.pattern_length} notes from memory" if self.role == "repeater"
                                else "Your opponent is repeating your pattern")

    @property
    def my_turn(self) -> bool:
        """True during this player's own phase, even after their notes or time run out."""
        if self.complete:
            return False
        return self.preview or (self.phase, self.role) in {("create", "creator"), ("repeat", "repeater")}

    def add_note(self, color: str) -> bool:
        if color not in COLOR_HEX or self.phase != "create" or len(self.pattern) >= MAX_PATTERN_STEPS:
            return False
        self.pattern.append(color)
        return True

    @property
    def blind(self) -> bool:
        """The watcher sees how many notes were played, but must memorise them from the keyboard."""
        return self.phase == "create" and self.role == "repeater" and not self.preview and not self.complete

    @property
    def counter(self) -> str:
        if self.phase == "create":
            return f"{len(self.pattern):02} / {MAX_PATTERN_STEPS} NOTES"
        return f"{len(self.feedback):02} / {self.pattern_length:02} ANSWERS"


class PixelCanvas(tk.Canvas):
    """A 1440 x 810 artboard with scaled, centered coordinates."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("bg", PALETTE["background"])
        super().__init__(master, highlightthickness=0, **kwargs)
        self.scale = 1.0
        self.ox = self.oy = 0.0

    def layout(self) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        self.scale = max(0.1, min(width / 1440, height / 810))
        self.ox = (width - 1440 * self.scale) / 2
        self.oy = (height - 810 * self.scale) / 2

    def rect(self, x, y, w, h, color, **kwargs):
        return self.create_rectangle(
            round(self.ox + x * self.scale), round(self.oy + y * self.scale),
            round(self.ox + (x + w) * self.scale), round(self.oy + (y + h) * self.scale),
            fill=color, outline="", **kwargs
        )

    def text(self, x, y, text, size=16, color=None, anchor="center", bold=False, **kwargs):
        return self.create_text(
            self.ox + x * self.scale, self.oy + y * self.scale,
            text=text, fill=color or PALETTE["text"], anchor=anchor,
            font=("Courier", -max(9, round(size * self.scale)), "bold" if bold else "normal"),
            **kwargs,
        )

    def _bits(self, left, top, rows, unit, color, **kwargs):
        # One rectangle per horizontal run of lit pixels keeps the canvas item count (and redraw time) low.
        for row, line in enumerate(rows):
            column = 0
            while column < len(line):
                if line[column] != "1":
                    column += 1
                    continue
                start = column
                while column < len(line) and line[column] == "1":
                    column += 1
                self.rect(left + start * unit, top + row * unit, (column - start) * unit, unit, color, **kwargs)

    def pixels(self, x, y, text, unit=4, color=None, center=False, shadow=True, **kwargs):
        text = str(text).upper()
        if center:
            x -= (len(text) * 6 - 1) * unit / 2
        for offset, fill in ([(unit, "#29135e")] if shadow else []) + [(0, color or PALETTE["text"])]:
            for char_index, char in enumerate(text):
                glyph = GLYPHS.get(char, GLYPHS["?"]).split("/")
                self._bits(x + char_index * 6 * unit + offset, y + offset, glyph, unit, fill, **kwargs)

    def label(self, x, y, text, unit=2, color=None, center=True):
        """Pixel-font text; falls back to Courier only for characters the pixel font lacks (e.g. Thai names)."""
        text = str(text).upper().replace("…", "...").replace("·", "-")
        if all(char in GLYPHS for char in text):
            self.pixels(x, y, text, unit, color, center=center, shadow=False)
        else:
            self.text(x, y + 3.5 * unit, text, round(unit * 7), color, anchor="center" if center else "w", bold=True)

    def icon(self, x, y, name, unit=3, color=None, **kwargs):
        """Draw a pixel icon centred on (x, y)."""
        rows = ICONS[name].split("/")
        left, top = x - len(rows[0]) * unit / 2, y - len(rows) * unit / 2
        self._bits(left, top, rows, unit, color or PALETTE["text"], **kwargs)

    def panel(self, x, y, w, h, accent=None, fill=None):
        accent = accent or PALETTE["blue"]
        self.rect(x + 5, y + 6, w, h, "#020512")
        self.rect(x + 5, y, w - 10, h, accent)
        self.rect(x, y + 5, w, h - 10, accent)
        self.rect(x + 4, y + 5, w - 8, h - 10, PALETTE["border"])
        self.rect(x + 7, y + 8, w - 14, h - 16, fill or PALETTE["panel"])
        self.rect(x + 9, y + 3, w - 18, 2, PALETTE["cyan"] if accent != PALETTE["pink"] else "#ffc8ed")
        self.rect(x + 8, y + h - 7, w - 16, 3, "#102452")

    def room(self) -> None:
        self.rect(0, 0, 1440, 810, PALETTE["background"])
        for y in range(0, 750, 66):
            self.rect(0, y, 1440, 2, "#0b1935")
            for x in range(-50 if y % 132 else 0, 1440, 112):
                self.rect(x, y, 2, 66, "#0b1935")
        # Night window, city silhouette and a stepped crescent moon.
        self.panel(24, 120, 136, 300, "#153d83", "#071331")
        self.rect(37, 135, 110, 268, "#112865")
        for x, y, w, h in [(45, 330, 26, 65), (77, 285, 30, 110), (112, 312, 25, 83)]:
            self.rect(x, y, w, h, "#050c29")
            for yy in range(y + 10, y + h - 5, 18):
                for xx in range(x + 6, x + w - 4, 12):
                    self.rect(xx, yy, 4, 6, "#d8b94c")
        for x, y, w, h in [(80, 165, 20, 8), (72, 173, 20, 24), (80, 197, 20, 8), (92, 190, 12, 7)]:
            self.rect(x, y, w, h, PALETTE["yellow"])
        self.rect(88, 164, 17, 25, "#112865")
        self.rect(88, 135, 5, 268, "#163875")
        self.rect(36, 264, 110, 5, "#163875")
        self.rect(17, 414, 151, 12, "#332844")
        # Pixel speaker and records on the opposite wall.
        self.panel(1288, 350, 121, 175, "#153d83")
        for y, size in [(378, 32), (432, 54)]:
            self.rect(1348 - size / 2, y, size, size, "#10265a")
            self.rect(1355 - size / 2, y + 7, size - 14, size - 14, "#020818")
            self.rect(1343, y + size / 2 - 5, 10, 10, "#234c87")
        for x, h, color in [(1298, 82, "#312862"), (1310, 90, "#153e66"), (1324, 74, "#673346"), (1336, 83, "#23595a"), (1352, 94, "#343668"), (1366, 80, "#66562b")]:
            self.rect(x, 654 - h, 9, h, color)
            self.rect(x + 2, 640 - h, 5, 3, "#7891bc")
        self.rect(1274, 655, 146, 10, "#332844")
        # Hanging plant and a warm pixel lamp.
        self.rect(1280, 241, 140, 10, "#332844")
        self.rect(1300, 212, 28, 27, "#503653")
        for x, y in [(1300, 197), (1315, 187), (1329, 207), (1290, 216), (1285, 233), (1280, 250), (1290, 267), (1281, 283)]:
            self.rect(x, y, 15, 9, "#125343")
            self.rect(x + 4, y - 4, 8, 9, "#23785c")
        self.rect(1373, 207, 5, 31, "#e9a648")
        self.rect(1356, 193, 40, 19, "#f6b644")
        self.rect(1364, 185, 24, 13, "#ffdf7f")
        for x, y in [(193, 167), (1215, 212), (94, 480), (1320, 116), (311, 286), (1192, 285)]:
            self.rect(x, y, 4, 14, "#733775")
            self.rect(x - 5, y + 5, 14, 4, "#733775")
        self.rect(0, 738, 1440, 3, "#12336b")
        for y in (752, 782, 808):
            self.rect(0, y, 1440, 2, "#0d2350")


class GameBoard(PixelCanvas):
    def __init__(self, master, state: BoardState, actions: dict[str, Callable]):
        super().__init__(master, takefocus=True)
        self.state = state
        self.actions = actions
        self.muted = False
        self.volume = 60
        self.instrument = INSTRUMENTS[0]
        self.active_note: str | None = None
        self.flashes = True
        self.hover = ""
        self.regions: list[tuple[str, tuple, Callable]] = []
        self._draw_job = None
        self._flash_job = None
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _event: self._set_hover(""))
        self.bind("<Destroy>", self._destroyed)

    def redraw(self) -> None:
        if self._draw_job is None and self.winfo_exists():
            self._draw_job = self.after_idle(self._render)

    def _destroyed(self, event) -> None:
        if event.widget is self:
            for job in (self._draw_job, self._flash_job):
                if job:
                    self.after_cancel(job)

    def flash(self, color: str, force: bool = False) -> None:
        """Light up a key. force=True ignores the "Flash keys" setting (used for the opponent's notes)."""
        if not self.flashes and not force:
            return
        if self._flash_job:
            self.after_cancel(self._flash_job)
        self.active_note = color
        self._flash_job = self.after(600, self._end_flash)
        self._draw_flash()

    def _end_flash(self) -> None:
        self._flash_job = None
        self.active_note = None
        self.delete("flash")

    def region(self, name: str, x, y, w, h, callback):
        self.regions.append((name, (x, y, x + w, y + h), callback))

    def _hit(self, event):
        x, y = (event.x - self.ox) / self.scale, (event.y - self.oy) / self.scale
        for name, (x1, y1, x2, y2), callback in reversed(self.regions):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name, callback
        return "", None

    def _click(self, event):
        self.focus_set()
        _name, callback = self._hit(event)
        if callback:
            callback()

    def _motion(self, event):
        name, _callback = self._hit(event)
        self._set_hover(name)

    def _set_hover(self, name):
        if name != self.hover:
            self.hover = name
            self.configure(cursor="hand2" if name else "")
            self.redraw()

    def control(self, name, x, y, w, h, label, accent=None, icon=None):
        self.panel(x, y, w, h, accent or PALETTE["blue"],
                   PALETTE["panel_light"] if self.hover == name else None)
        if icon:
            self.icon(x + w / 2, y + h / 2, icon, 3, accent or PALETTE["cyan"])
        else:
            unit = 2 if h < 50 else 2.5
            self.label(x + w / 2, y + h / 2 - 3.5 * unit, label, unit, accent or PALETTE["cyan"])
        self.region(name, x, y, w, h, self.actions[name])

    def _turn_color(self) -> str:
        s, p = self.state, PALETTE
        if s.preview:
            return p["cyan"]
        if s.complete:
            return p["yellow"]
        return p["green"] if s.my_turn else p["pink"]

    def _render(self) -> None:
        self._draw_job = None
        self.layout()
        self.delete("all")
        self.regions = []
        self.room()
        s, p = self.state, PALETTE
        turn = self._turn_color()
        if not s.preview:
            # Coloured frame around the whole screen: green = your turn, pink = opponent's.
            width, height = self.winfo_width(), self.winfo_height()
            for x1, y1, x2, y2 in ((0, 0, width, 6), (0, height - 6, width, height),
                                   (0, 0, 6, height), (width - 6, 0, width, height)):
                self.create_rectangle(x1, y1, x2, y2, fill=turn, outline="")
        self.panel(24, 23, 348, 68)
        self.pixels(44, 46, self._round_text(), 3, p["yellow"])
        self.panel(587, 16, 266, 87, p["cyan"])
        clock, clock_color = self._clock()
        self.pixels(720, 37, clock, 6, clock_color, center=True)
        self.control("settings", 1136, 26, 76, 58, "", icon="gear")
        self.control("help", 1228, 26, 76, 58, "", icon="book")
        self.control("fullscreen", 1320, 26, 76, 58, "", icon="fullscreen")
        if "server" in self.actions:
            self.control("server", 216, 732, 100, 56, "SERV")
        if "exit" in self.actions:
            # Force exit (bottom-left): forfeits a live match, or leaves offline practice.
            x, y, w, h = 24, 732, 176, 56
            self.panel(x, y, w, h, p["pink"], "#2a0f2e" if self.hover == "exit" else None)
            self.icon(x + 48, y + h / 2, "exit", 3, p["pink"])
            self.pixels(x + 112, y + h / 2 - 10, "EXIT", 3, p["pink"], center=True, shadow=False)
            self.region("exit", x, y, w, h, self.actions["exit"])
        self.pixels(720, 118, self._title(), 6, turn, center=True)
        self.label(720, 176, s.instruction, 2.5, p["text"])
        self._scores(turn)
        self._sequence()
        self._keyboard()
        if s.status:
            self.label(720, 724, s.status, 2.5, p["green"])
        if self.active_note:
            self._draw_flash()

    def _round_text(self) -> str:
        s = self.state
        return "FREE PLAY" if s.preview else f"ROUND {s.round_number} / {s.total_rounds}"

    def _clock(self) -> tuple[str, str]:
        s, p = self.state, PALETTE
        if s.preview:
            return "--:--", p["cyan"]
        remaining = max(0, s.remaining)
        return f"{remaining // 60:02}:{remaining % 60:02}", p["pink"] if remaining <= 4 else p["cyan"]

    def _title(self) -> str:
        s = self.state
        return ("FREE PLAY" if s.preview else "ROUND COMPLETE" if s.complete
                else "YOUR TURN" if s.my_turn else "OPPONENT'S TURN")

    def _scores(self, turn: str) -> None:
        s, p = self.state, PALETTE
        mine = 0
        for index, row in enumerate(s.scores[:2]):
            if s.welcome_name and str(row.get("nickname", "")).casefold() == s.welcome_name.casefold():
                mine = index
        active = None if s.complete else mine if (s.my_turn or s.preview) else 1 - mine
        for index, x in enumerate((367, 768)):
            row = s.scores[index] if len(s.scores) > index else {"nickname": "PLAYER", "score": 0}
            lit = index == active
            accent = turn if lit else (p["cyan"] if index == 0 else p["pink"]) if active is None else "#2b4677"
            grow = 4 if lit else 0
            self.panel(x - grow, 213 - grow, 307 + 2 * grow, 62 + 2 * grow, accent, p["panel_light"] if lit else None)
            nickname = str(row.get("nickname", "PLAYER"))
            if len(nickname) > 12:
                nickname = nickname[:11] + "."
            name_color = accent if active is None or lit else p["muted"]
            self.label(x + 24, 234, nickname, 3, name_color, center=False)
            self.pixels(x + 265, 233, str(row.get("score", 0)), 3, p["yellow"], center=True)
        self.pixels(720, 233, "VS", 3, p["muted"], center=True)

    def _sequence(self):
        s, p = self.state, PALETTE
        self.panel(176, 299, 1088, 147)
        self.label(201, 320, s.counter, 2.5, p["cyan"], center=False)
        if s.preview:
            self.control("undo", 992, 310, 112, 36, "UNDO")
            self.control("clear", 1117, 310, 122, 36, "CLEAR", p["pink"])
        for index in range(MAX_PATTERN_STEPS):
            x, y = 198 + index * 52, 362
            color, label = p["panel_light"], ""
            if index < len(s.pattern) and s.blind:
                color, label = "#1b3f7d", "?"
            elif index < len(s.pattern):
                color = COLOR_HEX.get(s.pattern[index], p["panel_light"])
                label = KEY_LABELS.get(s.pattern[index], "")
            elif s.phase == "repeat" and index < s.pattern_length:
                label = "?"
            if s.phase == "repeat" and not s.complete and index < len(s.feedback):
                color = "#244d3c" if s.feedback[index] else "#562239"
                label = "+" if s.feedback[index] else "X"
            border = p["cyan"] if (s.phase == "create" and index == len(s.pattern)) else p["border"]
            self.rect(x, y, 45, 52, border)
            self.rect(x + 2, y + 2, 41, 48, color)
            if label:
                dark_label = index < len(s.pattern) and not s.blind
                self.pixels(x + 22.5, y + 15, label, 3, "#081028" if dark_label else p["text"],
                            center=True, shadow=False)

    def _keyboard(self):
        s, p = self.state, PALETTE
        self.panel(153, 464, 1134, 248, self._turn_color())
        self.rect(169, 479, 1102, 215, "#02071a")
        # Draw white keys first; black key regions win overlap hit-testing.
        for color, key, _midi, _accent, index, _black in WHITE_KEYS:
            x, y, w, h = 180 + index * 108, 483, 104, 203
            fill = "#e8efff" if s.enabled else "#b2bfd8"
            self.rect(x + 3, y + 5, w, h, "#24428c")
            self.rect(x, y, w, h - 6, "#688ce2")
            self.rect(x + 3, y, w - 6, h - 12, fill)
            self.rect(x + 7, y + 4, w - 14, 5, "#ffffff")
            self.rect(x + 7, y + h - 23, w - 14, 5, "#bac9f1")
            self.pixels(x + w / 2, y + 140, key, 4, "#061233", center=True, shadow=False)
            if self.hover == f"note-{color}" and s.enabled:
                self.rect(x + 3, y + h - 13, w - 6, 4, p["cyan"])
            if s.enabled:
                self.region(f"note-{color}", x, y, w, h, lambda chosen=color: self.actions["note"](chosen))
        for color, key, _midi, _accent, index, _black in BLACK_KEYS:
            x, y, w, h = 180 + (index + 1) * 108 - 33, 483, 62, 125
            tag = {"tags": ("blackkey",)}
            self.rect(x + 3, y + 5, w, h, "#020512", **tag)
            self.rect(x, y, w, h, p["cyan"] if self.hover == f"note-{color}" else "#1b4caa", **tag)
            self.rect(x + 4, y + 3, w - 8, h - 10, "#040d28", **tag)
            self.rect(x + 7, y + 5, w - 14, 3, "#3a82ba", **tag)
            self.rect(x + 6, y + h - 12, w - 12, 4, "#70357f", **tag)
            self.pixels(x + w / 2, y + 84, key, 3, p["text"], center=True, shadow=False, **tag)
            if s.enabled:
                self.region(f"note-{color}", x, y, w, h, lambda chosen=color: self.actions["note"](chosen))

    def _draw_flash(self) -> None:
        """Light up the played key on its own layer, so it shows instantly without a full redraw."""
        self.delete("flash")
        note = next((row for row in PIANO_KEYS if row[0] == self.active_note), None)
        if note is None:
            return
        _color, key, _midi, accent, index, black = note
        if black:
            x, y, w, h = 180 + (index + 1) * 108 - 33, 483, 62, 125
        else:
            x, y, w, h = 180 + index * 108, 483, 104, 191
        glow = {"tags": ("flash",)}
        self.rect(x - 7, y - 7, w + 14, h + 14, "#ffffff", **glow)
        self.rect(x - 3, y - 3, w + 6, h + 6, accent, **glow)
        self.rect(x + 6, y + 6, w - 12, h - 12, "#ffffff" if black else accent, **glow)
        self.rect(x + 12, y + 12, w - 24, h - 24, accent, **glow)
        text_y = y + 84 if black else y + 140
        self.pixels(x + w / 2, text_y, key, 3 if black else 4, "#061233", center=True, shadow=False, **glow)
        if not black:
            # Keep neighbouring black keys on top of a lit white key.
            self.tag_raise("blackkey")


class PracticeBoard(GameBoard):
    """Practice board: live typing-test stats replace the two player scores.

    stage is "listen" while the melody plays, "answer" while the player repeats it,
    and "reveal" while the melody is shown after the last answer. state.pattern holds
    the notes on show (only the given first note until the reveal), state.pattern_length
    the whole melody, and state.feedback one entry per answer from the second note on.
    """

    def __init__(self, master, state: BoardState, actions: dict[str, Callable], stats: Callable[[], dict]):
        super().__init__(master, state, actions)
        self.stats = stats
        self.stage = "listen"

    def _turn_color(self) -> str:
        return {"listen": PALETTE["cyan"], "answer": PALETTE["green"]}.get(self.stage, PALETTE["yellow"])

    def _round_text(self) -> str:
        return f"MELODY {self.state.round_number} / {self.state.total_rounds}"

    def _clock(self) -> tuple[str, str]:
        seconds = int(self.stats()["seconds"])
        return f"{seconds // 60:02}:{seconds % 60:02}", PALETTE["cyan"]

    def _title(self) -> str:
        if self.stage == "listen":
            return "LISTEN"
        if self.stage == "answer":
            return "PLAY IT BACK"
        return "PERFECT!" if all(self.state.feedback) else "NICE TRY"

    def _scores(self, turn: str) -> None:
        stats, p = self.stats(), PALETTE
        played = stats["notes"]
        cells = (("ACC", f"{stats['accuracy']}%" if played else "-", p["green"]),
                 ("PREC", f"{stats['precision']}%" if played else "-", p["cyan"]),
                 ("NPM", str(stats["npm"]) if played else "-", p["yellow"]),
                 ("COMBO", str(stats["combo"]), p["pink"]))
        for index, (name, value, color) in enumerate(cells):
            x = 296 + index * 216
            self.panel(x, 213, 200, 62, color)
            self.label(x + 22, 238, name, 2, p["muted"], center=False)
            self.pixels(x + 136, 233, value, 3, color, center=True)

    def _sequence(self):
        s, p = self.state, PALETTE
        self.panel(176, 299, 1088, 147)
        to_find = max(0, s.pattern_length - 1)
        self.label(201, 320, f"FIRST NOTE GIVEN - {len(s.feedback):02} / {to_find:02} FOUND", 2.5, p["cyan"],
                   center=False)
        if self.stage == "answer" and "replay" in self.actions:
            self.control("replay", 1043, 310, 196, 36, "SPACE REPLAY")
        for index in range(s.pattern_length):
            x, y = 198 + index * 52, 362
            color, label, dark = p["panel_light"], "?", False
            if index < len(s.pattern):
                color, label, dark = COLOR_HEX.get(s.pattern[index], p["panel_light"]), KEY_LABELS.get(s.pattern[index], ""), True
            answer = index - 1
            if not s.complete and 0 <= answer < len(s.feedback):
                color, dark = ("#244d3c", False) if s.feedback[answer] else ("#562239", False)
                label = "+" if s.feedback[answer] else "X"
            current = self.stage == "answer" and answer == len(s.feedback)
            border = p["cyan"] if current else p["yellow"] if index == 0 else p["border"]
            self.rect(x, y, 45, 52, border)
            self.rect(x + 2, y + 2, 41, 48, color)
            self.pixels(x + 22.5, y + 15, label, 3, "#081028" if dark else p["text"], center=True, shadow=False)
            if index == 0:
                # The reference note: a yellow bar marks it as given, not scored.
                self.rect(x, 418, 45, 6, p["yellow"])
            elif s.complete and answer < len(s.feedback):
                # Under the revealed melody: green = you got it, pink = you missed it.
                self.rect(x, 418, 45, 6, p["green"] if s.feedback[answer] else p["pink"])

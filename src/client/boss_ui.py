"""Co-op boss fight board drawn on the approved "Concert Party" artwork.

Two allied performers on the left face THE DISSONANT on the right, two note
ribbons show each player's phrase, and the painted piano at the bottom is the
playable one. Painted text that changes during the fight (phrase, boss HP, the
P1/P2 tags, damage popups, the TEAM ATTACK banner and both ribbons) is cleared
from the artwork once at load and drawn live with the pixel font instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageTk

from src.common.config import BLACK_KEYS, BOSS_MAX_HP, BOSS_NAME, PIANO_KEYS, PLAYER_MAX_HP, WHITE_KEYS
from .art_screen import ART_DIR
from .pixel_ui import PALETTE, GameBoard

ART_PATH = ART_DIR / "boss-concert-party.png"
ART_W, ART_H = 1586, 992
RIBBON_DX = 783
# The painted piano: ten 125px white keys from x=200, black keys centred on the gaps.
KEY_LEFT, KEY_TOP, KEY_W = 200, 712, 125
BLACK_INDEXES = {note[4] for note in BLACK_KEYS}
CONTROL_BOXES = {"settings": (1338, 10, 1410, 74), "help": (1420, 10, 1494, 74),
                 "fullscreen": (1502, 10, 1574, 74), "exit": (20, 916, 194, 978)}
# Painted panels whose contents change: refilled with their own background colour.
CLEAR_BOXES = (
    ((994, 17, 1294, 54), (1000, 35)),       # phrase
    ((1043, 64, 1217, 101), (1100, 80)),     # boss HP number
    ((486, 66, 1038, 101), (980, 85)),       # boss HP bar
    ((138, 265, 262, 318), (300, 560)),      # P1 tag
    ((310, 265, 439, 318), (300, 560)),      # P2 tag
    ((36, 553, 781, 664), (300, 560)),       # P1 ribbon
    ((819, 553, 1553, 664), (1200, 600)),    # P2 ribbon
)
# Painted text over the scene, softened into the background instead:
# (box, blur radius, brightness) for the banner and the two damage popups.
SOFTEN_BOXES = (((524, 188, 1068, 306), 18, .22), ((1080, 106, 1220, 154), 24, .06),
                ((150, 327, 244, 373), 24, .06))

# Small pixel sprites, drawn like the glyphs in pixel_ui.
NOTE = "000110/000111/000101/000100/011100/111100/011000"
CHECK = "0000001/0000011/1000110/1101100/0111000/0010000"
CROSS = "1000001/0100010/0010100/0001000/0010100/0100010/1000001"


@lru_cache(maxsize=1)
def prepared_art() -> Image.Image:
    image = Image.open(ART_PATH).convert("RGB")
    draw = ImageDraw.Draw(image)
    for box, sample in CLEAR_BOXES:
        draw.rectangle(box, fill=image.getpixel(sample))
    for box, blur, brightness in SOFTEN_BOXES:
        patch = image.crop(box).filter(ImageFilter.GaussianBlur(blur))
        patch = ImageEnhance.Brightness(patch).enhance(brightness)
        mask = Image.new("L", patch.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((8, 8, patch.width - 8, patch.height - 8), 18, fill=255)
        image.paste(patch, box[:2], mask.filter(ImageFilter.GaussianBlur(6)))
    return image


def note_name(color: str) -> str:
    return color.upper().replace("S", "#")


@dataclass
class BossState:
    me: str = ""
    boss_name: str = BOSS_NAME
    boss_hp: int = BOSS_MAX_HP
    boss_max: int = BOSS_MAX_HP
    phrase: int = 0
    phase: str = "wait"  # wait | show | repeat | result
    remaining: int = 0
    players: list[dict] = field(default_factory=list)
    notes: dict[str, list[str]] = field(default_factory=dict)
    lengths: dict[str, int] = field(default_factory=dict)
    answers: dict[str, list[str]] = field(default_factory=dict)
    marks: dict[str, list[bool]] = field(default_factory=dict)
    shown: int = 0
    team_damage: int = 0
    hp_lost: dict[str, int] = field(default_factory=dict)
    status: str = ""
    sent: int = 0

    def apply_players(self, rows: list[dict]) -> None:
        if rows:
            self.players = rows

    def start(self, event: dict) -> None:
        self.boss_name = str(event.get("boss_name", BOSS_NAME))
        self.boss_hp = int(event.get("boss_hp", BOSS_MAX_HP))
        self.boss_max = int(event.get("boss_max_hp", BOSS_MAX_HP))
        self.apply_players(event.get("players", []))
        self.phase, self.phrase = "wait", 0

    def begin(self, event: dict) -> None:
        self.phase = str(event.get("phase", "show"))
        self.phrase = int(event.get("phrase", 1))
        self.remaining = math.ceil(float(event.get("duration", 0)))
        self.lengths = {str(k): int(v) for k, v in dict(event.get("lengths", {})).items()}
        self.boss_hp = int(event.get("boss_hp", self.boss_hp))
        self.boss_max = int(event.get("boss_max_hp", self.boss_max))
        self.apply_players(event.get("players", []))
        self.answers = {pid: [] for pid in self.lengths}
        self.marks = {pid: [] for pid in self.lengths}
        # During the repeat phase every melody is hidden again.
        self.notes = {self.me: list(event.get("notes", []))} if self.phase == "show" else {}
        self.shown = 0
        self.sent = 0
        self.status = ""
        self.team_damage = 0
        self.hp_lost = {}

    def feedback(self, event: dict) -> None:
        pid = str(event.get("player_id", ""))
        self.answers.setdefault(pid, []).append(str(event.get("color", "")))
        self.marks.setdefault(pid, []).append(bool(event.get("correct")))
        self.boss_hp = int(event.get("boss_hp", self.boss_hp))
        self.apply_players(event.get("players", []))

    def result(self, event: dict) -> None:
        self.phase = "result"
        self.remaining = 0
        rows = event.get("results", [])
        self.notes = {str(row["id"]): list(row.get("notes", [])) for row in rows}
        self.answers = {str(row["id"]): list(row.get("answers", [])) for row in rows}
        self.marks = {pid: [a == b for a, b in zip(self.notes[pid], answers)]
                      for pid, answers in self.answers.items()}
        self.lengths = {pid: len(notes) for pid, notes in self.notes.items()}
        self.hp_lost = {str(row["id"]): int(row.get("hp_lost", 0)) for row in rows}
        self.team_damage = int(event.get("team_damage", 0))
        self.boss_hp = int(event.get("boss_hp", self.boss_hp))
        self.apply_players(event.get("players", []))

    def row(self, mine: bool) -> tuple[int, dict]:
        """(player number, row) for this player or their ally."""
        for index, row in enumerate(self.players):
            if (row.get("id") == self.me) == mine:
                return index + 1, row
        return (1 if mine else 2), {"id": "", "nickname": "ALLY", "hp": PLAYER_MAX_HP, "max_hp": PLAYER_MAX_HP}

    @property
    def my_hp(self) -> int:
        return int(self.row(True)[1].get("hp", 0))

    @property
    def can_play(self) -> bool:
        return (self.phase == "repeat" and self.my_hp > 0 and self.boss_hp > 0
                and self.sent < self.lengths.get(self.me, 0))

    @property
    def enabled(self) -> bool:
        return self.can_play


class BossBoard(GameBoard):
    """The approved Concert Party artwork with the live fight drawn into it.

    Coordinates are artwork pixels (1586 x 992). The painted logo, boss, players,
    piano, controls and rules stay as painted; the painted piano is the real one.
    """

    def __init__(self, master, state: BossState, actions: dict[str, Callable]):
        super().__init__(master, state, actions)
        self._photo: ImageTk.PhotoImage | None = None
        self._photo_size = (0, 0)

    # ---- artwork coordinates ----

    def layout(self) -> None:
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        self.scale = max(0.1, min(width / ART_W, height / ART_H))
        self.ox = (width - ART_W * self.scale) / 2
        self.oy = (height - ART_H * self.scale) / 2

    def _background(self) -> None:
        size = (max(1, round(ART_W * self.scale)), max(1, round(ART_H * self.scale)))
        if size != self._photo_size:
            self._photo = ImageTk.PhotoImage(prepared_art().resize(size, Image.Resampling.LANCZOS), master=self)
            self._photo_size = size
        self.create_image(round(self.ox), round(self.oy), image=self._photo, anchor="nw")

    # ---- small drawing helpers ----

    def _sprite(self, x, y, rows, unit, color):
        rows = rows.split("/")
        self._bits(x - len(rows[0]) * unit / 2, y - len(rows) * unit / 2, rows, unit, color)

    @staticmethod
    def _width(text: str, unit: float) -> float:
        return (len(str(text)) * 6 - 1) * unit

    def _corners(self, box, color):
        x0, y0, x1, y1 = box
        for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            self.rect(min(x, x + dx * 16), y - (4 if dy > 0 else 0), 16, 4, color)
            self.rect(x - (4 if dx > 0 else 0), min(y, y + dy * 16), 4, 16, color)

    def _turn_color(self) -> str:
        s, p = self.state, PALETTE
        if s.phase == "result":
            return p["yellow"]
        if s.can_play:
            return p["green"]
        return p["cyan"] if s.phase in ("show", "wait") else p["pink"]

    # ---- the screen ----

    def _render(self) -> None:
        self._draw_job = None
        self.layout()
        self.delete("all")
        self.regions = []
        self._background()
        turn = self._turn_color()
        for x, y, w, h in ((0, 0, ART_W, 6), (0, ART_H - 6, ART_W, 6), (0, 0, 6, ART_H), (ART_W - 6, 0, 6, ART_H)):
            self.rect(x, y, w, h, turn)
        self._header()
        self._players()
        self._banner()
        self._ribbon(0, True)
        self._ribbon(RIBBON_DX, False)
        self._keyboard()
        self._controls()
        if self.active_note:
            self._draw_flash()

    def _header(self) -> None:
        s, p = self.state, PALETTE
        phase = {"show": f"LISTEN {s.remaining:02}", "repeat": f"PLAY {s.remaining:02}",
                 "result": "RESULTS", "wait": "GET READY"}.get(s.phase, "")
        text = f"PHRASE {s.phrase:02} / {phase}" if s.phrase else phase
        self.label(1144, 27, text, 2.3, p["pink"] if s.phase == "repeat" and s.remaining <= 4 else "#aef0ff")
        ratio = max(0.0, min(1.0, s.boss_hp / max(1, s.boss_max)))
        x, y, w, h = 490, 70, 544, 28
        self.rect(x, y, w, h, "#13314d")
        fill = round(w * ratio)
        self.rect(x, y, fill, h, "#86f25c" if ratio > .3 else p["danger"])
        self.rect(x, y, fill, 5, "#d6ffb8" if ratio > .3 else "#ffd0da")
        self.label(1130, 73, f"{s.boss_hp} / {s.boss_max} HP", 2.6, "#aef0ff")
        if s.phase == "result" and s.team_damage:
            self.label(1150, 116, f"-{s.team_damage} HP", 4, "#ff5c6c")

    def _players(self) -> None:
        s, p = self.state, PALETTE
        for mine, cx, accent, body in ((True, 200, p["cyan"], (100, 362, 290, 515)),
                                       (False, 375, p["pink"], (318, 350, 530, 515))):
            number, row = s.row(mine)
            hp, max_hp = int(row.get("hp", 0)), int(row.get("max_hp", PLAYER_MAX_HP))
            name = str(row.get("nickname", "PLAYER"))
            name = name if len(name) <= 6 else name[:5] + "."
            self.label(cx, 271, f"P{number} {name}", 2.4, accent)
            self.label(cx, 297, "KO" if hp <= 0 else f"{hp} / {max_hp} HP", 2.4,
                       p["muted"] if hp <= 0 else "#ffe36b" if mine else "#ffffff")
            if hp <= 0:
                # A knocked-out performer fades into the crowd.
                self.rect(body[0], body[1], body[2] - body[0], body[3] - body[1], "#000000", stipple="gray50")
            lost = s.hp_lost.get(str(row.get("id")), 0) if s.phase == "result" else 0
            if lost:
                self.label(cx - 4, 338, f"-{lost} HP", 3.2, "#ff5c6c")

    def _banner(self) -> None:
        s, p = self.state, PALETTE
        title, subtitle, color = self._banner_text()
        unit = 6 if len(title) <= 12 else 5
        self.pixels(795, 202, title, unit, color, center=True)
        half = self._width(title, unit) / 2
        for x in (795 - half - 34, 795 + half + 34):
            self._sprite(x, 228, NOTE, 5, color)
        if subtitle:
            self.label(795, 262, subtitle, 3.4, "#ffffff")
        if s.status:
            self.rect(560, 296, 470, 26, "#05082c", stipple="gray75")
            self.label(795, 302, s.status, 2.2, p["yellow"])

    def _banner_text(self) -> tuple[str, str, str]:
        s, p = self.state, PALETTE
        gold = "#ffd75a"
        if s.phase == "show":
            return ("LISTEN!", "MEMORIZE YOUR PHRASE", p["pink"]) if s.my_hp > 0 else \
                ("KNOCKED OUT", "YOUR ALLY FIGHTS ON", p["danger"])
        if s.phase == "repeat":
            if s.my_hp <= 0:
                return "KNOCKED OUT", "CHEER ON YOUR ALLY", p["danger"]
            if s.can_play:
                left = s.lengths.get(s.me, 0) - s.sent
                return "YOUR TURN", f"PLAY {left} MORE NOTE{'S' if left != 1 else ''}", p["green"]
            return "PHRASE DONE", "WAITING FOR YOUR ALLY", p["cyan"]
        if s.phase == "result":
            if s.boss_hp <= 0:
                return "BOSS DOWN!", f"{s.team_damage} DAMAGE TO BOSS", gold
            if not s.team_damage:
                return "MISSED!", "NO DAMAGE THIS PHRASE", p["danger"]
            return "TEAM ATTACK", f"{s.team_damage} DAMAGE TO BOSS", gold
        return "GET READY", f"{s.boss_name} TAKES THE STAGE", p["cyan"]

    def _ribbon(self, dx: int, mine: bool) -> None:
        s, p = self.state, PALETTE
        number, row = s.row(mine)
        pid = str(row.get("id", ""))
        hp, max_hp = int(row.get("hp", 0)), int(row.get("max_hp", PLAYER_MAX_HP))
        accent = p["cyan"] if mine else p["pink"]
        name = str(row.get("nickname", "PLAYER"))
        name = name if len(name) <= 10 else name[:9] + "."
        self.label(52 + dx, 562, f"{name} / {'YOU' if mine else 'ALLY'} (P{number})", 2.8, accent, center=False)
        for y in range(558, 662, 9):
            self.rect(496 + dx, y, 3, 5, "#3a5fa8")
        marks = s.marks.get(pid, [])
        correct = f"{sum(marks)} CORRECT"
        self.label(514 + dx, 566, correct, 2.1, "#8af25c", center=False)
        self.label(514 + dx + self._width(correct + " ", 2.1) + 2.1, 566, f"- {len(marks) - sum(marks)} WRONG",
                   2.1, "#ff5c6c", center=False)
        self.label(517 + dx, 607, f"{hp} / {max_hp} HP", 2.8, "#ffffff" if hp else p["muted"], center=False)
        ratio = max(0.0, min(1.0, hp / max(1, max_hp)))
        self.rect(518 + dx, 631, 176, 22, "#2b6fd6")
        self.rect(520 + dx, 633, 172, 18, "#13314d")
        self.rect(520 + dx, 633, round(172 * ratio), 18, "#86f25c" if ratio > .3 else p["danger"])
        lost = s.hp_lost.get(pid, 0) if s.phase == "result" else 0
        if lost:
            self.label(702 + dx, 636, f"-{lost} HP", 2.4, "#ff5c6c", center=False)
        length = s.lengths.get(pid, 0)
        if not length:
            self.label(269 + dx, 618, "KNOCKED OUT - WATCHING" if hp <= 0 else "WAITING FOR THE BOSS",
                       2.4, p["muted"])
            return
        notes, answers = s.notes.get(pid, []), s.answers.get(pid, [])
        step = min(73.5, 442 / length)
        width = step - 8
        unit = min(2.6, (width - 8) / 17)
        for index in range(length):
            x, y = 48 + dx + index * step, 591
            border, label, mark = "#2fd8ff", "?", None
            if s.phase == "show" and mine:
                if index < s.shown:
                    label = note_name(notes[index])
                    border = "#ffffff" if index == s.shown - 1 else border
            elif s.phase == "result" and index < len(notes):
                label = note_name(notes[index])
                mark = marks[index] if index < len(marks) else "missed"
            elif index < len(answers):
                label, mark = note_name(answers[index]), marks[index]
            elif s.phase == "repeat" and mine and index == len(answers) and s.can_play:
                border = p["green"]
            fill = {True: "#06233a", False: "#2a0b2c", "missed": "#0b0f2a"}.get(mark, "#040a2c")
            self.rect(x, y, width, 68, border)
            self.rect(x + 3, y + 3, width - 6, 62, fill)
            self.label(x + width / 2, y + 9, label, unit, p["muted"] if mark == "missed" else "#ffffff")
            if mark is True:
                self._sprite(x + width / 2, y + 48, CHECK, 3, "#8af25c")
            elif mark is False:
                self._sprite(x + width / 2, y + 48, CROSS, 3, "#ff5c6c")
            elif mark == "missed":
                self.rect(x + width / 2 - 10, y + 46, 20, 4, "#ff5c6c")

    def _key_box(self, index: int, black: bool) -> tuple[float, float, float, float]:
        if black:
            return KEY_LEFT + (index + 1) * KEY_W - 36, KEY_TOP, 72, 108
        return KEY_LEFT + index * KEY_W, KEY_TOP, KEY_W, 176

    def _keyboard(self) -> None:
        """Keep the painted piano visible; gate input with its click regions.

        The listen phase must still show the keys so forced note flashes have
        a visible keyboard beneath them. A full-piano black stipple overlay is
        not portable: macOS Tk can paint it as an opaque black rectangle.
        """
        s, p = self.state, PALETTE
        # White keys first; black key areas win overlapping clicks.
        for keys in (WHITE_KEYS, BLACK_KEYS):
            for color, _key, _midi, _accent, index, black in keys:
                x, y, w, h = self._key_box(index, black)
                if not s.enabled:
                    continue
                if self.hover == f"note-{color}":
                    self.rect(x + 6, y + h - (16 if not black else 14), w - 12, 6, p["cyan"])
                self.region(f"note-{color}", x, y, w, h, lambda chosen=color: self.actions["note"](chosen))

    def _controls(self) -> None:
        for name, box in CONTROL_BOXES.items():
            if name not in self.actions:
                continue
            x0, y0, x1, y1 = box
            self.region(name, x0, y0, x1 - x0, y1 - y0, self.actions[name])
            if self.hover == name:
                self._corners(box, PALETTE["pink"] if name == "exit" else PALETTE["cyan"])
        if "server" in self.actions:
            self.control("server", 212, 918, 150, 58, "SERV")

    def _draw_flash(self) -> None:
        self.delete("flash")
        note = next((row for row in PIANO_KEYS if row[0] == self.active_note), None)
        if note is None:
            return
        _color, key, _midi, accent, index, black = note
        glow = {"tags": ("flash",)}
        x, y, w, h = self._key_box(index, black)
        if black:
            self.rect(x + 3, y + 3, w - 6, h - 10, "#ffffff", **glow)
            self.rect(x + 8, y + 8, w - 16, h - 20, accent, **glow)
            self.pixels(x + w / 2, y + 62, key, 3, "#061233", center=True, shadow=False, **glow)
            return
        # A white key shows below the black keys and in the gap between them.
        left = 36 if index - 1 in BLACK_INDEXES else 0
        right = 36 if index in BLACK_INDEXES else 0
        self.rect(x + left + 4, y + 4, w - left - right - 8, 112, accent, **glow)
        self.rect(x + 5, y + 110, w - 10, h - 118, accent, **glow)
        self.rect(x + 5, y + h - 14, w - 10, 6, "#ffffff", **glow)
        self.pixels(x + w / 2, y + 122, key, 4, "#061233", center=True, shadow=False, **glow)

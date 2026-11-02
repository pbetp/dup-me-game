"""Live, scalable multiplayer lounge artwork and controls.

The original rooftop GIF preserves the detailed musicians, disco and keyboards.
Interface text and hit areas are real canvas controls, never a baked screenshot.
The original opening-screen animation is intentionally independent of this page.
"""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace
from tkinter import font as tkfont
from typing import Callable

from .art_screen import CHECK, ArtButton, ArtChoice, ArtScreen, ArtStatus, inside
from .pixel_ui import PixelCanvas

CYAN = "#22e7f5"
PINK = "#f85ccf"
GOLD = "#ffe27a"
INK = "#04102a"
PANEL = "#06132b"
MUTED = "#b8bde8"
HEADPHONES = "00011111000/00100000100/01000000010/10000000001/10000000001/11000000011/11100000111/11100000111/11100000111/11100000111/01100000110"


def _shade(color: str, amount: float) -> str:
    return "#" + "".join(f"{min(255, max(0, round(int(color[i:i + 2], 16) * amount))):02x}" for i in (1, 3, 5))


class LobbyButton(ArtButton):
    """A drawn arcade button with normal widget-style state and text calls."""
    focusable = True

    def __init__(self, screen, box, text, command, color=CYAN, primary=False):
        super().__init__(screen, box, command, color)
        self.text, self.primary = text, primary

    def configure(self, state=None, text=None, color=None, primary=None, **_options):
        if state is not None:
            self.disabled = state == "disabled"
        if text is not None:
            self.text = text
        if color is not None:
            self.color = color
        if primary is not None:
            self.primary = primary
        self.screen.refresh()

    config = configure

    def cget(self, key):
        if key == "text":
            return self.text
        if key == "state":
            return "disabled" if self.disabled else "normal"
        raise KeyError(key)

    def draw(self, screen, hover):
        x0, y0, x1, y1 = self.box
        w, h = x1 - x0, y1 - y0
        color = "#385184" if self.disabled else self.color
        if self.primary:
            screen.cut_panel(self.box, color, "#122449" if self.disabled else color, bevel=True)
            ink = "#8192bd" if self.disabled else INK
        else:
            screen.cut_panel(self.box, color, "#071831" if hover else PANEL, bevel=False)
            ink = "#8192bd" if self.disabled else self.color
        label = self.text.upper().replace("\u2713", "").strip()
        left_arrow, right_arrow = label.startswith("< "), label.endswith(" >")
        if left_arrow:
            label = label[2:]
        if right_arrow:
            label = label[:-2]
        checked = "\u2713" in self.text
        prefix = checked or left_arrow
        columns = len(label) * 6 - 1 + (10 if prefix else 0) + (10 if right_arrow else 0)
        unit = min(2.8 if self.primary else 2.4, (w - 24) / max(1, columns))
        left = (x0 + x1) / 2 - columns * unit / 2
        middle = (y0 + y1) / 2
        arrow = "00010/00100/01000/10000/01000/00100/00010"
        if prefix:
            screen.sprite(left + 3.5 * unit, middle, CHECK if checked else arrow, unit, ink)
            left += 10 * unit
        screen.label(left, middle - 3.5 * unit, label, unit, ink, center=False)
        if right_arrow:
            screen.sprite(left + (len(label) * 6 + 5) * unit, middle,
                          "/".join(row[::-1] for row in arrow.split("/")), unit, ink)
        if hover and not self.disabled:
            screen.corners((x0 - 4, y0 - 4, x1 + 4, y1 + 4), "#f0faff")


class LobbyServerList:
    """Small room browser with Listbox-compatible calls and live room details."""
    focusable = True

    def __init__(self, screen, box, on_select=None, on_join=None):
        self.screen, self.box = screen, box
        self.on_select, self.on_join = on_select, on_join
        self.disabled = False
        self.rows = []
        self.selected = None
        self.offset = 0
        self.row_height = 60
        self.bindings = {}

    @property
    def visible_count(self):
        return max(1, int((self.box[3] - self.box[1]) / self.row_height))

    def configure(self, state=None, **_options):
        if state is not None:
            self.disabled = state == "disabled"
        self.screen.refresh()

    config = configure

    def instate(self, states):
        return all(self.disabled if value == "disabled" else not self.disabled if value == "!disabled" else False for value in states)

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = callback

    def _notify(self):
        event = SimpleNamespace(widget=self)
        if self.on_select:
            self.on_select()
        callback = self.bindings.get("<<ListboxSelect>>")
        if callback:
            callback(event)
        self.screen.refresh()

    def set_rooms(self, servers):
        old = self.rows[self.selected] if self.selected is not None and self.selected < len(self.rows) else {}
        key = (old.get("host"), old.get("port"))
        self.rows = [dict(row) for row in servers]
        self.selected = next((i for i, row in enumerate(self.rows) if (row.get("host"), row.get("port")) == key and self._count(row) < 2), None)
        if self.selected is None:
            self.selected = next((i for i, row in enumerate(self.rows) if self._count(row) < 2), None)
        self.offset = max(0, min(self.selected or 0, max(0, len(self.rows) - self.visible_count)))
        self._notify()

    def delete(self, first, last=None):
        if last == "end" or first == 0:
            self.rows.clear()
            self.selected = None
            self.offset = 0
        else:
            del self.rows[int(first):int(last if last is not None else first) + 1]
            self.selected = None
        self.screen.refresh()

    def insert(self, index, text):
        # Compatibility for callers still filling an ordinary Listbox.
        if "no games found" not in str(text).lower():
            row = {"name": str(text).strip().split(" · ")[0]}
            if index == "end":
                self.rows.append(row)
            else:
                self.rows.insert(int(index), row)
        self.screen.refresh()

    def size(self):
        return len(self.rows)

    def get(self, index):
        return self.rows[int(index)].get("name", "Room")

    def selection_set(self, first, last=None):
        if self.rows and 0 <= int(first) < len(self.rows):
            self.selected = int(first)
            self.offset = max(0, min(self.selected, max(0, len(self.rows) - self.visible_count)))
            self._notify()

    select_set = selection_set

    def selection_clear(self, first=0, last="end"):
        self.selected = None
        self._notify()

    def curselection(self):
        return () if self.selected is None or self.selected >= len(self.rows) else (self.selected,)

    def press(self, x, y):
        if self.disabled:
            return
        visible_row = int((y - self.box[1]) / self.row_height)
        if (not inside(self.box, x, y) or visible_row >= self.visible_count
                or (y - self.box[1]) % self.row_height >= self.row_height - 4):
            return
        index = self.offset + visible_row
        if 0 <= index < len(self.rows):
            self.selection_set(index)

    def release(self, x, y):
        pass

    def invoke(self):
        if self.disabled or not self.curselection():
            return
        if self.on_join:
            self.on_join()
        elif "<Double-Button-1>" in self.bindings:
            self.bindings["<Double-Button-1>"](SimpleNamespace(widget=self))

    def move(self, direction):
        if not self.disabled and self.rows:
            self.selection_set(max(0, min(len(self.rows) - 1, (self.selected if self.selected is not None else 0) + direction)))

    @staticmethod
    def _count(row):
        value = row.get("players", row.get("player_count", 1))
        return len(value) if isinstance(value, (list, tuple, dict)) else int(value or 0)

    def draw(self, screen, hover):
        x0, y0, x1, y1 = self.box
        screen.rect(x0, y0, x1 - x0, y1 - y0, "#030c21")
        if not self.rows:
            screen.text(x0 + 16, (y0 + y1) / 2, "No games found yet.", 16, MUTED, anchor="w")
            return
        for index in range(self.offset, min(len(self.rows), self.offset + self.visible_count)):
            row = self.rows[index]
            y = y0 + (index - self.offset) * self.row_height
            active = index == self.selected
            screen.cut_panel((x0, y, x1, y + self.row_height - 4), PINK if active else "#204a75", "#21132e" if active else PANEL)
            screen.frame((x0 + 15, y + 17, x0 + 35, y + 37), PINK if active else "#42618b", 2)
            if active:
                screen.rect(x0 + 15, y + 17, 20, 20, PINK)
                screen.text(x0 + 25, y + 26, "\u2713", 17, INK, bold=True)
            name = str(row.get("name") or row.get("nickname") or "Friend's room")
            screen.text(x0 + 51, y + 19, screen.fit_text(name, x1 - x0 - 120, 16), 16, "#f2f2ff", anchor="w", bold=True)
            count = self._count(row)
            mode = "BOSS CO-OP" if row.get("mode") == "boss" else "1V1"
            rounds = row.get("total_rounds")
            details = f"{mode}  ·  " + (f"{rounds} rounds  ·  " if rounds else "") + f"{count} / 2 players"
            screen.text(x0 + 51, y + 43, details, 10, MUTED, anchor="w")
            screen.label(x1 - 27, y + 22, "FULL" if count >= 2 else "OPEN", 1.4, GOLD)
        if len(self.rows) > self.visible_count:
            screen.text(x1 - 5, y1 + 11, f"{self.offset + 1} / {len(self.rows)} · scroll for rooms", 10, MUTED, anchor="e")
        if self.disabled:
            screen.frame(self.box, "#385184", 2)
        elif hover:
            screen.corners(self.box, "#edf8ff")


class LobbyScreen(ArtScreen):
    """1280×720 logical lounge; preserves its 16:9 fit at every window size."""

    def __init__(self, master, page="host", role="host", nickname="", play_mode="versus", rounds=2,
                 can_animate: Callable[[], bool] = lambda: True):
        # Decode the exact original animation; never replace detailed art with polygons.
        super().__init__(master, "multiplayer-rooftop-jam.gif", can_animate)
        self.page, self.role, self.nickname = page, role, nickname
        self.play_mode, self.rounds = play_mode, rounds
        self._focus_control = None
        self._draw_tag = "interface"
        self._players = []
        self._player_id = self._host_id = None
        self._ready = {}
        self._browser = None
        self.bind("<Double-Button-1>", self._double)
        self.bind("<Tab>", lambda _event: self._tab(1))
        self.bind("<Shift-Tab>", lambda _event: self._tab(-1))
        self.bind("<ISO_Left_Tab>", lambda _event: self._tab(-1))
        self.bind("<Return>", self._return)
        self.bind("<KP_Enter>", self._return)
        self.bind("<space>", self._return)
        self.bind("<Down>", lambda _event: self._move_list(1))
        self.bind("<Up>", lambda _event: self._move_list(-1))
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda event: self._wheel(event, -1))
        self.bind("<Button-5>", lambda event: self._wheel(event, 1))

    def rect(self, x, y, w, h, color, **kwargs):
        kwargs.setdefault("tags", self._draw_tag)
        return PixelCanvas.rect(self, x, y, w, h, color, **kwargs)

    def text(self, x, y, text, size=16, color=None, anchor="center", bold=False, **kwargs):
        kwargs.setdefault("tags", self._draw_tag)
        return PixelCanvas.text(self, x, y, text, size, color, anchor, bold, **kwargs)

    def fit_text(self, value, width, size, bold=True):
        """Keep names on one line, including wide Unicode nicknames."""
        value = str(value)
        font = tkfont.Font(root=self, family="Courier", size=-max(9, round(size * self.scale)), weight="bold" if bold else "normal")
        if font.measure(value) <= width * self.scale:
            return value
        while value and font.measure(value + "...") > width * self.scale:
            value = value[:-1]
        return value + "..."

    def _poly(self, points, fill, outline="", width=1):
        coordinates = [value for x, y in points for value in self.to_canvas(x, y)]
        return self.create_polygon(*coordinates, fill=fill, outline=outline, width=max(1, width * self.scale), tags=self._draw_tag)

    def _line(self, points, color, width=1):
        coordinates = [value for x, y in points for value in self.to_canvas(x, y)]
        return self.create_line(*coordinates, fill=color, width=max(1, width * self.scale), tags=self._draw_tag)

    def cut_panel(self, box, color=CYAN, fill=PANEL, bevel=False):
        x0, y0, x1, y1 = box
        n = 5
        shape = [(x0 + n, y0), (x1 - n, y0), (x1, y0 + n), (x1, y1 - n), (x1 - n, y1), (x0 + n, y1), (x0, y1 - n), (x0, y0 + n)]
        self._poly(shape, fill, color, 2)
        if bevel:
            self._line([(x0 + 6, y0 + 4), (x1 - 7, y0 + 4), (x1 - 4, y0 + 7)], "#e6fbff", 2)
            self._line([(x0 + 5, y1 - 5), (x1 - 6, y1 - 5), (x1 - 3, y1 - 8)], _shade(color, .45), 3)
            for x, y in ((x0 + 7, y0 + 7), (x1 - 10, y0 + 7), (x0 + 7, y1 - 10), (x1 - 10, y1 - 10)):
                self.rect(x, y, 3, 3, "#f6fbff")

    def button(self, box, text, command, color=CYAN, primary=False):
        control = LobbyButton(self, box, text, command, color, primary)
        self.controls.append(control)
        self.refresh()
        return control

    def choices(self, variable, items, colors=None, command=None, style="button"):
        colors = dict({"border": "#225f8a", "hover": CYAN, "off": PANEL, "on": CYAN, "ink": INK, "back": PANEL, "unit": 1.9}, **(colors or {}))
        controls = super().choices(variable, items, colors, command, style)
        for control in controls:
            control.focusable = True
        self.refresh()
        return controls

    def status(self, left, right, y, text="", **options):
        options.setdefault("color", MUTED)
        result = super().status(left, right, y, text, **options)
        self.refresh()
        return result

    def server_list(self, box, on_select=None, on_join=None):
        control = LobbyServerList(self, box, on_select, on_join)
        self.controls.append(control)
        self._browser = control
        self.refresh()
        return control

    def set_players(self, players, player_id=None, host_id=None, ready_by_id=None):
        self._players = [dict(player) for player in players]
        self._player_id, self._host_id = player_id, host_id
        self._ready = ready_by_id or {player.get("id"): bool(player.get("ready")) for player in players}
        self.refresh()

    def set_details(self, rounds=None, play_mode=None):
        if rounds is not None:
            self.rounds = rounds
        if play_mode is not None:
            self.play_mode = play_mode
        self.refresh()

    def _redraw(self):
        self._redraw_job = None
        if self._disposed:
            return
        self.layout()
        self._paint_frame()
        self.delete("interface")
        self._draw_tag = "interface"
        self._draw_panel()
        for draw in self.drawers:
            draw(self)
        for control in self.controls:
            control.draw(self, control is self.hover or control is self._focus_control)

    def _draw_panel(self):
        # Keep the original jeweled neon frame and logo. Only replace its interior.
        self.rect(850, 210, 382, 435, PANEL)
        title = {"host": "HOST A GAME", "join": "JOIN A GAME", "lobby": "WAITING ROOM"}[self.page]
        # Layer the bitmap lettering for the chunky white/cyan arcade heading.
        self.label(871, 224, title, 3.0, "#128cbd", center=False)
        self.label(870.8, 222, title, 3.0, "#f2f5ff", center=False)
        self.label(870, 222, title, 3.0, "#f2f5ff", center=False)
        badge_color = CYAN if self.role == "host" else PINK
        self.cut_panel((1153, 219, 1220, 246), badge_color, PANEL)
        self.label(1186.5, 228, "HOST" if self.role == "host" else "CLIENT", 1.35, badge_color)
        mode = "BOSS CO-OP" if self.play_mode == "boss" else "1V1 BATTLE"
        self.label(870, 257, mode, 1.9, GOLD, center=False)
        helper = {"host": "Create a room for you and a friend.",
                  "join": "Find a room and play with a friend.",
                  "lobby": ("Team up against THE DISSONANT" if self.play_mode == "boss"
                            else f"{self.rounds} rounds · {'Standard' if self.rounds == 2 else 'Extended'}")}[self.page]
        self.text(870, 283, helper, 12, MUTED, anchor="w")
        self.rect(870, 302, 350, 1, CYAN)
        if self.page == "host":
            self.label(870, 316, "PLAYING AS", 1.6, CYAN, center=False)
            self.cut_panel((870, 340, 1220, 375), "#1b437a", PANEL)
            self.sprite(891, 357, HEADPHONES, 2.1, CYAN)
            self.text(918, 357, self.fit_text(self.nickname, 285, 17), 17, "#f2f5ff", anchor="w", bold=True)
            self.label(870, 390, "ROUNDS" if self.play_mode != "boss" else "TEAM UP", 1.6, CYAN, center=False)
        elif self.page == "join":
            self.label(870, 321, "PLAYING AS", 1.5, CYAN, center=False)
            self.sprite(980, 326, HEADPHONES, 1.8, PINK)
            self.text(1001, 328, self.fit_text(self.nickname, 218, 16), 16, "#f2f5ff", anchor="w", bold=True)
            self.label(870, 361, "NEARBY GAMES", 1.6, CYAN, center=False)
            count = len(self._browser.rows) if self._browser else 0
            self.text(1220, 367, f"{count} room{'s' if count != 1 else ''} found", 11, MUTED, anchor="e")
        else:
            self.label(870, 317, "PLAYERS", 1.6, CYAN, center=False)
            self.text(1220, 323, f"{len(self._players)} / 2", 16, CYAN, anchor="e", bold=True)
            players = sorted(self._players, key=lambda p: p.get("id") != self._host_id)
            for index in range(2):
                self._draw_player(index, players[index] if index < len(players) else None)

    def _draw_player(self, index, player):
        x0, y0 = 870, 340 + index * 75
        color = CYAN if index == 0 else PINK
        self.cut_panel((x0, y0, 1220, y0 + 65), color, PANEL, bevel=True)
        self.sprite(x0 + 32, y0 + 32, HEADPHONES, 3, color if player else "#99518c")
        if not player:
            self.text(x0 + 65, y0 + 20, "PLAYER 2", 16, "#e9ecff", anchor="w", bold=True)
            self.text(x0 + 65, y0 + 46, "WAITING TO JOIN", 12, GOLD, anchor="w", bold=True)
            return
        own = player.get("id") == self._player_id
        host = player.get("id") == self._host_id
        self.text(x0 + 65, y0 + 17, self.fit_text(player.get("nickname", "Player"), 267, 17),
                  17, "#f2f5ff", anchor="w", bold=True)
        badge = "YOU · HOST" if own and host else "HOST" if host else "YOU" if own else "PLAYER 2"
        self.rect(x0 + 65, y0 + 35, 98, 19, color)
        self.text(x0 + 114, y0 + 44, badge, 11, INK, bold=True)
        ready = self._ready.get(player.get("id"), player.get("ready", False))
        status = "CONNECTED" if host else "READY" if ready else "NOT READY"
        self.text(x0 + 182, y0 + 44, status, 12, color if (host or ready) else GOLD, anchor="w", bold=True)

    def _tab(self, direction):
        available = [control for control in self.controls if getattr(control, "focusable", False) and not getattr(control, "disabled", False)]
        if available:
            index = available.index(self._focus_control) if self._focus_control in available else (-1 if direction > 0 else 0)
            self._focus_control = available[(index + direction) % len(available)]
            self.refresh()
        return "break"

    def _mouse_down(self, event):
        self._focus_control = None
        return super()._mouse_down(event)

    def _return(self, _event=None):
        if self.can_animate():
            control = self._focus_control
            if control is not None and not getattr(control, "disabled", False):
                control.invoke()
            elif self.default_action is not None:
                self.default_action()
        return "break"

    def _double(self, event):
        control = self.control_at(*self._art_point(event))
        if isinstance(control, LobbyServerList):
            x, y = self._art_point(event)
            visible_row = int((y - control.box[1]) / control.row_height)
            if (visible_row < control.visible_count
                    and (y - control.box[1]) % control.row_height < control.row_height - 4
                    and control.offset + visible_row < len(control.rows)):
                control.invoke()
        return "break"

    def _move_list(self, direction):
        if isinstance(self._focus_control, LobbyServerList):
            self._focus_control.move(direction)
        else:
            return self._tab(direction)
        return "break"

    def _wheel(self, event, direction=None):
        control = self.control_at(*self._art_point(event))
        if isinstance(control, LobbyServerList):
            control.move(direction if direction is not None else (-1 if event.delta > 0 else 1))
        return "break"


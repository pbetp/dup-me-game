"""Pixel-art desktop client. The server owns all live game decisions."""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter import font as tkfont
from typing import Any

from src.common import message_types as mt
from src.common.config import (
    COLORS, CREATE_SECONDS, DEFAULT_ROUNDS, INSTRUMENTS, KEY_TO_COLOR, KEYSYM_TO_KEY, MAX_PATTERN_STEPS, ROUND_OPTIONS,
    REPEAT_SECONDS, SERVER_PORT,
)
from src.common.validation import validate_nickname
from src.common.discovery import discover_servers, load_connection_file, resolve_connection_file, save_connection_file
from src.server.server_ui import ServerWindow
from src.common.networking import listen_error, local_ip_addresses
from .practice import LENGTH_OPTIONS, LEVELS, PracticeSession
from .local_game import LocalGame
from .match_report import review_rounds, export_csv
from .network_client import NetworkClient
from .pixel_ui import KEY_LABELS, BoardState, GameBoard, PALETTE, PixelCanvas, PracticeBoard
from .sound import NotePlayer
from .music import BackgroundMusic
from .opening_screen import OpeningScreen
from .boss_ui import BossBoard, BossState
from .art_screen import ArtScreen
from .lobby_screen import LobbyScreen

SETUP_SCREENS = ("solo", "host", "join")
MODE_LABELS = {"versus": "1V1 BATTLE", "boss": "BOSS CO-OP"}
MODE_HINTS = {
    "versus": "1V1: take turns - most points wins.",
    "boss": "CO-OP: beat THE DISSONANT together.",
}
# Choice buttons drawn over the menu artwork ("back" is sampled from each artwork).
SINGLE_CHOICE = {"border": "#1f78ff", "hover": "#70e9ff", "off": "#071a4a", "on": "#5cf2ff", "ink": "#04102e"}
PRACTICE_CHOICE = {"border": "#8a5cff", "hover": "#c9a4ff", "off": "#171354", "on": "#5cf2ff", "ink": "#04102e"}
MODE_CHOICE = {"border": "#1f78ff", "hover": "#70e9ff", "off": "#071a4a", "on": "#ff6ad5", "ink": "#2a0630"}


class ClientWindow:
    def __init__(self, root: tk.Tk, preview: bool = False, mode: str = "join",
                 host: str | None = None, port: int = SERVER_PORT, nickname: str = "",
                 total_rounds: int = DEFAULT_ROUNDS, instrument: str = INSTRUMENTS[0]):
        self.root = root
        # Menu text and boxes grow with the window (the game board scales itself).
        self.ui_scale = 1.0
        self._fonts: dict[tuple[int, bool], tkfont.Font] = {}
        self._wrapped: list[tuple[tk.Widget, int]] = []
        self._sized: list[tuple[tk.Widget, int]] = []
        self._rescale_hooks: list[Any] = []
        self.result_texts: list[str] = []
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.network: NetworkClient | None = None
        self.player_id: str | None = None
        self.nickname = nickname
        self.mode, self.host, self.port = mode, host, port
        # Multiplayer style: "versus" (1v1) or "boss" (co-op). The host's choice wins on join.
        self.play_mode = "versus"
        self.boss_state = BossState()
        self.servers = ([{"name": "Configured server", "host": host, "port": port}] if host else [])
        self.dashboard: ServerWindow | None = None
        self.local_game = LocalGame()
        self.host_addresses: list[str] = []
        self.turn_id = ""
        self.difficulty = "medium"
        self.total_rounds = total_rounds
        self.players: list[dict] = []
        self.manual_lobby = False
        self.host_player_id: str | None = None
        self.lobby_scene: LobbyScreen | None = None
        self._joining = self._ready_pending = False
        self._lobby_file_dialog = False
        self.scores: list[dict] = []
        self.round_history: list[dict] = []
        self.role = self.phase = self.current_screen = ""
        self.round_number = 0
        self.input_enabled = self.preview_mode = False
        self.board: GameBoard | None = None
        self.opening_scene: OpeningScreen | None = None
        self.state = BoardState()
        self.audio = NotePlayer()
        self.audio.instrument = instrument
        self.music = BackgroundMusic()
        self.flashes = True
        self.practice: PracticeSession | None = None
        self.practice_level, self.practice_length = "medium", LENGTH_OPTIONS[0]
        self._practice_jobs: list[str] = []
        self.dialog: tk.Frame | None = None
        self._pressed: set[str] = set()
        self._release_jobs: dict[str, str] = {}
        self._sent_steps = 0
        self._notice = ("", 0.0)
        self._busy_widgets: list[tk.Widget] = []
        self.connect_button = self.nickname_entry = self.server_list = None
        self._poll_job = None
        self._closed = False
        self.root.title("Dup Me · Pixel Arcade")
        self.root.geometry("1280x800")
        self.root.minsize(960, 700)
        self.root.configure(bg=PALETTE["background"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<KeyPress>", self._key_press)
        self.root.bind("<KeyRelease>", self._key_release)
        self.root.bind("<FocusOut>", lambda _event: self._pressed.clear())
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self._escape)
        self.root.bind("<F1>", lambda _event: self.show_help())
        self.root.bind("<Control-m>", lambda _event: self.toggle_mute())
        self.root.bind("<Configure>", self._on_resize, add="+")
        self.container = tk.Frame(root, bg=PALETTE["background"])
        self.container.pack(fill="both", expand=True)
        self._configure_styles()
        self.show_preview() if preview else self.show_menu()
        self.music.start()
        self._poll_job = self.root.after(40, self._poll_events)

    def _font(self, size: int, bold: bool = False) -> tkfont.Font:
        """Shared Courier font that resizes with the window."""
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(root=self.root, family="Courier", size=self._px(size),
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def _px(self, value: float) -> int:
        return round(value * self.ui_scale)

    def _set_width(self, widget: tk.Widget, base: int) -> None:
        widget.place_configure(width=self._px(base))
        self._sized.append((widget, base))

    def _on_resize(self, event) -> None:
        if event.widget is not self.root:
            return
        # Never smaller than the original design; steps of 0.05 avoid re-flowing on every pixel.
        scale = round(max(1.0, min(event.width / 1280, event.height / 800)) * 20) / 20
        if scale != self.ui_scale:
            self.ui_scale = scale
            self._apply_scale()

    def _apply_scale(self) -> None:
        for (size, _bold), font in self._fonts.items():
            font.configure(size=self._px(size))
        style = ttk.Style(self.root)
        style.configure("Arcade.TButton", padding=(self._px(18), self._px(13)))
        style.configure("Small.Arcade.TButton", padding=(self._px(10), self._px(6)))
        style.configure("Choice.TRadiobutton", padding=(self._px(6), self._px(7)))
        self._wrapped = [(w, base) for w, base in self._wrapped if w.winfo_exists()]
        for widget, base in self._wrapped:
            widget.configure(wraplength=self._px(base))
        self._sized = [(w, base) for w, base in self._sized if w.winfo_exists()]
        for widget, base in self._sized:
            widget.place_configure(width=self._px(base))
        for hook in list(self._rescale_hooks):
            hook()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Arcade.TButton", font=self._font(13, True), padding=(18, 13),
                        background="#133369", foreground=PALETTE["cyan"],
                        bordercolor=PALETTE["blue"], lightcolor=PALETTE["blue"],
                        darkcolor="#07132f", focuscolor=PALETTE["pink"])
        style.map("Arcade.TButton", background=[("active", "#214986"), ("disabled", "#14223d")],
                  foreground=[("disabled", "#647995")])
        style.configure("Go.Arcade.TButton", background="#1c4a33", foreground=PALETTE["green"],
                        bordercolor=PALETTE["green"], lightcolor=PALETTE["green"])
        style.map("Go.Arcade.TButton", background=[("active", "#276446"), ("disabled", "#14223d")],
                  foreground=[("disabled", "#647995")])
        style.configure("Small.Arcade.TButton", font=self._font(11, True), padding=(10, 6))
        style.configure("Arcade.TCheckbutton", background=PALETTE["panel"],
                        foreground=PALETTE["text"], font=self._font(12), padding=8)
        style.map("Arcade.TCheckbutton", background=[("active", PALETTE["panel_light"])])
        # Use the clam button surface so selection is visible on every platform,
        # including macOS, where indicator-less classic radio buttons look alike.
        style.layout("Choice.TRadiobutton", style.layout("TButton"))
        style.configure("Choice.TRadiobutton", font=self._font(12, True), padding=(6, 7),
                        anchor="center", background="#133369", foreground=PALETTE["text"],
                        borderwidth=2, relief="flat", bordercolor="#133369",
                        lightcolor="#133369", darkcolor="#133369", focuscolor=PALETTE["pink"])
        style.map("Choice.TRadiobutton",
                  background=[("disabled", "selected", "#315864"), ("disabled", "#14223d"),
                              ("selected", PALETTE["cyan"]), ("active", "#214986")],
                  foreground=[("disabled", "#90abd2"), ("selected", PALETTE["panel"])])
        for option in ("bordercolor", "lightcolor", "darkcolor"):
            style.map("Choice.TRadiobutton", **{
                option: [("disabled", "selected", "#315864"), ("disabled", "#14223d"),
                         ("selected", PALETTE["cyan"]), ("active", PALETTE["border"])]})
        style.configure("Instrument.Choice.TRadiobutton", font=self._font(11, True))

    def _label(self, master, text="", size=13, color=None, **kwargs):
        wrap = kwargs.pop("wraplength", None)
        if wrap:
            kwargs["wraplength"] = self._px(wrap)
        label = tk.Label(master, text=text, bg=PALETTE["panel"],
                         fg=color or PALETTE["text"], font=self._font(size), **kwargs)
        if wrap:
            self._wrapped.append((label, wrap))
        return label

    def _button(self, master, text, command):
        return ttk.Button(master, text=text, command=command, style="Arcade.TButton")

    def _clear(self) -> None:
        self._cancel_practice_jobs()
        self.board = None
        self._rescale_hooks.clear()
        self._pressed.clear()
        for child in self.container.winfo_children():
            child.destroy()
        self.opening_scene = None
        self.lobby_scene = None

    def _scene(self, caption: str) -> tk.Frame:
        self._clear()
        scene = PixelCanvas(self.container)
        scene.pack(fill="both", expand=True)

        def paint(_event=None):
            scene.layout()
            scene.delete("all")
            scene.room()
            scene.pixels(720, 55, "DUP ME", 9, PALETTE["cyan"], center=True)
            scene.text(720, 152, caption, 18, PALETTE["muted"], bold=True)

        scene.bind("<Configure>", paint)
        panel = tk.Frame(self.container, bg=PALETTE["panel"], padx=32, pady=25,
                         highlightthickness=3, highlightbackground=PALETTE["blue"])
        panel.place(relx=.5, rely=.56, anchor="center")
        self._set_width(panel, 510)
        return panel

    def _menu(self, screen: str, caption: str, heading: str) -> tk.Frame:
        self.current_screen = screen
        self.preview_mode = self.input_enabled = False
        self.connect_button = self.nickname_entry = self.server_list = None
        self._busy_widgets: list[tk.Widget] = []
        panel = self._scene(caption)
        panel.place_configure(rely=.6)
        panel.configure(padx=28, pady=18)
        self._label(panel, heading, 20, PALETTE["yellow"]).pack(pady=(0, 12))
        return panel

    def _footer(self, panel: tk.Frame, message: str = "", start_text: str = "") -> None:
        self.join_status = self._label(panel, message, 10, PALETTE["danger"], wraplength=440, height=2)
        self.join_status.pack(fill="x", pady=(8, 4))
        actions = tk.Frame(panel, bg=PALETTE["panel"])
        actions.pack(fill="x")
        self._button(actions, "<  BACK", self._go_back).pack(side="left", fill="x", expand=True)
        if start_text:
            self.connect_button = self._button(actions, start_text, self.connect)
            self.connect_button.pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _choice_button(self, master, text, value, variable: tk.Variable,
                       command=None, style="Choice.TRadiobutton") -> ttk.Radiobutton:
        button = ttk.Radiobutton(master, value=value, variable=variable, command=command,
                                 style=style, width=len(text) + 2, cursor="hand2", takefocus=True)

        def update_marker(*_args):
            marker = "\u2713" if str(variable.get()) == str(value) else " "
            button.configure(text=f"{marker} {text}")

        # The checkmark makes the choice explicit without relying on color alone.
        # Watching the variable also covers defaults and programmatic changes.
        trace = variable.trace_add("write", update_marker)
        button.bind("<Destroy>", lambda _event: variable.trace_remove("write", trace))
        update_marker()
        return button

    def _choice_row(self, panel: tk.Frame, title: str, options, variable: tk.Variable) -> None:
        self._label(panel, title, 11, PALETTE["cyan"]).pack(anchor="w", pady=(10, 4))
        row = tk.Frame(panel, bg=PALETTE["panel"])
        row.pack(fill="x")
        for index, (value, text) in enumerate(options):
            button = self._choice_button(row, text, value, variable)
            button.pack(side="left", fill="x", expand=True, padx=(6 if index else 0, 0))
            self._busy_widgets.append(button)

    def _nickname_field(self, panel: tk.Frame) -> None:
        self._label(panel, "YOUR NICKNAME", 11, PALETTE["cyan"]).pack(anchor="w")
        self.nickname_entry = tk.Entry(panel, font=self._font(14))
        self.nickname_entry.pack(fill="x", pady=(5, 0), ipady=4)
        self.nickname_entry.insert(0, self.nickname)
        self.nickname_entry.focus_set()

    def _read_nickname(self) -> bool:
        valid, result = validate_nickname(self.nickname_entry.get())
        if valid:
            self.nickname = result
        else:
            self.join_status.configure(text=result, fg=PALETTE["danger"])
        return valid

    def _rounds_choice(self, panel: tk.Frame) -> None:
        self.rounds_var = tk.IntVar(value=self.total_rounds)
        options = [(rounds, f"{rounds} STD" if rounds == DEFAULT_ROUNDS else str(rounds)) for rounds in ROUND_OPTIONS]
        self._choice_row(panel, "ROUNDS · STANDARD OR EXTENDED", options, self.rounds_var)

    def show_menu(self, message: str = "") -> None:
        self.current_screen = "menu"
        self.preview_mode = self.input_enabled = False
        self.connect_button = self.nickname_entry = self.server_list = None
        self._busy_widgets = []
        self._clear()
        self.opening_scene = OpeningScreen(
            self.container,
            actions=(lambda: self.show_setup("solo"), self.show_multiplayer,
                     self.show_practice_setup, self.show_settings, self.close),
            can_activate=lambda: self.dialog is None and not self._closed,
        )
        self.opening_scene.pack(fill="both", expand=True)
        self.join_status = self._label(self.opening_scene, message, 10,
                                       PALETTE["danger"], wraplength=760)
        if message:
            self.join_status.place(relx=.5, rely=.985, anchor="s")

    def _art_menu(self, screen: str, art: str) -> ArtScreen:
        """A menu page that is the approved artwork, with its painted controls made live."""
        self.current_screen = screen
        self.preview_mode = self.input_enabled = False
        self.connect_button = self.nickname_entry = self.server_list = None
        self._busy_widgets = []
        self._clear()
        scene = ArtScreen(self.container, art, can_animate=lambda: self.dialog is None and not self._closed)
        scene.pack(fill="both", expand=True)
        scene.focus_set()
        return scene

    def _art_nickname(self, scene: ArtScreen, box) -> None:
        self.nickname_entry = scene.entry(box, size=17)
        self.nickname_entry.insert(0, self.nickname)
        self.nickname_entry.focus_set()

    def show_multiplayer(self, message: str = "") -> None:
        scene = self._art_menu("multiplayer", "multiplayer-rooftop-jam.gif")
        self._art_nickname(scene, (877, 305, 1215, 342))
        self.play_mode_var = tk.StringVar(value=self.play_mode)
        back = scene.sample(1200, 365)
        # The painted Wi-Fi hint makes way for the 1V1 / BOSS CO-OP switch.
        scene.patch((866, 349, 1226, 387), back)

        self._busy_widgets += scene.choices(self.play_mode_var, [
            ("versus", MODE_LABELS["versus"], (874, 352, 1043, 384)),
            ("boss", MODE_LABELS["boss"], (1051, 352, 1220, 384)),
        ], dict(MODE_CHOICE, back=back))

        def show_hint(*_args):
            # The status line explains the chosen mode until it has an error to show.
            if self.join_status.cget("text") in MODE_HINTS.values():
                self.join_status.configure(text=MODE_HINTS[self.play_mode_var.get()], fg=PALETTE["muted"])

        trace = self.play_mode_var.trace_add("write", show_hint)
        scene.bind("<Destroy>", lambda event: event.widget is scene
                   and self.play_mode_var.trace_remove("write", trace), add="+")
        self.join_status = scene.status(866, 1226, 561, message or MODE_HINTS[self.play_mode], size=11,
                                        color=PALETTE["danger"] if message else PALETTE["muted"])
        scene.button((858, 390, 1228, 462), lambda: self._multiplayer_next("host"), PALETTE["cyan"])
        scene.button((858, 472, 1228, 550), lambda: self._multiplayer_next("join"), PALETTE["pink"])
        scene.button((865, 571, 1220, 631), self._go_back, PALETTE["cyan"])

    def _multiplayer_next(self, mode: str) -> None:
        if hasattr(self, "play_mode_var"):
            self.play_mode = self.play_mode_var.get()
        if self._read_nickname():
            self.show_setup(mode)

    def show_setup(self, mode: str, message: str = "") -> None:
        """Last step before playing: solo (vs AI), host, or join."""
        self.mode = mode
        if mode == "solo":
            scene = self._art_menu("solo", "single-orbit-dojo.gif")
            self._art_nickname(scene, (797, 315, 1222, 349))
            self.nickname_entry.bind("<Return>", lambda _event: self.connect())
            scene.default_action = self.connect
            colors = dict(SINGLE_CHOICE, back=scene.sample(1000, 470))
            self.difficulty_var = tk.StringVar(value=self.difficulty)
            self._busy_widgets += scene.choices(self.difficulty_var, [
                ("easy", "EASY", (790, 399, 930, 447)), ("medium", "MEDIUM", (941, 399, 1080, 447)),
                ("hard", "HARD", (1091, 399, 1230, 447))], colors)
            self.rounds_var = tk.IntVar(value=self.total_rounds)
            boxes = ((790, 496, 876, 542), (885, 496, 944, 542), (953, 496, 1013, 542),
                     (1022, 496, 1082, 542), (1091, 496, 1156, 542), (1164, 496, 1230, 542))
            self._busy_widgets += scene.choices(self.rounds_var, [
                (rounds, f"{rounds} STD" if rounds == DEFAULT_ROUNDS else str(rounds), box)
                for rounds, box in zip(ROUND_OPTIONS, boxes)], colors)
            self.join_status = scene.status(790, 1230, 557, message, size=11)
            scene.button((785, 573, 986, 641), self._go_back, PALETTE["pink"])
            self.connect_button = scene.button((1001, 573, 1232, 641), self.connect, PALETTE["yellow"])
        else:
            self._show_multiplayer_setup(mode, message)

    def _lobby_menu(self, page: str) -> LobbyScreen:
        self.current_screen = "lobby" if page == "lobby" else self.mode
        self.preview_mode = self.input_enabled = False
        self.connect_button = self.nickname_entry = self.server_list = None
        self._busy_widgets = []
        self._joining = False
        self._clear()
        scene = LobbyScreen(
            self.container, page=page, role="host" if self.mode == "host" else "client",
            nickname=self.nickname, play_mode=self.play_mode, rounds=self.total_rounds,
            can_animate=lambda: self.dialog is None and not self._lobby_file_dialog
            and not (self.dashboard and self.dashboard.visible) and not self._closed,
        )
        self.lobby_scene = scene
        scene.pack(fill="both", expand=True)
        scene.focus_set()
        return scene

    def _show_multiplayer_setup(self, mode: str, message: str) -> None:
        scene = self._lobby_menu(mode)
        if mode == "host":
            self.rounds_var = tk.IntVar(value=self.total_rounds)
            if self.play_mode == "versus":
                boxes = ((520, 380, 634, 424), (644, 380, 743, 424),
                         (753, 380, 852, 424), (862, 380, 961, 424),
                         (971, 380, 1070, 424), (1080, 380, 1180, 424))
                self._busy_widgets += scene.choices(self.rounds_var, [
                    (rounds, f"{rounds} STD" if rounds == DEFAULT_ROUNDS else str(rounds), box)
                    for rounds, box in zip(ROUND_OPTIONS, boxes)],
                    dict(SINGLE_CHOICE, back="#06132b", unit=1.6))
                scene.status(520, 1180, 442, "Standard: 2 rounds. Extended: 4–12 rounds.",
                             size=13, color=PALETTE["muted"])
            else:
                scene.status(520, 1180, 380, "THE DISSONANT · 80 HP", size=17, color=PALETTE["yellow"])
                scene.status(520, 1180, 416, "Repeat your melody together. Each player has 8 HP.",
                             size=14, color=PALETTE["muted"])
            scene.status(520, 1180, 474, "Your friend can find your room on the same Wi-Fi.",
                         size=14, color=PALETTE["muted"])
            self.join_status = scene.status(520, 1180, 521, message, size=13)
            scene.button((520, 565, 770, 615), "< BACK", self._go_back)
            self.connect_button = scene.button((820, 565, 1180, 615), "START HOSTING >",
                                                self.connect, primary=True)
            scene.status(820, 1180, 632, "Keep this window open while hosting.",
                         size=12, color=PALETTE["muted"])
        else:
            self.server_list = scene.server_list((520, 345, 1180, 425),
                                                 on_select=self._server_selected, on_join=self.connect)
            self.check_button = scene.button((520, 445, 842, 490), "FIND GAMES", self.find_games)
            self.profile_button = scene.button((858, 445, 1180, 490), "LOAD FILE", self.load_connection)
            self._busy_widgets += [self.check_button, self.profile_button]
            self.join_status = scene.status(
                520, 1180, 521, message or "Use the same Wi-Fi, or load a connection file.",
                size=13, color=PALETTE["danger"] if message else PALETTE["muted"])
            scene.button((520, 565, 770, 615), "< BACK", self._go_back)
            self.connect_button = scene.button((820, 565, 1180, 615), "JOIN GAME >",
                                                self.connect, color=PALETTE["pink"], primary=True)
            scene.status(820, 1180, 632, "Join the selected room", size=12, color=PALETTE["muted"])
            self._display_servers()
            if not self.servers and not message:
                self.find_games()
        scene.default_action = self.connect
        scene.refresh()

    def _go_back(self) -> None:
        self._stop_connection()
        self.events = queue.Queue()
        if self.current_screen in ("host", "join"):
            self.show_multiplayer()
        else:
            self.show_menu()

    def _join_busy(self, busy: bool) -> None:
        self._joining = busy
        widgets = self._busy_widgets + [self.connect_button, self.nickname_entry, self.server_list]
        for widget in widgets:
            if widget is not None:
                widget.configure(state="disabled" if busy else "normal")
        if self.current_screen == "join":
            if self.connect_button is not None:
                self.connect_button.configure(text="JOINING..." if busy and self.network else "JOIN GAME >")
            if not busy:
                self._server_selected()

    def _server_selected(self, *_args) -> None:
        if self.current_screen != "join" or self.connect_button is None or self.server_list is None:
            return
        selection = self.server_list.curselection()
        row = self.servers[selection[0]] if selection and selection[0] < len(self.servers) else None
        available = row is not None and int(row.get("players", 0)) < 2
        self.connect_button.configure(state="normal" if available and not self._joining else "disabled")

    def _display_servers(self) -> None:
        if self.server_list is None:
            return
        self.server_list.set_rooms(self.servers)
        self._server_selected()

    def find_games(self, auto_connect=False) -> None:
        self._join_busy(True)
        self.join_status.configure(text="Finding games on this network…", fg=PALETTE["cyan"])
        events = self.events
        def find():
            try:
                events.put({"type": "servers_found", "servers": discover_servers(), "auto_connect": auto_connect})
            except OSError as exc:
                events.put({"type": "join_error", "message": f"Discovery unavailable: {exc}. Load the host's connection file instead."})
        threading.Thread(target=find, name="find-games", daemon=True).start()

    def load_connection(self) -> None:
        self._lobby_file_dialog = True
        try:
            path = filedialog.askopenfilename(parent=self.root, title="Load host connection",
                                              filetypes=[("Connection file", "*.json")])
        finally:
            self._lobby_file_dialog = False
        if path:
            self.connect_from_file(path)

    def connect_from_file(self, path) -> None:
        self._join_busy(True)
        self.join_status.configure(text="Checking the saved host…", fg=PALETTE["cyan"])
        events = self.events
        def check():
            try:
                host, port = resolve_connection_file(load_connection_file(path))
                events.put({"type": "servers_found", "servers": [{"name": "Saved host", "host": host, "port": port}]})
            except Exception as exc:
                events.put({"type": "join_error", "message": str(exc)})
        threading.Thread(target=check, name="load-connection", daemon=True).start()

    def connect(self) -> None:
        if self.connect_button is None or self.connect_button.instate(["disabled"]):
            return
        if self.nickname_entry is not None and not self._read_nickname():
            return
        mode = self.mode
        if mode == "join" and not self.servers:
            self.find_games(auto_connect=True)
            return
        if mode == "join":
            selection = self.server_list.curselection()
            if not selection:
                self.join_status.configure(text="Choose the host game first.", fg=PALETTE["danger"])
                return
            host, port = self.servers[selection[0]]["host"], self.servers[selection[0]]["port"]
        else:
            host, port = "127.0.0.1", self.port
            if mode == "solo":
                self.play_mode = "versus"
            if self.play_mode != "boss":
                self.total_rounds = self.rounds_var.get()
        if mode == "solo":
            self.difficulty = self.difficulty_var.get()
        self._stop_connection()
        self.events = queue.Queue()
        if mode in ("host", "solo"):
            try:
                port = self.local_game.start(solo=mode == "solo", port=port, total_rounds=self.total_rounds,
                                             mode=self.play_mode)
            except OSError as exc:
                self.join_status.configure(text=listen_error(port, exc), fg=PALETTE["danger"])
                return
            if mode == "host":
                self.local_game.server.name = f"{self.nickname}'s room"[:60]
                self.host_addresses = local_ip_addresses()
                self._create_dashboard()
        self._join_busy(True)
        self.join_status.configure(text="Joining the room..." if mode == "join" else "Opening your room...",
                                   fg=PALETTE["cyan"])
        self.network = NetworkClient(self.events, host, port)
        if mode == "join":
            self.connect_button.configure(text="JOINING...")
        self.network.connect_async(self.nickname)

    def _stop_connection(self) -> None:
        self._close_dialog()
        if self.dashboard:
            self.dashboard.dispose()
            self.dashboard = None
        if self.network:
            self.network.close()
        self.network = None
        self.local_game.close()
        self.player_id = None
        self.players = []
        self.manual_lobby = False
        self.host_player_id = None
        self._ready_pending = False

    def show_lobby(self, message: str = "") -> None:
        scene = self._lobby_menu("lobby")
        is_host = self.mode == "host" and self.local_game.server is not None
        scene.drawers.append(lambda screen: screen.frame((520, 440, 1180, 500), "#174170", 1))
        if is_host:
            scene.status(535, 950, 454, "INVITE YOUR FRIEND", size=15, color=PALETTE["cyan"])
            scene.status(535, 950, 480, "Use the same Wi-Fi or a connection file.",
                         size=12, color=PALETTE["muted"])
            scene.button((970, 455, 1165, 489), "SAVE CONNECTION FILE", self.save_lobby_connection)
            # Keep the existing dashboard accessible without making it the main lobby action.
            scene.button((1065, 215, 1180, 240), "DASHBOARD", self.show_server_dashboard)
        else:
            self.lobby_info = scene.status(535, 1165, 469, "", size=14, color=PALETTE["muted"])
        self.lobby_status = scene.status(520, 1180, 534, message, size=14, color=PALETTE["yellow"])
        scene.button((520, 565, 770, 615), "< CLOSE ROOM" if is_host else "< LEAVE ROOM",
                     self.return_to_join)
        self.lobby_hint = scene.status(805, 1180, 632, "", size=12, color=PALETTE["muted"])
        if is_host:
            self.start_lobby_button = scene.button((820, 565, 1180, 615), "START GAME >",
                                                    self.start_lobby_match, primary=True)
            scene.default_action = self.start_lobby_match
        else:
            self.ready_button = scene.button((820, 565, 1180, 615), "I'M READY",
                                              self.toggle_lobby_ready, color=PALETTE["pink"], primary=True)
            scene.default_action = self.toggle_lobby_ready
        self._refresh_player_list()
        if message:
            self.lobby_status.configure(text=message)
        scene.refresh()

    def save_lobby_connection(self) -> None:
        server = self.local_game.server
        if server is None:
            return
        self._lobby_file_dialog = True
        try:
            path = filedialog.asksaveasfilename(
                parent=self.root, title="Save host connection", initialfile="dup-me-connection.json",
                defaultextension=".json", filetypes=[("Connection file", "*.json")])
            if path:
                save_connection_file(path, local_ip_addresses(), server.port, server.name)
                self.lobby_status.configure(text="Saved. Your friend can choose Join a Game > Load File.",
                                             fg=PALETTE["cyan"])
        except (OSError, ValueError) as exc:
            self.lobby_status.configure(text=f"Couldn't save the connection file: {exc}",
                                         fg=PALETTE["danger"])
        finally:
            self._lobby_file_dialog = False

    def toggle_lobby_ready(self) -> None:
        if (self.current_screen != "lobby" or not self.network or not self.manual_lobby
                or self.player_id == self.host_player_id or self._ready_pending):
            return
        own = next((row for row in self.players if row.get("id") == self.player_id), None)
        if own is None:
            return
        if self.network.send({"type": mt.LOBBY_READY, "ready": not own.get("ready", False)}):
            self._ready_pending = True
            self.ready_button.configure(state="disabled")

    def start_lobby_match(self) -> None:
        if (self.current_screen != "lobby" or not self.network or not self.manual_lobby
                or self.player_id != self.host_player_id
                or self.start_lobby_button.instate(["disabled"])):
            return
        if self.network.send({"type": mt.LOBBY_START}):
            self.start_lobby_button.configure(state="disabled", text="STARTING...")
            self.lobby_status.configure(text="Starting the game...", fg=PALETTE["cyan"])

    def _create_dashboard(self) -> None:
        """Start recording the host's server activity; the dashboard stays hidden until opened."""
        if self.dashboard is None and self.local_game.server is not None:
            frame = tk.Frame(self.root, bg=PALETTE["background"])
            self.dashboard = ServerWindow(frame, server=self.local_game.server, on_close=self._dashboard_closed)

    def show_server_dashboard(self) -> None:
        if self.local_game.server is None:
            return
        self._create_dashboard()
        self._pressed.clear()
        self.dashboard.show()

    def _dashboard_closed(self) -> None:
        self._pressed.clear()
        if self.board:
            self.board.focus_set()

    def show_game(self) -> None:
        self.current_screen = "game"
        self._clear()
        actions = {
            "note": self.press_color, "settings": self.show_settings,
            "help": self.show_help, "fullscreen": self.toggle_fullscreen,
            "undo": self.preview_undo, "clear": self.preview_clear, "exit": self.force_exit,
        }
        if self.mode == "host" and self.local_game.server:
            actions["server"] = self.show_server_dashboard
        self.board = GameBoard(self.container, self.state, actions)
        self.board.pack(fill="both", expand=True)
        self._refresh_board()
        self.board.focus_set()

    def show_boss_game(self) -> None:
        self.current_screen = "boss_game"
        self.preview_mode = False
        self._clear()
        actions = {
            "note": self.press_color, "settings": self.show_settings,
            "help": self.show_help, "fullscreen": self.toggle_fullscreen, "exit": self.force_exit,
        }
        if self.mode == "host" and self.local_game.server:
            actions["server"] = self.show_server_dashboard
        # Keys are gated by BossState.can_play, so input stays switched on here.
        self.input_enabled = True
        self.board = BossBoard(self.container, self.boss_state, actions)
        self.board.pack(fill="both", expand=True)
        self._refresh_board()
        self.board.focus_set()

    def _boss_phrase(self, event: dict) -> None:
        self.turn_id = event.get("turn_id", "")
        self._cancel_practice_jobs()
        self.boss_state.begin(event)
        if self.current_screen != "boss_game":
            self.show_boss_game()
        if self.boss_state.phase == "show":
            # The boss plays this player's melody note by note, revealing each one.
            gap = round(float(event.get("note_gap", 0.6)) * 1000)
            for index, note in enumerate(self.boss_state.notes.get(self.boss_state.me, [])):
                self._practice_after(1000 + index * gap, lambda note=note, index=index: self._boss_note(note, index))
        self._refresh_board()

    def _boss_note(self, note: str, index: int) -> None:
        if self.boss_state.phase != "show" or self.board is None:
            return
        self.boss_state.shown = index + 1
        self.audio.play(note)
        self.board.flash(note, force=True)
        self._refresh_board()

    def show_preview(self) -> None:
        self._stop_connection()
        self.events = queue.Queue()
        self.player_id = None
        self.preview_mode = True
        self.state = BoardState(preview=True, total_rounds=self.total_rounds)
        self.state.begin({"round": 1, "phase": "create", "role": "creator", "duration": 0,
                          "scores": [{"nickname": self.nickname or "JOJI", "score": 0},
                                     {"nickname": "DUPBOT", "score": 0}]})
        self.state.instruction = "Try all 17 keys"
        self.input_enabled = True
        self.show_game()

    # ---- Practice: offline, no server; every note is judged like a typed letter ----

    def show_practice_setup(self) -> None:
        scene = self._art_menu("practice", "practice-meteor-rehearsal.gif")
        scene.default_action = self.start_practice
        colors = dict(PRACTICE_CHOICE, back=scene.sample(300, 420))
        columns = ((82, 228), (239, 384), (393, 538))
        self.practice_level_var = tk.StringVar(value=self.practice_level)
        scene.choices(self.practice_level_var, [
            (level, f"{level.upper()} {LEVELS[level][0] - 1}", (x0, 352, x1, 400))
            for level, (x0, x1) in zip(LEVELS, columns)], colors)
        self.practice_length_var = tk.IntVar(value=self.practice_length)
        scene.choices(self.practice_length_var, [
            (count, str(count), (x0, 455, x1, 504)) for count, (x0, x1) in zip(LENGTH_OPTIONS, columns)], colors)
        silent = not self.audio.available or self.audio.muted or self.audio.volume == 0
        self.join_status = scene.status(82, 538, 521, "Sound is off - unmute in SETTINGS (Ctrl+M)."
                                        if silent else "", size=11)
        scene.button((82, 538, 292, 598), self._go_back, PALETTE["cyan"])
        scene.button((300, 538, 538, 598), self.start_practice, PALETTE["yellow"])

    def start_practice(self) -> None:
        if self.current_screen == "practice":
            self.practice_level = self.practice_level_var.get()
            self.practice_length = self.practice_length_var.get()
        self._stop_connection()
        self.events = queue.Queue()
        self.practice = PracticeSession(self.practice_level, self.practice_length)
        self.current_screen = "practice_game"
        self.preview_mode = self.input_enabled = False
        self.state = BoardState(phase="repeat", role="repeater", total_rounds=self.practice_length,
                                instruction="", welcome_name=self.nickname)
        self._clear()
        actions = {"note": self.press_color, "settings": self.show_settings, "help": self.show_help,
                   "fullscreen": self.toggle_fullscreen, "exit": self.end_practice, "replay": self.practice_replay}
        self.board = PracticeBoard(self.container, self.state, actions, self.practice.stats)
        self.board.pack(fill="both", expand=True)
        self.board.focus_set()
        self._practice_tick()
        self._next_practice_melody()

    def _practice_after(self, delay: int, callback) -> None:
        self._practice_jobs.append(self.root.after(delay, callback))

    def _cancel_practice_jobs(self) -> None:
        for job in getattr(self, "_practice_jobs", []):
            self.root.after_cancel(job)
        self._practice_jobs = []

    def _practice_tick(self) -> None:
        """Redraw once a second so the clock and NPM stay live."""
        if self.current_screen == "practice_game" and self.board:
            self._refresh_board()
            self._practice_after(1000, self._practice_tick)

    def _next_practice_melody(self) -> None:
        session = self.practice
        if session is None or self.board is None:
            return
        if session.finished:
            self.show_practice_results()
            return
        melody = session.next_melody()
        s = self.state
        s.round_number, s.pattern_length = len(session.melodies), len(melody)
        # Only the first note is on show: the player finds the rest by interval.
        s.pattern, s.feedback, s.complete, s.status = melody[:1], [], False, ""
        self._play_practice_melody()

    def _play_practice_melody(self) -> None:
        melody = self.practice.current
        self._set_buttons(False)
        self.board.stage = "listen"
        silent = not self.audio.available or self.audio.muted or self.audio.volume == 0
        self.state.instruction = "Sound is off - press Ctrl+M to unmute" if silent else "Listen carefully..."
        self._refresh_board()
        gap = 620
        for index, note in enumerate(melody):
            self._practice_after(350 + index * gap, lambda note=note, first=index == 0: self._practice_sound(note, first))
        # Let the last note ring before the player's first key cuts it off.
        self._practice_after(350 + (len(melody) - 1) * gap + 450, self._practice_listen_done)

    def _practice_sound(self, note: str, first: bool) -> None:
        self.audio.play(note)
        if first and self.board:
            # Light the given first note on the keyboard; the rest stay dark.
            self.board.flash(note, force=True)

    def _practice_listen_done(self) -> None:
        if self.board is None or self.practice is None:
            return
        self.board.stage = "answer"
        self._set_buttons(True)
        self.state.instruction = f"Start from {self.practice.current[0].upper()} - find the next {len(self.practice.current) - 1} notes. SPACE replays"
        self.practice.start_answer()
        self._refresh_board()

    def practice_replay(self) -> None:
        if (self.practice is None or self.board is None or self.dialog is not None
                or self.board.stage != "answer"):
            return
        self.practice.replays += 1
        self._play_practice_melody()

    def _practice_note(self, color: str) -> None:
        session, s = self.practice, self.state
        correct = session.answer(color)
        self.audio.play(color)
        if self.board:
            self.board.flash(color)
        s.feedback.append(correct)
        if session.melody_done:
            self._set_buttons(False)
            self.board.stage = "reveal"
            s.complete = True
            s.pattern = session.current
            hits = sum(s.feedback)
            s.status = f"{hits} / {len(s.feedback)} CORRECT"
            s.instruction = "This was the melody"
            self._practice_after(1200 if hits == len(s.feedback) else 2200, self._next_practice_melody)
        self._refresh_board()

    def end_practice(self) -> None:
        """EXIT / Esc: show the stats so far, or go straight back if nothing was played."""
        if self.practice is not None and self.practice.stats()["notes"]:
            self.practice.stop()
            self.show_practice_results()
        else:
            self.practice = None
            self.show_menu()

    def show_practice_results(self) -> None:
        session = self.practice
        stats = session.stats()
        self.current_screen = "practice_results"
        self.input_enabled = False
        panel = self._scene("PRACTICE RESULTS")
        panel.place_configure(rely=.6)
        self._set_width(panel, 620)
        panel.configure(padx=24, pady=14)
        card = PixelCanvas(panel, bg=PALETTE["panel"], height=self._px(96))
        card.pack(fill="x")
        big = ((f"{stats['accuracy']}%", "ACC", PALETTE["green"]),
               (f"{stats['precision']}%", "PRECISION", PALETTE["cyan"]),
               (str(stats["npm"]), "NOTES / MIN", PALETTE["yellow"]))

        def draw(_event=None):
            card.configure(height=self._px(96))
            card.delete("all")
            card.scale, card.ox, card.oy = self.ui_scale, 0, 0
            width = card.winfo_width() / self.ui_scale
            for index, (value, name, color) in enumerate(big):
                x = width * (2 * index + 1) / 6
                card.label(x, 6, name, 2, PALETTE["muted"])
                card.pixels(x, 34, value, 7, color, center=True)

        card.bind("<Configure>", draw)
        self._rescale_hooks.append(draw)
        minutes, seconds = divmod(int(stats["seconds"]), 60)
        weakest = "  ".join(f"{note.upper()} ({KEY_LABELS.get(note, '?')})" for note in stats["weakest"]) or "none"
        rows = (("LEVEL", f"{session.level.upper()} · first note + {LEVELS[session.level][0] - 1}"),
                ("PERFECT MELODIES", f"{stats['perfect']} / {stats['melodies']}"),
                ("CORRECT NOTES", f"{stats['correct']} / {stats['notes']}"),
                ("BEST COMBO", str(stats["best_combo"])),
                ("AVERAGE MISS", f"{stats['avg_miss']:.1f} semitones off" if stats["notes"] > stats["correct"] else "-"),
                ("REPLAYS", str(stats["replays"])),
                ("ANSWER TIME", f"{minutes}:{seconds:02}"),
                ("MISSED MOST", weakest))
        grid = tk.Frame(panel, bg=PALETTE["panel"])
        grid.pack(fill="x", pady=(10, 4))
        grid.columnconfigure(1, weight=1)
        for row, (name, value) in enumerate(rows):
            self._label(grid, name, 11, PALETTE["cyan"], anchor="w").grid(row=row, column=0, sticky="w")
            self._label(grid, value, 11, PALETTE["text"], anchor="e").grid(row=row, column=1, sticky="e")
        ttk.Button(panel, text="TRY AGAIN  >", command=self.start_practice,
                   style="Go.Arcade.TButton").pack(fill="x", pady=(10, 8))
        actions = tk.Frame(panel, bg=PALETTE["panel"])
        actions.pack(fill="x")
        self._button(actions, "CHANGE LEVEL", self.show_practice_setup).pack(side="left", fill="x", expand=True)
        self._button(actions, "MAIN MENU", self.show_menu).pack(side="left", fill="x", expand=True, padx=(8, 0))

    def force_exit(self) -> None:
        """Leave immediately: offline practice returns to the menu; a live match is forfeited (LOST)."""
        if self.preview_mode:
            self.show_menu()
        elif self.network and self.network.send({"type": mt.FORFEIT}):
            self._set_buttons(False)
            self._set_status("Leaving the match…")
        else:
            self.return_to_join()

    def preview_undo(self) -> None:
        if self.preview_mode and self.state.pattern:
            self.state.pattern.pop()
            self.state.status = ""
            self._refresh_board()

    def preview_clear(self) -> None:
        if self.preview_mode:
            self.state.pattern.clear()
            self.state.status = ""
            self._refresh_board()

    def show_results(self, event: dict) -> None:
        self.current_screen = "results"
        self.input_enabled = False
        panel = self._scene("MATCH COMPLETE")
        panel.place_configure(rely=.6)
        result = event.get("result", "draw")
        boss = event.get("mode") == "boss"
        title = {"win": "YOU WIN", "loss": "YOU LOST", "draw": "DRAW"}.get(result, "MATCH OVER")
        if boss:
            title = "VICTORY" if result == "win" else "DEFEAT"
        color = {"win": PALETTE["green"], "loss": PALETTE["pink"], "draw": PALETTE["cyan"]}.get(result, PALETTE["text"])
        reason = event.get("reason", "")
        self.scores = event.get("scores", self.scores)
        self.result_texts = [title, reason]
        winner = event.get("winner_id")
        height = 214 if reason else 190
        card = PixelCanvas(panel, bg=PALETTE["panel"], height=self._px(height))
        card.pack(fill="x")

        def draw(_event=None):
            # Pixel-font result card: title, reason, then one row per player (winner lit green).
            card.configure(height=self._px(height))
            card.delete("all")
            card.scale, card.ox, card.oy = self.ui_scale, 0, 0
            width = card.winfo_width() / self.ui_scale
            card.pixels(width / 2, 4, title, 7, color, center=True)
            top = 70
            if reason:
                card.label(width / 2, 66, reason, 2, PALETTE["yellow"])
                top = 94
            for index, row in enumerate(self.scores[:2]):
                y = top + index * 60
                won = (winner is not None and row.get("id") == winner) or (boss and result == "win")
                accent = PALETTE["green"] if won else "#2b4677"
                card.panel(4, y, width - 14, 54, accent, PALETTE["panel_light"] if won else None)
                name = str(row.get("nickname", "PLAYER"))
                name = name if len(name) <= 12 else name[:11] + "."
                card.label(24, y + 17, name, 3, PALETTE["text"] if won or winner is None else PALETTE["muted"],
                           center=False)
                if row.get("id") == self.player_id:
                    card.label(24 + len(name) * 18 + 10, y + 20, "YOU", 2, PALETTE["cyan"], center=False)
                if boss:
                    card.label(width - 130, y + 20, "DMG", 2, PALETTE["muted"])
                card.pixels(width - 52, y + 13, str(row.get("score", 0)), 4, PALETTE["yellow"], center=True)

        card.bind("<Configure>", draw)
        self._rescale_hooks.append(draw)
        self.rematch_button = ttk.Button(panel, text="REMATCH  >", command=self.request_rematch,
                                         style="Go.Arcade.TButton")
        self.rematch_button.pack(fill="x", pady=(14, 0))
        self.result_status = self._label(panel, "", 11, PALETTE["cyan"], wraplength=435)
        self.result_status.pack(pady=6)
        actions = tk.Frame(panel, bg=PALETTE["panel"])
        actions.pack(fill="x")
        if not boss:
            self._button(actions, "ROUND REVIEW", self.show_match_review).pack(side="left", fill="x", expand=True)
        self._button(actions, "LEAVE MATCH", self.return_to_join).pack(side="left", fill="x", expand=True,
                                                                       padx=(0 if boss else 8, 0))

    def show_match_review(self) -> None:
        if self.current_screen != "results":
            return
        panel = self._new_dialog("MATCH REVIEW", width=600)
        if panel is None:
            return
        frame = tk.Frame(panel, bg=PALETTE["background"])
        frame.pack(fill="both", expand=True)
        review = tk.Text(frame, width=44, height=17, wrap="none", font=self._font(12),
                         bg=PALETTE["background"], fg=PALETTE["text"], bd=0, highlightthickness=0,
                         padx=14, pady=10, cursor="arrow")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=review.yview)
        review.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        review.pack(side="left", fill="both", expand=True)
        for tag, color, size, bold in (("round", PALETTE["yellow"], 15, True), ("who", PALETTE["muted"], 11, False),
                                       ("head", PALETTE["cyan"], 11, True), ("OK", PALETTE["green"], 12, True),
                                       ("WRONG", PALETTE["pink"], 12, True), ("MISSED", PALETTE["muted"], 12, True),
                                       ("score", PALETTE["text"], 13, True)):
            review.tag_configure(tag, foreground=color, font=self._font(size, bold))
        rounds = review_rounds(self.round_history, self.scores)
        if not rounds:
            review.insert("end", "No rounds were finished in this match.\n", "who")
        for entry in rounds:
            review.insert("end", f"ROUND {entry['round']}\n", "round")
            review.insert("end", f"{entry['creator']} created  ·  {entry['repeater']} repeated\n", "who")
            review.insert("end", f"{entry['correct']} / {entry['total']} correct   {entry['accuracy']}\n\n", "score")
            if not entry["steps"]:
                review.insert("end", "  Empty pattern - nothing to repeat.\n\n", "who")
                continue
            review.insert("end", "  #   PATTERN    ANSWER\n", "head")
            for step, note, answer, verdict in entry["steps"]:
                played = f"{KEY_LABELS.get(answer, '?')} {answer.upper():<4}" if answer else "-     "
                review.insert("end", f"  {step:<3} {KEY_LABELS.get(note, '?')} {note.upper():<4}   {played}   ")
                review.insert("end", f"{verdict}\n", verdict)
            review.insert("end", "\n")
        review.configure(state="disabled")
        self._button(panel, "SAVE CSV REPORT", self.save_match_report).pack(fill="x", pady=(12, 6))
        self._button(panel, "DONE", self._close_dialog).pack(fill="x")

    def save_match_report(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.dialog or self.root, title="Save match report", initialfile="dup-me-match.csv", defaultextension=".csv", filetypes=[("CSV report", "*.csv")])
        if path:
            try:
                export_csv(path, self.round_history, self.scores)
                self.result_status.configure(text="Match report saved.")
            except OSError as exc:
                self.result_status.configure(text=f"Could not save: {exc}", fg=PALETTE["danger"])

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == mt.WELCOME:
            self.player_id = event["player_id"]
            self.nickname = event["nickname"]
            self.state.welcome_name = self.nickname
            self.total_rounds = int(event.get("total_rounds", DEFAULT_ROUNDS))
            self.play_mode = "versus" if self.mode == "solo" else event.get("mode", "versus")
            self.manual_lobby = bool(event.get("manual_lobby", False))
            self.host_player_id = event.get("host_player_id")
            self._ready_pending = False
            self.boss_state = BossState(me=self.player_id)
            self.show_lobby()
            if self.mode == "solo":
                self.local_game.start_bot(self.nickname, self.difficulty)
        elif event_type == mt.PLAYER_LIST:
            self.players = event.get("players", [])
            self.manual_lobby = bool(event.get("manual_lobby", self.manual_lobby))
            self.host_player_id = event.get("host_player_id", self.host_player_id)
            self._ready_pending = False
            self._refresh_player_list()
        elif event_type == mt.MATCH_START:
            self._close_dialog()
            self.round_history = []
            self.scores = event.get("players", [])
            if event.get("mode") == "boss":
                self.play_mode = "boss"
                self.boss_state = BossState(me=self.player_id or "")
                self.boss_state.start(event)
                self.show_boss_game()
        elif event_type == mt.BOSS_PHRASE:
            self._boss_phrase(event)
        elif event_type == mt.BOSS_FEEDBACK and isinstance(self.board, BossBoard):
            self.boss_state.feedback(event)
            self.scores = self.boss_state.players
            self._refresh_board()
        elif event_type == mt.BOSS_RESULT and isinstance(self.board, BossBoard):
            self._cancel_practice_jobs()
            self.boss_state.result(event)
            self.scores = self.boss_state.players
            self._refresh_board()
        elif event_type == mt.TIMER_UPDATE and isinstance(self.board, BossBoard):
            self.boss_state.remaining = max(0, int(event.get("remaining", 0)))
            self._refresh_board()
        elif event_type == mt.ROUND_START:
            self.preview_mode = False
            self.turn_id = event.get("turn_id", "")
            self.state.begin(event)
            self.state.preview = False
            self.round_number, self.role, self.phase = self.state.round_number, self.state.role, self.state.phase
            self.scores = self.state.scores
            self.input_enabled = self.state.enabled
            self._sent_steps = 0
            self.show_game()
            (notice, when), self._notice = self._notice, ("", 0.0)
            if notice and self.round_number == 1 and time.monotonic() - when < 3:
                self._set_status(notice)
        elif event_type == mt.PATTERN_UPDATE and self.board:
            color = str(event.get("color", ""))
            if self.state.add_note(color):
                self.audio.play(color)
                self.board.flash(color, force=self.state.role == "repeater")
                if len(self.state.pattern) >= MAX_PATTERN_STEPS:
                    self._set_buttons(False)
            self._refresh_board()
        elif event_type == mt.TIMER_UPDATE and self.board:
            self.state.remaining = max(0, int(event.get("remaining", 0)))
            if self.state.remaining == 0:
                self._set_buttons(False)
            self._refresh_board()
        elif event_type == mt.REPEAT_FEEDBACK and self.board:
            self.scores = event.get("scores", self.scores)
            self.state.scores = self.scores
            self.state.feedback.append(bool(event.get("correct")))
            answered, total = event.get("answered", 0), event.get("total", 0)
            self.state.status = f"{'CORRECT!' if event.get('correct') else 'MISS'}  {answered}/{total}"
            color = str(event.get("color", ""))
            if self.state.role == "creator" and color in dict(COLORS):
                # Let the creator watch the opponent's answers on the keyboard too.
                self.audio.play(color)
                self.board.flash(color, force=True)
            if answered >= total:
                self._set_buttons(False)
            self._refresh_board()
        elif event_type == mt.ROUND_RESULT and self.board:
            self.round_history.append(event)
            self._set_buttons(False)
            self.scores = event.get("scores", self.scores)
            self.state.scores = self.scores
            self.state.pattern = event.get("pattern", [])
            self.state.complete = True
            self.state.remaining = 0
            self.state.instruction = "Pattern revealed - next round soon"
            if self.state.round_number >= self.state.total_rounds:
                self.state.instruction = "Pattern revealed - final scores soon"
            self.state.status = f"{event.get('points', 0)} / {len(self.state.pattern)} correct"
            self._refresh_board()
        elif event_type == mt.MATCH_RESULT:
            self.show_results(event)
        elif event_type == "rematch_status" and self.current_screen == "results":
            self.result_status.configure(text=f"Rematch votes: {event.get('votes', 0)}/{event.get('needed', 2)}")
        elif event_type == mt.GAME_RESET:
            self._notice = (event.get("reason", ""), time.monotonic())
            self._close_dialog()
            self.round_history = []
            self.scores = []
            self.show_lobby(event.get("reason", "Game reset."))
        elif event_type == mt.PLAYER_LEFT:
            self._set_status(f"{event.get('nickname', 'A player')} disconnected.")
        elif event_type == mt.ERROR:
            if self.current_screen == "lobby":
                self._ready_pending = False
                self._refresh_player_list()
            self._set_status(event.get("message", "Server rejected that action."), error=True)
            if self.current_screen in SETUP_SCREENS:
                self._join_busy(False)
        elif event_type == "servers_found" and self.current_screen == "join":
            # List only games of the chosen mode. Connection files carry no mode;
            # the host's mode is applied on WELCOME.
            found = event["servers"]
            self.servers = [row for row in found if row.get("mode", self.play_mode) == self.play_mode]
            self._join_busy(False)
            self._display_servers()
            other = MODE_LABELS["boss" if self.play_mode == "versus" else "versus"]
            message = ("Select a room, then choose JOIN GAME." if self.servers else
                       f"Only a {other} game was found. Go BACK and pick {other} to join it." if found else
                       "No rooms found yet. Ask your friend to start hosting, then find games again.")
            self.join_status.configure(text=message, fg=PALETTE["cyan"])
            if len(self.servers) == 1 and event.get("auto_connect"):
                self.connect()
        elif event_type == "join_error" and self.current_screen == "join":
            self._join_busy(False)
            self.join_status.configure(text=event["message"], fg=PALETTE["danger"])
        elif event_type == "network_error":
            self._stop_connection()
            self.events = queue.Queue()
            self.show_setup(self.mode, event.get("message", "Connection lost."))

    def _refresh_board(self) -> None:
        if self.board:
            self.board.volume = self.audio.volume
            self.board.instrument = self.audio.instrument
            self.board.muted = self.audio.muted or self.audio.volume == 0 or not self.audio.available
            self.board.flashes = self.flashes
            self.board.redraw()

    def _set_status(self, message: str, error: bool = False) -> None:
        color = PALETTE["danger"] if error else PALETTE["cyan"]
        if self.board:
            (self.boss_state if isinstance(self.board, BossBoard) else self.state).status = message
            self._refresh_board()
        else:
            widget = "join_status" if self.current_screen in SETUP_SCREENS else {
                "lobby": "lobby_status", "results": "result_status"}.get(self.current_screen)
            if widget and hasattr(self, widget):
                getattr(self, widget).configure(text=message, fg=color)

    def _refresh_player_list(self) -> None:
        if self.current_screen != "lobby" or self.lobby_scene is None:
            return
        scene = self.lobby_scene
        scene.set_players(self.players, self.player_id, self.host_player_id,
                          {row.get("id"): bool(row.get("ready")) for row in self.players})
        scene.set_details(rounds=self.total_rounds, play_mode=self.play_mode)
        is_host = self.mode == "host" and self.local_game.server is not None
        guest = next((row for row in self.players if row.get("id") != self.host_player_id), None)
        if not self.manual_lobby:
            status = "Starting solo play..." if self.mode == "solo" else "Waiting for another player to join..."
            if not is_host:
                self.ready_button.configure(text="AUTO START", state="disabled")
                self.lobby_info.configure(text="This room starts automatically when both players join.")
            else:
                self.start_lobby_button.configure(state="disabled")
            hint = "The match starts automatically"
        elif is_host:
            can_start = len(self.players) == 2 and guest is not None and guest.get("ready", False)
            self.start_lobby_button.configure(state="normal" if can_start else "disabled", text="START GAME >")
            status = ("Everyone is ready. Start the game!" if can_start else
                      "Waiting for your friend to get ready..." if guest else
                      "Waiting for your friend to join...")
            hint = "Everyone is ready" if can_start else "Available when your friend is ready"
        else:
            own = next((row for row in self.players if row.get("id") == self.player_id), None)
            ready = bool(own and own.get("ready"))
            self.ready_button.configure(text="✓ READY" if ready else "I'M READY",
                                        state="normal" if own and not self._ready_pending else "disabled")
            self.lobby_info.configure(text=("You're ready. The host will start the game." if ready else
                                           "Mark yourself ready when you're ready to play."))
            status = "Waiting for the host to start..." if ready else "Waiting for you to get ready..."
            hint = "Click to cancel ready" if ready else "The host starts when everyone is ready"
        self.lobby_status.configure(text=status, fg=PALETTE["yellow"])
        self.lobby_hint.configure(text=hint)
        scene.refresh()

    def _set_buttons(self, enabled: bool) -> None:
        self.input_enabled = self.state.enabled = enabled

    def press_color(self, color: str) -> None:
        if not self.input_enabled or color not in dict(COLORS) or getattr(self, "dialog", None) is not None:
            return
        if getattr(self, "practice", None) is not None and self.current_screen == "practice_game":
            self._practice_note(color)
            return
        if self.preview_mode:
            if self.state.add_note(color):
                self.audio.play(color)
                if self.board:
                    self.board.flash(color)
                self._refresh_board()
            else:
                self._set_status("20 notes - use UNDO or CLEAR")
            return
        if getattr(self, "current_screen", "") == "boss_game":
            self._boss_press(color)
            return
        if self.network is None:
            return
        limit = MAX_PATTERN_STEPS if self.phase == "create" else self.state.pattern_length
        if self._sent_steps >= limit:
            return
        message_type = mt.PATTERN_STEP if self.phase == "create" else mt.REPEAT_STEP
        if self.network.send({"type": message_type, "color": color, "turn_id": self.turn_id}):
            self._sent_steps += 1
            if self.phase == "repeat":
                self.audio.play(color)
                if self.board:
                    self.board.flash(color)

    def _boss_press(self, color: str) -> None:
        boss = self.boss_state
        if self.network is None or not boss.can_play:
            return
        if self.network.send({"type": mt.REPEAT_STEP, "color": color, "turn_id": self.turn_id}):
            boss.sent += 1
            self.audio.play(color)
            if self.board:
                self.board.flash(color)
            self._refresh_board()

    def _key_press(self, event: tk.Event) -> None:
        if event.widget.winfo_toplevel() != self.root or self.dialog is not None:
            return
        dashboard = getattr(self, "dashboard", None)
        if dashboard is not None and dashboard.visible:
            return
        if int(event.state) & 0x0C:
            return
        key = str(event.keysym).lower()
        key = KEYSYM_TO_KEY.get(key, key)
        if key in self._release_jobs:
            self.root.after_cancel(self._release_jobs.pop(key))
        if key in self._pressed:
            return
        self._pressed.add(key)
        if key == "space" and getattr(self, "current_screen", "") == "practice_game":
            self.practice_replay()
            return
        color = KEY_TO_COLOR.get(key)
        if color:
            self.press_color(color)

    def _key_release(self, event: tk.Event) -> None:
        key = str(event.keysym).lower()
        key = KEYSYM_TO_KEY.get(key, key)
        if key in self._release_jobs:
            self.root.after_cancel(self._release_jobs[key])

        def release():
            self._pressed.discard(key)
            self._release_jobs.pop(key, None)

        self._release_jobs[key] = self.root.after_idle(release)

    def toggle_mute(self) -> None:
        # Piano and music now have independent levels; master mute preserves both.
        self.audio.muted = not self.audio.muted
        self.music.set_muted(self.audio.muted)
        self._refresh_board()

    def set_volume(self, value: int) -> None:
        self.audio.volume = value
        if value > 0:
            self.audio.muted = False
        self.music.set_muted(self.audio.muted)

    def set_music_volume(self, value: int) -> None:
        self.music.set_volume(value)

    def toggle_fullscreen(self, _event=None) -> str:
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))
        return "break"

    def _escape(self, _event=None) -> str:
        if self.dialog:
            self._close_dialog()
        elif self.dashboard is not None and self.dashboard.visible:
            self.dashboard.close()
        elif self.root.attributes("-fullscreen"):
            self.root.attributes("-fullscreen", False)
        elif self.current_screen == "practice_game":
            self.end_practice()
        elif self.preview_mode or self.current_screen == "practice_results":
            self.show_menu()
        elif self.current_screen in SETUP_SCREENS + ("multiplayer", "practice"):
            self._go_back()
        elif self.current_screen == "lobby":
            self.return_to_join()
        return "break"

    def _new_dialog(self, title: str, width: int = 560) -> tk.Frame | None:
        """Open a panel inside the game window (no separate pop-up window). Esc closes it."""
        if self.dialog:
            self.dialog.lift()
            return None
        self._pressed.clear()
        self.dialog = tk.Frame(self.root, bg=PALETTE["blue"], padx=3, pady=3)
        panel = tk.Frame(self.dialog, bg=PALETTE["panel"], padx=28, pady=22)
        panel.pack(fill="both", expand=True)
        self.dialog.place(relx=.5, rely=.5, anchor="center")
        self._set_width(self.dialog, width)
        self.dialog.lift()
        self._label(panel, title, 22, PALETTE["cyan"]).pack(anchor="w", pady=(0, 16))
        if self.current_screen in ("game", "boss_game") and not self.preview_mode:
            self._label(panel, "LIVE MATCH · The round timer keeps running.", 11,
                        PALETTE["yellow"], wraplength=455).pack(anchor="w", pady=(0, 12))
        self._grab_dialog()
        return panel

    def _grab_dialog(self) -> None:
        """Only the open panel takes mouse clicks; buttons behind it are blocked until it closes."""
        if self.dialog is None:
            return
        try:
            self.dialog.update_idletasks()
            self.dialog.grab_set()
            self.dialog.focus_set()
        except tk.TclError:  # not drawn yet: try again in a moment
            self.root.after(30, self._grab_dialog)

    def _close_dialog(self) -> None:
        if self.dialog:
            self.dialog.grab_release()
            self.dialog.destroy()
            self.dialog = None
        self._pressed.clear()
        if self.board:
            self.board.focus_set()

    def _select_instrument(self, name: str) -> None:
        self.audio.instrument = name
        self._refresh_board()

    def show_settings(self) -> None:
        """Full-window settings page: the approved artwork with its controls made live."""
        if self.dialog:
            self.dialog.lift()
            return
        self._pressed.clear()
        scene = ArtScreen(self.root, "settings-orbital-mixer.gif")
        scene.place(x=0, y=0, relwidth=1, relheight=1)
        self.dialog = scene
        scene.default_action = self._close_dialog

        def draw_speakers(screen: ArtScreen) -> None:
            # A pink slash across a painted speaker shows it is silent.
            for (x0, y0, x1, y1), silent in (((338, 252, 400, 282), self.audio.muted),
                                             ((338, 327, 400, 357), self.audio.muted or self.music.volume == 0)):
                if silent:
                    for step in range(10):
                        screen.rect(x0 + step * (x1 - x0 - 6) / 9, y0 + step * (y1 - y0 - 6) / 9, 6, 6,
                                    PALETTE["pink"])

        def toggle_piano() -> None:
            self.toggle_mute()
            scene.refresh()

        def toggle_music() -> None:
            if self.music.volume:
                self._music_restore = self.music.volume
                self.music_slider.set(0)
            else:
                self.music_slider.set(getattr(self, "_music_restore", 0) or 18)

        def volume(value: int) -> None:
            # Initializing the slider must not undo an existing master mute.
            if value != self.audio.volume:
                self.set_volume(value)

        scene.drawers.append(draw_speakers)
        scene.button((329, 245, 410, 289), toggle_piano, PALETTE["cyan"])
        self.volume_slider = scene.slider((422, 246, 954, 287), (440, 258, 934, 276), PALETTE["cyan"],
                                          self.audio.volume, volume, on_release=lambda: self.audio.play("c4"),
                                          clear=(427, 251, 949, 283))
        scene.button((329, 320, 410, 364), toggle_music, PALETTE["pink"])
        self.music_slider = scene.slider((422, 321, 954, 360), (440, 333, 934, 351), "#ff4fd8",
                                         self.music.volume, self.set_music_volume, step=1,
                                         clear=(427, 326, 949, 353))
        if not self.music.available or not self.audio.available:
            scene.patch((420, 362, 720, 379), scene.sample(700, 371))
            scene.status(420, 940, 370, "Audio output unavailable; visual feedback still works."
                         if not self.audio.available else "Background music unavailable; piano still works.",
                         size=10, color=PALETTE["yellow"])
        # Our tick follows the chosen instrument, so the painted one is covered.
        scene.patch((336, 412, 366, 443), scene.sample(370, 428))
        self.instrument_var = tk.StringVar(value=self.audio.instrument)
        boxes = ((325, 401, 636, 453), (644, 401, 954, 453), (325, 464, 636, 518), (644, 464, 954, 518))
        self.instrument_buttons = scene.choices(
            self.instrument_var, [(name, name.upper(), box) for name, box in zip(INSTRUMENTS, boxes)],
            {"on": PALETTE["cyan"]}, command=lambda: self._select_instrument(self.instrument_var.get()),
            style="marker")
        flashes = tk.BooleanVar(value=self.flashes)

        def apply_options() -> None:
            self.flashes = flashes.get()
            self._refresh_board()

        scene.toggle((331, 531, 356, 556), flashes, apply_options)
        scene.button((353, 585, 926, 641), self._close_dialog, PALETTE["cyan"])
        self._grab_dialog()

    def show_help(self) -> None:
        panel = self._new_dialog("HOW TO PLAY")
        if panel is None:
            return
        if self.current_screen == "practice_game":
            lines = (
                "01  LISTEN\nA short melody plays. Only its first note is shown\n"
                "and lit on the keyboard: find the rest by interval.\n\n"
                "02  PLAY IT BACK\nPress the notes after the first one, in order.\n"
                "Each note is judged at once. The first note is not scored.\n"
                "SPACE (or REPLAY) plays the melody again.\n\n"
                "ACC    notes that were exactly right\n"
                "PREC   how close your notes were in pitch\n"
                "       (one semitone off still scores 92%)\n"
                "NPM    correct notes per minute\n"
                "COMBO  correct notes in a row\n\n"
                "WHITE: Z X C V B N M , . /\nBLACK: S D G H J L ;"
            )
            self._label(panel, lines, 11, PALETTE["text"], justify="left", anchor="w").pack(anchor="w")
            self._button(panel, "GOT IT", self._close_dialog).pack(fill="x", pady=(16, 0))
            return
        if self.current_screen == "boss_game":
            lines = (
                "01  LISTEN\nTHE DISSONANT plays each of you your own melody.\n"
                "Watch your notes light up and memorize them.\n\n"
                "02  REPEAT\nThe notes hide. Play your melody back in order.\n"
                "Correct key = 1 damage to the boss.\n"
                "Wrong key = 1 damage to you. Unplayed notes count as wrong.\n\n"
                "03  WIN TOGETHER\nBoss 80 HP · each player 8 HP. Melodies grow\n"
                "from 4 to 8 notes. A player on 0 HP sits out;\n"
                "the team loses if both are knocked out.\n\n"
                "WHITE: Z X C V B N M , . /\nBLACK: S D G H J L ;"
            )
            self._label(panel, lines, 11, PALETTE["text"], justify="left", anchor="w").pack(anchor="w")
            self._button(panel, "GOT IT", self._close_dialog).pack(fill="x", pady=(16, 0))
            return
        lines = (
            f"01  CREATE\nBuild up to {MAX_PATTERN_STEPS} notes in {CREATE_SECONDS} seconds.\nYour opponent watches and memorizes.\n\n"
            f"02  REPEAT\nThe pattern hides. Repeat it in {REPEAT_SECONDS} seconds.\nEach correct position earns one point.\n\n"
            "03  SWITCH\nSwap roles every round. Most points wins.\nStandard: 2 rounds. Extended: 4, 6, 8, 10 or 12.\n\n"
            "WHITE: Z X C V B N M , . /\nBLACK: S D G H J L ;\n17 notes from C4 to E5. Sound: gear button > Instrument.\n\n"
            "Click the keys or press their letters.\nLive notes are final; the server runs the timer."
        )
        self._label(panel, lines, 11, PALETTE["text"], justify="left", anchor="w").pack(anchor="w")
        if self.preview_mode:
            self._button(panel, "BACK TO MENU", self._leave_preview).pack(fill="x", pady=(16, 0))
        else:
            self._button(panel, "GOT IT", self._close_dialog).pack(fill="x", pady=(16, 0))

    def _leave_preview(self) -> None:
        self._close_dialog()
        self.show_menu()

    def request_rematch(self) -> None:
        if self.network and self.network.send({"type": mt.REMATCH_VOTE}):
            self.rematch_button.configure(state="disabled")
            self.result_status.configure(text="Waiting for the other player…")

    def return_to_join(self) -> None:
        self._stop_connection()
        self.events = queue.Queue()
        self.show_setup(self.mode, "Disconnected. You can reconnect when ready.")

    def _poll_events(self) -> None:
        if self._closed:
            return
        self.music.set_muted(self.audio.muted)
        for _ in range(100):
            try:
                self._handle_event(self.events.get_nowait())
            except queue.Empty:
                break
        self._poll_job = self.root.after(40, self._poll_events)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_connection()
        if self._poll_job:
            self.root.after_cancel(self._poll_job)
        for job in self._release_jobs.values():
            self.root.after_cancel(job)
        self.music.close()
        self.audio.close()
        self.root.destroy()


def run_client_app(preview: bool = False, **options) -> None:
    root = tk.Tk()
    ClientWindow(root, preview=preview, **options)
    root.mainloop()


if __name__ == "__main__":
    run_client_app()

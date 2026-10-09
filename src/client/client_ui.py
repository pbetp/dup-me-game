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
from src.common.discovery import discover_servers, load_connection_file, resolve_connection_file
from src.server.server_ui import ServerWindow
from src.common.networking import listen_error, local_ip_addresses
from .practice import LENGTH_OPTIONS, LEVELS, PracticeSession
from .local_game import LocalGame
from .match_report import review_rounds, export_csv
from .network_client import NetworkClient
from .pixel_ui import KEY_LABELS, BoardState, GameBoard, PALETTE, PixelCanvas, PracticeBoard
from .sound import NotePlayer

SETUP_SCREENS = ("solo", "host", "join")


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
        self.servers = ([{"name": "Configured server", "host": host, "port": port}] if host else [])
        self.dashboard: ServerWindow | None = None
        self.local_game = LocalGame()
        self.host_addresses: list[str] = []
        self.turn_id = ""
        self.difficulty = "medium"
        self.total_rounds = total_rounds
        self.players: list[dict] = []
        self.scores: list[dict] = []
        self.round_history: list[dict] = []
        self.role = self.phase = self.current_screen = ""
        self.round_number = 0
        self.input_enabled = self.preview_mode = False
        self.board: GameBoard | None = None
        self.state = BoardState()
        self.audio = NotePlayer()
        self.audio.instrument = instrument
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

    def _choice_row(self, panel: tk.Frame, title: str, options, variable: tk.Variable) -> None:
        self._label(panel, title, 11, PALETTE["cyan"]).pack(anchor="w", pady=(10, 4))
        row = tk.Frame(panel, bg=PALETTE["panel"])
        row.pack(fill="x")
        for index, (value, text) in enumerate(options):
            button = tk.Radiobutton(
                row, text=text, value=value, variable=variable, indicatoron=False,
                font=self._font(12, True), pady=7, bd=0, highlightthickness=0, cursor="hand2",
                bg="#133369", fg=PALETTE["text"], selectcolor=PALETTE["blue"],
                activebackground="#214986", activeforeground=PALETTE["text"], disabledforeground="#647995")
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
        panel = self._menu("menu", "THE PATTERN MEMORY ARCADE", "MAIN MENU")
        for text, command in (("SINGLE PLAYER", lambda: self.show_setup("solo")),
                              ("MULTIPLAYER", self.show_multiplayer),
                              ("PRACTICE", self.show_practice_setup),
                              ("SETTINGS", self.show_settings),
                              ("QUIT", self.close)):
            self._button(panel, text, command).pack(fill="x", pady=(0, 8))
        self.join_status = self._label(panel, message, 10, PALETTE["danger"], wraplength=440)
        self.join_status.pack(fill="x")

    def show_multiplayer(self, message: str = "") -> None:
        panel = self._menu("multiplayer", "MULTIPLAYER", "PLAY WITH A FRIEND")
        self._nickname_field(panel)
        self._label(panel, "Both computers must be on the same Wi-Fi or phone hotspot.",
                    11, PALETTE["muted"], wraplength=440).pack(pady=(12, 8))
        for text, mode in (("HOST A GAME", "host"), ("JOIN A GAME", "join")):
            self._button(panel, text, lambda mode=mode: self._multiplayer_next(mode)).pack(fill="x", pady=(0, 8))
        self._footer(panel, message)

    def _multiplayer_next(self, mode: str) -> None:
        if self._read_nickname():
            self.show_setup(mode)

    def show_setup(self, mode: str, message: str = "") -> None:
        """Last step before playing: solo (vs AI), host, or join."""
        self.mode = mode
        if mode == "solo":
            panel = self._menu("solo", "SINGLE PLAYER", "PLAY VS DUPBOT")
            self._nickname_field(panel)
            self.nickname_entry.bind("<Return>", lambda _event: self.connect())
            self.difficulty_var = tk.StringVar(value=self.difficulty)
            self._choice_row(panel, "AI LEVEL", [(level, level.upper()) for level in ("easy", "medium", "hard")],
                             self.difficulty_var)
            self._rounds_choice(panel)
            self._footer(panel, message, "START  >")
        elif mode == "host":
            panel = self._menu("host", "MULTIPLAYER", "HOST A GAME")
            self._label(panel, f"Playing as {self.nickname}", 13, PALETTE["text"], wraplength=440).pack()
            self._rounds_choice(panel)
            self._label(panel, "Starts your server and dashboard. Your friend picks JOIN A GAME. "
                        "Keep this window open; do not also run server.py.",
                        11, PALETTE["muted"], wraplength=440, justify="left", anchor="w").pack(fill="x", pady=(12, 0))
            self._footer(panel, message, "START HOSTING  >")
        else:
            panel = self._menu("join", "MULTIPLAYER", "JOIN A GAME")
            self._label(panel, f"Playing as {self.nickname}", 13, PALETTE["text"], wraplength=440).pack()
            self._label(panel, "NEARBY GAMES", 11, PALETTE["cyan"]).pack(anchor="w", pady=(10, 4))
            self.server_list = tk.Listbox(panel, height=3, bg="#030b20", fg=PALETTE["text"],
                                          font=self._font(12), borderwidth=0, exportselection=False,
                                          selectbackground=PALETTE["border"], highlightthickness=0)
            self.server_list.pack(fill="x", ipady=4)
            self.server_list.bind("<Double-Button-1>", lambda _event: self.connect())
            tools = tk.Frame(panel, bg=PALETTE["panel"])
            tools.pack(fill="x", pady=(8, 0))
            self.check_button = ttk.Button(tools, text="FIND GAMES", command=self.find_games, style="Small.Arcade.TButton")
            self.check_button.pack(side="left", fill="x", expand=True)
            self.profile_button = ttk.Button(tools, text="LOAD FILE", command=self.load_connection, style="Small.Arcade.TButton")
            self.profile_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
            self._busy_widgets += [self.check_button, self.profile_button]
            self._footer(panel, message, "JOIN  >")
            self._display_servers()
            if not self.servers:
                self.find_games()

    def _go_back(self) -> None:
        self._stop_connection()
        self.events = queue.Queue()
        if self.current_screen in ("host", "join"):
            self.show_multiplayer()
        else:
            self.show_menu()

    def _join_busy(self, busy: bool) -> None:
        widgets = self._busy_widgets + [self.connect_button, self.nickname_entry, self.server_list]
        for widget in widgets:
            if widget is not None:
                widget.configure(state="disabled" if busy else "normal")

    def _display_servers(self) -> None:
        if self.server_list is None:
            return
        self.server_list.delete(0, "end")
        for row in self.servers:
            self.server_list.insert("end", f" {row['name']}  ·  {row['host']}:{row['port']}")
        if self.servers:
            self.server_list.selection_set(0)
        else:
            self.server_list.insert("end", " No games found yet.")

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
        path = filedialog.askopenfilename(parent=self.root, title="Load host connection", filetypes=[("Connection file", "*.json")])
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
            self.total_rounds = self.rounds_var.get()
        if mode == "solo":
            self.difficulty = self.difficulty_var.get()
        self._stop_connection()
        self.events = queue.Queue()
        if mode in ("host", "solo"):
            try:
                port = self.local_game.start(solo=mode == "solo", port=port, total_rounds=self.total_rounds)
            except OSError as exc:
                self.join_status.configure(text=listen_error(port, exc), fg=PALETTE["danger"])
                return
            if mode == "host":
                self.host_addresses = local_ip_addresses()
                self._create_dashboard()
        self._join_busy(True)
        self.join_status.configure(text=f"Connecting to {host}:{port}...", fg=PALETTE["cyan"])
        self.network = NetworkClient(self.events, host, port)
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

    def show_lobby(self, message: str = "Waiting for another player…") -> None:
        self.current_screen = "lobby"
        self.preview_mode = self.input_enabled = False
        panel = self._scene("PLAYER LOBBY")
        panel.place_configure(rely=.60)
        self._set_width(panel, 700)
        panel.configure(padx=24, pady=14)
        self._label(panel, f"Welcome, {self.nickname}.", 18, PALETTE["cyan"], wraplength=435).pack(pady=(0, 16))
        self._label(panel, "ONLINE PLAYERS", 11, PALETTE["yellow"]).pack(anchor="w", pady=(0, 8))
        self.player_listbox = tk.Listbox(panel, height=3, bg="#030b20", fg=PALETTE["text"],
                                       font=self._font(12), borderwidth=0,
                                       selectbackground=PALETTE["border"], highlightthickness=0)
        self.player_listbox.pack(fill="x", ipady=6)
        self._refresh_player_list()
        self.lobby_status = self._label(panel, message, 12, PALETTE["cyan"], wraplength=435)
        self.lobby_status.pack(pady=(8, 8))
        self._label(panel, f"{self.total_rounds} rounds · The match starts when two players join.", 11, PALETTE["muted"]).pack()
        if self.mode == "host" and self.local_game.server:
            self._label(panel, "Friend: choose Join a game → START on the same network.", 11, PALETTE["yellow"], wraplength=620).pack(pady=(10, 0))
            self._button(panel, "SERVER DASHBOARD / RESET", self.show_server_dashboard).pack(fill="x", pady=(8, 0))
        self._button(panel, "DISCONNECT", self.return_to_join).pack(fill="x", pady=(8, 0))

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
        panel = self._menu("practice", "PRACTICE", "PRACTICE BY EAR")
        self._label(panel, "Hear a short melody and play it back. The first note is shown, so find "
                    "the rest by interval. Every note is scored like a typing test: "
                    "accuracy, pitch precision and speed.",
                    11, PALETTE["muted"], wraplength=440, justify="left", anchor="w").pack(fill="x")
        self.practice_level_var = tk.StringVar(value=self.practice_level)
        self._choice_row(panel, "LEVEL · NOTES TO FIND AFTER THE FIRST",
                         [(level, f"{level.upper()} {LEVELS[level][0] - 1}") for level in LEVELS], self.practice_level_var)
        self.practice_length_var = tk.IntVar(value=self.practice_length)
        self._choice_row(panel, "MELODIES", [(count, str(count)) for count in LENGTH_OPTIONS], self.practice_length_var)
        self._label(panel, "EASY: nearby white keys · MEDIUM: all white keys · HARD: all 17 keys",
                    10, PALETTE["muted"], wraplength=440).pack(fill="x", pady=(10, 0))
        silent = not self.audio.available or self.audio.muted or self.audio.volume == 0
        self.join_status = self._label(panel, "Sound is off - unmute in SETTINGS (Ctrl+M) to hear melodies."
                                       if silent else "", 10, PALETTE["danger"], wraplength=440)
        self.join_status.pack(fill="x", pady=(6, 4))
        actions = tk.Frame(panel, bg=PALETTE["panel"])
        actions.pack(fill="x")
        self._button(actions, "<  BACK", self._go_back).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="START  >", command=self.start_practice,
                   style="Go.Arcade.TButton").pack(side="left", fill="x", expand=True, padx=(8, 0))

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
        title = {"win": "YOU WIN", "loss": "YOU LOST", "draw": "DRAW"}.get(result, "MATCH OVER")
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
                won = winner is not None and row.get("id") == winner
                accent = PALETTE["green"] if won else "#2b4677"
                card.panel(4, y, width - 14, 54, accent, PALETTE["panel_light"] if won else None)
                name = str(row.get("nickname", "PLAYER"))
                name = name if len(name) <= 12 else name[:11] + "."
                card.label(24, y + 17, name, 3, PALETTE["text"] if won or winner is None else PALETTE["muted"],
                           center=False)
                if row.get("id") == self.player_id:
                    card.label(24 + len(name) * 18 + 10, y + 20, "YOU", 2, PALETTE["cyan"], center=False)
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
        self._button(actions, "ROUND REVIEW", self.show_match_review).pack(side="left", fill="x", expand=True)
        self._button(actions, "LEAVE MATCH", self.return_to_join).pack(side="left", fill="x", expand=True,
                                                                       padx=(8, 0))

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
            self.show_lobby()
            if self.mode == "solo":
                self.local_game.start_bot(self.nickname, self.difficulty)
        elif event_type == mt.PLAYER_LIST:
            self.players = event.get("players", [])
            self._refresh_player_list()
        elif event_type == mt.MATCH_START:
            self._close_dialog()
            self.round_history = []
            self.scores = event.get("players", [])
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
            self._set_status(event.get("message", "Server rejected that action."), error=True)
            if self.current_screen in SETUP_SCREENS:
                self._join_busy(False)
        elif event_type == "servers_found" and self.current_screen == "join":
            self.servers = event["servers"]
            self._join_busy(False)
            self._display_servers()
            message = ("Host found. Choose your game and press START." if self.servers else
                       "No host found. Start Host and play on the other computer, then FIND GAMES again; or load its connection file.")
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
            self.state.status = message
            self._refresh_board()
        else:
            widget = "join_status" if self.current_screen in SETUP_SCREENS else {
                "lobby": "lobby_status", "results": "result_status"}.get(self.current_screen)
            if widget and hasattr(self, widget):
                getattr(self, widget).configure(text=message, fg=color)

    def _refresh_player_list(self) -> None:
        if self.current_screen != "lobby":
            return
        self.player_listbox.delete(0, "end")
        for player in self.players:
            status = "PLAYING" if player.get("in_match") else "READY"
            own = " (you)" if player.get("id") == self.player_id else ""
            self.player_listbox.insert("end", f" {player.get('nickname')}{own} · {status}")

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
        if self.audio.volume == 0:
            # Slider was dragged to zero: the speaker brings the sound back.
            self.audio.volume, self.audio.muted = 50, False
        else:
            self.audio.muted = not self.audio.muted
        self._refresh_board()

    def set_volume(self, value: int) -> None:
        self.audio.volume = value
        if value > 0:
            self.audio.muted = False

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
        if self.current_screen == "game" and not self.preview_mode:
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
        panel = self._new_dialog("SETTINGS")
        if panel is None:
            return
        self._label(panel, "SOUND", 12, PALETTE["yellow"]).pack(anchor="w")
        sound = tk.Frame(panel, bg=PALETTE["panel"])
        sound.pack(fill="x", pady=(6, 14))
        speaker = PixelCanvas(sound, width=64, height=44, cursor="hand2")
        speaker.pack(side="left")

        def draw_speaker():
            speaker.delete("all")
            silent = self.audio.muted or self.audio.volume == 0
            speaker.rect(0, 0, 64, 44, PALETTE["panel_light"])
            speaker.icon(32, 22, "speaker_off" if silent else "speaker", 3, PALETTE["cyan"])
            if silent:
                for step in range(11):
                    speaker.rect(7 + step * 3, 5 + step * 3, 4, 4, PALETTE["pink"])

        def volume(value):
            self.set_volume(int(float(value)))
            draw_speaker()

        slider = tk.Scale(sound, from_=0, to=100, resolution=5, orient="horizontal", showvalue=False,
                          command=volume, bg=PALETTE["cyan"], troughcolor="#163568",
                          activebackground="#ffffff", highlightthickness=0, bd=0,
                          sliderlength=26, width=18, sliderrelief="flat")

        def toggle(_event=None):
            self.toggle_mute()
            slider.set(self.audio.volume)
            draw_speaker()

        speaker.bind("<Button-1>", toggle)
        slider.set(self.audio.volume)
        slider.pack(side="left", fill="x", expand=True, padx=(14, 0))
        slider.bind("<ButtonRelease-1>", lambda _event: self.audio.play("c4"))
        draw_speaker()
        self.volume_slider = slider

        self._label(panel, "INSTRUMENT", 12, PALETTE["yellow"]).pack(anchor="w")
        choices = tk.Frame(panel, bg=PALETTE["panel"])
        choices.pack(fill="x", pady=(6, 12))
        choices.columnconfigure((0, 1), weight=1, uniform="instrument")
        self.instrument_var = tk.StringVar(value=self.audio.instrument)
        for index, name in enumerate(INSTRUMENTS):
            tk.Radiobutton(
                choices, text=name.upper(), value=name, variable=self.instrument_var, indicatoron=False,
                command=lambda: self._select_instrument(self.instrument_var.get()),
                font=self._font(11, True), pady=7, bd=0, highlightthickness=0, cursor="hand2",
                bg="#133369", fg=PALETTE["text"], selectcolor=PALETTE["blue"],
                activebackground="#214986", activeforeground=PALETTE["text"],
            ).grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 6, 0), pady=(0, 6))
        flashes = tk.BooleanVar(value=self.flashes)

        def apply_options():
            self.flashes = flashes.get()
            self._refresh_board()

        ttk.Checkbutton(panel, text="Flash my keys when I play", variable=flashes,
                        command=apply_options, style="Arcade.TCheckbutton").pack(anchor="w")
        if not self.audio.available:
            self._label(panel, "Audio output unavailable on this system.\nVisual feedback remains enabled.",
                        10, PALETTE["yellow"]).pack(pady=4)
        self._label(panel, "F11: fullscreen   Ctrl+M: mute   F1: help   Esc: close",
                    10, PALETTE["muted"]).pack(pady=(8, 10))
        self._button(panel, "BACK TO GAME" if self.current_screen in ("game", "practice_game") else "DONE",
                     self._close_dialog).pack(fill="x")

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
        self.audio.close()
        self.root.destroy()


def run_client_app(preview: bool = False, **options) -> None:
    root = tk.Tk()
    ClientWindow(root, preview=preview, **options)
    root.mainloop()


if __name__ == "__main__":
    run_client_app()

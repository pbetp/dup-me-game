"""Tkinter dashboard for the local game server.

It runs in its own window for server.py, or inside the game window as an
overlay when a player chooses HOST A GAME (pass a Frame instead of a window).
"""

from __future__ import annotations

import datetime as dt
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from src.client.pixel_ui import PALETTE
from src.common.config import DEFAULT_ROUNDS, SERVER_BIND_HOST, SERVER_PORT
from src.common.networking import local_ip_addresses, listen_error
from src.common.discovery import save_connection_file

from .server import DupMeServer

FONT = "Courier"


class ServerWindow:
    def __init__(self, root: tk.Misc, host: str = SERVER_BIND_HOST, port: int = SERVER_PORT,
                 total_rounds: int = DEFAULT_ROUNDS, server: DupMeServer | None = None,
                 on_close: Callable[[], None] | None = None):
        self.root = root
        self.embedded = not isinstance(root, (tk.Tk, tk.Toplevel))
        self.on_close = on_close
        self.visible = not self.embedded
        self._closed = False
        self._poll_job = None
        self.events: queue.Queue[dict] = queue.Queue()
        self.owns_server = server is None
        self.server = server or DupMeServer(self.events, host, port, total_rounds)
        self.server.event_queue = self.events
        self.root.configure(bg=PALETTE["background"])
        if not self.embedded:
            self.root.title("Dup Me Server")
            self.root.geometry("860x680")
            self.root.minsize(760, 600)
            self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="Starting…")
        self.online_var = tk.StringVar(value="Online clients: 0")
        self.online_count_var = tk.StringVar(value="0")
        self.match_var = tk.StringVar(value="Waiting for players")
        self.roles_var = tk.StringVar(value="Creator: —    Repeater: —")
        self.timer_var = tk.StringVar(value="Time remaining: —")
        self.scores_var = tk.StringVar(value="Scores: —")

        self._build()
        try:
            if self.owns_server:
                self.server.start()
            addresses = ", ".join(local_ip_addresses()) or "See your Wi-Fi IPv4 in network settings"
            self.status_var.set(f"TCP port {self.server.port}  ·  {addresses}\n{self.server.discovery_status}")
        except OSError as exc:
            self.status_var.set("Could not start server")
            messagebox.showerror("Server error", listen_error(port, exc))
        self._show_snapshot(self.server.snapshot())
        self._poll_job = self.root.after(100, self._poll_events)

    # --- layout -------------------------------------------------------------

    def _styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        common = dict(font=(FONT, 12, "bold"), padding=(14, 10), darkcolor="#07132f")
        style.configure("Dash.TButton", background="#133369", foreground=PALETTE["cyan"],
                        bordercolor=PALETTE["blue"], lightcolor=PALETTE["blue"], **common)
        style.map("Dash.TButton", background=[("active", "#214986")])
        style.configure("Danger.Dash.TButton", background="#3a1438", foreground=PALETTE["pink"],
                        bordercolor=PALETTE["pink"], lightcolor=PALETTE["pink"], **common)
        style.map("Danger.Dash.TButton", background=[("active", "#5a1f55")])

    def _card(self, master, title: str, accent: str = PALETTE["blue"]) -> tk.Frame:
        card = tk.Frame(master, bg=PALETTE["panel"], padx=16, pady=12,
                        highlightthickness=3, highlightbackground=accent)
        tk.Label(card, text=title, bg=PALETTE["panel"], fg=PALETTE["cyan"],
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(0, 6))
        return card

    def _text(self, master, variable: tk.StringVar, size=12, color=None, bold=False, **kwargs) -> tk.Label:
        return tk.Label(master, textvariable=variable, bg=PALETTE["panel"], fg=color or PALETTE["text"],
                        font=(FONT, size, "bold" if bold else "normal"), justify="left", anchor="w", **kwargs)

    def _build(self) -> None:
        self._styles()
        bg = PALETTE["background"]
        main = tk.Frame(self.root, bg=bg, padx=24, pady=18)
        main.pack(fill="both", expand=True)

        header = tk.Frame(main, bg=bg)
        header.pack(fill="x")
        tk.Label(header, text="SERVER DASHBOARD", bg=bg, fg=PALETTE["cyan"],
                 font=(FONT, 24, "bold")).pack(side="left")
        if self.embedded:
            ttk.Button(header, text="BACK TO GAME  >", style="Dash.TButton",
                       command=self.close).pack(side="right")
        tk.Label(main, textvariable=self.status_var, bg=bg, fg=PALETTE["muted"], font=(FONT, 11),
                 justify="left", anchor="w", wraplength=780).pack(fill="x", pady=(4, 14))

        row = tk.Frame(main, bg=bg)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1, uniform="cards")
        row.columnconfigure(1, weight=1, uniform="cards")

        match = self._card(row, "CURRENT MATCH", PALETTE["blue"])
        match.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._text(match, self.match_var, 15, PALETTE["yellow"], bold=True, wraplength=340).pack(fill="x")
        for variable in (self.roles_var, self.timer_var, self.scores_var):
            self._text(match, variable, 11, wraplength=340).pack(fill="x", pady=(4, 0))

        players = self._card(row, "PLAYERS ONLINE", PALETTE["pink"])
        players.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        count_row = tk.Frame(players, bg=PALETTE["panel"])
        count_row.pack(fill="x")
        self._text(count_row, self.online_count_var, 28, PALETTE["pink"], bold=True).pack(side="left")
        tk.Label(count_row, text="CONNECTED", bg=PALETTE["panel"], fg=PALETTE["muted"],
                 font=(FONT, 10, "bold")).pack(side="left", padx=(12, 0))
        self.players = tk.Listbox(players, height=4, bg="#030b20", fg=PALETTE["text"], font=(FONT, 12),
                                  borderwidth=0, highlightthickness=0, activestyle="none",
                                  selectbackground=PALETTE["border"])
        self.players.pack(fill="both", expand=True, pady=(6, 0))

        log_card = self._card(main, "ACTIVITY LOG")
        log_card.pack(fill="both", expand=True, pady=(14, 0))
        self.log = tk.Text(log_card, height=8, state="disabled", wrap="word", bg="#030b20",
                           fg=PALETTE["green"], font=(FONT, 11), borderwidth=0, highlightthickness=0,
                           insertbackground=PALETTE["text"], padx=8, pady=6)
        self.log.pack(fill="both", expand=True)

        controls = tk.Frame(main, bg=bg)
        controls.pack(fill="x", pady=(14, 0))
        ttk.Button(controls, text="SAVE CONNECTION FILE", style="Dash.TButton",
                   command=self.save_connection).pack(side="left")
        self.reset_button = ttk.Button(controls, text="RESTART MATCH", style="Dash.TButton",
                                       command=self.restart_match)
        self.reset_button.pack(side="right")
        self.end_button = ttk.Button(controls, text="END MATCH", style="Danger.Dash.TButton",
                                     command=self.end_match)
        self.end_button.pack(side="right", padx=(0, 10))
        self.notice = tk.Label(controls, text="", bg=bg, fg=PALETTE["green"], font=(FONT, 10),
                               wraplength=260, justify="left")
        self.notice.pack(side="left", padx=12)

    # --- live updates -------------------------------------------------------

    def _poll_events(self) -> None:
        if self._closed:
            return
        try:
            while True:
                event = self.events.get_nowait()
                if event.get("type") == "log":
                    timestamp = dt.datetime.now().strftime("%H:%M:%S")
                    self.log.configure(state="normal")
                    self.log.insert("end", f"[{timestamp}] {event['message']}\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif event.get("type") == "snapshot":
                    self._show_snapshot(event)
        except queue.Empty:
            pass
        self._show_snapshot(self.server.snapshot())
        self._poll_job = self.root.after(100, self._poll_events)

    def _show_snapshot(self, snapshot: dict) -> None:
        self.online_var.set(f"Online clients: {snapshot['online_count']}")
        self.online_count_var.set(str(snapshot["online_count"]))
        rows = [f" {player['nickname']:<16} {player['address']}" for player in snapshot["players"]]
        if list(self.players.get(0, "end")) != rows:
            self.players.delete(0, "end")
            for row in rows:
                self.players.insert("end", row)
        state = snapshot["state"].replace("_", " ").upper()
        round_number = snapshot["round"]
        self.match_var.set(state + (f" · ROUND {round_number} / {snapshot['total_rounds']}" if round_number else ""))
        self.roles_var.set(f"Creator: {snapshot['creator']}    Repeater: {snapshot['repeater']}")
        remaining = snapshot["remaining"]
        self.timer_var.set(f"Time remaining: {remaining if remaining is not None else '—'}")
        scores = "    ".join(f"{name}: {score}" for name, score in snapshot["scores"].items())
        self.scores_var.set(f"Scores: {scores or '—'}")

    # --- actions ------------------------------------------------------------

    def show(self) -> None:
        self.visible = True
        if self.embedded:
            self.root.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.root.lift()
            self.root.focus_set()
        else:
            self.root.deiconify()
            self.root.lift()

    def end_match(self) -> None:
        if self.server.end_match("The host ended the match."):
            self._after_host_action()
        else:
            self.notice.configure(text="No match is running.", fg=PALETTE["yellow"])

    def restart_match(self) -> None:
        self.server.reset_game("The host restarted the match.")
        self._after_host_action()

    def _after_host_action(self) -> None:
        self.notice.configure(text="")
        if self.embedded:
            self.close()  # Return the host to the game to see the result.

    def save_connection(self) -> None:
        addresses = local_ip_addresses()
        path = filedialog.asksaveasfilename(parent=self.root, title="Save host connection", initialfile="dup-me-connection.json", defaultextension=".json", filetypes=[("Connection file", "*.json")])
        if path:
            try:
                save_connection_file(path, addresses, self.server.port, self.server.name)
                self.notice.configure(text="Saved. On the other computer: JOIN A GAME → LOAD FILE.", fg=PALETTE["green"])
            except (OSError, ValueError) as exc:
                self.notice.configure(text=f"Could not save: {exc}", fg=PALETTE["danger"])

    def close(self) -> None:
        """Hide the dashboard. A dashboard that owns its server stops it instead."""
        if not self.owns_server and not self._closed:
            self.visible = False
            if self.embedded:
                self.root.place_forget()
            else:
                self.root.withdraw()
            if self.on_close:
                self.on_close()
            return
        self.dispose()

    def dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.visible = False
        if self._poll_job:
            self.root.after_cancel(self._poll_job)
        if self.owns_server:
            self.server.stop()
        elif self.server.event_queue is self.events:
            self.server.event_queue = None
        self.root.destroy()


def run_server_app(host: str = SERVER_BIND_HOST, port: int = SERVER_PORT, total_rounds: int = DEFAULT_ROUNDS) -> None:
    root = tk.Tk()
    ServerWindow(root, host, port, total_rounds)
    root.mainloop()


if __name__ == "__main__":
    run_server_app()

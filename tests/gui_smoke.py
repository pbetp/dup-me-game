"""Opt-in real Tk windows and sockets: python -m tests.gui_smoke."""
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch
from src.common.config import COLOR_NAMES, INSTRUMENTS, PIANO_KEYS
from src.common.discovery import save_connection_file
from src.client.art_screen import ArtChoice, ArtScreen
from src.client.lobby_screen import LobbyScreen
from src.client.client_ui import ClientWindow
from src.server import server as server_module
from src.server.server_ui import ServerWindow
import socket


def drain(root, seconds=.04):
    """Run the real Tk loop for a bounded interval, including timers and redraws.

    macOS Tk can keep update() draining forever beneath animated photo/Entry
    overlays. A timed mainloop matches normal app operation and enforces
    verification deadlines without pausing any artwork.
    """
    root.after(max(1, round(seconds * 1000)), root.quit)
    root.mainloop()


def pump(root, predicate, seconds=6):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        drain(root)
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for the GUI state')


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


ART_SCREENS = ('solo', 'multiplayer', 'practice', 'host', 'join', 'lobby')


def layout(root, app):
    # A full update, not just idle tasks: on Windows a new page is not mapped until then.
    drain(root)
    if app.current_screen in ART_SCREENS:
        # The whole artwork is visible and the nickname box sits inside it.
        scene = app.container.winfo_children()[0]
        assert isinstance(scene, (ArtScreen, LobbyScreen)) and scene.winfo_ismapped()
        left, top, width, height = scene.art_box
        assert left >= 0 and top >= 0, scene.art_box
        assert left + width <= scene.winfo_width() + 1 and top + height <= scene.winfo_height() + 1
        if app.nickname_entry is not None:
            entry = app.nickname_entry
            assert left <= entry.winfo_x() and entry.winfo_x() + entry.winfo_width() <= left + width + 1
            assert top <= entry.winfo_y() and entry.winfo_y() + entry.winfo_height() <= top + height + 1
        return
    if app.current_screen == 'menu':
        scene = app.opening_scene
        assert scene and scene.winfo_ismapped()
        left, top, width, height = scene.art_box
        assert left >= 0 and top >= 0
        assert left + width <= scene.winfo_width()
        assert top + height <= scene.winfo_height()
        for index in range(5):
            x0, y0, x1, y1 = scene.button_bounds(index)
            assert scene.button_at((x0 + x1) / 2, (y0 + y1) / 2) == index
        return
    scene, panel = app.container.winfo_children()
    assert panel.winfo_y() > scene.oy + 166 * scene.scale, ('header overlap', panel.winfo_y())
    assert panel.winfo_y() + panel.winfo_height() < root.winfo_height(), ('panel clipped', panel.winfo_height())
    def inside(widget):
        for child in widget.winfo_children():
            if child.winfo_manager():
                assert child.winfo_x() >= 0 and child.winfo_y() >= 0, str(child)
                assert child.winfo_x() + child.winfo_width() <= widget.winfo_width(), ('width', str(child))
                assert child.winfo_y() + child.winfo_height() <= widget.winfo_height(), ('height', str(child))
                inside(child)
    inside(panel)


def check_choices(root, parent):
    """Each group shows exactly one choice, including before and after a click."""
    groups = {}

    def collect(widget):
        if isinstance(widget, (ArtScreen, LobbyScreen)):
            for control in widget.controls:
                if isinstance(control, ArtChoice):
                    groups.setdefault(str(control.variable), []).append(control)
        for child in widget.winfo_children():
            if isinstance(child, ttk.Radiobutton):
                groups.setdefault(str(child.cget('variable')), []).append(child)
            collect(child)

    collect(parent)
    style = ttk.Style(root)
    for variable, buttons in groups.items():
        original = root.getvar(variable)

        def selected():
            active = [button for button in buttons if button.instate(['selected'])]
            marked = [button for button in buttons if button.cget('text').startswith('\u2713 ')]
            assert len(active) == 1 and active == marked
            if isinstance(active[0], ArtChoice):
                return active[0]
            button_style = active[0].cget('style')
            fill = style.lookup(button_style, 'background', ('selected',))
            assert fill != style.lookup(button_style, 'background', ())
            assert fill == style.lookup(button_style, 'background', ('selected', 'active'))
            return active[0]

        selected()
        for button in buttons:
            button.invoke()
            drain(root)
            assert selected() is button
        root.setvar(variable, original)
        drain(root)
        selected()


def run():
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args))
    app = ClientWindow(root, nickname='Human', port=free_port())
    app.audio.muted = True
    friend = None
    try:
        assert app.current_screen == 'menu'
        screens = (app.show_menu, app.show_multiplayer, lambda: app.show_setup('solo'),
                   lambda: app.show_setup('host'), lambda: app.show_setup('join'), app.show_practice_setup)
        for geometry in ('960x700', '1280x800'):
            root.geometry(geometry)
            for show in screens:
                show()
                layout(root, app)
                check_choices(root, app.container)
        # Animated photo + native Entry controls remain responsive on macOS Tk.
        app.show_setup('solo')
        scene = app.container.winfo_children()[0]
        heartbeat = []
        root.after(120, lambda: heartbeat.append(True))
        first = scene.frame_index
        drain(root, .35)
        assert heartbeat and scene.frame_index != first, 'Solo animation starved UI callbacks'
        # Step-by-step navigation: BACK returns to the previous menu.
        app.show_setup('host')
        app._go_back()
        assert app.current_screen == 'multiplayer'
        app.nickname_entry.delete(0, 'end')
        app._multiplayer_next('host')
        assert app.current_screen == 'multiplayer' and 'nickname' in app.join_status.cget('text').lower()
        app.nickname_entry.insert(0, 'Human')
        app._multiplayer_next('host')
        assert app.current_screen == 'host' and app.rounds_var.get() == 2
        app.connect()
        pump(root, lambda: app.current_screen == 'lobby')
        root.geometry('960x700')
        layout(root, app)
        server = app.local_game.server
        # Host dashboard lives inside the game window: hidden until opened, no extra window.
        assert app.dashboard and app.dashboard.server is server and app.dashboard.embedded
        assert not app.dashboard.visible and not any(isinstance(w, tk.Toplevel) for w in root.winfo_children())
        app.show_server_dashboard()
        drain(root)
        assert app.dashboard.visible and app.dashboard.root.winfo_ismapped()
        pump(root, lambda: app.dashboard.online_var.get() == 'Online clients: 1')
        app._escape()
        assert server.running.is_set() and not app.dashboard.visible and not app.dashboard.root.winfo_ismapped()
        app.show_server_dashboard()
        app.dashboard.close()
        # Second real GUI client: normal START must discover and connect, no endpoint entered.
        friend_root = tk.Toplevel(root)
        friend = ClientWindow(friend_root, nickname='Friend')
        friend.audio.muted = True
        friend.show_multiplayer()
        friend._multiplayer_next('join')
        pump(root, lambda: friend.servers and not friend.connect_button.instate(['disabled']))
        friend.connect()
        pump(root, lambda: app.current_screen == friend.current_screen == 'lobby'
             and len(app.players) == len(friend.players) == 2)
        assert app.start_lobby_button.instate(['disabled'])
        friend.toggle_lobby_ready()
        pump(root, lambda: app.start_lobby_button.instate(['!disabled']))
        app.start_lobby_match()
        pump(root, lambda: app.current_screen == friend.current_screen == 'game')
        pump(root, lambda: app.dashboard.online_var.get() == 'Online clients: 2')
        assert app.dashboard.players.size() == 2
        assert app.state.welcome_name == 'Human' and friend.state.welcome_name == 'Friend'
        completed = set()
        initial_creator = app if app.role == 'creator' else friend
        for number in (1, 2):
            pump(root, lambda: app.phase == friend.phase == 'create' and app.round_number == friend.round_number == number)
            creator = app if app.role == 'creator' else friend
            repeater = friend if creator is app else app
            assert (creator is initial_creator) == (number == 1)
            pattern = list(COLOR_NAMES) + list(COLOR_NAMES[:3])
            for note in pattern:
                creator.press_color(note)
            pump(root, lambda: len(creator.state.pattern) == len(repeater.state.pattern) == 20)
            assert repeater.state.blind and not creator.state.blind
            pump(root, lambda: app.phase == friend.phase == 'repeat')
            assert not app.state.pattern and not friend.state.pattern
            for note in pattern:
                repeater.press_color(note if number == 1 else 'e5')
        pump(root, lambda: app.current_screen == friend.current_screen == 'results')
        assert sorted(row['score'] for row in app.scores) == [1, 20]
        assert app.scores == friend.scores
        assert len(app.round_history) == len(friend.round_history) == 2
        assert app.rematch_button.cget('text') == 'REMATCH  >'
        def labels(client):
            return list(client.result_texts)
        assert {'YOU WIN', 'YOU LOST'} <= set(labels(app) + labels(friend))
        layout(root, app)
        app.show_match_review()
        drain(root)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'match.csv')
            with patch('src.client.client_ui.filedialog.asksaveasfilename', return_value=path):
                app.save_match_report()
            assert 'Final score' in Path(path).read_text()
        app._close_dialog()
        winner = next(row['id'] for row in app.scores if row['score'] == 20)
        app.request_rematch()
        drain(root)
        assert app.current_screen == 'results'
        friend.request_rematch()
        pump(root, lambda: app.current_screen == friend.current_screen == 'game' and app.round_number == friend.round_number == 1)
        assert (app.role == 'creator') == (app.player_id == winner)
        assert 'server' in app.board.actions and 'server' not in friend.board.actions
        # Host FORCE RESET: straight back to round 1 of the same match, no lobby, no reconnect.
        assert 'reset' in app.board.actions and 'reset' not in friend.board.actions
        assert any(name == 'reset' for name, _box, _cb in app.board.regions)
        creator = app if app.role == 'creator' else friend
        creator.press_color('c4')
        pump(root, lambda: len(app.state.pattern) == len(friend.state.pattern) == 1)
        network = friend.network
        app.board.actions['reset']()
        pump(root, lambda: app.current_screen == friend.current_screen == 'game'
             and app.round_number == friend.round_number == 1 and not app.state.pattern and not friend.state.pattern)
        assert friend.network is network and len(app.players) == 2
        assert [row['score'] for row in app.scores] == [0, 0]
        assert 'restarted' in app.state.status and 'restarted' in friend.state.status
        # Host RESET ROOM clears scores and readiness, then requires a new ready/start.
        app.show_server_dashboard()
        app.dashboard.reset_button.invoke()
        assert not app.dashboard.visible
        pump(root, lambda: app.current_screen == friend.current_screen == 'lobby')
        assert app.start_lobby_button.instate(['disabled'])
        friend.toggle_lobby_ready()
        pump(root, lambda: app.start_lobby_button.instate(['!disabled']))
        app.start_lobby_match()
        pump(root, lambda: app.current_screen == friend.current_screen == 'game'
             and app.round_number == friend.round_number == 1)
        assert app.round_number == friend.round_number == 1 and not app.round_history
        assert [row['score'] for row in app.scores] == [0, 0]
        # Host END MATCH: results now, decided by current scores (0-0 is a draw).
        app.show_server_dashboard()
        app.dashboard.end_button.invoke()
        pump(root, lambda: app.current_screen == friend.current_screen == 'results')
        assert 'DRAW' in labels(app) and 'The host ended the match.' in labels(friend)
        app.request_rematch()
        friend.request_rematch()
        pump(root, lambda: app.current_screen == friend.current_screen == 'game')
        # Force exit: the player who leaves always loses, whatever the score.
        friend.force_exit()
        pump(root, lambda: app.current_screen == friend.current_screen == 'results')
        assert 'YOU LOST' in labels(friend) and 'You forfeited the match.' in labels(friend)
        assert 'YOU WIN' in labels(app) and 'Friend forfeited the match.' in labels(app)
        # Results/menu boxes grow with the window and still fit (fullscreen-sized window).
        root.geometry('1500x860')
        drain(root)
        assert app.ui_scale > 1
        layout(root, app)
        root.geometry('960x700')
        drain(root)
        assert app.ui_scale == 1
        friend.close()
        friend = None
        pump(root, lambda: app.current_screen == 'lobby')
        pump(root, lambda: app.dashboard.online_var.get() == 'Online clients: 1')
        app.return_to_join()
        assert app.dashboard is None and app.local_game.server is None
        # Extended matches are explicitly separate; solo starts its own actual bot.
        app.show_setup('solo')
        app.rounds_var.set(8)
        app.difficulty_var.set('hard')
        app.connect()
        pump(root, lambda: app.current_screen == 'game')
        assert app.local_game.bot is not None and app.local_game.server.host == '127.0.0.1'
        assert app.state.total_rounds == 8
        assert app.difficulty == 'hard'
        # Solo FORCE RESET restarts against the same bot.
        bot = app.local_game.bot
        app.board.actions['reset']()
        pump(root, lambda: app.current_screen == 'game' and app.round_number == 1 and 'restarted' in app.state.status)
        assert app.local_game.bot is bot and app.state.total_rounds == 8
        app.return_to_join()
        assert app.current_screen == 'solo'
        app.servers = [{'name': 'Unavailable', 'host': '127.0.0.1', 'port': free_port()}]
        app.show_setup('join')
        app.connect()
        pump(root, lambda: app.current_screen == 'join' and not app.connect_button.instate(['disabled']))
        assert 'refused' in app.join_status.cget('text').lower()
        # File fallback reaches a server with UDP advertising disabled.
        dashboard = ServerWindow(tk.Toplevel(root), host='127.0.0.1', port=0)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'connection.json'
                save_connection_file(path, ['127.0.0.1'], dashboard.server.port)
                app.connect_from_file(path)
                pump(root, lambda: not app.connect_button.instate(['disabled']))
                assert app.servers[0]['port'] == dashboard.server.port
                app.connect()
                pump(root, lambda: app.current_screen == 'lobby')
                pump(root, lambda: dashboard.online_var.get() == 'Online clients: 1')
                dashboard.close()
                pump(root, lambda: app.current_screen == 'join')
        finally:
            dashboard.close()
        app.show_preview()
        app.force_exit()
        assert app.current_screen == 'menu' and not app.preview_mode
        app.show_preview()
        drain(root)
        for note, _key, _midi, _accent, index, black in PIANO_KEYS:
            x = 180 + (index + 1) * 108 if black else 180 + index * 108 + 52
            y = 520 if black else 650
            app.board.event_generate('<Button-1>', x=round(app.board.ox + x * app.board.scale), y=round(app.board.oy + y * app.board.scale))
            drain(root)
            assert app.state.pattern[-1] == note
        assert app.state.pattern == list(COLOR_NAMES)
        app.preview_undo()
        assert len(app.state.pattern) == 16
        app.show_settings()
        drain(root)
        # Settings opens inside the game window, not as a separate window.
        assert not any(isinstance(w, tk.Toplevel) for w in root.winfo_children())
        assert app.dialog.winfo_ismapped()
        # Settings is the full-window Orbital Mixer artwork with live controls.
        panel = app.dialog
        buttons = app.instrument_buttons
        assert isinstance(panel, ArtScreen) and len(buttons) == len(INSTRUMENTS)
        check_choices(root, panel)
        before = list(app.state.pattern)
        app.press_color('c4')  # the board behind an open panel ignores notes
        assert app.state.pattern == before
        app.volume_slider.set(0)
        drain(root)
        assert app.audio.volume == 0
        app.volume_slider.set(70)
        drain(root)
        assert app.audio.volume == 70 and not app.audio.muted
        for instrument, button in zip(INSTRUMENTS, buttons):
            button.invoke()
            drain(root)
            assert app.audio.instrument == instrument and app.board.instrument == instrument
            assert button.instate(['selected']) and button.cget('text').startswith('\u2713 ')
            assert app.state.pattern == before
        left, top, width, height = panel.art_box
        assert left >= 0 and top >= 0 and left + width <= panel.winfo_width() + 1
        app._close_dialog()
        app.show_help()
        drain(root)
        app._close_dialog()
        app._escape()
        assert app.current_screen == 'menu' and not app.preview_mode
        app.show_settings()
        drain(root)
        check_choices(root, app.dialog)
        # Menu buttons behind the open panel are blocked until it closes.
        assert app.root.grab_current() is app.dialog
        app._close_dialog()
        assert app.root.grab_current() is None
        assert not errors, errors
        print('PASS: main menu -> single/multiplayer -> host/join navigation; two real GUI clients discovered each other, waited for client readiness and host start, and completed standard match; WIN/LOST, welcome, scores, role swap, review/CSV, both-vote winner-first rematch, host room reset/end match, forfeit = LOST, server count/list/reset/hide/reopen, disconnect, extended AI startup, failed connection retry, connection-file fallback, 17 clickable keys, four instruments, layout at both sizes, settings/help; zero Tk callback errors.')
    finally:
        if friend:
            friend.close()
        app.close()


if __name__ == '__main__':
    with patch.object(server_module, 'CREATE_SECONDS', 1.5), patch.object(server_module, 'PHASE_RESULT_SECONDS', .15):
        run()

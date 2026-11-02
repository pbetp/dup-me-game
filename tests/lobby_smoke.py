"""Opt-in live lobby, animation, and keyboard checks: python -m tests.lobby_smoke.

Use --screenshots PATH to save the actual app screens during verification.
"""
from __future__ import annotations

import argparse
import subprocess
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import ImageGrab

from src.client.client_ui import ClientWindow
from src.client.lobby_screen import LobbyScreen
from tests.gui_smoke import check_choices, free_port, layout, pump


def settle(root, seconds=.25):
    root.after(max(1, round(seconds * 1000)), root.quit)
    root.mainloop()


def click(scene, box):
    left, top, width, height = scene.art_box
    x = round(left + (box[0] + box[2]) / 2 * width / 1280)
    y = round(top + (box[1] + box[3]) / 2 * height / 720)
    scene.event_generate('<ButtonPress-1>', x=x, y=y)
    scene.event_generate('<ButtonRelease-1>', x=x, y=y)


def rendered_region(scene, y_min, y_max):
    """Compare actual animated artwork, rather than only a frame counter."""
    result = []
    for item in scene.find_withtag('animation'):
        coords = scene.coords(item)
        if len(coords) < 2:
            continue
        logical_y = (coords[1] - scene.oy) / scene.scale
        if y_min <= logical_y <= y_max:
            result.append((scene.type(item), tuple(round(value, 2) for value in coords),
                           scene.itemcget(item, 'fill')))
    return tuple(result)


def screenshot(root, folder, name):
    if folder is None:
        return
    root.lift()
    settle(root, .15)
    folder.mkdir(parents=True, exist_ok=True)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    try:
        image = ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()))
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'SKIP optional screenshot {name}: screen capture is unavailable ({exc}).')
        return
    image.save(folder / (name + '.png'))


def run(screenshots=None):
    root = tk.Tk()
    root.geometry('1280x800+10+30')
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args))
    with patch('src.client.client_ui.BackgroundMusic.start'):
        app = ClientWindow(root, nickname='joji', port=free_port())
    app.audio.muted = True
    friend = None
    temporary = None
    try:
        for geometry in ('960x700', '1280x800', '1600x900'):
            root.geometry(geometry)
            app.show_setup('host')
            settle(root)
            layout(root, app)
            scene = app.lobby_scene
            assert isinstance(scene, LobbyScreen)
            check_choices(root, scene)
            assert app.rounds_var.get() == 2
            choices = [control for control in scene.controls if hasattr(control, 'variable')]
            click(scene, choices[-1].box)
            settle(root, .05)
            assert app.rounds_var.get() == 12
            click(scene, choices[0].box)
            assert app.rounds_var.get() == 2
            for control in scene.controls:
                if not hasattr(control, 'box'):
                    continue
                x0, y0, x1, y1 = control.box
                assert 0 <= x0 < x1 <= 1280 and 0 <= y0 < y1 <= 720

        root.geometry('1280x800+10+30')
        app.show_setup('host')
        settle(root)
        scene = app.lobby_scene
        first = scene.frame_index
        ball = rendered_region(scene, 200, 460)
        keyboard = rendered_region(scene, 490, 720)
        settle(root, .5)
        assert scene.frame_index != first
        assert ball != rendered_region(scene, 200, 460), 'Disco tiles did not rotate'
        assert keyboard != rendered_region(scene, 490, 720), 'Keyboard keys did not animate'
        screenshot(root, screenshots, 'host-setup-1280')

        # Empty rows are not joinable, and ending a busy state must not enable Join.
        app.servers = []
        app.show_setup('join', 'No rooms found yet.')
        settle(root)
        assert app.server_list.size() == 0 and not app.server_list.curselection()
        assert app.connect_button.instate(['disabled'])
        app._join_busy(True)
        assert app.profile_button.instate(['disabled'])
        app._join_busy(False)
        assert app.connect_button.instate(['disabled'])
        app.servers = [
            {'name': "joji's room", 'host': '127.0.0.1', 'port': free_port(),
             'players': 1, 'total_rounds': 2, 'mode': 'versus'},
            {'name': 'Full room', 'host': '127.0.0.1', 'port': free_port(),
             'players': 2, 'total_rounds': 4, 'mode': 'versus'},
        ]
        app._display_servers()
        app.server_list.selection_set(1)
        assert app.connect_button.instate(['disabled']), 'Full room was joinable'
        app.server_list.selection_set(0)
        assert app.connect_button.instate(['!disabled'])
        # The blank area below the visible room must not select/join an offscreen row.
        browser = app.server_list
        browser.press(540, 415)
        assert browser.curselection() == (0,)
        joined = []
        original_join = browser.on_join
        browser.on_join = lambda: joined.append(True)
        left, top, width, height = app.lobby_scene.art_box
        app.lobby_scene._double(SimpleNamespace(x=left + 540 * width / 1280,
                                               y=top + 415 * height / 720))
        assert not joined
        browser.on_join = original_join
        app.server_list.selection_clear()
        assert app.connect_button.instate(['disabled'])
        app.server_list.selection_set(0)
        screenshot(root, screenshots, 'client-join-1280')
        # A click starts one connection and exposes its loading state.
        with patch('src.client.client_ui.NetworkClient') as network:
            app.connect_button.invoke()
            assert network.return_value.connect_async.call_count == 1
            assert app.connect_button.instate(['disabled'])
            assert 'JOINING' in app.connect_button.cget('text')
            app.connect_button.invoke()
            assert network.return_value.connect_async.call_count == 1
            app._stop_connection()

        # Keyboard operation on the same canvas works without pointer focus.
        app._clear()
        allowed = [True]
        temporary = LobbyScreen(app.container, page='host', nickname='joji',
                                can_animate=lambda: allowed[0])
        temporary.pack(fill='both', expand=True)
        invoked = []
        button = temporary.button((820, 565, 1180, 615), 'CONTINUE >',
                                  lambda: invoked.append(True), primary=True)
        settle(root)
        temporary.focus_force()
        temporary.event_generate('<Tab>')
        temporary.event_generate('<Return>')
        assert len(invoked) == 1
        button.configure(state='disabled')
        temporary.event_generate('<Return>')
        assert len(invoked) == 1
        allowed[0] = False
        frozen = temporary.frame_index
        settle(root, .25)
        assert temporary.frame_index == frozen
        allowed[0] = True
        settle(root, .2)
        assert temporary.frame_index != frozen
        root.withdraw()
        settle(root, .1)
        assert temporary._timer is None
        root.deiconify()
        settle(root, .2)
        assert temporary._timer is not None
        temporary.destroy()
        assert temporary._disposed and temporary._timer is None
        temporary = None

        # Two real clients remain in the room until the client is ready and host starts.
        app.show_setup('host')
        app.connect()
        pump(root, lambda: app.current_screen == 'lobby')
        assert app.start_lobby_button.instate(['disabled'])
        screenshot(root, screenshots, 'host-waiting-room-1280')
        friend_root = tk.Toplevel(root)
        with patch('src.client.client_ui.BackgroundMusic.start'):
            friend = ClientWindow(friend_root, nickname='jojo')
        friend.audio.muted = True
        friend.servers = [{'name': "joji's room", 'host': '127.0.0.1',
                           'port': app.local_game.server.port, 'players': 1,
                           'mode': 'versus', 'total_rounds': 2}]
        friend.show_setup('join')
        friend.server_list.selection_set(0)
        friend.connect()
        pump(root, lambda: friend.current_screen == app.current_screen == 'lobby'
             and len(app.players) == len(friend.players) == 2)
        assert app.start_lobby_button.instate(['disabled'])
        friend.ready_button.invoke()
        pump(root, lambda: app.start_lobby_button.instate(['!disabled']))
        assert friend.current_screen == app.current_screen == 'lobby'
        assert 'READY' in friend.ready_button.cget('text')
        screenshot(friend_root, screenshots, 'client-waiting-room-1280')
        for geometry in ('960x700', '1280x800'):
            root.geometry(geometry)
            friend_root.geometry(geometry)
            settle(root)
            layout(root, app)
            layout(root, friend)
        screenshot(root, screenshots, 'host-waiting-room-960')
        # Cancel readiness, then leave: the host cannot start from stale state.
        friend.ready_button.invoke()
        pump(root, lambda: app.start_lobby_button.instate(['disabled']))
        friend.close()
        friend = None
        pump(root, lambda: len(app.players) == 1)
        assert app.current_screen == 'lobby' and app.start_lobby_button.instate(['disabled'])
        previous = app.lobby_scene
        app.return_to_join()
        settle(root)
        assert previous._disposed and previous._timer is None
        assert not errors, errors
    finally:
        if temporary is not None:
            temporary.destroy()
        if friend is not None:
            friend.close()
        app.close()
    print('PASS: three sizes; host rounds by click; empty/full/selected/loading room states; '
          'keyboard activation; real rotating disco and playing-keyboard artwork; '
          'modal pause and minimize/resume; two-client readiness/cancel/disconnect; '
          'timer disposal; zero Tk callback errors.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--screenshots', type=Path)
    options = parser.parse_args()
    run(options.screenshots)

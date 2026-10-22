"""Opt-in real desktop/audio check: python -m tests.music_smoke (macOS)."""
import ctypes
import time
import tkinter as tk
from unittest.mock import patch

from src.client.client_ui import ClientWindow
from src.client.music import BackgroundMusic


def pump(root, seconds=.15):
    # A continuously animated canvas can keep update()'s event queue nonempty.
    # Use the application's normal event loop with an explicit deadline.
    root.after(max(1, round(seconds * 1000)), root.quit)
    root.mainloop()


def run():
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args))
    # Verify actual native playback silently; do not change system volume.
    def quiet_music():
        music = BackgroundMusic()
        music.set_volume(0)
        return music

    with patch('src.client.client_ui.BackgroundMusic', side_effect=quiet_music):
        app = ClientWindow(root)
    try:
        assert app.music.available, app.music.error
        native = app.music._player
        assert native._call(native._sound, 'loops', ctypes.c_bool)
        assert native._call(native._sound, 'duration', ctypes.c_double) == 120
        app.audio.muted = True
        app.music.set_muted(True)
        for size in ('960x700', '1280x800'):
            root.geometry(size)
            app.show_settings()
            pump(root)
            assert app.audio.muted and app.music.muted, 'Opening settings unmuted audio'
            dialog = app.dialog
            assert dialog.winfo_y() >= 0
            assert dialog.winfo_y() + dialog.winfo_height() <= root.winfo_height()
            app.music_slider.set(35)
            pump(root)
            assert app.music.volume == 35 and app.music.muted
            app.music_slider.set(0)
            pump(root)
            assert app.music.volume == 0 and app.audio.volume == 60
            app._close_dialog()

        native._call(native._sound, 'setCurrentTime:', None, (ctypes.c_double,), 119.7)
        pump(root, .8)
        position = native._call(native._sound, 'currentTime', ctypes.c_double)
        assert 0 < position < 2, position
        assert native._call(native._sound, 'isPlaying', ctypes.c_bool)

        app.show_preview()
        app.show_menu()
        pump(root, .2)
        assert app.music._player is native
        assert native._call(native._sound, 'currentTime', ctypes.c_double) > position
        app.toggle_mute()
        assert not app.audio.muted and not app.music.muted
        # Start a real piano note while the silent soundtrack continues.
        app.audio.volume = 1
        app.audio.play('c4')
        pump(root, .15)
        assert native._call(native._sound, 'isPlaying', ctypes.c_bool)
        assert not errors, errors
    finally:
        app.close()
    assert native._sound is None
    print('PASS: native playback wraps past 120 seconds; piano plays alongside music; '
          'screen changes preserve playback; master mute and music slider work; '
          'settings fit 960x700 and 1280x800; close releases audio; zero Tk errors.')


if __name__ == '__main__':
    run()

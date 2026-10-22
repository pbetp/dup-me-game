"""Real-window checks for the animated menu: python -m tests.opening_smoke."""

import time
import tkinter as tk
from unittest.mock import patch

from PIL import Image, ImageTk

from src.client.client_ui import ClientWindow
from src.client.music import BackgroundMusic
from src.client.opening_screen import ART_PATH


def pump(root, seconds=.2):
    root.after(max(1, round(seconds * 1000)), root.quit)
    root.mainloop()


def click(scene, index):
    x0, y0, x1, y1 = scene.button_bounds(index)
    x, y = round((x0 + x1) / 2), round((y0 + y1) / 2)
    scene.event_generate("<ButtonPress-1>", x=x, y=y)
    scene.event_generate("<ButtonRelease-1>", x=x, y=y)


def run():
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args))

    def quiet_music():
        music = BackgroundMusic()
        music.set_volume(0)
        return music

    with patch("src.client.client_ui.BackgroundMusic", side_effect=quiet_music):
        app = ClientWindow(root)
    app.audio.muted = True
    try:
        for geometry in ("960x700", "1280x800", "1600x900"):
            root.geometry(geometry)
            pump(root)
            scene = app.opening_scene
            left, top, width, height = scene.art_box
            assert left >= 0 and top >= 0
            assert left + width <= scene.winfo_width()
            assert top + height <= scene.winfo_height()
            assert abs(width / height - 16 / 9) < .005
            assert scene.button_at(1, 1) is None
            # Compare what Tk displays against the exact decoded original frame.
            with Image.open(ART_PATH) as expected:
                expected.seek(scene.frame_index)
                expected = expected.convert("RGBA").resize((width, height), Image.Resampling.NEAREST)
                actual = ImageTk.getimage(scene._photo).convert("RGBA")
                assert actual.tobytes() == expected.tobytes(), "Artwork changed during rendering"
            for index, target in ((0, "solo"), (1, "multiplayer"), (2, "practice")):
                previous = app.opening_scene
                click(previous, index)
                pump(root, .05)
                assert app.current_screen == target, (index, app.current_screen)
                assert previous._disposed and previous._timer is None
                app._go_back()
                pump(root, .05)
                assert app.current_screen == "menu"

        scene = app.opening_scene
        first = scene.frame_index
        sample_start = time.monotonic()
        pump(root, 1)
        print("Animation playback: %.1f frames/second" % (
            ((scene.frame_index - first) % scene.frame_count) / (time.monotonic() - sample_start)))
        assert scene.frame_index != first and scene.frame_count == 192
        scene._stop()
        scene.frame_index = scene.frame_count - 1
        scene._source.seek(scene.frame_index)
        scene._deadline = time.monotonic()
        scene._advance()
        assert scene.frame_index == 0, ("Animation did not wrap cleanly", scene.frame_index, errors)

        click(scene, 3)
        pump(root)
        assert app.dialog is not None and root.grab_current() is app.dialog
        paused_frame = scene.frame_index
        pump(root, .2)
        assert scene.frame_index == paused_frame, "Background should rest beneath a modal"
        scene.activate(0)
        assert app.current_screen == "menu", "Modal did not block menu actions"
        app._close_dialog()
        pump(root, .2)
        assert scene.frame_index != paused_frame, "Animation did not resume after the modal"
        scene.focus_force()
        scene.selected = 0
        pump(root, .05)
        scene.event_generate("<Down>")
        scene.event_generate("<Return>")
        pump(root, .05)
        assert app.current_screen == "multiplayer", "Keyboard navigation failed"
        app._go_back()
        pump(root)

        root.withdraw()
        pump(root, .05)
        assert app.opening_scene._timer is None
        root.deiconify()
        pump(root, .1)
        assert app.opening_scene._timer is not None
        assert not errors, errors
        click(app.opening_scene, 4)
        assert app._closed
    finally:
        app.close()
    print("PASS: exact artwork pixels; 192-frame loop; three window sizes; all five "
          "buttons; keyboard navigation; modal blocking; animation cleanup and "
          "minimize/resume; zero Tk callback errors.")


if __name__ == "__main__":
    run()

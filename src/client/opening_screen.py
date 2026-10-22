"""Animated opening artwork and menu hit areas; no gameplay state lives here."""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from typing import Callable, Sequence

from PIL import Image, ImageTk


ART_PATH = Path(__file__).resolve().parents[2] / "assets" / "ui" / "disco-opening.gif"
ART_SIZE = (1280, 720)
# Coordinates belong to the buttons already painted into the approved artwork.
BUTTON_BOXES = (
    (871, 155, 1211, 228),
    (871, 244, 1211, 321),
    (871, 333, 1211, 408),
    (871, 416, 1211, 494),
    (871, 503, 1211, 577),
)
BUTTON_COLORS = ("#58f6ff", "#ff68bd", "#d17aff", "#ffdc65", "#62b9ff")


class OpeningScreen(tk.Canvas):
    """Play the original GIF and route its five menu areas to existing actions.

    Only the current decoded frame is retained. The animation does not load all
    192 full-size frames into Tk, and its timer is stopped when the page closes.
    """

    def __init__(self, master: tk.Misc, actions: Sequence[Callable[[], None]],
                 can_activate: Callable[[], bool] = lambda: True):
        super().__init__(master, bg="#01051e", highlightthickness=0, bd=0,
                         takefocus=True)
        if len(actions) != len(BUTTON_BOXES):
            raise ValueError("The opening screen needs all five menu actions.")
        self.actions = tuple(actions)
        self.can_activate = can_activate
        self._source = Image.open(ART_PATH)
        self.frame_count = self._source.n_frames
        self.frame_index = 0
        self._frame = self._source.convert("RGB")
        self._photo: ImageTk.PhotoImage | None = None
        self._image_item = self.create_image(0, 0, anchor="nw")
        self._timer: str | None = None
        self._resize_job: str | None = None
        self._disposed = False
        self._deadline = 0.0
        self._render_size = (0, 0)
        self.art_box = (0, 0, 1280, 720)
        self.selected = 0
        self._hover: int | None = None
        self._pressed_button: int | None = None
        self._keyboard_focus = False

        self.bind("<Configure>", self._resize)
        self.bind("<Map>", self._start)
        self.bind("<Unmap>", self._stop)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._mouse_down)
        self.bind("<ButtonRelease-1>", self._mouse_up)
        self.bind("<Down>", lambda _event: self._move(1))
        self.bind("<Up>", lambda _event: self._move(-1))
        self.bind("<Tab>", lambda _event: self._move(1))
        self.bind("<Shift-Tab>", lambda _event: self._move(-1))
        self.bind("<ISO_Left_Tab>", lambda _event: self._move(-1))
        self.bind("<Return>", lambda _event: self.activate(self.selected))
        self.bind("<KP_Enter>", lambda _event: self.activate(self.selected))
        self.bind("<space>", lambda _event: self.activate(self.selected))
        self.bind("<FocusOut>", self._focus_out)

    def _start(self, _event=None) -> None:
        if self._disposed or self._timer is not None:
            return
        self.focus_set()
        self._paint()
        delay = max(20, int(self._source.info.get("duration", 50)))
        self._deadline = time.monotonic() + delay / 1000
        self._timer = self.after(delay, self._advance)

    def _stop(self, _event=None) -> None:
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def _advance(self) -> None:
        self._timer = None
        if self._disposed or not self.winfo_ismapped():
            return
        # Avoid repainting a large image beneath native modal controls. On macOS
        # Tk this can continuously invalidate the overlay and starve update().
        # Audio is independent; playback resumes at the next frame on closing.
        if not self.can_activate():
            self._deadline = time.monotonic()
            self._timer = self.after(100, self._advance)
            return
        self.frame_index = (self.frame_index + 1) % self.frame_count
        self._source.seek(self.frame_index)
        self._frame = self._source.convert("RGB")
        self._paint()
        delay = max(20, int(self._source.info.get("duration", 50)))
        self._deadline += delay / 1000
        now = time.monotonic()
        # Recover gently if moving/resizing the window stalls the UI thread.
        if self._deadline < now:
            self._deadline = now + delay / 1000
        self._timer = self.after(max(1, round((self._deadline - now) * 1000)), self._advance)

    def _resize(self, _event=None) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after_idle(self._paint)

    def _paint(self) -> None:
        if self._disposed:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        scale = min(width / ART_SIZE[0], height / ART_SIZE[1])
        size = (max(1, round(ART_SIZE[0] * scale)), max(1, round(ART_SIZE[1] * scale)))
        left, top = (width - size[0]) // 2, (height - size[1]) // 2
        self.art_box = (left, top, size[0], size[1])
        frame = self._frame if size == ART_SIZE else self._frame.resize(size, Image.Resampling.NEAREST)
        if self._photo is None or size != self._render_size:
            self._photo = ImageTk.PhotoImage(frame, master=self)
            self.itemconfigure(self._image_item, image=self._photo)
            self._render_size = size
        else:
            self._photo.paste(frame)
        self.coords(self._image_item, left, top)
        self._draw_focus()

    def button_bounds(self, index: int) -> tuple[float, float, float, float]:
        """Return the visible button rectangle, including resize/letterboxing."""
        left, top, width, height = self.art_box
        x0, y0, x1, y1 = BUTTON_BOXES[index]
        return (left + x0 * width / ART_SIZE[0], top + y0 * height / ART_SIZE[1],
                left + x1 * width / ART_SIZE[0], top + y1 * height / ART_SIZE[1])

    def button_at(self, x: float, y: float) -> int | None:
        for index in range(len(self.actions)):
            x0, y0, x1, y1 = self.button_bounds(index)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return index
        return None

    def _motion(self, event) -> None:
        hovered = self.button_at(event.x, event.y)
        if hovered != self._hover:
            self._hover = hovered
            self.configure(cursor="hand2" if hovered is not None else "")
            self._draw_focus()

    def _leave(self, _event=None) -> None:
        self._hover = None
        self._draw_focus()

    def _mouse_down(self, event) -> str:
        if self.can_activate():
            self.focus_set()
            self._keyboard_focus = False
            self._pressed_button = self.button_at(event.x, event.y)
        return "break"

    def _mouse_up(self, event) -> str:
        index = self._pressed_button
        self._pressed_button = None
        if index is not None and index == self.button_at(event.x, event.y):
            return self.activate(index)
        return "break"

    def _move(self, direction: int) -> str:
        if self.can_activate():
            self.selected = (self.selected + direction) % len(self.actions)
            self._keyboard_focus = True
            self._hover = None
            self._draw_focus()
        return "break"

    def _focus_out(self, _event=None) -> None:
        self._keyboard_focus = False
        self._pressed_button = None
        self._draw_focus()

    def _draw_focus(self) -> None:
        self.delete("menu_focus")
        index = self.selected if self._keyboard_focus else self._hover
        if index is None or not self.can_activate():
            return
        x0, y0, x1, y1 = self.button_bounds(index)
        length = max(5, round(10 * self.art_box[2] / ART_SIZE[0]))
        for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1),
                              (x0, y1, 1, -1), (x1, y1, -1, -1)):
            self.create_line(x, y + dy * length, x, y, x + dx * length, y,
                             fill=BUTTON_COLORS[index], width=2, tags="menu_focus")

    def activate(self, index: int) -> str:
        if not self._disposed and self.can_activate():
            self.selected = index
            self.actions[index]()
        return "break"

    def destroy(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._stop()
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        self._source.close()
        super().destroy()
        self._photo = None

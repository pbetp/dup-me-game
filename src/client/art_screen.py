"""Menu screens drawn from approved artwork, with the painted controls made live.

Each screen shows one artwork (an animated GIF or a still image) fitted into the
window without cropping, like the opening screen. The artwork already pictures
every control. Registered controls sit exactly on top of the painted ones, in
artwork pixels, so they line up at every window size:

* plain buttons only add a click area, hover corners and a dimmed disabled look;
* choice buttons, sliders, the checkbox, the nickname box and status text are
  redrawn over the art, because what they show changes while you use them.

The control objects answer the same calls the menu code already makes on Tk
widgets (configure(state=...), instate, invoke, cget("text"), set/get).
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from typing import Callable

from PIL import Image, ImageTk

from .pixel_ui import PALETTE, PixelCanvas

ART_DIR = Path(__file__).resolve().parents[2] / "assets" / "ui"
CHECK = "0000001/0000011/1000110/1101100/0111000/0010000"

Box = tuple[float, float, float, float]


def inside(box: Box, x: float, y: float) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


class ArtButton:
    """A button painted into the artwork."""

    def __init__(self, screen: "ArtScreen", box: Box, command: Callable[[], None], color: str):
        self.screen, self.box, self.command, self.color = screen, box, command, color
        self.disabled = False

    def configure(self, state: str | None = None, **_options) -> None:
        if state is not None:
            self.disabled = state == "disabled"
            self.screen.refresh()

    config = configure

    def instate(self, states: list[str]) -> bool:
        return all(self.disabled if state == "disabled" else not self.disabled if state == "!disabled"
                   else False for state in states)

    def invoke(self) -> None:
        if not self.disabled:
            self.command()

    def press(self, x: float, y: float) -> None:
        pass

    def release(self, x: float, y: float) -> None:
        if inside(self.box, x, y):
            self.invoke()

    def draw(self, screen: "ArtScreen", hover: bool) -> None:
        x0, y0, x1, y1 = self.box
        if self.disabled:
            screen.rect(x0, y0, x1 - x0, y1 - y0, "#000000", stipple="gray50")
        elif hover:
            screen.corners(self.box, self.color)


class ArtChoice:
    """One button of a choice group, drawn over the painted one.

    style "button" repaints the whole button (label included); style "marker"
    keeps the painted button and adds a selection frame and tick.
    """

    def __init__(self, screen: "ArtScreen", box: Box, value, text: str, variable: tk.Variable,
                 colors: dict[str, str], command: Callable[[], None] | None = None, style: str = "button"):
        self.screen, self.box, self.value, self.text = screen, box, value, text
        self.variable, self.colors, self.command, self.style = variable, colors, command, style
        self.disabled = False

    @property
    def selected(self) -> bool:
        return str(self.variable.get()) == str(self.value)

    def configure(self, state: str | None = None, **_options) -> None:
        if state is not None:
            self.disabled = state == "disabled"
            self.screen.refresh()

    config = configure

    def instate(self, states: list[str]) -> bool:
        checks = {"selected": self.selected, "!selected": not self.selected,
                  "disabled": self.disabled, "!disabled": not self.disabled}
        return all(checks.get(state, False) for state in states)

    def cget(self, key: str):
        if key == "text":
            return f"{chr(0x2713) if self.selected else ' '} {self.text}"
        raise KeyError(key)

    def invoke(self) -> None:
        if self.disabled:
            return
        self.variable.set(self.value)
        if self.command:
            self.command()
        self.screen.refresh()

    def press(self, x: float, y: float) -> None:
        self.invoke()

    def release(self, x: float, y: float) -> None:
        pass

    def draw(self, screen: "ArtScreen", hover: bool) -> None:
        x0, y0, x1, y1 = self.box
        w, h, c = x1 - x0, y1 - y0, self.colors
        if self.style == "marker":
            if self.selected:
                for inset, color in ((0, "#ffffff"), (3, c["on"])):
                    screen.frame((x0 + inset, y0 + inset, x1 - inset, y1 - inset), color, 3)
                screen.sprite(x0 + 26, (y0 + y1) / 2, CHECK, 3.2, "#ffffff")
            elif hover and not self.disabled:
                screen.frame(self.box, c["on"], 2)
            return
        on = self.selected
        border = c["on"] if on else (c["hover"] if hover and not self.disabled else c["border"])
        screen.rect(x0 - 2, y0 - 2, w + 4, h + 4, c["back"])
        screen.rect(x0, y0, w, h, border)
        screen.rect(x0 + 3, y0 + 3, w - 6, h - 6, c["on"] if on else c["off"])
        for cx, cy in ((x0 + 5, y0 + 5), (x1 - 8, y0 + 5), (x0 + 5, y1 - 8), (x1 - 8, y1 - 8)):
            screen.rect(cx, cy, 3, 3, "#ffffff" if on else border)
        unit = c.get("unit", 2.0)
        ink = c["ink"] if on else "#ffffff"
        label = self.text.upper()
        text_w = (len(label) * 6 - 1) * unit + (11 * unit if on else 0)
        left = (x0 + x1) / 2 - text_w / 2
        if on:
            screen.sprite(left + 3.5 * unit, (y0 + y1) / 2, CHECK, unit, ink)
            left += 11 * unit
        screen.label(left, (y0 + y1) / 2 - 3.5 * unit, label, unit, ink, center=False)
        if self.disabled:
            screen.rect(x0, y0, w, h, "#000000", stipple="gray50")


class ArtSlider:
    """A segmented 0-100 slider drawn over the painted one."""

    def __init__(self, screen: "ArtScreen", box: Box, track: Box, color: str, value: int,
                 command: Callable[[int], None], step: int = 5, segments: int = 25,
                 on_release: Callable[[], None] | None = None, clear: Box | None = None):
        self.screen, self.box, self.track, self.color = screen, box, track, color
        # The area painted over first, so the artwork's own knob and fill disappear.
        self.clear = clear or (track[0] - 3, track[1] - 3, track[2] + 3, track[3] + 3)
        self.value, self.command, self.step, self.segments = value, command, step, segments
        self.on_release = on_release

    def get(self) -> int:
        return self.value

    def set(self, value: float) -> None:
        self.value = max(0, min(100, int(round(float(value) / self.step) * self.step)))
        self.command(self.value)
        self.screen.refresh()

    def _from_x(self, x: float) -> float:
        x0, _y0, x1, _y1 = self.track
        return (x - x0) / (x1 - x0) * 100

    def press(self, x: float, y: float) -> None:
        self.set(self._from_x(x))

    def drag(self, x: float, y: float) -> None:
        self.set(self._from_x(x))

    def release(self, x: float, y: float) -> None:
        if self.on_release:
            self.on_release()

    def draw(self, screen: "ArtScreen", hover: bool) -> None:
        cx0, cy0, cx1, cy1 = self.clear
        screen.rect(cx0, cy0, cx1 - cx0, cy1 - cy0, "#04112e")
        x0, y0, x1, y1 = self.track
        gap = 3
        width = (x1 - x0 - gap * (self.segments - 1)) / self.segments
        lit = round(self.value / 100 * self.segments)
        for index in range(self.segments):
            sx = x0 + index * (width + gap)
            screen.rect(sx, y0, width, y1 - y0, self.color if index < lit else "#0b2a5e")
            if index < lit:
                screen.rect(sx, y0, width, 3, "#ffffff")
        knob = x0 + (x1 - x0) * self.value / 100
        screen.rect(knob - 9, y0 - 7, 18, y1 - y0 + 14, "#ffffff")
        screen.rect(knob - 6, y0 - 4, 12, y1 - y0 + 8, self.color)
        if hover:
            screen.corners(self.box, self.color)


class ArtToggle:
    """A checkbox drawn over the painted one."""

    def __init__(self, screen: "ArtScreen", box: Box, variable: tk.BooleanVar, command: Callable[[], None]):
        self.screen, self.box, self.variable, self.command = screen, box, variable, command

    def invoke(self) -> None:
        self.variable.set(not self.variable.get())
        self.command()
        self.screen.refresh()

    def press(self, x: float, y: float) -> None:
        self.invoke()

    def release(self, x: float, y: float) -> None:
        pass

    def draw(self, screen: "ArtScreen", hover: bool) -> None:
        x0, y0, x1, y1 = self.box
        screen.rect(x0 - 2, y0 - 2, x1 - x0 + 4, y1 - y0 + 4, "#04112e")
        screen.frame(self.box, PALETTE["cyan"] if not hover else "#ffffff", 3)
        if self.variable.get():
            screen.sprite((x0 + x1) / 2, (y0 + y1) / 2, CHECK, 2.6, PALETTE["cyan"])


class ArtStatus:
    """A line of status text; answers configure(text=, fg=) like a Tk label."""

    def __init__(self, screen: "ArtScreen", left: float, right: float, y: float, text: str = "",
                 color: str = PALETTE["danger"], size: int = 13, backing: str | None = None):
        self.screen, self.left, self.right, self.y = screen, left, right, y
        self.text, self.color, self.size, self.backing = text, color, size, backing

    def configure(self, text: str | None = None, fg: str | None = None, **_options) -> None:
        if text is not None:
            self.text = text
        if fg is not None:
            self.color = fg
        self.screen.refresh()

    config = configure

    def cget(self, key: str):
        if key == "text":
            return self.text
        if key == "fg":
            return self.color
        raise KeyError(key)

    def draw(self, screen: "ArtScreen", hover: bool) -> None:
        if not self.text:
            return
        if self.backing:
            screen.rect(self.left, self.y - self.size * .8, self.right - self.left, self.size * 1.6, self.backing)
        screen.text((self.left + self.right) / 2, self.y, self.text, self.size, self.color, bold=True,
                    width=(self.right - self.left) * screen.scale, justify="center")


class ArtScreen(PixelCanvas):
    """Play one artwork and draw its live controls on top."""

    def __init__(self, master: tk.Misc, art_name: str, can_animate: Callable[[], bool] = lambda: True):
        super().__init__(master, bg="#01051e", takefocus=True)
        self._source = Image.open(ART_DIR / art_name)
        self.art_w, self.art_h = self._source.size
        self.frame_count = getattr(self._source, "n_frames", 1)
        self.frame_index = 0
        self._first = self._source.convert("RGB")
        self._frame = self._first
        self._photo: ImageTk.PhotoImage | None = None
        self._render_size = (0, 0)
        self._image_item = self.create_image(0, 0, anchor="nw")
        self.can_animate = can_animate
        self.controls: list = []
        self.drawers: list[Callable[["ArtScreen"], None]] = []
        self.entries: list[tuple[tk.Entry, Box, tkfont.Font, float]] = []
        self.default_action: Callable[[], None] | None = None
        self.hover = None
        self._active = None
        self._timer: str | None = None
        self._redraw_job: str | None = None
        self._deadline = 0.0
        self._disposed = False
        self.bind("<Configure>", lambda _event: self.refresh())
        self.bind("<Map>", self._start)
        self.bind("<Unmap>", self._stop)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _event: self._set_hover(None))
        self.bind("<ButtonPress-1>", self._mouse_down)
        self.bind("<B1-Motion>", self._mouse_drag)
        self.bind("<ButtonRelease-1>", self._mouse_up)
        self.bind("<Return>", self._return)
        self.bind("<KP_Enter>", self._return)

    # ---- artwork coordinates ----

    def layout(self) -> None:
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        self.scale = min(width / self.art_w, height / self.art_h)
        self.ox = (width - self.art_w * self.scale) / 2
        self.oy = (height - self.art_h * self.scale) / 2

    @property
    def art_box(self) -> tuple[int, int, int, int]:
        """Visible artwork rectangle in canvas pixels: left, top, width, height."""
        return (round(self.ox), round(self.oy), round(self.art_w * self.scale), round(self.art_h * self.scale))

    def to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + x * self.scale, self.oy + y * self.scale

    def sample(self, x: int, y: int) -> str:
        """The artwork's own colour at a point, to blend overlays into it."""
        r, g, b = self._first.getpixel((x, y))
        return f"#{r:02x}{g:02x}{b:02x}"

    # ---- registering controls ----

    def button(self, box: Box, command: Callable[[], None], color: str = PALETTE["cyan"]) -> ArtButton:
        control = ArtButton(self, box, command, color)
        self.controls.append(control)
        return control

    def choices(self, variable: tk.Variable, items, colors: dict[str, str],
                command: Callable[[], None] | None = None, style: str = "button") -> list[ArtChoice]:
        group = [ArtChoice(self, box, value, text, variable, colors, command, style) for value, text, box in items]
        self.controls.extend(group)
        trace = variable.trace_add("write", lambda *_args: self.refresh())
        self.bind("<Destroy>", lambda event: event.widget is self and variable.trace_remove("write", trace), add="+")
        return group

    def slider(self, box: Box, track: Box, color: str, value: int, command: Callable[[int], None],
               **options) -> ArtSlider:
        control = ArtSlider(self, box, track, color, value, command, **options)
        self.controls.append(control)
        return control

    def toggle(self, box: Box, variable: tk.BooleanVar, command: Callable[[], None]) -> ArtToggle:
        control = ArtToggle(self, box, variable, command)
        self.controls.append(control)
        return control

    def status(self, left: float, right: float, y: float, text: str = "", **options) -> ArtStatus:
        control = ArtStatus(self, left, right, y, text, **options)
        self.controls.append(control)
        return control

    def patch(self, box: Box, color: str) -> None:
        """Paint over part of the artwork that a live control replaces."""
        self.drawers.append(lambda screen: screen.rect(box[0], box[1], box[2] - box[0], box[3] - box[1], color))

    def entry(self, box: Box, size: float = 16, bg: str | None = None) -> tk.Entry:
        font = tkfont.Font(root=self, family="Courier", size=-16, weight="bold")
        field = tk.Entry(self, font=font, bg=bg or self.sample(int(box[0]) + 4, int(box[3]) - 4),
                         fg=PALETTE["text"], insertbackground=PALETTE["cyan"], relief="flat", bd=0,
                         highlightthickness=0, disabledbackground="#20283d", disabledforeground=PALETTE["muted"])
        self.entries.append((field, box, font, size))
        self.refresh()
        return field

    # ---- drawing ----

    def refresh(self) -> None:
        if self._redraw_job is None and not self._disposed:
            self._redraw_job = self.after_idle(self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        if self._disposed:
            return
        self.layout()
        self._paint_frame()
        self.addtag_all("overlay")
        self.dtag(self._image_item, "overlay")
        self.delete("overlay")
        for draw in self.drawers:
            draw(self)
        for control in self.controls:
            control.draw(self, control is self.hover)
        for field, (x0, y0, x1, y1), font, size in self.entries:
            font.configure(size=-max(8, round(size * self.scale)))
            left, top = self.to_canvas(x0, y0)
            field.place(x=left, y=top, width=(x1 - x0) * self.scale, height=(y1 - y0) * self.scale)

    def _paint_frame(self) -> None:
        size = (max(1, round(self.art_w * self.scale)), max(1, round(self.art_h * self.scale)))
        frame = self._frame if size == (self.art_w, self.art_h) else self._frame.resize(size, Image.Resampling.NEAREST)
        if self._photo is None or size != self._render_size:
            self._photo = ImageTk.PhotoImage(frame, master=self)
            self.itemconfigure(self._image_item, image=self._photo)
            self._render_size = size
        else:
            self._photo.paste(frame)
        self.coords(self._image_item, round(self.ox), round(self.oy))

    def frame(self, box: Box, color: str, width: float) -> None:
        x0, y0, x1, y1 = box
        self.rect(x0, y0, x1 - x0, width, color)
        self.rect(x0, y1 - width, x1 - x0, width, color)
        self.rect(x0, y0, width, y1 - y0, color)
        self.rect(x1 - width, y0, width, y1 - y0, color)

    def corners(self, box: Box, color: str) -> None:
        """Hover / focus marker, matching the opening screen."""
        x0, y0, x1, y1 = box
        for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            self.rect(min(x, x + dx * 14), y - (3 if dy > 0 else 0), 14, 3, color)
            self.rect(x - (3 if dx > 0 else 0), min(y, y + dy * 14), 3, 14, color)

    def sprite(self, x: float, y: float, rows: str, unit: float, color: str) -> None:
        lines = rows.split("/")
        self._bits(x - len(lines[0]) * unit / 2, y - len(lines) * unit / 2, lines, unit, color)

    # ---- animation ----

    def _start(self, _event=None) -> None:
        self.refresh()
        if self._disposed or self._timer is not None or self.frame_count < 2:
            return
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
        if not self.can_animate():
            self._deadline = time.monotonic()
            self._timer = self.after(100, self._advance)
            return
        self.frame_index = (self.frame_index + 1) % self.frame_count
        self._source.seek(self.frame_index)
        self._frame = self._source.convert("RGB")
        self._paint_frame()
        delay = max(20, int(self._source.info.get("duration", 50)))
        self._deadline += delay / 1000
        now = time.monotonic()
        if self._deadline < now:
            self._deadline = now + delay / 1000
        self._timer = self.after(max(1, round((self._deadline - now) * 1000)), self._advance)

    # ---- input ----

    def _art_point(self, event) -> tuple[float, float]:
        return (event.x - self.ox) / self.scale, (event.y - self.oy) / self.scale

    def control_at(self, x: float, y: float):
        for control in reversed(self.controls):
            box = getattr(control, "box", None)
            if box is not None and inside(box, x, y):
                return control
        return None

    def _set_hover(self, control) -> None:
        if control is not self.hover:
            self.hover = control
            self.configure(cursor="hand2" if control is not None else "")
            self.refresh()

    def _motion(self, event) -> None:
        self._set_hover(self.control_at(*self._art_point(event)))

    def _mouse_down(self, event) -> str:
        self.focus_set()
        x, y = self._art_point(event)
        self._active = self.control_at(x, y)
        if self._active is not None:
            self._active.press(x, y)
        return "break"

    def _mouse_drag(self, event) -> None:
        if self._active is not None and hasattr(self._active, "drag"):
            self._active.drag(*self._art_point(event))

    def _mouse_up(self, event) -> str:
        control, self._active = self._active, None
        if control is not None:
            control.release(*self._art_point(event))
        return "break"

    def _return(self, _event=None) -> str:
        if self.default_action is not None:
            self.default_action()
        return "break"

    def destroy(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._stop()
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        self._source.close()
        super().destroy()
        self._photo = None

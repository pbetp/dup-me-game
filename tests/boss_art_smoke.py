"""Verify the actual boss piano remains visible: python -m tests.boss_art_smoke."""
import tkinter as tk

from PIL import ImageTk

from src.client.boss_ui import BossBoard, BossState, KEY_LEFT, KEY_TOP, KEY_W
from tests.gui_smoke import drain


def assert_visible_piano(board):
    """Check displayed pixels and layers, including disabled LISTEN states."""
    image = ImageTk.getimage(board._photo).convert('RGB')
    samples = []
    for index in range(10):
        x = KEY_LEFT + (index + .5) * KEY_W
        y = KEY_TOP + 145
        # The scaled image contains a light white key at each of these positions.
        rgb = image.getpixel((round(x * board.scale), round(y * board.scale)))
        assert min(rgb) > 195, ('Piano artwork lost its visible white keys', index, rgb)
        samples.append((board.ox + x * board.scale, board.oy + y * board.scale))
    # A photo can be correct while an opaque Canvas item hides it. Reject a dark
    # rectangle covering every key, even if a stipple is requested: native macOS
    # Tk can paint stipples as solid black.
    for item in board.find_all():
        if board.type(item) != 'rectangle':
            continue
        fill = board.itemcget(item, 'fill')
        if not fill or max(board.winfo_rgb(fill)) > 12000:
            continue
        x0, y0, x1, y1 = board.coords(item)
        assert not all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in samples), \
            'A dark canvas overlay covers the entire boss piano'


def run():
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args))
    state = BossState(me='p1', players=[
        {'id': 'p1', 'nickname': 'joji', 'hp': 8, 'max_hp': 8},
        {'id': 'p2', 'nickname': 'jojo', 'hp': 8, 'max_hp': 8},
    ], lengths={'p1': 3, 'p2': 3})
    played = []
    board = BossBoard(root, state, {'note': played.append})
    board.pack(fill='both', expand=True)
    try:
        for geometry in ('960x700', '1280x800', '1600x900'):
            root.geometry(geometry)
            for phase in ('wait', 'show', 'repeat', 'result'):
                state.phase, state.sent = phase, 0
                board.redraw()
                drain(root, .08)
                assert_visible_piano(board)
                regions = [row for row in board.regions if row[0].startswith('note-')]
                assert len(regions) == (17 if phase == 'repeat' else 0), (phase, len(regions))
                x = board.ox + (KEY_LEFT + KEY_W / 2) * board.scale
                y = board.oy + (KEY_TOP + 145) * board.scale
                before = len(played)
                board.event_generate('<Button-1>', x=round(x), y=round(y))
                drain(root, .02)
                assert len(played) == before + (1 if phase == 'repeat' else 0)
            state.phase = 'show'
            board.flash('c4', force=True)
            drain(root, .02)
            assert board.find_withtag('flash'), 'Listening note flash disappeared'
            assert_visible_piano(board)
        assert not errors, errors
    finally:
        root.destroy()
    print('PASS: boss piano remains visibly white in wait/listen/play/result at three sizes; '
          'no opaque disabled overlay; listening flashes visible; input disabled outside play; '
          '17 playable notes; zero Tk callback errors.')


if __name__ == '__main__':
    run()

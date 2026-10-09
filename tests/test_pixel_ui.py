"""Presentation and input regressions; no display server required."""

import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.client_ui import ClientWindow
from src.client.pixel_ui import BoardState, GameBoard
from src.client.sound import NotePlayer
from src.common import message_types as mt
from src.common.config import (BLACK_KEYS, COLOR_NAMES, INSTRUMENTS, KEY_TO_COLOR,
                               NOTE_FREQUENCIES, PIANO_KEYS, WHITE_KEYS)
from src.common.validation import validate_color


class PixelStateTests(unittest.TestCase):
    def test_pattern_disappears_when_repetition_begins(self):
        state = BoardState()
        state.begin({"phase": "create", "role": "creator"})
        state.add_note("c4")
        state.add_note("d4")
        state.begin({"phase": "repeat", "role": "repeater", "pattern_length": 2})
        self.assertEqual(state.pattern, [])
        self.assertEqual(state.counter, "00 / 02 ANSWERS")
        self.assertTrue(state.enabled)
        self.assertFalse(state.add_note("c4"))

    def test_only_the_active_role_gets_controls(self):
        state = BoardState()
        for phase, role, enabled in [("create", "creator", True), ("create", "repeater", False),
                                     ("repeat", "creator", False), ("repeat", "repeater", True)]:
            with self.subTest(phase=phase, role=role):
                state.begin({"phase": phase, "role": role})
                self.assertEqual(state.enabled, enabled)

    def test_pattern_limit_and_invalid_color(self):
        state = BoardState()
        self.assertFalse(state.add_note("not-a-color"))
        for _ in range(20):
            self.assertTrue(state.add_note("c4"))
        self.assertFalse(state.add_note("d4"))
        self.assertEqual(state.counter, "20 / 20 NOTES")

    def test_new_round_clears_feedback_and_result(self):
        state = BoardState(complete=True, feedback=[True, False], status="old")
        state.begin({"round": 2, "phase": "create", "role": "repeater", "duration": 10})
        self.assertEqual(state.feedback, [])
        self.assertEqual(state.status, "")
        self.assertFalse(state.complete)
        self.assertEqual(state.remaining, 10)


class PixelInputTests(unittest.TestCase):
    def setUp(self):
        self.app = ClientWindow.__new__(ClientWindow)
        self.app.input_enabled = True
        self.app.preview_mode = False
        self.app.phase = "create"
        self.app.turn_id = "test-turn"
        self.app.state = BoardState()
        self.app.network = Mock()
        self.app.network.send.return_value = True
        self.app.audio = Mock()
        self.app.board = Mock()
        self.app.flashes = True
        self.app._sent_steps = 0

    def test_send_limit_does_not_depend_on_network_latency(self):
        for _ in range(25):
            self.app.press_color("c4")
        self.assertEqual(self.app.network.send.call_count, 20)
        self.app.network.send.assert_called_with({"type": mt.PATTERN_STEP, "color": "c4", "turn_id": "test-turn"})

    def test_waiting_player_cannot_send(self):
        self.app.input_enabled = False
        self.app.press_color("c4")
        self.app.network.send.assert_not_called()

    def test_repeat_uses_correct_message_and_answer_limit(self):
        self.app.phase = "repeat"
        self.app.state.pattern_length = 2
        for _ in range(3):
            self.app.press_color("d4")
        self.assertEqual(self.app.network.send.call_count, 2)
        self.app.network.send.assert_called_with({"type": mt.REPEAT_STEP, "color": "d4", "turn_id": "test-turn"})

    def test_unsent_note_does_not_use_capacity(self):
        self.app.network.send.return_value = False
        self.app.press_color("c4")
        self.assertEqual(self.app._sent_steps, 0)

    def test_preview_is_offline_and_allows_undo(self):
        self.app.preview_mode = True
        self.app.press_color("e4")
        self.assertEqual(self.app.state.pattern, ["e4"])
        self.app.network.send.assert_not_called()
        self.app.preview_undo()
        self.assertEqual(self.app.state.pattern, [])

    def test_hold_key_and_settings_do_not_submit_extra_notes(self):
        self.app.root = Mock()
        self.app.dialog = None
        self.app._release_jobs = {}
        self.app._pressed = set()
        widget = Mock()
        widget.winfo_toplevel.return_value = self.app.root
        event = SimpleNamespace(widget=widget, keysym="z", state=0)
        self.app._key_press(event)
        self.app._key_press(event)
        self.assertEqual(self.app.network.send.call_count, 1)
        self.app._pressed.clear()
        self.app.dialog = Mock()
        self.app._key_press(event)
        self.assertEqual(self.app.network.send.call_count, 1)


class ExpandedPianoTests(unittest.TestCase):
    def test_reference_layout_and_chromatic_pitches(self):
        self.assertEqual([n[1] for n in WHITE_KEYS], list("zxcvbnm,./"))
        self.assertEqual([n[1] for n in BLACK_KEYS], list("sdghjl;"))
        self.assertEqual(len(set(KEY_TO_COLOR.values())), 17)
        self.assertEqual([n[2] for n in PIANO_KEYS], list(range(60, 77)))
        self.assertEqual(NOTE_FREQUENCIES["a4"], 440)
        for note in COLOR_NAMES:
            self.assertTrue(validate_color(note))
        for invalid in ("red", "a", "c6", None, 60):
            self.assertFalse(validate_color(invalid))

    def test_every_physical_key_including_punctuation(self):
        app = ClientWindow.__new__(ClientWindow)
        app.root, app.press_color = Mock(), Mock()
        app.dialog, app._release_jobs, app._pressed = None, {}, set()
        widget = Mock()
        widget.winfo_toplevel.return_value = app.root
        punctuation = {",": "comma", ".": "period", "/": "slash", ";": "semicolon"}
        for key, note in KEY_TO_COLOR.items():
            app._key_press(SimpleNamespace(widget=widget, keysym=punctuation.get(key, key), state=0))
            app.press_color.assert_called_with(note)
        self.assertEqual(app.press_color.call_count, 17)
        app._key_press(SimpleNamespace(widget=widget, keysym="a", state=0))
        self.assertEqual(app.press_color.call_count, 17)

    def test_black_keys_win_overlapping_mouse_hits(self):
        board = GameBoard.__new__(GameBoard)
        board.state, board.actions = BoardState(enabled=True), {"note": Mock()}
        board.scale, board.ox, board.oy = 1, 0, 0
        board.hover, board.active_note, board.regions = "", None, []
        for name in ("panel", "rect", "text", "pixels"):
            setattr(board, name, Mock())
        board._keyboard()
        self.assertEqual(len(board.regions), 17)
        for note, _key, _midi, _accent, index, black in PIANO_KEYS:
            x = 180 + (index + 1) * 108 if black else 180 + index * 108 + 52
            name, callback = board._hit(SimpleNamespace(x=x, y=520 if black else 650))
            self.assertEqual(name, f"note-{note}")
            callback()
            board.actions["note"].assert_called_with(note)

    def test_turn_follows_phase_and_role_even_when_input_locks(self):
        state = BoardState()
        state.begin({"phase": "create", "role": "creator"})
        self.assertTrue(state.my_turn)
        state.enabled = False  # notes or time ran out: still this player's turn
        self.assertTrue(state.my_turn)
        state.begin({"phase": "create", "role": "repeater"})
        self.assertFalse(state.my_turn)
        self.assertTrue(state.blind)
        state.begin({"phase": "repeat", "role": "repeater", "pattern_length": 3})
        self.assertTrue(state.my_turn)
        state.complete = True
        self.assertFalse(state.my_turn)

    def test_server_round_count_updates_board(self):
        state = BoardState()
        state.begin({"round": 7, "total_rounds": 12, "phase": "repeat", "role": "repeater"})
        self.assertEqual((state.round_number, state.total_rounds), (7, 12))


class NoteAudioTests(unittest.TestCase):
    def test_notes_are_valid_cached_wavs_and_cleanup(self):
        player = NotePlayer()
        try:
            path = player._note_file("c4")
            self.assertEqual(path, player._note_file("c4"))
            with wave.open(str(path), "rb") as note:
                self.assertEqual(note.getnchannels(), 1)
                self.assertEqual(note.getsampwidth(), 2)
                self.assertEqual(note.getframerate(), 22050)
                self.assertGreater(note.getnframes(), 0)
            player.volume = 20
            self.assertNotEqual(path, player._note_file("c4"))
        finally:
            player.close()
        self.assertFalse(path.exists())

    def test_all_instruments_have_distinct_valid_notes_and_separate_caches(self):
        player = NotePlayer()
        try:
            sounds = set()
            for instrument in INSTRUMENTS:
                player.instrument = instrument
                for note in COLOR_NAMES:
                    path = player._note_file(note)
                    with wave.open(str(path), "rb") as audio:
                        data = audio.readframes(audio.getnframes())
                        self.assertGreater(len(data), 2000)
                        self.assertNotEqual(data, bytes(len(data)))
                    if note == "c4":
                        sounds.add(data)
            self.assertEqual(len(sounds), 4)
            with self.assertRaises(ValueError):
                player.instrument = "unknown"
        finally:
            player.close()


if __name__ == "__main__":
    unittest.main()

"""Room-browser interaction regressions that require no Tk window or network."""

import unittest

from src.client.lobby_screen import LobbyServerList


class StubScreen:
    def __init__(self):
        self.refreshes = 0

    def refresh(self):
        self.refreshes += 1


def room(name, port, players=1):
    return {"name": name, "host": "127.0.0.1", "port": port, "players": players}


class LobbyRoomBrowserTests(unittest.TestCase):
    def setUp(self):
        self.screen = StubScreen()
        self.selected_events = []
        self.joined = []
        self.browser = LobbyServerList(
            self.screen, (520, 345, 1180, 425),
            on_select=lambda: self.selected_events.append(self.browser.curselection()),
            on_join=lambda: self.joined.append(self.browser.get(self.browser.selected)),
        )

    def test_blank_area_below_visible_room_does_not_select_hidden_room(self):
        self.browser.set_rooms([room("Visible room", 55000), room("Hidden room", 55001)])
        self.assertEqual(self.browser.curselection(), (0,))
        initial_events = len(self.selected_events)
        for y in (405, 415, 425):
            with self.subTest(y=y):
                self.browser.press(800, y)
                self.assertEqual(self.browser.curselection(), (0,))
                self.assertEqual(self.browser.get(self.browser.selected), "Visible room")
                self.assertEqual(self.browser.offset, 0)
                self.assertEqual(len(self.selected_events), initial_events)

    def test_gap_under_room_does_not_restore_a_cleared_selection(self):
        self.browser.set_rooms([room("Room A", 55000), room("Room B", 55001)])
        self.browser.selection_clear()
        initial_events = len(self.selected_events)
        for y in (402, 403, 404):
            with self.subTest(y=y):
                self.browser.press(800, y)
                self.assertEqual(self.browser.curselection(), ())
                self.assertEqual(len(self.selected_events), initial_events)
        self.browser.invoke()
        self.assertEqual(self.joined, [])

    def test_click_in_a_rendered_room_selects_that_room(self):
        self.browser.set_rooms([room("Room A", 55000), room("Room B", 55001)])
        self.browser.selection_clear()
        self.browser.press(800, 370)
        self.assertEqual(self.browser.curselection(), (0,))
        self.browser.invoke()
        self.assertEqual(self.joined, ["Room A"])
        self.browser.move(1)
        self.browser.selection_clear()
        self.browser.press(800, 370)
        self.assertEqual(self.browser.curselection(), (1,))
        self.browser.invoke()
        self.assertEqual(self.joined, ["Room A", "Room B"])

    def test_refresh_preserves_the_selected_endpoint_when_rooms_reorder(self):
        a, b, c = room("Room A", 55000), room("Room B", 55001), room("Room C", 55002)
        self.browser.set_rooms([a, b, c])
        self.browser.selection_set(1)
        updated_b = dict(b, name="Room B renamed", total_rounds=12)
        self.browser.set_rooms([c, a, updated_b])
        self.assertEqual(self.browser.curselection(), (2,))
        self.assertEqual(self.browser.get(2), "Room B renamed")
        self.browser.invoke()
        self.assertEqual(self.joined, ["Room B renamed"])

    def test_full_only_rooms_have_no_default_selection_or_join_action(self):
        self.browser.set_rooms([room("Full room A", 55000, 2), room("Full room B", 55001, 2)])
        self.assertEqual(self.browser.size(), 2)
        self.assertEqual(self.browser.curselection(), ())
        self.browser.invoke()
        self.assertEqual(self.joined, [])

    def test_refresh_replaces_a_selection_that_is_now_full(self):
        a, b = room("Room A", 55000), room("Room B", 55001)
        self.browser.set_rooms([a, b])
        self.browser.selection_set(1)
        self.browser.set_rooms([a, dict(b, players=2)])
        self.assertEqual(self.browser.curselection(), (0,))
        self.browser.invoke()
        self.assertEqual(self.joined, ["Room A"])

    def test_disabled_browser_ignores_mouse_keyboard_and_join(self):
        self.browser.set_rooms([room("Room A", 55000), room("Room B", 55001)])
        self.browser.selection_clear()
        self.browser.configure(state="disabled")
        self.browser.press(800, 370)
        self.browser.move(1)
        self.browser.invoke()
        self.assertEqual(self.browser.curselection(), ())
        self.assertEqual(self.joined, [])


if __name__ == "__main__":
    unittest.main()


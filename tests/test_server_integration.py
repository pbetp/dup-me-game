import socket
import time
import unittest

from src.common import message_types as mt
from src.common.config import APP_VERSION, COLOR_NAMES
from src.common.protocol import receive_message, send_message
from src.server import server as server_module
from src.server.server import DupMeServer


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.original_create = server_module.CREATE_SECONDS
        server_module.CREATE_SECONDS = .5
        self.original_pause = server_module.PHASE_RESULT_SECONDS
        server_module.PHASE_RESULT_SECONDS = 0.05
        self.server = DupMeServer(host="127.0.0.1", port=0)
        self.server.start()
        self.sockets: list[socket.socket] = []

    def tearDown(self):
        for sock in self.sockets:
            try:
                sock.close()
            except OSError:
                pass
        self.server.stop()
        server_module.PHASE_RESULT_SECONDS = self.original_pause
        server_module.CREATE_SECONDS = self.original_create

    def connect(self, nickname: str) -> socket.socket:
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        sock.settimeout(3)
        self.sockets.append(sock)
        send_message(sock, {"type": mt.JOIN, "nickname": nickname, "version": APP_VERSION})
        return sock

    @staticmethod
    def wait_for(sock: socket.socket, message_type: str, phase: str | None = None) -> dict:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            message = receive_message(sock)
            if message.get("type") == message_type and (
                phase is None or message.get("phase") == phase
            ):
                return message
        raise AssertionError(f"Did not receive {message_type}")

    def play_creation(self, sockets_by_id: dict[str, socket.socket], starts: list[dict]) -> list[str]:
        creator_id = starts[0]["creator_id"]
        pattern = ["c4", "d4"] * 10
        for color in pattern:
            send_message(sockets_by_id[creator_id], {"type": mt.PATTERN_STEP, "color": color, "turn_id": starts[0]["turn_id"]})
        return pattern

    def test_two_round_match_and_winner_starts_rematch(self):
        alice = self.connect("Alice")
        alice_welcome = self.wait_for(alice, mt.WELCOME)
        bob = self.connect("Bob")
        bob_welcome = self.wait_for(bob, mt.WELCOME)
        sockets_by_id = {
            alice_welcome["player_id"]: alice,
            bob_welcome["player_id"]: bob,
        }

        round1_starts = [
            self.wait_for(alice, mt.ROUND_START, "create"),
            self.wait_for(bob, mt.ROUND_START, "create"),
        ]
        pattern = self.play_creation(sockets_by_id, round1_starts)
        repeat1 = [
            self.wait_for(alice, mt.ROUND_START, "repeat"),
            self.wait_for(bob, mt.ROUND_START, "repeat"),
        ]
        first_repeater = repeat1[0]["repeater_id"]
        for color in pattern:
            send_message(sockets_by_id[first_repeater], {"type": mt.REPEAT_STEP, "color": color, "turn_id": repeat1[0]["turn_id"]})
        self.wait_for(alice, mt.ROUND_RESULT)
        self.wait_for(bob, mt.ROUND_RESULT)

        round2_starts = [
            self.wait_for(alice, mt.ROUND_START, "create"),
            self.wait_for(bob, mt.ROUND_START, "create"),
        ]
        self.play_creation(sockets_by_id, round2_starts)
        repeat2 = [
            self.wait_for(alice, mt.ROUND_START, "repeat"),
            self.wait_for(bob, mt.ROUND_START, "repeat"),
        ]
        second_repeater = repeat2[0]["repeater_id"]
        for _ in pattern:
            send_message(sockets_by_id[second_repeater], {"type": mt.REPEAT_STEP, "color": "e4", "turn_id": repeat2[0]["turn_id"]})
        self.wait_for(alice, mt.ROUND_RESULT)
        self.wait_for(bob, mt.ROUND_RESULT)
        alice_result = self.wait_for(alice, mt.MATCH_RESULT)
        bob_result = self.wait_for(bob, mt.MATCH_RESULT)

        winner_id = alice_result["winner_id"]
        self.assertEqual(winner_id, first_repeater)
        self.assertEqual({alice_result["result"], bob_result["result"]}, {"win", "loss"})

        send_message(alice, {"type": mt.REMATCH_VOTE})
        send_message(bob, {"type": mt.REMATCH_VOTE})
        rematch = self.wait_for(alice, mt.MATCH_START)
        self.assertEqual(rematch["first_creator_id"], winner_id)

    def test_twelve_round_match_all_notes_and_rematch_keep_selected_total(self):
        self.server.stop()
        self.server = DupMeServer(host="127.0.0.1", port=0, total_rounds=12)
        self.server.start()
        alice = self.connect("Alice")
        welcome_a = self.wait_for(alice, mt.WELCOME)
        bob = self.connect("Bob")
        welcome_b = self.wait_for(bob, mt.WELCOME)
        self.assertEqual(welcome_a["total_rounds"], 12)
        self.assertEqual(welcome_b["total_rounds"], 12)
        sockets = {welcome_a["player_id"]: alice, welcome_b["player_id"]: bob}
        previous_creator = None
        pattern = list(COLOR_NAMES) + list(COLOR_NAMES[:3])
        for number in range(1, 13):
            starts = [self.wait_for(sock, mt.ROUND_START, "create") for sock in (alice, bob)]
            for event in starts:
                self.assertEqual((event["round"], event["total_rounds"]), (number, 12))
            creator = starts[0]["creator_id"]
            self.assertNotEqual(creator, previous_creator)
            previous_creator = creator
            for note in pattern:
                send_message(sockets[creator], {"type": mt.PATTERN_STEP, "color": note, "turn_id": starts[0]["turn_id"]})
            repeats = [self.wait_for(sock, mt.ROUND_START, "repeat") for sock in (alice, bob)]
            for note in pattern:
                send_message(sockets[repeats[0]["repeater_id"]], {"type": mt.REPEAT_STEP, "color": note, "turn_id": repeats[0]["turn_id"]})
            for sock in (alice, bob):
                result = self.wait_for(sock, mt.ROUND_RESULT)
                self.assertEqual(result["pattern"], pattern)
                self.assertEqual(result["points"], 20)
        for sock in (alice, bob):
            result = self.wait_for(sock, mt.MATCH_RESULT)
            self.assertEqual(result["result"], "draw")
            self.assertEqual([row["score"] for row in result["scores"]], [120, 120])
            send_message(sock, {"type": mt.REMATCH_VOTE})
        for sock in (alice, bob):
            self.assertEqual(self.wait_for(sock, mt.MATCH_START)["total_rounds"], 12)
            start = self.wait_for(sock, mt.ROUND_START, "create")
            self.assertEqual((start["round"], start["total_rounds"]), (1, 12))


if __name__ == "__main__":
    unittest.main()

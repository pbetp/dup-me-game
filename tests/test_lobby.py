"""Real TCP checks for the launcher's explicit multiplayer waiting-room flow."""

import socket
import time
import unittest

from src.common import message_types as mt
from src.common.config import APP_VERSION
from src.common.networking import check_connection
from src.common.protocol import receive_message, send_message
from src.server.boss_server import BossFightServer
from src.server.game_engine import WAITING_FOR_PLAYERS
from src.server.server import DupMeServer


class ManualLobbyTests(unittest.TestCase):
    def setUp(self):
        self.server = DupMeServer(host="127.0.0.1", port=0, manual_lobby=True)
        self.server.start()
        self.sockets = []

    def tearDown(self):
        for sock in self.sockets:
            sock.close()
        self.server.stop()

    def connect(self, nickname):
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        sock.settimeout(3)
        self.sockets.append(sock)
        send_message(sock, {"type": mt.JOIN, "nickname": nickname, "version": APP_VERSION})
        welcome = self.wait_for(sock, mt.WELCOME)
        return sock, welcome

    @staticmethod
    def wait_for(sock, message_type, predicate=lambda _message: True):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            message = receive_message(sock)
            if message.get("type") == message_type and predicate(message):
                return message
        raise AssertionError(f"Did not receive {message_type}")

    def pair(self):
        host, host_welcome = self.connect("Host")
        client, client_welcome = self.connect("Friend")
        players = self.wait_for(host, mt.PLAYER_LIST, lambda event: len(event["players"]) == 2)
        return host, client, host_welcome, client_welcome, players

    def ready(self, sock, value=True):
        send_message(sock, {"type": mt.LOBBY_READY, "ready": value})
        return self.wait_for(sock, mt.PLAYER_LIST,
                             lambda event: any(not row["is_host"] and row["ready"] is value
                                               for row in event["players"]))

    def test_two_players_wait_for_ready_and_host_start(self):
        host, client, hw, cw, event = self.pair()
        self.assertTrue(hw["manual_lobby"] and cw["manual_lobby"])
        self.assertEqual(hw["host_player_id"], hw["player_id"])
        self.assertEqual(cw["host_player_id"], hw["player_id"])
        players = {row["id"]: row for row in event["players"]}
        self.assertTrue(players[hw["player_id"]]["ready"])
        self.assertTrue(players[hw["player_id"]]["is_host"])
        self.assertFalse(players[cw["player_id"]]["ready"])
        self.assertFalse(players[cw["player_id"]]["is_host"])
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)
        self.ready(client)
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)
        self.assertIsNone(self.server.pending_transition)
        send_message(host, {"type": mt.LOBBY_START})
        for sock in (host, client):
            self.wait_for(sock, mt.MATCH_START)
            self.wait_for(sock, mt.ROUND_START)
        self.assertEqual(set(self.server.game.players), {hw["player_id"], cw["player_id"]})

    def test_client_cannot_start_even_when_ready(self):
        host, client, _hw, _cw, _event = self.pair()
        self.ready(client)
        send_message(client, {"type": mt.LOBBY_START})
        self.assertIn("Only the host", self.wait_for(client, mt.ERROR)["message"])
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)

    def test_host_cannot_start_before_client_ready(self):
        host, _client, _hw, _cw, _event = self.pair()
        send_message(host, {"type": mt.LOBBY_START})
        self.assertIn("mark themselves ready", self.wait_for(host, mt.ERROR)["message"])
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)

    def test_host_cannot_start_alone(self):
        host, _welcome = self.connect("Host")
        send_message(host, {"type": mt.LOBBY_START})
        self.assertIn("join", self.wait_for(host, mt.ERROR)["message"])
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)

    def test_client_can_cancel_readiness(self):
        host, client, _hw, _cw, _event = self.pair()
        self.ready(client)
        self.ready(client, False)
        send_message(host, {"type": mt.LOBBY_START})
        self.assertIn("mark themselves ready", self.wait_for(host, mt.ERROR)["message"])
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)

    def test_ready_requires_boolean_and_host_readiness_is_implicit(self):
        host, client, hw, cw, _event = self.pair()
        for value in (1, "true", None):
            send_message(client, {"type": mt.LOBBY_READY, "ready": value})
            self.assertIn("true or false", self.wait_for(client, mt.ERROR)["message"])
        send_message(host, {"type": mt.LOBBY_READY, "ready": False})
        self.assertIn("already ready", self.wait_for(host, mt.ERROR)["message"])
        self.assertIn(hw["player_id"], self.server._ready_player_ids)
        self.assertNotIn(cw["player_id"], self.server._ready_player_ids)

    def test_reset_returns_to_waiting_and_clears_client_readiness(self):
        host, client, hw, cw, _event = self.pair()
        self.ready(client)
        send_message(host, {"type": mt.LOBBY_START})
        self.wait_for(host, mt.ROUND_START)
        self.server.reset_game()
        self.wait_for(host, mt.GAME_RESET)
        players = self.wait_for(host, mt.PLAYER_LIST)
        self.assertFalse(next(row for row in players["players"] if row["id"] == cw["player_id"])["ready"])
        self.assertEqual(self.server._ready_player_ids, {hw["player_id"]})
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)
        self.assertIsNone(self.server.pending_transition)

    def test_disconnected_client_must_ready_again_after_rejoining(self):
        host, client, hw, _cw, _event = self.pair()
        self.ready(client)
        client.close()
        self.wait_for(host, mt.PLAYER_LIST, lambda event: len(event["players"]) == 1)
        replacement, rw = self.connect("Friend")
        players = self.wait_for(host, mt.PLAYER_LIST, lambda event: len(event["players"]) == 2)
        self.assertFalse(next(row for row in players["players"] if row["id"] == rw["player_id"])["ready"])
        self.assertEqual(self.server._ready_player_ids, {hw["player_id"]})
        send_message(host, {"type": mt.LOBBY_START})
        self.assertIn("mark themselves ready", self.wait_for(host, mt.ERROR)["message"])

    def test_connection_probe_does_not_clear_a_ready_client(self):
        host, client, _hw, cw, _event = self.pair()
        self.ready(client)
        check_connection("127.0.0.1", self.server.port)
        deadline = time.monotonic() + 2
        while len(self.server.sessions) > 2 and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(len(self.server.sessions), 2)
        # A connection-file probe is not a player leaving the waiting room.
        send_message(host, {"type": mt.PING})
        while True:
            event = receive_message(host)
            self.assertNotEqual(event["type"], mt.PLAYER_LEFT)
            if event["type"] == mt.PONG:
                break
        send_message(host, {"type": mt.LOBBY_START})
        self.wait_for(host, mt.MATCH_START)
        self.assertIn(cw["player_id"], self.server._ready_player_ids)

    def test_manual_room_rejects_a_third_player(self):
        _host, _client, _hw, _cw, _event = self.pair()
        extra = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        extra.settimeout(3)
        self.sockets.append(extra)
        send_message(extra, {"type": mt.JOIN, "nickname": "Third", "version": APP_VERSION})
        self.assertIn("room is full", self.wait_for(extra, mt.ERROR)["message"])
        self.assertEqual(len(self.server.snapshot()["players"]), 2)

    def test_readiness_cannot_change_during_a_match(self):
        host, client, _hw, cw, _event = self.pair()
        self.ready(client)
        send_message(host, {"type": mt.LOBBY_START})
        self.wait_for(client, mt.ROUND_START)
        send_message(client, {"type": mt.LOBBY_READY, "ready": False})
        self.assertIn("waiting room", self.wait_for(client, mt.ERROR)["message"])
        self.assertIn(cw["player_id"], self.server._ready_player_ids)

    def test_boss_room_obeys_the_same_ready_and_host_start_contract(self):
        self.server.stop()
        self.server = BossFightServer(host="127.0.0.1", port=0, manual_lobby=True)
        self.server.start()
        host, client, _hw, _cw, _event = self.pair()
        self.ready(client)
        self.assertEqual(self.server.game.state, WAITING_FOR_PLAYERS)
        send_message(client, {"type": mt.LOBBY_START})
        self.assertIn("Only the host", self.wait_for(client, mt.ERROR)["message"])
        send_message(host, {"type": mt.LOBBY_START})
        event = self.wait_for(host, mt.MATCH_START)
        self.assertEqual(event["mode"], "boss")
        self.wait_for(client, mt.BOSS_PHRASE)


if __name__ == "__main__":
    unittest.main()


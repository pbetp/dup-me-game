import random
import socket
import time
import unittest

from src.common import message_types as mt
from src.common.config import APP_VERSION, BOSS_MAX_HP, PLAYER_MAX_HP
from src.common.protocol import receive_message, send_message
from src.server import boss_server as boss_module
from src.server.boss_engine import BossEngine, make_phrase, phrase_length


class BossEngineTests(unittest.TestCase):
    def setUp(self):
        self.game = BossEngine(rng=random.Random(4))
        self.game.begin_match(["a", "b"])
        self.game.begin_repeat()

    def test_phrases_grow_and_step_without_repeats(self):
        self.assertEqual([phrase_length(n) for n in range(1, 8)], [4, 5, 6, 7, 8, 8, 8])
        phrase = make_phrase(8, random.Random(1))
        self.assertEqual(len(phrase), 8)
        self.assertTrue(all(x != y for x, y in zip(phrase, phrase[1:])))

    def test_correct_hits_boss_and_wrong_hits_self(self):
        expected = self.game.phrases["a"][0]
        wrong = next(note for note in ("c4", "d4") if note != self.game.phrases["a"][1])
        self.assertTrue(self.game.add_answer("a", expected))
        self.assertFalse(self.game.add_answer("a", wrong))
        self.assertEqual(self.game.boss_hp, BOSS_MAX_HP - 1)
        self.assertEqual(self.game.hp["a"], PLAYER_MAX_HP - 1)
        self.assertEqual(self.game.scores, {"a": 1, "b": 0})

    def test_unplayed_notes_cost_hp_and_knocked_out_player_sits_out(self):
        rows = {row["id"]: row for row in self.game.finish_phrase()}
        self.assertEqual(rows["b"]["missed"], 4)
        self.assertEqual(self.game.hp["b"], PLAYER_MAX_HP - 4)
        self.game.hp["b"] = 0
        self.game.begin_phrase(2)
        self.assertEqual(self.game.phrases["b"], [])
        self.game.begin_repeat()
        self.assertFalse(self.game.can_answer("b"))
        self.game.hp["a"] = 0
        self.assertTrue(self.game.team_defeated)

    def test_boss_defeat_ends_phrase_without_miss_penalty(self):
        self.game.boss_hp = 1
        self.game.add_answer("a", self.game.phrases["a"][0])
        self.assertTrue(self.game.boss_defeated and self.game.phrase_done)
        self.game.finish_phrase()
        self.assertEqual(self.game.hp, {"a": PLAYER_MAX_HP, "b": PLAYER_MAX_HP})


class BossServerTests(unittest.TestCase):
    def setUp(self):
        self.originals = (boss_module.show_seconds, boss_module.BOSS_RESULT_SECONDS)
        boss_module.show_seconds = lambda length: 0.3
        boss_module.BOSS_RESULT_SECONDS = 0.05
        self.server = boss_module.BossFightServer(host="127.0.0.1", port=0)
        self.server.start()
        self.sockets = []

    def tearDown(self):
        for sock in self.sockets:
            sock.close()
        self.server.stop()
        boss_module.show_seconds, boss_module.BOSS_RESULT_SECONDS = self.originals

    def connect(self, nickname):
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        sock.settimeout(3)
        self.sockets.append(sock)
        send_message(sock, {"type": mt.JOIN, "nickname": nickname, "version": APP_VERSION})
        return sock

    @staticmethod
    def wait_for(sock, message_type, phase=None):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            message = receive_message(sock)
            if message.get("type") == message_type and phase in (None, message.get("phase")):
                return message
        raise AssertionError(f"Did not receive {message_type}")

    def test_team_damages_boss_until_victory(self):
        self.server.game.boss_max_hp = 6
        alice, bob = self.connect("Alice"), self.connect("Bob")
        welcome = self.wait_for(alice, mt.WELCOME)
        self.assertEqual(welcome["mode"], "boss")
        self.assertEqual(self.server.discovery_info()["mode"], "boss")
        start = self.wait_for(alice, mt.MATCH_START)
        self.assertEqual((start["mode"], start["boss_hp"]), ("boss", 6))
        shows = [self.wait_for(sock, mt.BOSS_PHRASE, "show") for sock in (alice, bob)]
        # Each player hears only their own melody.
        self.assertEqual(len(shows[0]["notes"]), 4)
        self.assertEqual(shows[0]["notes"], self.server.game.phrases[welcome["player_id"]])
        self.assertEqual(sorted(shows[0]["lengths"].values()), [4, 4])
        repeats = [self.wait_for(sock, mt.BOSS_PHRASE, "repeat") for sock in (alice, bob)]
        self.assertEqual(repeats[0]["notes"], [])
        for sock, show, repeat in zip((alice, bob), shows, repeats):
            for note in show["notes"]:
                send_message(sock, {"type": mt.REPEAT_STEP, "color": note, "turn_id": repeat["turn_id"]})
        result = self.wait_for(alice, mt.BOSS_RESULT)
        self.assertEqual((result["team_damage"], result["boss_hp"]), (6, 0))
        final = self.wait_for(bob, mt.MATCH_RESULT)
        self.assertEqual((final["mode"], final["result"]), ("boss", "win"))

    def test_wrong_notes_and_forfeit_lose_the_fight(self):
        alice, bob = self.connect("Alice"), self.connect("Bob")
        show = self.wait_for(alice, mt.BOSS_PHRASE, "show")
        repeat = self.wait_for(alice, mt.BOSS_PHRASE, "repeat")
        wrong = "e5" if show["notes"][0] != "e5" else "c4"
        send_message(alice, {"type": mt.REPEAT_STEP, "color": wrong, "turn_id": repeat["turn_id"]})
        feedback = self.wait_for(bob, mt.BOSS_FEEDBACK)
        self.assertFalse(feedback["correct"])
        hp = {row["nickname"]: row["hp"] for row in feedback["players"]}
        self.assertEqual(hp, {"Alice": PLAYER_MAX_HP - 1, "Bob": PLAYER_MAX_HP})
        send_message(bob, {"type": mt.FORFEIT})
        final = self.wait_for(alice, mt.MATCH_RESULT)
        self.assertEqual(final["result"], "loss")
        self.assertIn("Bob left", final["reason"])

    def test_force_reset_restarts_fight_at_full_hp(self):
        alice, bob = self.connect("Alice"), self.connect("Bob")
        repeat = self.wait_for(alice, mt.BOSS_PHRASE, "repeat")
        send_message(alice, {"type": mt.REPEAT_STEP, "color": "c4", "turn_id": repeat["turn_id"]})
        self.wait_for(bob, mt.BOSS_FEEDBACK)
        self.assertTrue(self.server.restart_match())
        for sock in (alice, bob):
            start = self.wait_for(sock, mt.MATCH_START)
            self.assertEqual(start["boss_hp"], BOSS_MAX_HP)
            self.assertIn("restarted", start["reason"])
            show = self.wait_for(sock, mt.BOSS_PHRASE, "show")
            self.assertEqual(show["phrase"], 1)
            self.assertEqual({row["hp"] for row in show["players"]}, {PLAYER_MAX_HP})
        self.assertEqual(len(self.server.sessions), 2)


if __name__ == "__main__":
    unittest.main()

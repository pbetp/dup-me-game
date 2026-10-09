"""Rubric checks that exercise deadlines, reset, and real socket permissions."""
import queue
import socket
import time
import unittest
from unittest.mock import patch
from src.server.server import DupMeServer
from src.server import server as server_module
from src.client.network_client import NetworkClient
from src.common.config import CREATE_SECONDS, REPEAT_SECONDS
from tests.test_connections import wait_event, eventually


class RubricTests(unittest.TestCase):
    def setUp(self):
        self.server = DupMeServer(host='127.0.0.1', port=0)
        self.server.start()
        self.addCleanup(self.server.stop)

    def player(self, name):
        events = queue.Queue()
        client = NetworkClient(events, '127.0.0.1', self.server.port)
        self.addCleanup(client.close)
        client.connect_async(name)
        welcome = wait_event(events, 'welcome')
        return client, events, welcome

    def pair(self):
        self.a, self.qa, self.wa = self.player('Alice')
        self.b, self.qb, self.wb = self.player('Bob')
        self.sa, self.sb = wait_event(self.qa, 'round_start'), wait_event(self.qb, 'round_start')
        return (self.a, self.qa, self.sa) if self.sa['role'] == 'creator' else (self.b, self.qb, self.sb)

    def test_online_count_tracks_registered_clients_and_disconnect(self):
        probe = socket.create_connection(('127.0.0.1', self.server.port), timeout=2)
        self.addCleanup(probe.close)
        eventually(lambda: self.server.snapshot()['connection_count'] == 1)
        self.assertEqual(self.server.snapshot()['online_count'], 0)
        a, _, _ = self.player('Alice')
        snapshot = self.server.snapshot()
        self.assertEqual(snapshot['online_count'], 1)
        self.assertEqual([p['nickname'] for p in snapshot['players']], ['Alice'])
        a.close()
        eventually(lambda: self.server.snapshot()['online_count'] == 0)

    def test_standard_creation_keeps_full_deadline_at_capacity(self):
        creator, events, start = self.pair()
        self.assertEqual((CREATE_SECONDS, REPEAT_SECONDS), (10, 20))
        self.assertEqual((start['total_rounds'], start['duration']), (2, 10))
        deadline = self.server.deadline
        for _ in range(20):
            creator.send({'type': 'pattern_step', 'color': 'c4', 'turn_id': start['turn_id']})
        eventually(lambda: len(self.server.game.pattern) == 20)
        self.assertEqual(self.server.deadline, deadline)
        self.assertTrue(self.server.game.is_creating)
        creator.send({'type': 'pattern_step', 'color': 'd4', 'turn_id': start['turn_id']})
        self.assertIn('full', wait_event(events, 'error')['message'])
        self.assertEqual(len(self.server.game.pattern), 20)
        with self.server.lock:
            self.server.deadline = time.monotonic() - .01
        repeat = wait_event(events, 'round_start')
        self.assertEqual((repeat['phase'], repeat['duration']), ('repeat', 20))

    def test_empty_pattern_does_not_invent_notes_or_points(self):
        with patch.object(server_module, 'CREATE_SECONDS', .15), patch.object(server_module, 'REPEAT_SECONDS', .15):
            _, events, _ = self.pair()
            result = wait_event(events, 'round_result')
            self.assertEqual(result['pattern'], [])
            self.assertEqual(result['points'], 0)

    def test_reset_clears_scored_match_and_restarts_with_new_turn(self):
        with patch.object(server_module, 'CREATE_SECONDS', .4):
            creator, events, start = self.pair()
            creator.send({'type': 'pattern_step', 'color': 'c4', 'turn_id': start['turn_id']})
            ra, rb = wait_event(self.qa, 'round_start'), wait_event(self.qb, 'round_start')
            repeater, reply = (self.a, ra) if ra['role'] == 'repeater' else (self.b, rb)
            repeater.send({'type': 'repeat_step', 'color': 'c4', 'turn_id': reply['turn_id']})
            wait_event(self.qa, 'round_result')
            wait_event(self.qb, 'round_result')
            self.assertEqual(sum(self.server.game.scores.values()), 1)
            self.server.reset_game()
            wait_event(self.qa, 'game_reset')
            wait_event(self.qb, 'game_reset')
            snapshot = self.server.snapshot()
            # Reset restarts straight away when two players remain, so scores are a fresh 0-0.
            self.assertEqual(set(snapshot['scores'].values()), {0})
            self.assertEqual(snapshot['online_count'], 2)
            restarted = wait_event(self.qa, 'round_start')
            self.assertEqual(restarted['round'], 1)
            self.assertNotEqual(restarted['turn_id'], start['turn_id'])
            self.assertEqual([row['score'] for row in restarted['scores']], [0, 0])

    def test_forfeit_loses_regardless_of_score(self):
        with patch.object(server_module, 'CREATE_SECONDS', .4):
            creator, events, start = self.pair()
            creator.send({'type': 'pattern_step', 'color': 'c4', 'turn_id': start['turn_id']})
            ra, rb = wait_event(self.qa, 'round_start'), wait_event(self.qb, 'round_start')
            repeater, repeater_events, reply = (self.a, self.qa, ra) if ra['role'] == 'repeater' else (self.b, self.qb, rb)
            repeater.send({'type': 'repeat_step', 'color': 'c4', 'turn_id': reply['turn_id']})
            wait_event(repeater_events, 'round_result')
            # The repeater is ahead 1-0 but forfeits, so still loses.
            repeater.send({'type': 'forfeit'})
            other_events = self.qb if repeater is self.a else self.qa
            leaver, other = wait_event(repeater_events, 'match_result'), wait_event(other_events, 'match_result')
            self.assertEqual((leaver['result'], other['result']), ('loss', 'win'))
            self.assertEqual(leaver['reason'], 'You forfeited the match.')
            self.assertTrue(other['ended_early'])
            self.assertIsNone(self.server.deadline)
            self.assertIsNone(self.server.pending_transition)
            repeater.send({'type': 'forfeit'})
            self.assertIn('no match', wait_event(repeater_events, 'error')['message'])

    def test_host_end_match_decides_by_current_score(self):
        self.pair()
        self.assertTrue(self.server.end_match())
        for events in (self.qa, self.qb):
            result = wait_event(events, 'match_result')
            self.assertEqual((result['result'], result['reason']), ('draw', 'The host ended the match.'))
        self.assertFalse(self.server.end_match())

    def test_inactive_role_and_tokenless_move_cannot_change_pattern(self):
        creator, events, start = self.pair()
        other, other_events, other_start = (self.b, self.qb, self.sb) if creator is self.a else (self.a, self.qa, self.sa)
        other.send({'type': 'pattern_step', 'color': 'c4', 'turn_id': other_start['turn_id']})
        self.assertIn('Only the creator', wait_event(other_events, 'error')['message'])
        creator.send({'type': 'pattern_step', 'color': 'c4'})
        self.assertIn('earlier turn', wait_event(events, 'error')['message'])
        self.assertEqual(self.server.game.pattern, [])

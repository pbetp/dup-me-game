"""Real TCP regressions for hosting, reconnecting, cancellation and AI play."""
import queue
import socket
import struct
import threading
import time
import unittest
from unittest.mock import patch

from src.bot.ai_bot import AdaptiveBot
from src.client.local_game import LocalGame
from src.client.network_client import NetworkClient
from src.common.config import APP_VERSION, MAX_MESSAGE_BYTES
from src.common.networking import check_connection, local_ip_addresses, validate_endpoint
from src.common.protocol import ProtocolError, encode_message, receive_message, send_message
from src.server.server import DupMeServer
from src.server import server as server_module


def wait_event(events, kind, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            event = events.get(timeout=max(.01, end - time.monotonic()))
        except queue.Empty:
            break
        if event['type'] == kind:
            return event
        if event['type'] in ('network_error', 'error'):
            raise AssertionError(event)
    raise AssertionError(f'Timed out waiting for {kind}')


def eventually(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Condition did not become true')


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.server = DupMeServer(host='127.0.0.1', port=0)
        self.server.start()
        self.addCleanup(self.server.stop)

    def client(self, nickname='Alice', host='127.0.0.1', port=None):
        events = queue.Queue()
        client = NetworkClient(events, host, port or self.server.port)
        self.addCleanup(client.close)
        client.connect_async(nickname)
        return client, events

    def test_probe_does_not_join_or_start_match(self):
        self.assertIn('Ready to join', check_connection('127.0.0.1', self.server.port))
        eventually(lambda: len(self.server.snapshot()['players']) == 0)
        self.assertEqual(self.server.game.players, [])

    def test_duplicate_nickname_is_recoverable(self):
        first, events = self.client()
        wait_event(events, 'welcome')
        duplicate, rejected = self.client('alice')
        error = wait_event(rejected, 'network_error')
        self.assertIn('already connected', error['message'])
        duplicate.close()
        replacement, accepted = self.client('Bob')
        wait_event(accepted, 'welcome')
        wait_event(accepted, 'round_start')

    def test_disconnect_then_same_name_reconnect(self):
        first, events = self.client()
        wait_event(events, 'welcome')
        first.close()
        eventually(lambda: not self.server.snapshot()['players'])
        second, events2 = self.client()
        wait_event(events2, 'welcome')

    def test_stop_notifies_client_and_port_can_restart(self):
        client, events = self.client()
        wait_event(events, 'welcome')
        port = self.server.port
        self.server.stop()
        wait_event(events, 'network_error')
        replacement = DupMeServer(host='127.0.0.1', port=port)
        self.addCleanup(replacement.stop)
        replacement.start()
        self.assertIn('Ready to join', check_connection('127.0.0.1', port))

    def test_port_conflict_leaves_original_server_alive(self):
        conflicting = DupMeServer(host='127.0.0.1', port=self.server.port)
        with self.assertRaises(OSError):
            conflicting.start()
        self.assertFalse(conflicting.running.is_set())
        self.assertIsNone(conflicting.listener)
        self.assertIn('Ready to join', check_connection('127.0.0.1', self.server.port))

    def test_old_version_is_rejected_clearly(self):
        with socket.create_connection(('127.0.0.1', self.server.port), timeout=2) as sock:
            send_message(sock, {'type': 'join', 'nickname': 'Old', 'version': '1.0'})
            reply = receive_message(sock)
            self.assertEqual(reply['type'], 'error')
            self.assertIn('Version mismatch', reply['message'])

    def test_stale_turn_move_is_rejected(self):
        alice, qa = self.client('Alice')
        wait_event(qa, 'welcome')
        bob, qb = self.client('Bob')
        wait_event(qb, 'welcome')
        sa, sb = wait_event(qa, 'round_start'), wait_event(qb, 'round_start')
        creator, events = (alice, qa) if sa['role'] == 'creator' else (bob, qb)
        creator.send({'type': 'pattern_step', 'color': 'c4', 'turn_id': 'old-turn'})
        self.assertIn('earlier turn', wait_event(events, 'error')['message'])
        self.assertEqual(self.server.game.pattern, [])

    def test_cancel_during_connection_closes_late_socket(self):
        entered, release = threading.Event(), threading.Event()
        real_create = socket.create_connection
        late = []
        def delayed(*args, **kwargs):
            entered.set()
            release.wait(2)
            sock = real_create(*args, **kwargs)
            late.append(sock)
            return sock
        with patch('src.client.network_client.socket.create_connection', side_effect=delayed):
            client, events = self.client('Cancelled')
            self.assertTrue(entered.wait(2))
            client.close()
            release.set()
            eventually(lambda: bool(late) and late[0].fileno() == -1)
        self.assertTrue(events.empty())
        self.assertIsNone(client.sock)

    def test_solo_is_isolated_from_hosted_game(self):
        solo = LocalGame()
        self.addCleanup(solo.close)
        port = solo.start(solo=True)
        self.assertNotEqual(port, self.server.port)
        self.assertEqual(solo.server.host, '127.0.0.1')
        self.assertIn('Ready to join', check_connection('127.0.0.1', port))
        solo.close()
        self.assertIn('Ready to join', check_connection('127.0.0.1', self.server.port))

    def test_invalid_frame_does_not_stop_server(self):
        with socket.create_connection(('127.0.0.1', self.server.port), timeout=2) as sock:
            sock.sendall(struct.pack('!I', MAX_MESSAGE_BYTES + 1))
            self.assertEqual(sock.recv(1), b'')
        self.assertIn('Ready to join', check_connection('127.0.0.1', self.server.port))

    def test_bot_cancels_pending_moves_after_reset(self):
        bot = AdaptiveBot('Bot', '127.0.0.1', self.server.port, 'easy', log=lambda _: None)
        self.addCleanup(bot.close)
        sent = []
        bot.network.send = lambda message: sent.append(message)
        bot._handle({'type': 'round_start', 'round': 1, 'phase': 'create', 'role': 'creator', 'turn_id': 'old'})
        bot._handle({'type': 'game_reset'})
        time.sleep(.6)
        self.assertEqual(sent, [])

    def test_human_client_and_real_ai_complete_match_and_rematch(self):
        # Accelerated test timers; bot still observes network events normally.
        with patch.object(server_module, 'CREATE_SECONDS', 1.5), patch.object(server_module, 'PHASE_RESULT_SECONDS', .05):
            bot = AdaptiveBot('DupBot', '127.0.0.1', self.server.port, 'hard', log=lambda _: None)
            bot.model.press_delay = lambda: .01
            worker = threading.Thread(target=bot.connect_and_run, daemon=True)
            human, events = self.client('Human')
            wait_event(events, 'welcome')
            worker.start()
            patterns, result, errors = {}, None, []
            try:
                end = time.monotonic() + 12
                while time.monotonic() < end:
                    message = events.get(timeout=4)
                    kind = message['type']
                    if kind == 'round_start':
                        number = message['round']
                        if message['phase'] == 'create':
                            patterns[number] = []
                            if message['role'] == 'creator':
                                for color in ['c4', 'd4'] * 10:
                                    human.send({'type': 'pattern_step', 'color': color, 'turn_id': message['turn_id']})
                        elif message['role'] == 'repeater':
                            for color in patterns[number]:
                                human.send({'type': 'repeat_step', 'color': color, 'turn_id': message['turn_id']})
                    elif kind == 'pattern_update':
                        patterns.setdefault(message['round'], []).append(message['color'])
                    elif kind in ('error', 'network_error'):
                        errors.append(message)
                    elif kind == 'match_result':
                        result = message
                        break
                self.assertIsNotNone(result)
                self.assertEqual(errors, [])
                self.assertEqual(len(result['scores']), 2)
                human.send({'type': 'rematch_vote'})
                wait_event(events, 'match_start', timeout=4)
                self.assertIsNone(bot.error)
            finally:
                bot.close()
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())


class NetworkUtilityTests(unittest.TestCase):
    def test_addresses_and_ports_are_validated(self):
        self.assertEqual(validate_endpoint(' 192.168.1.12 ', '55000'), ('192.168.1.12', 55000))
        for host, port in [('0.0.0.0', 55000), ('http://localhost', 55000), ('127.0.0.1:55000', 55000),
                           ('', 55000), ('localhost', -1), ('localhost', 65536), ('localhost', 'abc')]:
            with self.subTest(host=host, port=port), self.assertRaises(ValueError):
                validate_endpoint(host, port)

    def test_fragmented_and_coalesced_messages(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        frames = encode_message({'type': 'ping'}) + encode_message({'type': 'join', 'nickname': 'ทดสอบ'})
        def write():
            for byte in frames:
                left.sendall(bytes([byte]))
        worker = threading.Thread(target=write)
        worker.start()
        self.assertEqual(receive_message(right), {'type': 'ping'})
        self.assertEqual(receive_message(right)['nickname'], 'ทดสอบ')
        worker.join(timeout=1)

    def test_wildcard_listener_accepts_loopback_and_own_lan_ip(self):
        addresses = local_ip_addresses()
        if not addresses:
            self.skipTest('No non-loopback IPv4 address on this machine')
        server = DupMeServer(host='0.0.0.0', port=0)
        server.start()
        self.addCleanup(server.stop)
        self.assertIn('Ready to join', check_connection('127.0.0.1', server.port))
        self.assertIn('Ready to join', check_connection(addresses[0], server.port))


if __name__ == '__main__':
    unittest.main()

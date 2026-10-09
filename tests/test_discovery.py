"""Discovery and connection-file checks over actual local UDP/TCP sockets."""
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.common.discovery import discover_servers, save_connection_file, load_connection_file, resolve_connection_file
from src.common.protocol import ProtocolError
from src.common.config import APP_VERSION
from src.server.server import DupMeServer


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.server = DupMeServer(host='0.0.0.0', port=0, advertise=True, discovery_port=0, name='Test host')
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_udp_finds_tcp_endpoint_without_registering_player(self):
        rows = discover_servers(timeout=.3, discovery_port=self.server.discovery.port)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['port'], self.server.port)
        self.assertEqual(rows[0]['name'], 'Test host')
        self.assertEqual(rows[0]['version'], APP_VERSION)
        self.assertEqual(rows[0]['total_rounds'], 2)
        self.assertEqual(self.server.snapshot()['online_count'], 0)
        self.assertEqual(resolve_connection_file([(rows[0]['host'], rows[0]['port'])])[1], self.server.port)

    def test_searcher_that_closes_early_does_not_disable_responder(self):
        # Windows reports WinError 10054 on the next read after replying to a closed port.
        import json, socket, time, uuid
        from src.common.discovery import DiscoveryResponder, discover_servers
        responder = DiscoveryResponder(lambda: {'server_id': uuid.uuid4().hex, 'name': 'Host', 'port': 5000}, port=0)
        responder.start()
        self.addCleanup(responder.close)
        for _ in range(3):
            early = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            early.sendto(json.dumps({'type': 'dupme_discover', 'nonce': uuid.uuid4().hex}).encode(),
                         ('127.0.0.1', responder.port))
            early.close()
        time.sleep(.4)
        self.assertTrue(responder.thread.is_alive())
        self.assertTrue(discover_servers(timeout=1, discovery_port=responder.port))

    def test_bad_datagrams_do_not_disable_responder(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for data in (b'garbage', b'[]', b'{"type":"dupme_discover","nonce":5}', b'{}'):
                sock.sendto(data, ('127.0.0.1', self.server.discovery.port))
        self.assertTrue(discover_servers(timeout=.3, discovery_port=self.server.discovery.port))

    def test_connection_file_roundtrip_works_without_discovery(self):
        self.server.discovery.close()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'connection.json'
            save_connection_file(path, ['127.0.0.1'], self.server.port)
            self.assertEqual(resolve_connection_file(load_connection_file(path)), ('127.0.0.1', self.server.port))
            self.assertEqual(self.server.snapshot()['online_count'], 0)

    def test_connection_file_rejects_wrong_version_and_invalid_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            for data in ([], {'app': 'Else'}, {'app': 'Dup Me', 'version': APP_VERSION, 'addresses': ['0.0.0.0'], 'port': 55000},
                         {'app': 'Dup Me', 'version': APP_VERSION, 'addresses': ['localhost'], 'port': 70000}):
                path.write_text(json.dumps(data))
                with self.subTest(data=data), self.assertRaises(ValueError):
                    load_connection_file(path)

    def test_profile_checks_remaining_addresses_after_protocol_failure(self):
        endpoints = [('bad-host', 55000), ('good-host', 55000)]
        with patch('src.common.discovery.check_connection', side_effect=[ProtocolError('Wrong version'), 'Ready']):
            self.assertEqual(resolve_connection_file(endpoints), endpoints[1])

    def test_discovery_port_conflict_does_not_disable_game_server(self):
        second = DupMeServer(host='127.0.0.1', port=0, advertise=True, discovery_port=self.server.discovery.port)
        self.addCleanup(second.stop)
        second.start()
        self.assertIn('unavailable', second.discovery_status)
        self.assertEqual(resolve_connection_file([('127.0.0.1', second.port)])[1], second.port)

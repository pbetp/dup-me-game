import queue
import time
import unittest
from unittest.mock import patch
from src.client import network_client as client_module
from src.server import server as server_module
from src.server.server import DupMeServer
from src.client.network_client import NetworkClient
from tests.test_connections import wait_event, eventually


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.server = DupMeServer(host='127.0.0.1', port=0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.events = queue.Queue()
        self.client = NetworkClient(self.events, '127.0.0.1', self.server.port)
        self.addCleanup(self.client.close)

    def test_quiet_lobby_stays_connected_with_heartbeats(self):
        with patch.object(client_module, 'HEARTBEAT_INTERVAL', .03), patch.object(client_module, 'HEARTBEAT_TIMEOUT', .5), patch.object(server_module, 'HEARTBEAT_TIMEOUT', .5):
            self.client.connect_async('Alice')
            wait_event(self.events, 'welcome')
            first = wait_event(self.events, 'pong')
            self.assertEqual(first['app'], 'Dup Me')
            time.sleep(.65)
            self.assertEqual(self.server.snapshot()['online_count'], 1)
            self.assertIsNotNone(self.client.sock)
            self.client.close()

    def test_unresponsive_server_returns_client_to_retry(self):
        with patch.object(client_module, 'HEARTBEAT_INTERVAL', .03), patch.object(client_module, 'HEARTBEAT_TIMEOUT', .2):
            self.client.connect_async('Alice')
            wait_event(self.events, 'welcome')
            with patch.object(self.server, 'handle_message'):
                error = wait_event(self.events, 'network_error')
                self.assertIn('stopped responding', error['message'])
            eventually(lambda: self.server.snapshot()['online_count'] == 0)

    def test_server_drops_client_that_stops_sending(self):
        with patch.object(client_module, 'HEARTBEAT_INTERVAL', .03), patch.object(server_module, 'HEARTBEAT_TIMEOUT', .2):
            self.client.connect_async('Alice')
            wait_event(self.events, 'welcome')
            with patch.object(self.client, 'send', return_value=True):
                wait_event(self.events, 'network_error')
                eventually(lambda: self.server.snapshot()['online_count'] == 0)

import socket
import unittest

from src.common.protocol import ProtocolError, encode_message, receive_message


class ProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        left.sendall(encode_message({"type": "join", "nickname": "Alice"}))
        self.assertEqual(receive_message(right)["nickname"], "Alice")

    def test_rejects_non_dictionary(self):
        with self.assertRaises(ProtocolError):
            encode_message(["not", "a", "dictionary"])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()


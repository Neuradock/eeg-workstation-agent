import socket
import threading
import unittest

from neuradock_agent.realtime import capture_tcp


def _packet_line(index):
    fields = [f"{index / 50:.6f}", "0"]
    for sample in range(5):
        fields.extend(str(channel + sample * 0.1) for channel in range(7))
        fields.append("0")
    return ",".join(fields) + "\n"


class RealtimeTests(unittest.TestCase):
    def test_mock_neuradock_tcp_capture(self):
        ready = threading.Event()
        port_holder = []

        def server():
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port_holder.append(listener.getsockname()[1])
            ready.set()
            connection, _address = listener.accept()
            connection.recv(16)
            payload = "".join(_packet_line(index) for index in range(50))
            connection.sendall(payload.encode("utf-8"))
            connection.close()
            listener.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(2))
        data, metrics = capture_tcp(
            "127.0.0.1", port_holder[0], windows=1, timeout_sec=2
        )
        thread.join(timeout=2)
        self.assertEqual(data.shape, (7, 250))
        self.assertEqual(metrics["lines_skipped"], 0)
        self.assertEqual(metrics["samples_captured"], 250)


if __name__ == "__main__":
    unittest.main()


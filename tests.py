import unittest
from unittest.mock import patch
import time
import random
import queue
import threading
from main import VirtualMachine


# For testing, we define a subclass that avoids starting server threads and file I/O.
class TestableVirtualMachine(VirtualMachine):
    def __init__(self, vm_id, port, peer_info):
        # Instead of calling the original __init__, we set up only what is needed.
        self.vm_id = vm_id
        self.port = port
        self.peer_info = peer_info
        self.clock_rate = (
            100  # Use a high clock rate to minimize sleep delays in tests.
        )
        self.logical_clock = 0
        self.message_queue = queue.Queue()
        self.running = True
        self.lock = threading.Lock()
        # Replace file logging with in-memory lists for testing.
        self.logs = []
        self.sent_messages = []

    def update_log(self, event_type, details=""):
        # Instead of writing to a file, we append log entries to a list.
        log_entry = (
            f"{time.time()} | {event_type} | LC: {self.logical_clock} | {details}"
        )
        self.logs.append(log_entry)

    def send_message(self, peer_id, message):
        # Instead of sending via sockets, record the sent message.
        self.sent_messages.append((peer_id, message))

    def process_tick(self):
        """
        Execute one tick of the VM's main loop.
        This mimics the behavior from the run() method but only processes a single event.
        """
        tick_start = time.time()
        if not self.message_queue.empty():
            msg = self.message_queue.get()
            received_clock = msg.get("clock", 0)
            sender = msg.get("sender", "Unknown")
            with self.lock:
                self.logical_clock = max(self.logical_clock, received_clock) + 1
            self.update_log(
                "RECEIVE", f"From: {sender}, QueueLen: {self.message_queue.qsize()}"
            )
        else:
            event = random.randint(1, 10)
            if event == 1:
                # Send event type 1: send to first peer (lowest peer id).
                peer_id = sorted(self.peer_info.keys())[0]
                message = {"sender": self.vm_id, "clock": self.logical_clock}
                self.send_message(peer_id, message)
                with self.lock:
                    self.logical_clock += 1
                self.update_log(f"SEND to {peer_id}")
            elif event == 2:
                # Send event type 2: send to second peer (or only one available).
                peer_ids = sorted(self.peer_info.keys())
                peer_id = peer_ids[1] if len(peer_ids) > 1 else peer_ids[0]
                message = {"sender": self.vm_id, "clock": self.logical_clock}
                self.send_message(peer_id, message)
                with self.lock:
                    self.logical_clock += 1
                self.update_log(f"SEND to {peer_id}")
            elif event == 3:
                # Send event type 3: send to all peers.
                for peer_id in self.peer_info.keys():
                    message = {"sender": self.vm_id, "clock": self.logical_clock}
                    self.send_message(peer_id, message)
                with self.lock:
                    self.logical_clock += 1
                self.update_log("SEND to both")
            else:
                # Internal event.
                with self.lock:
                    self.logical_clock += 1
                self.update_log("INTERNAL event")
        tick_duration = time.time() - tick_start
        sleep_time = max(0, 1.0 / self.clock_rate - tick_duration)
        time.sleep(sleep_time)


class VirtualMachineTestSuite(unittest.TestCase):
    def setUp(self):
        # Setup a test VM with dummy peer info.
        peer_info = {2: ("localhost", 10002), 3: ("localhost", 10003)}
        self.vm = TestableVirtualMachine(1, 10001, peer_info)

    def test_internal_event(self):
        # Force random.randint to return 4 (an internal event).
        with patch("random.randint", return_value=4):
            initial_clock = self.vm.logical_clock
            self.vm.process_tick()
            self.assertEqual(self.vm.logical_clock, initial_clock + 1)
            self.assertTrue(
                any("INTERNAL event" in log for log in self.vm.logs),
                "Log should contain an INTERNAL event entry.",
            )

    def test_send_event_type1(self):
        # Force random.randint to return 1 to trigger a send event (type 1).
        with patch("random.randint", return_value=1):
            initial_clock = self.vm.logical_clock
            self.vm.process_tick()
            self.assertEqual(self.vm.logical_clock, initial_clock + 1)
            expected_peer = sorted(self.vm.peer_info.keys())[0]
            # Check that a message was recorded as sent to the expected peer.
            self.assertTrue(
                any(expected_peer == sent[0] for sent in self.vm.sent_messages),
                "Message should be sent to the peer with the lowest ID.",
            )
            self.assertTrue(
                any(f"SEND to {expected_peer}" in log for log in self.vm.logs),
                "Log should record a SEND event for the correct peer.",
            )

    def test_send_event_type2(self):
        # Force random.randint to return 2 to trigger a send event (type 2).
        with patch("random.randint", return_value=2):
            initial_clock = self.vm.logical_clock
            self.vm.process_tick()
            self.assertEqual(self.vm.logical_clock, initial_clock + 1)
            peer_ids = sorted(self.vm.peer_info.keys())
            expected_peer = peer_ids[1] if len(peer_ids) > 1 else peer_ids[0]
            self.assertTrue(
                any(expected_peer == sent[0] for sent in self.vm.sent_messages),
                "Message should be sent to the correct peer for event type 2.",
            )
            self.assertTrue(
                any(f"SEND to {expected_peer}" in log for log in self.vm.logs),
                "Log should record a SEND event for the correct peer.",
            )

    def test_send_event_type3(self):
        # Force random.randint to return 3 to trigger a send event (type 3).
        with patch("random.randint", return_value=3):
            initial_clock = self.vm.logical_clock
            self.vm.process_tick()
            self.assertEqual(self.vm.logical_clock, initial_clock + 1)
            # For type 3, messages are sent to all peers.
            for peer_id in self.vm.peer_info.keys():
                self.assertTrue(
                    any(peer_id == sent[0] for sent in self.vm.sent_messages),
                    f"Message should be sent to peer {peer_id} in event type 3.",
                )
            self.assertTrue(
                any("SEND to both" in log for log in self.vm.logs),
                "Log should record a SEND to both event.",
            )

    def test_receive_event(self):
        # Test that processing a received message correctly updates the logical clock.
        # Set the local clock to a known value.
        self.vm.logical_clock = 5
        # Create a message with a higher clock value.
        message = {"sender": 2, "clock": 10}
        self.vm.message_queue.put(message)
        self.vm.process_tick()
        # The new clock should be max(5, 10) + 1 = 11.
        self.assertEqual(self.vm.logical_clock, 11)
        self.assertTrue(
            any("RECEIVE" in log for log in self.vm.logs),
            "Log should record a RECEIVE event.",
        )

    def test_multiple_ticks(self):
        # Simulate a series of ticks with different events.
        # We'll force a sequence: internal event, send type 1, then a receive event.
        events = [4, 1, None]  # None indicates we'll inject a message (receive event)

        def side_effect(*args, **kwargs):
            return events.pop(0) if events[0] is not None else 4

        with patch("random.randint", side_effect=side_effect):
            # First tick: internal event.
            initial_clock = self.vm.logical_clock
            self.vm.process_tick()
            self.assertEqual(self.vm.logical_clock, initial_clock + 1)

            # Second tick: send event type 1.
            initial_clock = self.vm.logical_clock
            self.vm.process_tick()
            self.assertEqual(self.vm.logical_clock, initial_clock + 1)
            expected_peer = sorted(self.vm.peer_info.keys())[0]
            self.assertTrue(
                any(expected_peer == sent[0] for sent in self.vm.sent_messages),
                "Send event type 1 should deliver a message to the correct peer.",
            )

            # Third tick: simulate a receive event by inserting a message.
            message = {"sender": 3, "clock": 20}
            self.vm.message_queue.put(message)
            initial_clock = self.vm.logical_clock
            self.vm.process_tick()
            self.assertEqual(
                self.vm.logical_clock,
                max(initial_clock, 20) + 1,
                "Logical clock should be updated correctly upon receiving a message.",
            )


if __name__ == "__main__":
    unittest.main()

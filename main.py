#!/usr/bin/env python3
"""
main.py

This script runs a distributed system simulation using three separate processes,
each emulating a virtual machine (VM). Each VM maintains a Lamport-style logical clock
and communicates with its peers over TCP. The simulation parameters (run time, log directory,
variation mode, and internal event probability) are provided as command-line arguments.

Simulation Details:
 - Each VM's clock rate is determined by the variation_mode:
     - "order": Clock rates vary from 1 to 6 ticks per second.
     - "small": Clock rates vary from 2 to 3 ticks per second.
 - At each tick, a VM will either perform an internal event or send a message,
   based on the probability specified by internal_prob.
 - For sending events, if more than one peer is available, the VM randomly
   chooses to send to one or both peers.
 - All events are logged in files with the format:
     <system time> | <event type> | LC: <logical_clock> | <details>
   which is compatible with run_experiments.py.
 - Prior to running, any previous log files in the log directory are deleted.
 
Usage Example:
    python main.py --run_time 60 --log_dir trial_1 --variation_mode order --internal_prob 0.7
"""

import socket
import threading
import time
import random
import json
import queue
import os
import glob
import argparse
import sys
from multiprocessing import Process

def delete_log_files(log_dir):
    """Deletes all log files in the specified log directory matching vm_*.log."""
    log_files = glob.glob(os.path.join(log_dir, "vm_*.log"))
    for log_file in log_files:
        try:
            os.remove(log_file)
            print(f"Deleted log file: {log_file}")
        except Exception as e:
            print(f"Error deleting log file {log_file}: {e}")

class VirtualMachine:
    def __init__(self, vm_id, port, peer_info, log_dir, clock_rate_range, internal_prob):
        """
        vm_id: Identifier for this VM.
        port: Port number to listen on.
        peer_info: Dictionary mapping peer IDs to (ip, port) tuples.
        log_dir: Directory to write log files.
        clock_rate_range: Tuple (min, max) for random clock ticks per second.
        internal_prob: Probability that an event is internal (0 to 1).
        """
        self.vm_id = vm_id
        self.port = port
        self.peer_info = peer_info  # Peers: {peer_id: (ip, port)}
        self.clock_rate = random.randint(clock_rate_range[0], clock_rate_range[1])
        self.internal_prob = internal_prob
        self.logical_clock = 0
        self.message_queue = queue.Queue()
        self.running = True

        # Open a log file for writing events.
        self.log_file_path = os.path.join(log_dir, f"vm_{vm_id}.log")
        self.log_file = open(self.log_file_path, "a")
        # Log the initial clock rate so that analysis can pick it up.
        self.update_log("INIT", f"ClockRate: {self.clock_rate}")

        # Dictionary to hold client sockets for sending messages to peers.
        self.peer_sockets = {}

        # Lock to ensure that updates to the logical clock are thread-safe.
        self.lock = threading.Lock()

        # Start the server thread that will listen for incoming messages.
        self.server_thread = threading.Thread(target=self.start_server, daemon=True)

    def start_server(self):
        """Starts a TCP server to listen for incoming connections and messages."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("localhost", self.port))
        server_sock.listen(5)
        server_sock.settimeout(1.0)
        while self.running:
            try:
                conn, addr = server_sock.accept()
                # Start a new thread to handle the connection.
                threading.Thread(
                    target=self.handle_connection, args=(conn,), daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"VM {self.vm_id}: Server error: {e}")
        server_sock.close()

    def handle_connection(self, conn):
        """Handles an incoming connection, reading messages and enqueuing them."""
        buffer = ""
        while self.running:
            try:
                data = conn.recv(1024).decode("utf-8")
                if not data:
                    break
                buffer += data
                # Process complete messages terminated by newline.
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line:
                        try:
                            msg = json.loads(line)
                            self.message_queue.put(msg)
                        except Exception as e:
                            print(f"VM {self.vm_id}: Error parsing message: {e}")
            except Exception as e:
                break
        conn.close()

    def connect_to_peers(self):
        """Connects as a client to all peer VMs."""
        for peer_id, (peer_ip, peer_port) in self.peer_info.items():
            connected = False
            while not connected and self.running:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((peer_ip, peer_port))
                    self.peer_sockets[peer_id] = s
                    connected = True
                    print(
                        f"VM {self.vm_id}: Connected to peer {peer_id} at {peer_ip}:{peer_port}"
                    )
                except Exception:
                    time.sleep(1)

    def send_message(self, peer_id, message):
        """Sends a JSON message to the specified peer."""
        if peer_id in self.peer_sockets:
            try:
                msg_str = json.dumps(message) + "\n"
                self.peer_sockets[peer_id].sendall(msg_str.encode("utf-8"))
            except Exception as e:
                print(f"VM {self.vm_id}: Error sending message to peer {peer_id}: {e}")
        else:
            print(f"VM {self.vm_id}: Peer {peer_id} not connected")

    def update_log(self, event_type, details=""):
        """Logs an event with the system time, event type, and current logical clock."""
        log_entry = (
            f"{time.time()} | {event_type} | LC: {self.logical_clock} | {details}\n"
        )
        self.log_file.write(log_entry)
        self.log_file.flush()

    def run(self):
        """Main loop running at the machine's clock rate."""
        # Start the server thread and connect to peers.
        self.server_thread.start()
        self.connect_to_peers()

        print(f"VM {self.vm_id}: Running with clock rate {self.clock_rate} ticks/sec")
        while self.running:
            tick_start = time.time()
            if not self.message_queue.empty():
                # Process one message from the message queue.
                msg = self.message_queue.get()
                received_clock = msg.get("clock", 0)
                sender = msg.get("sender", "Unknown")
                with self.lock:
                    # Update the logical clock on receipt: max(local, received) + 1.
                    self.logical_clock = max(self.logical_clock, received_clock) + 1
                self.update_log(
                    "RECEIVE", f"From: {sender}, QueueLen: {self.message_queue.qsize()}"
                )
            else:
                # Decide between an internal event or a sending event based on internal_prob.
                if random.random() < self.internal_prob:
                    # Internal event.
                    with self.lock:
                        self.logical_clock += 1
                    self.update_log("INTERNAL event")
                else:
                    # Sending event.
                    peer_ids = sorted(self.peer_info.keys())
                    if len(peer_ids) == 0:
                        # No peers to send to.
                        with self.lock:
                            self.logical_clock += 1
                        self.update_log("INTERNAL event (no peers)")
                    else:
                        # Choose sending mode based on the number of peers.
                        if len(peer_ids) == 1:
                            chosen_peer = peer_ids[0]
                            message = {"sender": self.vm_id, "clock": self.logical_clock}
                            self.send_message(chosen_peer, message)
                            with self.lock:
                                self.logical_clock += 1
                            self.update_log(f"SEND to {chosen_peer}")
                        else:
                            sending_choice = random.choice(["send1", "send2", "send_both"])
                            if sending_choice == "send1":
                                chosen_peer = peer_ids[0]
                                message = {"sender": self.vm_id, "clock": self.logical_clock}
                                self.send_message(chosen_peer, message)
                                with self.lock:
                                    self.logical_clock += 1
                                self.update_log(f"SEND to {chosen_peer}")
                            elif sending_choice == "send2":
                                chosen_peer = peer_ids[1]
                                message = {"sender": self.vm_id, "clock": self.logical_clock}
                                self.send_message(chosen_peer, message)
                                with self.lock:
                                    self.logical_clock += 1
                                self.update_log(f"SEND to {chosen_peer}")
                            elif sending_choice == "send_both":
                                for peer in peer_ids:
                                    message = {"sender": self.vm_id, "clock": self.logical_clock}
                                    self.send_message(peer, message)
                                with self.lock:
                                    self.logical_clock += 1
                                self.update_log("SEND to both")
            # Wait until the next tick based on the machine's clock rate.
            tick_duration = time.time() - tick_start
            sleep_time = max(0, 1.0 / self.clock_rate - tick_duration)
            time.sleep(sleep_time)

    def stop(self):
        """Stops the machine's execution and closes sockets and log file."""
        self.running = False
        self.log_file.close()
        for s in self.peer_sockets.values():
            s.close()

def run_vm(vm_id, port, peer_info, log_dir, clock_rate_range, internal_prob):
    """
    Function to create and run a VirtualMachine instance.
    This will be the target for each process.
    """
    vm = VirtualMachine(vm_id, port, peer_info, log_dir, clock_rate_range, internal_prob)
    try:
        vm.run()
    except KeyboardInterrupt:
        vm.stop()

def main():
    parser = argparse.ArgumentParser(description="Distributed simulation for logical clocks.")
    parser.add_argument("--run_time", type=int, required=True, help="Duration of the simulation in seconds.")
    parser.add_argument("--log_dir", type=str, required=True, help="Directory to store log files.")
    parser.add_argument("--variation_mode", type=str, default="order",
                        help="Clock variation mode: 'order' (1-6 ticks/sec) or 'small' (2-3 ticks/sec).")
    parser.add_argument("--internal_prob", type=float, default=0.7, help="Probability of an internal event (0 to 1).")
    parser.add_argument("--port_offset", type=int, default=0,
                        help="Port offset to avoid conflicts when running parallel simulations.")
    args = parser.parse_args()

    # Use the port offset to shift the fixed port numbers.
    port_offset = args.port_offset
    config = {
        1: ("localhost", 10001 + port_offset),
        2: ("localhost", 10002 + port_offset),
        3: ("localhost", 10003 + port_offset),
    }

    # Create the log directory if it does not exist.
    if not os.path.exists(args.log_dir):
        os.makedirs(args.log_dir)
    else:
        # Optionally delete previous log files.
        delete_log_files(args.log_dir)

    # Determine clock rate range based on variation mode.
    if args.variation_mode == "order":
        clock_rate_range = (1, 6)
    elif args.variation_mode == "small":
        clock_rate_range = (2, 3)
    else: 
        clock_rate_range = (1, 4)  # medium 

    # Create and start a process for each virtual machine.
    processes = []
    for vm_id, (host, port) in config.items():
        # Peers: all other VMs.
        peers = {peer_id: addr for peer_id, addr in config.items() if peer_id != vm_id}
        p = Process(
            target=run_vm,
            args=(vm_id, port, peers, args.log_dir, clock_rate_range, args.internal_prob)
        )
        p.start()
        processes.append(p)

    print(f"Simulation running for {args.run_time} seconds...")
    try:
        time.sleep(args.run_time)
    except KeyboardInterrupt:
        print("Simulation interrupted by user.")

    print("Stopping simulation processes...")
    for p in processes:
        p.terminate()  # Force termination of the VM process.
    for p in processes:
        p.join()

if __name__ == "__main__":
    main()

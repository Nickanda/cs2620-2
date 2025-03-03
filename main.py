import socket
import threading
import time
import random
import json
import queue
import os
import glob


def delete_log_files():
    """Deletes all log files in the current directory."""
    log_files = glob.glob("vm_*.log")
    for log_file in log_files:
        try:
            os.remove(log_file)
            print(f"Deleted log file: {log_file}")
        except Exception as e:
            print(f"Error deleting log file {log_file}: {e}")


class VirtualMachine:
    def __init__(self, vm_id, port, peer_info):
        """
        vm_id: an identifier for this virtual machine.
        port: the port number on which this VM will listen.
        peer_info: a dict mapping peer IDs to (ip, port) tuples.
        """
        self.vm_id = vm_id
        self.port = port
        self.peer_info = peer_info  # Peers: {peer_id: (ip, port)}
        self.clock_rate = random.randint(1, 6)
        self.logical_clock = 0
        self.message_queue = queue.Queue()
        self.running = True

        # Open a log file for writing events.
        self.log_file = open(f"vm_{vm_id}.log", "a")

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
                # No message received; generate an event.
                event = random.randint(1, 10)
                if event == 1:
                    # Send to first peer (lowest peer id).
                    peer_id = sorted(self.peer_info.keys())[0]
                    message = {"sender": self.vm_id, "clock": self.logical_clock}
                    self.send_message(peer_id, message)
                    with self.lock:
                        self.logical_clock += 1
                    self.update_log(f"SEND to {peer_id}")
                elif event == 2:
                    # Send to second peer (if exists, otherwise the only one).
                    peer_ids = sorted(self.peer_info.keys())
                    peer_id = peer_ids[1] if len(peer_ids) > 1 else peer_ids[0]
                    message = {"sender": self.vm_id, "clock": self.logical_clock}
                    self.send_message(peer_id, message)
                    with self.lock:
                        self.logical_clock += 1
                    self.update_log(f"SEND to {peer_id}")
                elif event == 3:
                    # Send to both peers.
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


def main():
    # Configuration for 3 virtual machines:
    # Each VM is defined by its unique id and the port it will listen on.
    config = {
        1: ("localhost", 10001),
        2: ("localhost", 10002),
        3: ("localhost", 10003),
    }

    # Create VirtualMachine instances.
    vms = {}
    for vm_id in config.keys():
        # Peers: all other VMs.
        peers = {peer_id: addr for peer_id, addr in config.items() if peer_id != vm_id}
        vm = VirtualMachine(vm_id, config[vm_id][1], peers)
        vms[vm_id] = vm

    # Start each VM in its own thread.
    threads = []
    for vm in vms.values():
        t = threading.Thread(target=vm.run, daemon=True)
        t.start()
        threads.append(t)

    # Let the simulation run for 60 seconds.
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        print("Simulation interrupted by user.")

    # Stop all virtual machines.
    for vm in vms.values():
        vm.stop()

    # Wait for all threads to finish.
    for t in threads:
        t.join()


if __name__ == "__main__":
    delete_log_files()
    main()

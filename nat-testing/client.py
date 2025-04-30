# client.py
import socket
import threading
import json
import time
import logging
import argparse
import random
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class P2PClient:
    def __init__(self, server_host, server_port, client_id=None):
        self.server_host = server_host
        self.server_port = server_port
        self.client_id = client_id or f"client_{random.randint(1000, 9999)}"

        # Server connection
        self.server_socket = None

        # P2P connections
        self.p2p_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.p2p_port = random.randint(10000, 65000)
        self.p2p_socket.bind(('0.0.0.0', self.p2p_port))

        # Keep track of peers
        self.peers = {}  # {peer_id: (ip, port)}

        # Public IP and port as seen by the server
        self.public_ip = None
        self.public_port = None

        logging.info(f"Initialized client {self.client_id} listening on UDP port {self.p2p_port}")

    def connect_to_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.connect((self.server_host, self.server_port))
            logging.info(f"Connected to server at {self.server_host}:{self.server_port}")

            # Register with the server
            self.send_to_server({
                'type': 'register',
                'client_id': self.client_id,
                'local_port': self.p2p_port
            })

            # Start listening for server messages
            server_thread = threading.Thread(target=self.listen_to_server)
            server_thread.daemon = True
            server_thread.start()

            return True
        except Exception as e:
            logging.error(f"Failed to connect to server: {e}")
            return False

    def listen_to_server(self):
        try:
            while True:
                data = self.server_socket.recv(1024)
                if not data:
                    logging.info("Disconnected from server")
                    break

                message = json.loads(data.decode('utf-8'))
                self.process_server_message(message)
        except Exception as e:
            logging.error(f"Server connection error: {e}")
        finally:
            self.server_socket.close()

    def process_server_message(self, message):
        msg_type = message.get('type')

        if msg_type == 'register_ack':
            self.public_ip = message.get('public_ip')
            self.public_port = message.get('public_port')
            logging.info(f"Registered with server. Public address: {self.public_ip}:{self.public_port}")

        elif msg_type == 'client_list':
            clients = message.get('clients', [])
            if clients:
                logging.info(f"Available clients: {', '.join(clients)}")
            else:
                logging.info("No other clients available")

        elif msg_type == 'connection_request':
            from_id = message.get('from_id')
            public_ip = message.get('public_ip')
            public_port = message.get('public_port')
            local_port = message.get('local_port')

            logging.info(f"Connection request from {from_id} ({public_ip}:{public_port})")

            # Auto-accept for this example (in a real app, you might prompt the user)
            accept = True

            self.send_to_server({
                'type': 'connection_response',
                'to_id': from_id,
                'accept': accept
            })

            if accept:
                # Start hole punching process
                self.initiate_hole_punching(from_id, public_ip, public_port, local_port)

        elif msg_type == 'connection_accepted':
            target_id = message.get('target_id')
            public_ip = message.get('public_ip')
            public_port = message.get('public_port')
            local_port = message.get('local_port')

            logging.info(f"Connection accepted by {target_id} ({public_ip}:{public_port})")

            # Start hole punching process
            self.initiate_hole_punching(target_id, public_ip, public_port, local_port)

        elif msg_type == 'connection_rejected':
            target_id = message.get('target_id')
            logging.info(f"Connection rejected by {target_id}")

        elif msg_type == 'error':
            logging.error(f"Server error: {message.get('message')}")

    def initiate_hole_punching(self, peer_id, public_ip, public_port, local_port):
        """Attempt to establish direct connection through NAT hole punching"""
        # Try multiple endpoints - public and possibly local if on same network
        endpoints = [
            (public_ip, int(public_port)),  # Public endpoint
            (public_ip, int(local_port))   # Possible direct local endpoint
        ]

        # Create a new thread for hole punching
        punch_thread = threading.Thread(
            target=self.hole_punching_process,
            args=(peer_id, endpoints)
        )
        punch_thread.daemon = True
        punch_thread.start()

    def hole_punching_process(self, peer_id, endpoints):
        """Try to establish connection with peer by sending UDP packets to potential endpoints"""
        logging.info(f"Starting hole punching with {peer_id}")

        # Send initial packets to create NAT mapping
        for i, endpoint in enumerate(endpoints):
            try:
                punch_message = {
                    'type': 'punch',
                    'client_id': self.client_id,
                    'endpoint_index': i
                }
                logging.info(f"Sending punch packet to {endpoint}")
                self.p2p_socket.sendto(json.dumps(punch_message).encode('utf-8'), endpoint)
            except Exception as e:
                logging.error(f"Error sending to endpoint {endpoint}: {e}")

        # Continue sending periodically
        attempts = 0
        while attempts < 20 and peer_id not in self.peers:
            for i, endpoint in enumerate(endpoints):
                try:
                    punch_message = {
                        'type': 'punch',
                        'client_id': self.client_id,
                        'attempt': attempts,
                        'endpoint_index': i
                    }
                    self.p2p_socket.sendto(json.dumps(punch_message).encode('utf-8'), endpoint)
                except:
                    pass

            time.sleep(0.5)
            attempts += 1

        if peer_id in self.peers:
            logging.info(f"Successfully established connection with {peer_id}")
        else:
            logging.info(f"Failed to establish connection with {peer_id} after {attempts} attempts")

    def start_p2p_listener(self):
        """Listen for incoming P2P messages"""
        p2p_thread = threading.Thread(target=self.listen_for_p2p)
        p2p_thread.daemon = True
        p2p_thread.start()

    def listen_for_p2p(self):
        """Listen for incoming UDP packets"""
        try:
            while True:
                try:
                    data, addr = self.p2p_socket.recvfrom(1024)
                    message = json.loads(data.decode('utf-8'))
                    self.process_p2p_message(message, addr)
                except json.JSONDecodeError:
                    logging.warning(f"Received invalid JSON from {addr}")
                except Exception as e:
                    logging.error(f"Error in P2P listener: {e}")
        except Exception as e:
            logging.error(f"P2P socket error: {e}")

    def process_p2p_message(self, message, addr):
        msg_type = message.get('type')

        if msg_type == 'punch':
            peer_id = message.get('client_id')
            logging.info(f"Received punch packet from {peer_id} at {addr}")

            # Record peer's address
            self.peers[peer_id] = addr

            # Send acknowledgement
            ack_message = {
                'type': 'punch_ack',
                'client_id': self.client_id
            }
            self.p2p_socket.sendto(json.dumps(ack_message).encode('utf-8'), addr)

        elif msg_type == 'punch_ack':
            peer_id = message.get('client_id')
            logging.info(f"Received punch acknowledgement from {peer_id} at {addr}")

            # Record peer's address if not already done
            if peer_id not in self.peers:
                self.peers[peer_id] = addr

        elif msg_type == 'message':
            peer_id = message.get('client_id')
            content = message.get('content')

            if peer_id not in self.peers:
                self.peers[peer_id] = addr

            logging.info(f"Message from {peer_id}: {content}")

    def send_to_server(self, message):
        """Send a message to the server"""
        try:
            self.server_socket.send(json.dumps(message).encode('utf-8'))
        except Exception as e:
            logging.error(f"Error sending to server: {e}")

    def list_clients(self):
        """Request a list of available clients from the server"""
        self.send_to_server({
            'type': 'list_clients',
            'client_id': self.client_id
        })

    def request_connection(self, target_id):
        """Request connection to another client"""
        logging.info(f"Requesting connection to {target_id}")
        self.send_to_server({
            'type': 'connect_request',
            'client_id': self.client_id,
            'target_id': target_id
        })

    def send_p2p_message(self, peer_id, content):
        """Send a direct message to a peer"""
        if peer_id in self.peers:
            try:
                message = {
                    'type': 'message',
                    'client_id': self.client_id,
                    'content': content
                }
                self.p2p_socket.sendto(json.dumps(message).encode('utf-8'), self.peers[peer_id])
                logging.info(f"Sent message to {peer_id}")
                return True
            except Exception as e:
                logging.error(f"Error sending P2P message: {e}")
                return False
        else:
            logging.error(f"Peer {peer_id} not connected")
            return False

    def close(self):
        """Close all connections"""
        if self.server_socket:
            self.server_socket.close()
        if self.p2p_socket:
            self.p2p_socket.close()


# client_cli.py
def main():
    parser = argparse.ArgumentParser(description='P2P Client')
    parser.add_argument('--server', default='65.21.183.166', help='Server hostname/IP')
    parser.add_argument('--port', type=int, default=9999, help='Server port')
    parser.add_argument('--id', help='Client ID (optional)')

    args = parser.parse_args()

    client = P2PClient(args.server, args.port, args.id)

    # Start P2P listener
    client.start_p2p_listener()

    # Connect to server
    if not client.connect_to_server():
        logging.error("Failed to connect to server. Exiting.")
        sys.exit(1)

    print(f"\nP2P Client {client.client_id}")
    print("Commands:")
    print("  list - List available clients")
    print("  connect <client_id> - Request connection to another client")
    print("  send <client_id> <message> - Send message to connected peer")
    print("  peers - Show connected peers")
    print("  exit - Exit the application")

    try:
        while True:
            cmd = input("\nEnter command: ").strip()

            if not cmd:
                continue

            parts = cmd.split(' ', 2)
            command = parts[0].lower()

            if command == 'exit':
                break

            elif command == 'list':
                client.list_clients()

            elif command == 'connect' and len(parts) > 1:
                target_id = parts[1]
                client.request_connection(target_id)

            elif command == 'send' and len(parts) > 2:
                peer_id = parts[1]
                message = parts[2]
                if client.send_p2p_message(peer_id, message):
                    print(f"Message sent to {peer_id}")
                else:
                    print(f"Failed to send message. Is {peer_id} connected?")

            elif command == 'peers':
                if client.peers:
                    print("Connected peers:")
                    for peer_id, addr in client.peers.items():
                        print(f"  {peer_id}: {addr[0]}:{addr[1]}")
                else:
                    print("No connected peers")

            else:
                print("Unknown command")

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        client.close()

if __name__ == "__main__":
    main()
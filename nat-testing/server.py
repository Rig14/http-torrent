# server.py
import socket
import threading
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NATTraversalServer:
    def __init__(self, host='0.0.0.0', port=9999):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}  # {client_id: {'conn': conn, 'addr': addr, 'public_ip': ip, 'public_port': port}}
        self.pending_connections = {}  # {initiator_id: target_id}

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logging.info(f"Server started on {self.host}:{self.port}")

        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            logging.info("Server shutting down...")
        finally:
            self.server_socket.close()

    def handle_client(self, client_socket, client_address):
        logging.info(f"New connection from {client_address}")
        try:
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break

                message = json.loads(data.decode('utf-8'))
                self.process_message(client_socket, client_address, message)
        except Exception as e:
            logging.error(f"Error handling client: {e}")
        finally:
            # Remove client from active clients
            for client_id, client_info in list(self.clients.items()):
                if client_info['conn'] == client_socket:
                    del self.clients[client_id]
                    logging.info(f"Client {client_id} disconnected")
                    break
            client_socket.close()

    def process_message(self, client_socket, client_address, message):
        msg_type = message.get('type')
        client_id = message.get('client_id')

        if msg_type == 'register':
            # Register the client with their ID
            public_ip = client_address[0]
            public_port = message.get('local_port')  # The port they're listening on

            self.clients[client_id] = {
                'conn': client_socket,
                'addr': client_address,
                'public_ip': public_ip,
                'public_port': public_port
            }

            response = {
                'type': 'register_ack',
                'public_ip': public_ip,
                'public_port': client_address[1]  # The port as seen by the server
            }
            client_socket.send(json.dumps(response).encode('utf-8'))
            logging.info(f"Registered client {client_id} with public address {public_ip}:{client_address[1]}")

        elif msg_type == 'list_clients':
            # Send list of available clients
            available_clients = [id for id in self.clients.keys() if id != client_id]
            response = {
                'type': 'client_list',
                'clients': available_clients
            }
            client_socket.send(json.dumps(response).encode('utf-8'))

        elif msg_type == 'connect_request':
            # Client wants to connect to another client
            target_id = message.get('target_id')

            if target_id in self.clients:
                initiator_info = self.clients[client_id]
                target_info = self.clients[target_id]

                # Store the connection request
                self.pending_connections[client_id] = target_id

                # Send connection info to the target
                connection_request = {
                    'type': 'connection_request',
                    'from_id': client_id,
                    'public_ip': initiator_info['public_ip'],
                    'public_port': initiator_info['addr'][1],
                    'local_port': initiator_info['public_port']
                }
                target_info['conn'].send(json.dumps(connection_request).encode('utf-8'))
                logging.info(f"Connection request from {client_id} to {target_id}")
            else:
                # Target client not found
                response = {
                    'type': 'error',
                    'message': f"Client {target_id} not found or offline"
                }
                client_socket.send(json.dumps(response).encode('utf-8'))

        elif msg_type == 'connection_response':
            # Client is responding to a connection request
            initiator_id = message.get('to_id')
            accepted = message.get('accept', False)

            if initiator_id in self.clients and initiator_id in self.pending_connections:
                if accepted:
                    responder_info = self.clients[client_id]

                    # Send connection details to the initiator
                    connection_info = {
                        'type': 'connection_accepted',
                        'target_id': client_id,
                        'public_ip': responder_info['public_ip'],
                        'public_port': responder_info['addr'][1],
                        'local_port': responder_info['public_port']
                    }
                    self.clients[initiator_id]['conn'].send(json.dumps(connection_info).encode('utf-8'))
                    logging.info(f"Connection accepted between {initiator_id} and {client_id}")
                else:
                    # Connection rejected
                    rejection = {
                        'type': 'connection_rejected',
                        'target_id': client_id
                    }
                    self.clients[initiator_id]['conn'].send(json.dumps(rejection).encode('utf-8'))

                # Clear the pending connection
                del self.pending_connections[initiator_id]
            else:
                logging.warning(f"Invalid connection response from {client_id}")

if __name__ == "__main__":
    server = NATTraversalServer()
    server.start()
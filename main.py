import sys
from ensurepip import bootstrap
from http.server import HTTPServer
from threading import Thread

from nodes import NodeManager, Node, update_nodes_daemon
from routes import Handler

PORT = int(sys.argv[1])
HOST = "localhost"

# represents this instance of the app
instance_node = Node()
instance_node.port = PORT
instance_node.host = HOST

# bootstrap node (every node starts from here)
bootstrap_node = Node()
bootstrap_node.port = 8000
bootstrap_node.host = "localhost"


def start_server(host: str, port: int):
    # to regularly update the known nodes
    node_manager = NodeManager()
    node_manager.set_instance_node(instance_node)
    node_manager.add_node_to_check(bootstrap_node)
    Thread(target=update_nodes_daemon).start()

    server = HTTPServer((host, port), Handler)
    print(f"Server is starting on host {host} port {port}...")
    server.serve_forever()


if __name__ == "__main__":
    start_server(HOST, PORT)
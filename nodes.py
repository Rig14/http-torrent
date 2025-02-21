import json
import time
import urllib.parse
from collections import Counter
from datetime import datetime
from queue import PriorityQueue, Queue

import requests

from util import ThreadSafeUniquePriorityQueue


class Node:
    host: str
    port: int
    last_checked: datetime = datetime.now()

    def as_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "last_checked": self.last_checked.isoformat()
        }

    @staticmethod
    def from_dict(node_dict):
        node = Node()
        node.host = str(node_dict["host"])
        node.port = int(node_dict["port"])
        node.last_checked = datetime.fromisoformat(
            node_dict["last_checked"] if "last_checked" in node_dict else datetime.now().isoformat()
        )
        return node

    def __lt__(self, other):
        return self.last_checked < other.last_checked

    def __eq__(self, other):
        return self.host == other.host and self.port == other.port

    def __hash__(self):
        return hash((self.host, self.port))



class NodeManager:
    """Manages nodes in the network."""

    """
    Priority queue that holds nodes to check.
    Priority is based on the last time the node was checked.
    Checked long time ago -> high priority
    """
    _nodes_to_check = ThreadSafeUniquePriorityQueue()

    _known_nodes: set[Node] = set()

    """
    Node that represents this running instance of the program
    """
    _instance_node: Node | None = None

    def __new__(cls):
        """Makes this class a Singleton type"""
        if not hasattr(cls, 'instance'):
            cls.instance = super(NodeManager, cls).__new__(cls)
        return cls.instance

    def set_instance_node(self, node: Node):
        assert self._instance_node is None, "Instance node is already set"
        self._instance_node = node

    def get_instance_node(self) -> Node:
        return self._instance_node

    def add_node_to_check(self, node: Node):
        if node == self._instance_node: return
        self._nodes_to_check.enqueue(node, node.last_checked)

    def get_known_nodes_as_json(self):
        return json.dumps([node.as_dict() for node in self._known_nodes])

    def check_next_node(self):
        if self._nodes_to_check.is_empty(): return
        print("There is currently", self._nodes_to_check.size(), "nodes to check. Known nodes size is ", len(self._known_nodes))

        node = self._nodes_to_check.dequeue()
        print(f"Checking node {node.host}:{node.port}")

        # construct address request URL to check if node is reachable
        url = f"http://{node.host}:{node.port}/addr?"
        params = {"host": self._instance_node.host, "port": self._instance_node.port}
        response = requests.get(url + urllib.parse.urlencode(params))

        if response.status_code != 200:
            print("Node at {node.host}:{node.port} is not reachable.")
            print("Removing node from known nodes.")
            self._known_nodes.remove(node)
            return

        # add requested node to known nodes and to be checked
        node.last_checked = datetime.now()
        self._known_nodes.add(node)

        # add the nodes known to requested node to the queue
        known_nodes = [Node.from_dict(x) for x in json.loads(response.content)]
        for known_node in known_nodes:
            if known_node == node: continue
            self.add_node_to_check(known_node)






def update_nodes_daemon():
    node_manager = NodeManager()
    while True:
        time.sleep(1)
        node_manager.check_next_node()



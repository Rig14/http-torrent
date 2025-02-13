import json
from datetime import datetime

import requests

class Node:
    host: str
    port: int
    last_checked: datetime

nodes: list[Node] = []

def get_known_nodes_as_json() -> str:
    return json.dumps({
        "nodes": nodes
    })

def request_known_nodes_from(node: Node) -> list[Node]:
    response = requests.get(f"http://{node.host}:{node.port}/addr")
    data = json.loads(response.content)
    return data["nodes"]


import asyncio
import json
import logging
import pickle
import base64
import socket
from typing import Any, Dict, Optional, Tuple, Union, List
from kademlia.network import Server


class KademliaDHT:
    """
    A wrapper around Kademlia DHT that supports storing and retrieving complex Python objects.
    """

    def __init__(self, listen_port: int = 8468, bootstrap_nodes: Optional[List[Tuple[str, int]]] = None):
        """
        Initialize a KademliaComplexStore instance.

        Args:
            listen_port: Port to listen on for Kademlia DHT communication
            bootstrap_nodes: List of (host, port) tuples for bootstrapping the Kademlia network
        """
        self.server = Server()
        self.listen_port = listen_port
        self.bootstrap_nodes = bootstrap_nodes or []
        self._loop = None

    async def start(self) -> None:
        """Start the Kademlia server and bootstrap the network."""
        await self.server.listen(self.listen_port)

        if self.bootstrap_nodes:
            for host, port in self.bootstrap_nodes:
                await self.server.bootstrap([(host, port)])

        print(f"Kademlia DHT server running on port {self.listen_port} host {self.get_node_address()[0]}")

    async def stop(self) -> None:
        """Stop the Kademlia server."""
        self.server.stop()

    def get_node_address(self) -> Tuple[str, int]:
        """
        Get this node's network address information that can be shared with other nodes.

        Returns:
            Tuple of (host_ip, port) that can be used for bootstrapping
        """
        # Get the local IP address
        # This gets a connection to an external site without actually sending data
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Connect to Google DNS
            host_ip = s.getsockname()[0]
            s.close()
        except:
            # Fallback to localhost if we can't determine external IP
            host_ip = "127.0.0.1"

        return (host_ip, self.listen_port)

    def _serialize_value(self, value: Any) -> str:
        """
        Serialize a value to store in the DHT.

        Args:
            value: Any Python object to serialize

        Returns:
            Serialized string representation of the value
        """
        try:
            # First try JSON serialization for simpler objects (strings, numbers, lists, dicts)
            serialized = {
                'type': 'json',
                'data': json.dumps(value)
            }
            return json.dumps(serialized)
        except (TypeError, OverflowError, ValueError):
            # Fall back to pickle for more complex objects
            # Note: Custom classes won't be fully supported across different code bases
            # unless the class definition is identical on all nodes
            pickle_bytes = pickle.dumps(value)
            base64_str = base64.b64encode(pickle_bytes).decode('utf-8')
            serialized = {
                'type': 'pickle',
                'data': base64_str
            }
            return json.dumps(serialized)

    def _deserialize_value(self, serialized_value: str) -> Any:
        """
        Deserialize a value retrieved from the DHT.

        Args:
            serialized_value: Serialized string from the DHT

        Returns:
            The original Python object
        """
        container = json.loads(serialized_value)

        if container['type'] == 'json':
            return json.loads(container['data'])
        elif container['type'] == 'pickle':
            pickle_bytes = base64.b64decode(container['data'].encode('utf-8'))
            return pickle.loads(pickle_bytes)
        else:
            raise ValueError(f"Unknown serialization type: {container['type']}")

    async def set(self, key: str, value: Any) -> bool:
        """
        Store a key-value pair in the DHT. The value can be any serializable Python object.

        Args:
            key: String key to store the value under
            value: Any Python object to store

        Returns:
            True if the operation was successful
        """
        serialized_value = self._serialize_value(value)
        return await self.server.set(key, serialized_value)

    async def get(self, key: str) -> Any:
        """
        Retrieve a value from the DHT.

        Args:
            key: String key to retrieve

        Returns:
            The original Python object or None if key not found
        """
        result = await self.server.get(key)
        if result is not None:
            return self._deserialize_value(result)
        return None

    def run(self, callback=None):
        """
        Run the Kademlia server in the current thread.

        Args:
            callback: Optional callback function to run after server starts
        """
        self._loop = asyncio.get_event_loop()

        async def _run():
            await self.start()
            if callback:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self)
                else:
                    callback(self)

        try:
            self._loop.run_until_complete(_run())
            self._loop.run_forever()
        except KeyboardInterrupt:
            print("Shutting down Kademlia server...")
        finally:
            self._loop.run_until_complete(self.stop())
            self._loop.close()


# Example usage
async def example():
    # Create two nodes in the same network
    node1 = KademliaDHT(listen_port=8468)
    await node1.start()

    # Get node1's address info
    node1_address = node1.get_node_address()
    print(f"Node 1 address for bootstrapping: {node1_address}")

    # Let's wait a moment for node1 to start
    await asyncio.sleep(1)

    # Create a second node that bootstraps from the first
    node2 = KademliaDHT(
        listen_port=8469,
        bootstrap_nodes=[node1_address]  # Using the address from node1
    )
    await node2.start()

    print(f"Node 2 address: {node2.get_node_address()}")

    # Wait for bootstrap
    await asyncio.sleep(2)

    # Store different types of values
    print("Setting values...")

    # Simple types
    await node1.set('string_key', 'Hello, Kademlia!')
    await node1.set('int_key', 42)
    await node1.set('float_key', 3.14159)

    # Complex types
    await node1.set('list_key', [1, 2, 3, 4, 5])
    await node1.set('dict_key', {
        'name': 'Alice',
        'age': 30,
        'metrics': {
            'score': 95.2,
            'active_days': 127,
            'achievements': ['first_post', 'top_contributor']
        }
    })

    # Nested complex data
    complex_data = {
        'users': [
            {'id': 1, 'name': 'Alex', 'tags': ['admin', 'developer']},
            {'id': 2, 'name': 'Taylor', 'tags': ['moderator']}
        ],
        'settings': {
            'public': True,
            'notification_types': ['email', 'push'],
            'limits': {'max_storage': 500, 'max_users': 50}
        }
    }
    await node1.set('complex_key', complex_data)

    # Wait for values to propagate through the network
    await asyncio.sleep(2)

    # Retrieve values from node2
    print("\nRetrieving values from different node...")
    print(f"string_key: {await node2.get('string_key')}")
    print(f"int_key: {await node2.get('int_key')}")
    print(f"float_key: {await node2.get('float_key')}")
    print(f"list_key: {await node2.get('list_key')}")
    print(f"dict_key: {await node2.get('dict_key')}")
    print(f"complex_key: {await node2.get('complex_key')}")

    # Cleanup
    await node1.stop()
    await node2.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Run the example
    asyncio.run(example())
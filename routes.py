from http.server import BaseHTTPRequestHandler
import urllib.parse as urlparse

from nodes import NodeManager, Node


class Handler(BaseHTTPRequestHandler):
    _node_manager = NodeManager()

    def version_string(self):
        # Server header value
        return "http-torrent-v0.1"

    def do_GET(self):
        parsed_url = urlparse.urlparse(self.path)
        path = parsed_url.path
        query = urlparse.parse_qs(parsed_url.query)

        content: bytes = "404 Not Found.".encode("UTF-8")
        status: int = 404
        headers: list[tuple[str, str]] = []

        # ROUTES
        if path == "/addr":
            host = query.get("host", None)
            port = query.get("port", None)
            # add incoming host and port for checking
            if host and port:
                node = Node.from_dict({"host": host[0], "port": port[0]})
                if node != self._node_manager.get_instance_node():
                    self._node_manager.add_node_to_check(node)

            # return all addresses that are know to this node
            status = 200
            headers.append(("Content-Type", "application/json"))
            content = self._node_manager.get_known_nodes_as_json().encode("UTF-8")


        # SENDING
        self.send_response(status)
        for header in headers: self.send_header(header[0], header[1])
        self.end_headers()
        self.wfile.write(content)
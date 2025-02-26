from http.server import BaseHTTPRequestHandler
import urllib.parse as urlparse

from nodes import get_known_nodes_as_json


class Handler(BaseHTTPRequestHandler):

    def version_string(self):
        # Server header value
        return "http-torrent-v0.1"

    def do_GET(self):
        parsed_url = urlparse.urlparse(self.path)

        content: bytes = "404 Not Found.".encode("UTF-8")
        status: int = 404
        headers: list[tuple[str, str]] = []

        # ROUTES
        if parsed_url.path == "/heartbeat":
            status = 200
            content = "Service is running".encode("UTF-8")
        if parsed_url.path == "/addr":
            status = 200
            headers.append(("Content-Type", "application/json"))
            content = get_known_nodes_as_json().encode("UTF-8")

        # SENDING
        self.send_response(status)
        for header in headers: self.send_header(header[0], header[1])
        self.end_headers()
        self.wfile.write(content)


    def do_POST(self):
        parsed_url = urlparse.urlparse(self.path)

        content: bytes = "404 Not Found.".encode("UTF-8")
        status: int = 404
        headers: list[tuple[str, str]] = []

        # ROUTES

        # SENDING
        self.send_response(status)
        for header in headers: self.send_header(header[0], header[1])
        self.end_headers()
        self.wfile.write(content)
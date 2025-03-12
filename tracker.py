import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from random import shuffle
from threading import Thread
import urllib.parse as urlparse
import sys

from util import get_ip

class Client:
    host: str
    port: str


class Tracker:
    def __init__(self, port: int, serve_forever: bool = False):
        self.host: str = get_ip()
        self.port: int = port
        self.chunk_client_registry: dict[str, list[Client]] = {}

        Thread(target=self.start_http_listener, daemon=True).start()
        print(f"Tracker server started on {self.host}:{self.port}")

        if serve_forever:
            while True:
                pass

    def start_http_listener(self):
        tracker = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                parsed_url = urlparse.urlparse(self.path)

                content: str = "404 Not Found."
                status: int = 404
                headers: list[tuple[str, str]] = []
                request_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))

                # ROUTES
                if parsed_url.path == "/chunk":
                    try:
                        hashes = json.loads(request_body)
                        max_hashes_per_client = len(hashes) // 4

                        response = []
                        for h in hashes:
                            if h not in tracker.chunk_client_registry: raise Exception(f"Chunk ({h}) not registered in tracker")
                        
                            clients = tracker.chunk_client_registry.get(h)
                            shuffle(clients)
                            if len(clients) <= 0:
                                continue

                            # check if already found client can handle the hash also (less strain on the network)
                            added = False
                            for r in response:
                                if r["client"] in clients and len(r["hashes"]) <= max_hashes_per_client:
                                    r["hashes"].append(h)
                                    added = True
                                    break

                            if not added:
                                response.append({"client": clients[0], "hashes": [h]})

                        content = json.dumps([
                            {
                                "client_host": x["client"].host,
                                "client_port": x["client"].port,
                                "hash_list": x["hashes"]
                            } for x in response
                        ])
                        status = 200


                    except Exception as e:
                        print("Could not parse chunk request", e)
                        status = 400
                        content = f"Could not parse chunk request. {e}"

                # SENDING
                self.send_response(status)
                for header in headers: self.send_header(header[0], header[1])
                self.end_headers()
                self.wfile.write(content.encode("UTF-8"))

            def do_PUT(self):
                parsed_url = urlparse.urlparse(self.path)
                content: str = "404 Not Found."
                status: int = 404
                headers: list[tuple[str, str]] = []
                request_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))

                # ROUTES
                if parsed_url.path == "/chunk":
                    try:
                        j = json.loads(request_body)
                                        
                        hashes = j["hashes"]
                        client = Client()
                        client.host = j["client_host"]
                        client.port = j["client_port"]

                        for h in hashes:
                            # if h not in tracker.chunk_client_registry: raise Exception(f"Chunk ({h}) not registered in tracker")
                            if h not in tracker.chunk_client_registry:
                                tracker.chunk_client_registry[h] = [client]
                            else:
                                clients = tracker.chunk_client_registry.get(h)
                                clients.append(client)
                            print(tracker.chunk_client_registry)

                        content = "Ok"
                        status = 200
                    except Exception as e:
                        content = f"Error parsing torrent file from request body {e}"
                        status = 400
                        print("Error parsing torrent file from request body", e)

                # SENDING
                self.send_response(status)
                for header in headers: self.send_header(header[0], header[1])
                self.end_headers()
                self.wfile.write(content.encode("UTF-8"))

        server = HTTPServer((self.host, self.port), Handler)
        server.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1])
    Tracker(port, serve_forever=True)

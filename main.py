import threading
from http.server import HTTPServer

import requests

from routes import Handler

def start_server(host: str="", port: int = 8000):
    server = HTTPServer((host, port), Handler)
    print(f"Server is starting on host {host} port {port}...")
    server.serve_forever()

def start_client():
    while True:
        a = input("input ")
        print(a)

if __name__ == "__main__":
    port = 8000 # find_free_port()
    host = "localhost"

    # define threads
    server_thread = threading.Thread(target=start_server, args=(host, port))
    client_thread = threading.Thread(target=start_client)

    # start the threads
    server_thread.start()
    while True:
        # wait for server to start the client
        result = requests.get(f"http://{host}:{port}/heartbeat")
        if result.status_code == 200:
            print(f"Server has started on host {host} port {port}")
            print("Starting client CLI")
            client_thread.start()
            break
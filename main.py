from http.server import HTTPServer
from routes import Handler

def start_server(host: str="", port: int = 8000):
    server = HTTPServer((host, port), Handler)
    print(f"Server is starting on host {host} port {port}...")
    server.serve_forever()


if __name__ == "__main__":
    port = 8000 # find_free_port()
    host = "localhost"

    server = HTTPServer(("", port), Handler)
    print("Server is starting...")
    server.serve_forever()
from http.server import HTTPServer
from routes import Handler

if __name__ == "__main__":
    port = 8000 # find_free_port()
    server = HTTPServer(("", port), Handler)
    print(f"Server has started on localhost port {port}")
    server.serve_forever()
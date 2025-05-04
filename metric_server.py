import time
from threading import Thread

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

class Client:
    client_host: str
    client_port: int

    def __hash__(self):
        return hash((self.client_host, self.client_port))

    def __eq__(self, other):
        return self.client_host == other.client_host and self.client_port == other.client_port

class ClientMetrics:
    downloaded_chunks: int
    uploaded_chunks: int
    total_chunks: int
    chunk_size: int
    dht_peers: int
    dht_enabled: bool


metrics: dict[Client, ClientMetrics] = {}
last_updated: dict[Client, float] = {}
@app.route("/")
def hello_world():
    return render_template("dashboard.html")

@app.get("/metrics")
def get_metrics():
    """
    [
        {
            "client": "12.45.21.23:2234",
            "downloaded_chunks": 10,
            "uploaded_chunks": 20,
            "total_chunks": 100,
            "chunk_size": 128,
            "dht_peers": 10,
            "dht_enabled": true
        },
        ...
    ]
    """
    update_clients()

    return jsonify([{
        "client": f"{client.client_host}:{client.client_port}",
        "downloaded_chunks": metrics[client].downloaded_chunks,
        "uploaded_chunks": metrics[client].uploaded_chunks,
        "total_chunks": metrics[client].total_chunks,
        "chunk_size": metrics[client].chunk_size,
        "dht_peers": metrics[client].dht_peers,
        "dht_enabled": metrics[client].dht_enabled
    } for client in metrics])

######################
# ENDPOINT FOR USE BY CLIENTS (TORRENT CLIENT WILL CALL THEM)
######################

@app.post("/metrics")
def post_metrics():
    """
    {
        "client_host": "12.4.23.111",
        "client_port": 1234,
        "downloaded_chunks": 10,
        "uploaded_chunks": 20,
        "total_chunks": 100,
        "chunk_size": 128,
        "dht_peers": 10
        "dht_enabled": true
    }
    """
    j = request.get_json()

    client = Client()
    client.client_host = j["client_host"]
    client.client_port = j["client_port"]

    if client not in metrics:
        metrics[client] = ClientMetrics()

    metrics[client].downloaded_chunks = j["downloaded_chunks"]
    metrics[client].uploaded_chunks = j["uploaded_chunks"]
    metrics[client].total_chunks = j["total_chunks"]
    metrics[client].chunk_size = j["chunk_size"]
    metrics[client].dht_peers = j["dht_peers"]
    metrics[client].dht_enabled = j["dht_enabled"]

    last_updated[client] = time.time()

    return "Ok"


def update_clients():
    for k, v in last_updated.items():
        if time.time() - v > 15:
            del metrics[k]
            del last_updated[k]

if __name__ == "__main__":
    app.run(port=8080)





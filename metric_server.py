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


metrics: dict[Client, ClientMetrics] = {}
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
            "total_chunks": 100
        },
        ...
    ]
    """
    return jsonify([{
        "client": f"{client.client_host}:{client.client_port}",
        "downloaded_chunks": metrics[client].downloaded_chunks,
        "uploaded_chunks": metrics[client].uploaded_chunks,
        "total_chunks": metrics[client].total_chunks
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
        "total_chunks": 100
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

    return "Ok"









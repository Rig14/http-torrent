# HTTP-Torrent

A simple P2P BitTorrent-like file sharing system implemented with HTTP protocol and Distributed Hash Table (DHT) support.

## Technologies Used

- **Python 3**: Core programming language
- **Flask**: Web framework for the metrics server
- **HTTP Server**: Native Python http.server for client and tracker communication
- **Kademlia**: Implementation of the Kademlia distributed hash table for P2P functionality
- **TailwindCSS**: Frontend styling for the metrics dashboard

## Components

### 1. Torrentify

Tool for generating torrent metadata files from source files.

### 2. Tracker

Central coordinator that maintains a registry of which clients have which file chunks.

### 3. Client

P2P client that downloads chunks from peers and shares them with others.

### 4. DHT (Distributed Hash Table)

Distributed system for storing chunk location information, providing redundancy when the tracker is unavailable.

### 5. Metrics Server

Dashboard for monitoring client activity, download/upload progress, and system health.

## Communication Protocol

### Tracker-Client Communication

#### Update Tracker with Available Chunks
```
PUT /chunk
```

Request Body:
```json
{
  "client_host": "123.42.23.12",
  "client_port": 8000,
  "hashes": [
    "oc3kikx1o9x1oxo21k1x",
    "xyz123abc456def789",
    ...
  ]
}
```

Response:
```
Ok
```

#### Get Peers with Required Chunks
```
POST /chunk
```

Request Body:
```json
[
  "oc3kikx1o9x1oxo21k1x",
  "xyz123abc456def789",
  ...
]
```

Response:
```json
[
  {
    "client_host": "123.42.23.12",
    "client_port": 8000,
    "hash_list": [
      "oc3kikx1o9x1oxo21k1x",
      ...
    ]
  },
  {
    "client_host": "189.45.67.89",
    "client_port": 8001,
    "hash_list": [
      "xyz123abc456def789",
      ...
    ]
  },
  ...
]
```

#### Register DHT Node
```
POST /dht
```

Request Body:
```json
{
  "host": "123.42.23.12",
  "port": 8468
}
```

Response:
```
Ok
```

#### Get DHT Nodes
```
GET /dht
```

Response:
```json
[
  {
    "host": "123.42.23.12",
    "port": 8468
  },
  {
    "host": "189.45.67.89",
    "port": 8469
  },
  ...
]
```

### Client-Client Communication

#### Request Chunks
```
POST /chunk
```

Request Body:
```json
[
  "oc3kikx1o9x1oxo21k1x",
  "xyz123abc456def789",
  ...
]
```

Response:
```json
[
  {
    "hash": "oc3kikx1o9x1oxo21k1x",
    "content": "base64_encoded_content_here"
  },
  {
    "hash": "xyz123abc456def789",
    "content": "base64_encoded_content_here"
  },
  ...
]
```

#### Health Check
```
GET /ping
```

Response:
```
pong
```

### DHT Network Messages

The DHT implementation uses the Kademlia protocol with custom serialization for key-value storage:

#### Key-Value Operations

- **Keys**: File chunk hashes (e.g., "oc3kikx1o9x1oxo21k1x")
- **Values**: JSON stringified arrays of client addresses (e.g., `["123.42.23.12:8000", "189.45.67.89:8001"]`)

#### DHT Communication Flow

1. **Bootstrap**: New nodes contact known peers (from tracker) to join the network
2. **Store**: When a client has a chunk, it stores `chunk_hash -> ["ip:port"]` in the DHT
3. **Retrieve**: When a client needs a chunk, it queries the DHT for `chunk_hash` to get a list of peers
4. **Update**: When a client gets a new chunk, it adds itself to the list of providers for that chunk

## Metrics Server

The metrics server collects and displays real-time information about all active clients including:

- Download/upload progress
- Number of chunks downloaded/uploaded
- Total file size
- DHT status (enabled/disabled)
- Number of DHT peers
- Tracker connectivity status
- Upload/download ratio

Metrics are sent to the server every 3 seconds and displayed in a real-time dashboard at `http://localhost:8080/`.

## Usage Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate a Torrent File

```bash
python torrentify.py <your_file> <tracker_ip:port>
```

Example:
```bash
python torrentify.py example.mp4 localhost:5000
```

This generates a `torrent.json` file containing metadata about the file chunks.

### 3. Start the Tracker

```bash
python tracker.py [port_number]
```

Default port is 5000 if not specified.

### 4. Start the Metrics Server

```bash
python metric_server.py
```

Access the dashboard at http://localhost:8080

### 5. Start Clients

To start a client with the source file (seeder):
```bash
python client.py has_file [dht_enabled]
```

To start a client without the source file (leecher):
```bash
python client.py [dht_enabled]
```

Add the `dht_enabled` parameter to enable DHT functionality.

### 6. Run a Stress Test

```bash
python stress_test.py
```

This will automatically start multiple clients and simulate a P2P network environment.

## File Structure

- **client.py**: Implementation of the torrent client
- **dht.py**: Kademlia-based distributed hash table implementation
- **metric_server.py**: Monitoring dashboard server
- **torrentify.py**: Utility to create torrent metadata files
- **tracker.py**: Central tracker server implementation
- **util.py**: Helper functions for network operations
- **templates/dashboard.html**: Metrics visualization dashboard

## Fault Tolerance

The system is designed with redundancy in mind:

1. If the tracker is offline, clients can continue to discover peers through the DHT network
2. If a peer disconnects, clients automatically find alternative sources
3. Health checks remove unavailable peers from the tracker registry

## License

This project is licensed under the terms of the license included in the LICENSE file.


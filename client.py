import sys
import json
import requests
import concurrent.futures
import util
import socket
import time
import os

from hashlib import sha1
from dataclasses import dataclass, asdict
from torrentify import chunkify


@dataclass
class TorrentFileChunk:
    order_number: int
    hash: str


@dataclass
class DataChunk:
    orderNumber: int
    content: bytes


@dataclass
class Peer:
    peer_host: str
    peer_port: int
    peer_chunks: [str]


class TorrentData:
    chunks: list[TorrentFileChunk]
    tracker_url: str
    file_name: str
    file_hash: str
    chunk_size: int

    def __init__(self, torrent_file: dict):
        self.chunks = list(
            map(
                lambda x: TorrentFileChunk(x["orderNumber"], x["hash"]),
                torrent_file["chunks"],
            )
        )
        self.tracker_addr = torrent_file["trackerUrl"]
        self.file_hash = torrent_file["fileHash"]
        self.file_name = torrent_file["fileName"]
        self.chunk_size = int(torrent_file["chunkSize"])

    def __repr__(self):
        return f"Tracker: {self.tracker_addr}, Chunks length: {len(self.chunks)}, Filename {self.file_name}, File hash {self.file_hash}"


class TorrentClient:
    owned_chunks: list[DataChunk]
    needed_chunks: list[DataChunk]
    torrent_data: TorrentData
    tracker_url: str
    seed_port = 5001
    tracker_batch_size = 5
    client_ip: str
    temp_file_name: str

    def __init__(self, torrent_data: TorrentData):
        self.torrent_data = torrent_data
        self.owned_chunks = set()
        self.needed_chunks = {chunk.hash for chunk in torrent_data.chunks}
        self.client_ip = util.get_ip()
        self.tracker_url = f"http://{torrent_data.tracker_addr}/chunk"
        self.temp_file_name = os.path.join(os.getcwd(), f"{torrent_data.file_name}.tmp")

    def load_chunk(self, chunk: DataChunk):
        chunk_hash = sha1(chunk.content).hexdigest()
        if chunk_hash in self.needed_chunks:
            self.needed_chunks.remove(chunk_hash)
            self.owned_chunks.add(chunk.content)
            self.write_chunk_to_file(chunk)

    def write_chunk_to_file(self, chunk: DataChunk):
        with open(self.temp_file_name, "wb") as f:
            f.write(chunk.content)

    def fetch_chunk_from_peer(self, peer: Peer):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect((peer.peer_host, peer.peer_port))
                while True:
                    data = s.recv(torrent_data.chunk_size)
                    chunk = DataChunk(0, data)
                    self.load_chunk(chunk)
                    if not data:
                        break
                    print("Seeder sends", data)
                print("Leecher ended connection")
            except ConnectionRefusedError:
                print(f"Peer {peer} refused connection")

    def request_peers_with_chunks(self):
        for i in range(0, len(torrent_data.chunks), self.tracker_batch_size):
            chunk_batch = list(self.needed_chunks)[i : i + self.tracker_batch_size]
            chunk_batch_json = json.dumps(chunk_batch)
            resp = requests.post(self.tracker_url, chunk_batch_json)

            peer_data_json = json.loads(resp.content)
            peers = [
                Peer(
                    peer_json["client_host"],
                    peer_json["client_port"],
                    peer_json["hash_list"],
                )
                for peer_json in peer_data_json
            ]

            return peers

    def seed_chunks(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.client_ip, self.seed_port))
            s.listen()
            conn, addr = s.accept()
            with conn:
                print("Seeder connected by", addr)
                for chunk in chunkify(
                    self.torrent_data.file_name, torrent_data.chunk_size
                ):
                    print("Sending chunk: ", chunk.orderNumber)
                    conn.send(chunk.content)

    def announce_chunks_to_tracker(self):
        print("Announcing chunks to tracker")
        for i in range(0, len(torrent_data.chunks), self.tracker_batch_size):
            chunk_batch = list(self.owned_chunks)[i : i + self.tracker_batch_size]
            # print(chunk_batch)
            chunk_batch_json = json.dumps(
                {
                    "client_host": self.client_ip,
                    "client_port": self.seed_port,
                    "hashes": [sha1(chunk).hexdigest() for chunk in chunk_batch],
                }
            )
            resp = requests.put(self.tracker_url, chunk_batch_json)
            if resp.content == b"Ok":
                print("Data successfully announced to tracker")
            else:
                print("Error:", resp.content)

    def start_client(self):
        # check if i have local chunks. do that by checking if i have filename in dir
        ready_data_name = os.path.join(os.getcwd(), self.torrent_data.file_name)

        print("Starting client")

        if os.path.exists(ready_data_name):
            # assume client has the entire file
            for chunk in chunkify(
                self.torrent_data.file_name, self.torrent_data.chunk_size
            ):
                client.load_chunk(chunk)

            self.announce_chunks_to_tracker()
            self.seed_chunks()

        elif os.path.exists(self.temp_file_name):
            for chunk in chunkify(self.temp_file_name, self.torrent_data.chunk_size):
                client.load_chunk(chunk)

            peers = self.request_peers_with_chunks()
            for peer in peers:
                self.fetch_chunk_from_peer(peer)
    
            self.seed_port = util.find_free_port()
            self.announce_chunks_to_tracker()
            self.seed_chunks()
            peers = self.request_peers_with_chunks()

        else:
            # create new temp file
            open(self.temp_file_name, "w").close()
            peers = self.request_peers_with_chunks()
            for peer in peers:
                self.fetch_chunk_from_peer(peer)


def load_torrent_file(torrent_file_name: str) -> TorrentData:
    with open(torrent_file_name, "r") as f:
        torrent_data_json = json.load(f)
        torrent_data = TorrentData(torrent_data_json)

    return torrent_data


if __name__ == "__main__":
    torrent_file_name = sys.argv[1]
    torrent_data = load_torrent_file(torrent_file_name)
    client = TorrentClient(torrent_data)
    client.start_client()

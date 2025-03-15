import sys
import json
import requests
import threading
import util
import socket
import time
import random
import os

from hashlib import sha1
from dataclasses import dataclass


@dataclass
class TorrentFileChunk:
    order_number: int
    hash: str


@dataclass
class DataChunk:
    order_number: int
    content: bytes
    hash: str


@dataclass
class Peer:
    peer_host: str
    peer_port: int
    peer_chunks: [str]


class TorrentData:
    chunks: list[TorrentFileChunk] = []
    tracker_url: str
    file_name: str
    file_hash: str
    chunk_size: int
    chunk_hash_id_map: dict[str, str] = {}

    def __init__(self, torrent_file: dict):
        for chunkJson in torrent_file["chunks"]:
            torrent_file_chunk = TorrentFileChunk(chunkJson["orderNumber"], chunkJson["hash"]) 
            self.chunks.append(torrent_file_chunk)
            self.chunk_hash_id_map[chunkJson["hash"]] = chunkJson["orderNumber"]
            
        self.tracker_url = f"http://{torrent_file["trackerUrl"]}/chunk"
        self.file_hash = torrent_file["fileHash"]
        self.file_name = torrent_file["fileName"]
        self.chunk_size = int(torrent_file["chunkSize"])

    def __repr__(self):
        return f"Tracker: {self.tracker_url}, Chunks length: {len(self.chunks)}, Filename {self.file_name}, File hash {self.file_hash}"


class TorrentClient:
    owned_chunks: list[DataChunk]
    needed_chunks_hashes: set[str]
    torrent_data: TorrentData
    seed_port = 5001
    tracker_batch_size = 5
    client_ip: str
    temp_file_name: str

    def __init__(self, torrent_data: TorrentData):
        self.torrent_data = torrent_data
        self.owned_chunks = []
        self.needed_chunks_hashes = {chunk.hash for chunk in torrent_data.chunks}
        self.client_ip = util.get_ip()
        self.temp_file_name = os.path.join(os.getcwd(), f"{torrent_data.file_name}.tmp")

    def load_chunk(self, chunk: DataChunk):
        chunk_hash = sha1(chunk.content).hexdigest()
        chunk.hash = chunk_hash
        if chunk_hash in self.needed_chunks_hashes:
            self.needed_chunks_hashes.remove(chunk_hash)
            self.owned_chunks.append(chunk)

    def write_chunks_to_file(self):
        with open(self.temp_file_name, "wb") as f:
             for chunk in self.owned_chunks:
                    written = f.write(chunk.content)
                    print(written, "bytes written")
                    


    def request_peers_with_chunks(self):
        for i in range(0, len(torrent_data.chunks), self.tracker_batch_size):
            chunk_batch = list(self.needed_chunks_hashes)[i : i + self.tracker_batch_size]
            chunk_batch_json = json.dumps(chunk_batch)
            resp = requests.post(self.torrent_data.tracker_url, chunk_batch_json)

            peer_data_json = json.loads(resp.content)

            # peers who have the needed chunks
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
            print("Seeding chunks...")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.client_ip, self.seed_port))
                s.listen()
            
                while True:
                    conn, addr = s.accept()
                
                    with conn:
                        print("Seeder connected by", addr)

                        hash_digest_length = 40
                        needed_hash = conn.recv(hash_digest_length).decode()
                        print("Leecher needs", needed_hash)
                        
                        needed_chunk = [chunk for chunk in self.owned_chunks if chunk.hash == needed_hash][0]
                        conn.send(needed_chunk.content)
                        print(f"Sent {needed_chunk.hash} to leecher")

    def announce_chunks_to_tracker(self):
        print("Announcing chunks to tracker")
        for i in range(0, len(self.owned_chunks), self.tracker_batch_size):
            chunk_batch = self.owned_chunks[i : i + self.tracker_batch_size]
            # print(chunk_batch)
            chunk_batch_json = json.dumps(
                {
                    "client_host": self.client_ip,
                    "client_port": self.seed_port,
                    "hashes": [chunk.hash for chunk in chunk_batch],
                }
            )
            resp = requests.put(self.torrent_data.tracker_url, chunk_batch_json)
            if resp.content == b"Ok":
                print("Data successfully announced to tracker")
            else:
                print("Error:", resp.content)

    def chunkify(self, filename: str, chunk_size: int):
        with open(filename, "rb") as f:
            it = 0
            while buffer := f.read(chunk_size):
                chunk = DataChunk(it, buffer, sha1(buffer).hexdigest())
                it += 1
                yield chunk

    def fetch_chunk_from_peer(self, peer: Peer):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect((peer.peer_host, peer.peer_port))
                while True:
                    # send wanted chunk hash
                    chunk_hash = random.choice(peer.peer_chunks)
                    s.send(chunk_hash.encode())
                    data = s.recv(torrent_data.chunk_size)
                    if data:
                        print(f"Peer {peer.peer_host}:{peer.peer_port} sends {data}")
                        
                        sent_chunk_hash = sha1(data).hexdigest()
                        order_number = int(self.torrent_data.chunk_hash_id_map[sent_chunk_hash])
                        chunk = DataChunk(order_number, data, sent_chunk_hash)
                        self.load_chunk(chunk)
                    else:
                        break
                # print("Chunks fetched")
            except ConnectionRefusedError:
                print(f"Peer {peer} refused connection")
                
    def fetch_from_peers(self):
         while True:
            try:
                if self.needed_chunks_hashes:
                    # while i still need something
                    peers = self.request_peers_with_chunks()
                    for peer in peers:
                        self.fetch_chunk_from_peer(peer)
                    
                    self.write_chunks_to_file()
                    self.announce_chunks_to_tracker()
                    time.sleep(5)
                else:
                    print("All the pieces gotten")
                    self.owned_chunks.sort(key=lambda x: x.order_number)
                    file_hash = sha1()

                    for chunk in self.owned_chunks:
                        file_hash.update(chunk.content)

                    print(file_hash.hexdigest(), self.torrent_data.file_hash)
                    if file_hash.hexdigest() == self.torrent_data.file_hash:
                        print("Integrity check succeeded")
                        self.write_chunks_to_file()
                        self.announce_chunks_to_tracker()
                
                    break
            except Exception as e:
                print(f"Error in fetch thread: {e}")
                time.sleep(10) 

    def start_client(self):
        # check if i have local chunks. do that by checking if i have filename in dir
        ready_data_name = os.path.join(os.getcwd(), self.torrent_data.file_name)

        # port from which the client starts tcp server to serve chunks
        self.seed_port = util.find_free_port()
        seeding_thread = threading.Thread(target=self.seed_chunks, daemon=True)
        seeding_thread.start()

        # flushing_to_file_thread = threading.Thread(target=self.write_chunks_to_file, daemon=True)

        if os.path.exists(ready_data_name):
            # chunkify the existing file and only start seeding
            for chunk in self.chunkify(
                self.torrent_data.file_name, self.torrent_data.chunk_size
            ):
                client.load_chunk(chunk)
            self.announce_chunks_to_tracker()

        else:
            if os.path.exists(self.temp_file_name):
                # file download has stopped but some parts exists
                for chunk in self.chunkify(self.temp_file_name, self.torrent_data.chunk_size):
                    client.load_chunk(chunk)
            else:
                open(self.temp_file_name, "w").close()
                
            fetching_thread = threading.Thread(
                target=self.fetch_from_peers,
                daemon=True
            )
            
            fetching_thread.start()
        try:
            while True:
                time.sleep(0.1)  # Sleep to avoid high CPU usage
        except KeyboardInterrupt:
                print("Shutting down client...")

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

import sys
import json
from typing import Generator
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
class DataChunk:
    offset: int
    hash: str


@dataclass
class Peer:
    peer_host: str
    peer_port: int
    peer_chunks: list[str]


class TorrentData:
    tracker_url: str
    file_name: str
    file_hash: str
    file_size: int
    chunk_size: int
    chunk_hash_id_map: dict[str, str] = {}
    chunk_hashes: list[str] = []

    def __init__(self, torrent_file: dict):
        for chunkJson in torrent_file["chunks"]:
            self.chunk_hashes.append(chunkJson["hash"])
            self.chunk_hash_id_map[chunkJson["hash"]] = chunkJson["orderNumber"]

        self.tracker_url = f"http://{torrent_file["trackerUrl"]}/chunk"
        self.file_hash = torrent_file["fileHash"]
        self.file_name = torrent_file["fileName"]
        self.file_size = torrent_file["fileSize"]
        self.chunk_size = int(torrent_file["chunkSize"])

    def __repr__(self):
        return f"Tracker: {self.tracker_url}, Filename {self.file_name}, File hash {self.file_hash}"


class TorrentClient:
    owned_chunks: list[DataChunk]
    needed_chunks_hashes: set[str]
    torrent_data: TorrentData
    seed_port: int
    tracker_batch_size = 5
    client_ip: str
    temp_file_name: str
    download_metadata_file_name: str
    ready_file_name: str
    uploaded_chunks: int

    def __init__(self, torrent_data: TorrentData):
        self.torrent_data = torrent_data
        self.owned_chunks = []
        self.needed_chunks_hashes = set(torrent_data.chunk_hashes)
        self.client_ip = util.get_ip()
        self.temp_file_name = os.path.join(os.getcwd(), f"{torrent_data.file_name}.tmp")
        self.download_metadata_file_name = os.path.join(
            os.getcwd(), f"{torrent_data.file_name}.metadata.txt"
        )
        self.ready_file_name = os.path.join(os.getcwd(), self.torrent_data.file_name)
        self.uploaded_chunks = 0

    def request_peers_with_chunks(self) -> Generator[list[Peer], None, None]:
        for i in range(0, len(self.needed_chunks_hashes), self.tracker_batch_size):
            chunk_batch = list(self.needed_chunks_hashes)[
                i : i + self.tracker_batch_size
            ]
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

            yield peers

    def fetch_from_peers(self):
        while True:
            try:
                if self.needed_chunks_hashes:
                    # while i still need something
                    needed_length = len(self.needed_chunks_hashes)
                    for peers in self.request_peers_with_chunks():
                        for peer in peers:
                            self.fetch_chunk_from_peer(peer)

                    length_after = len(self.needed_chunks_hashes)

                    if needed_length > length_after:
                        self.announce_chunks_to_tracker()
                else:
                    print("All the pieces gotten")
                    file_hash = sha1()
                    self.owned_chunks.sort(key=lambda x: x.offset)
                    for chunk in self.owned_chunks:
                        content = self.read_chunk_content_from_disk(chunk)
                        file_hash.update(content)

                    if file_hash.hexdigest() == self.torrent_data.file_hash:
                        print("Integrity check succeeded")
                        os.rename(self.temp_file_name, self.ready_file_name)
                        os.remove(self.download_metadata_file_name)
                        
                        for chunk in self.chunkify(self.torrent_data.file_name):
                            client.register_chunk_to_memory(chunk)
                        self.announce_chunks_to_tracker()

                    else:
                        print(
                            "File hashes differed",
                            file_hash.hexdigest(),
                            self.torrent_data.file_hash,
                        )

                    break
            except Exception as e:
                print(f"Error in fetch thread: {e}")
                time.sleep(10)

    def fetch_chunk_from_peer(self, peer: Peer):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                print(f"Fetching peer {peer.peer_host}:{peer.peer_port}")
                s.connect((peer.peer_host, peer.peer_port))
                while True:
                    # give me a random chunk from peer's chunk list
                    chunk_hash = random.choice(peer.peer_chunks)
                    s.sendall(chunk_hash.encode())

                    received = 0
                    fragments = []
                    while received < self.torrent_data.chunk_size:
                        data = s.recv(self.torrent_data.chunk_size) 
                        if not data:
                            break
                        fragments.append(data)
                    complete = b"".join(fragments)
                    if len(complete) > 0:
                        print("Received", len(complete), "bytes of data")
                        sent_chunk_hash = sha1(complete).hexdigest()
                        
                        if sent_chunk_hash == chunk_hash:
                            order_number = int(
                                self.torrent_data.chunk_hash_id_map[sent_chunk_hash]
                            )
                            offset = order_number * torrent_data.chunk_size
                            chunk = DataChunk(offset, sent_chunk_hash)
                            self.write_chunk_content_to_disk(chunk, complete)
                            self.register_chunk_to_memory(chunk)
                    else:
                        break
            except ConnectionRefusedError:
                print(f"Peer {peer} refused connection")

                
    def seed_chunks(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.client_ip, self.seed_port))
            
            s.listen()
            print(f"Seeding chunks on {self.client_ip}:{self.seed_port}")

            while True:
                conn, addr = s.accept()

                with conn:
                    print("Seeder connected by", addr)
                   
                    # msg_type_length = 3
                    message = conn.recv(1024).decode()
                    
                    if message.startswith("GET"):
                        # healthcheck
                        print("Tracker sent health request")
                        response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
                        conn.sendall(response)
                        
                        conn.close()
                        continue

                    hash_digest_length = 40
                    # needed_hash = conn.recv(hash_digest_length).decode()
                    needed_hash = message[0:hash_digest_length]
                    print("Leecher needs", needed_hash)

                    needed_chunk = [
                        chunk
                        for chunk in self.owned_chunks
                        if chunk.hash == needed_hash
                    ][0]
                    content = self.read_chunk_content_from_disk(needed_chunk)
                    conn.sendall(content)
                    self.uploaded_chunks +=1
                    print(f"Sent {needed_chunk.hash} to leecher")

    def announce_chunks_to_tracker(self):
        for i in range(0, len(self.owned_chunks), self.tracker_batch_size):
            chunk_batch = self.owned_chunks[i : i + self.tracker_batch_size]
            chunk_batch_json = json.dumps(
                {
                    "client_host": self.client_ip,
                    "client_port": self.seed_port,
                    "hashes": [chunk.hash for chunk in chunk_batch],
                }
            )
            resp = requests.put(self.torrent_data.tracker_url, chunk_batch_json)
            if resp.content != b"Ok":
                print("Error:", resp.content)

    def register_chunk_to_memory(self, chunk: DataChunk):
        if chunk.hash in self.needed_chunks_hashes:
            self.needed_chunks_hashes.remove(chunk.hash)
            self.owned_chunks.append(chunk)

    def write_chunk_content_to_disk(self, chunk: DataChunk, content: bytes):
        with open(self.temp_file_name, "r+b") as f:
            # set file cursor location to its offset
            f.seek(chunk.offset)
            # check if chunk exists at offset
            data = f.read(self.torrent_data.chunk_size)

            # reading moved the cursor, reset it before writing
            f.seek(chunk.offset)

            if all(byte == 0 for byte in data):
                written = f.write(content)
                print(f"{written} bytes written to offset {chunk.offset}")

                with open(self.download_metadata_file_name, "a") as mf:
                    mf.write(f"{self.temp_file_name}:{chunk.offset}:{chunk.hash}\n")

    def read_chunk_content_from_disk(self, chunk: DataChunk) -> bytes:
        with open(self.download_metadata_file_name, "r") as mf:
            for line in mf:
                file, _, hash = line.split(":")
                if hash.strip() == chunk.hash:
                    with open(file, "rb") as f:
                        f.seek(int(chunk.offset))
                        content = f.read(self.torrent_data.chunk_size)
                        return content
        raise ValueError("Chunk not found")

    def chunkify(self, filename: str):
        with open(filename, "rb") as f:
            it = 0
            offset = 0

            while buffer := f.read(self.torrent_data.chunk_size):
                chunk = DataChunk(offset, sha1(buffer).hexdigest())
                with open(self.download_metadata_file_name, "a") as mf:
                    mf.write(f"{self.ready_file_name}:{chunk.offset}:{chunk.hash}\n")
                it += 1
                offset = it * self.torrent_data.chunk_size

                yield chunk

    def start_client(self):
        # check if i have local chunks. do that by checking if i have filename in dir

        # port from which the client starts tcp server to serve chunks
        self.seed_port = util.find_free_port()
        seeding_thread = threading.Thread(target=self.seed_chunks, daemon=True)
        threading.Thread(target=self.metrics_service, daemon=True).start()

        if os.path.exists(self.ready_file_name):
            # chunkify the existing file and only start seeding
            for chunk in self.chunkify(self.torrent_data.file_name):
                client.register_chunk_to_memory(chunk)
            self.announce_chunks_to_tracker()

            seeding_thread.start()

        else:
            if os.path.exists(self.temp_file_name):
                # file download has stopped but some parts exists

                with open(self.download_metadata_file_name, "r") as f:
                    for line in f:
                        file, offset, hash = line.split(":")
                        offset = int(offset)
                        with open(file, "rb") as tf:
                            tf.seek(offset)
                            client.register_chunk_to_memory(
                                DataChunk(offset, hash)
                            )
            else:
                with open(self.temp_file_name, "wb") as f:
                    f.truncate(self.torrent_data.file_size)
                open(self.download_metadata_file_name, "wb").close()

            seeding_thread.start()

            # for i in range(2):
            fetching_thread = threading.Thread(
                target=self.fetch_from_peers, daemon=True
            )
            fetching_thread.start()
        try:
            while True:
                time.sleep(0.1)  # Sleep to avoid high CPU usage
        except KeyboardInterrupt:
            print("Shutting down client...")

    def metrics_service(self) -> None:
        while True:
            payload = {
                "client_host": self.client_ip,
                "client_port": self.seed_port,
                "downloaded_chunks": len(self.owned_chunks),
                "uploaded_chunks": self.uploaded_chunks,
                "total_chunks": len(self.torrent_data.chunk_hashes),
                "chunk_size": self.torrent_data.chunk_size
            }
            requests.post("http://localhost:5000/metrics", json=payload)

            time.sleep(3)

if __name__ == "__main__":
    torrent_file_name = sys.argv[1]

    with open(torrent_file_name, "r") as f:
        torrent_data_json = json.load(f)
        torrent_data = TorrentData(torrent_data_json)

    client = TorrentClient(torrent_data)
    client.start_client()

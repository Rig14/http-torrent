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
class DataChunk:
    offset: int
    content: bytes
    hash: str


@dataclass
class Peer:
    peer_host: str
    peer_port: int
    peer_chunks: [str]


class TorrentData:
    tracker_url: str
    file_name: str
    file_hash: str
    file_size: int
    chunk_size: int
    chunk_hash_id_map: dict[str, str] = {}
    chunk_hashes: [str] = []

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

    def __init__(self, torrent_data: TorrentData):
        self.torrent_data = torrent_data
        self.owned_chunks = []
        self.needed_chunks_hashes = torrent_data.chunk_hashes
        self.client_ip = util.get_ip()
        self.temp_file_name = os.path.join(os.getcwd(), f"{torrent_data.file_name}.tmp")
        self.download_metadata_file_name = os.path.join(os.getcwd(), f"{torrent_data.file_name}.metadata.txt")
        self.ready_file_name = os.path.join(os.getcwd(), self.torrent_data.file_name)

    def request_peers_with_chunks(self):
        for i in range(0, len(torrent_data.chunk_hashes), self.tracker_batch_size):
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
                        print(f"Peer {peer.peer_host}:{peer.peer_port} sends data")
                        
                        sent_chunk_hash = sha1(data).hexdigest()
                        order_number = int(self.torrent_data.chunk_hash_id_map[sent_chunk_hash])
                        offset = order_number * torrent_data.chunk_size
                        chunk = DataChunk(offset, data, sent_chunk_hash)
                        self.load_chunk(chunk)
                    else:
                        break
            except ConnectionRefusedError:
                print(f"Peer {peer} refused connection")
                
    def fetch_from_peers(self):
         while True:
            try:
                if self.needed_chunks_hashes:
                    # while i still need something
                    peers = self.request_peers_with_chunks()
                    needed_length = len(self.needed_chunks_hashes)
                    for peer in peers:
                        self.fetch_chunk_from_peer(peer)
                    
                    length_after = len(self.needed_chunks_hashes)

                    if needed_length > length_after:
                        self.write_chunks_to_file()
                        self.announce_chunks_to_tracker()
                else:
                    print("All the pieces gotten")
                    file_hash = sha1()
                    self.owned_chunks.sort(key=lambda x: x.offset)
                    for chunk in self.owned_chunks:
                        file_hash.update(chunk.content)

                    if file_hash.hexdigest() == self.torrent_data.file_hash:
                        print("Integrity check succeeded")
                        os.rename(self.temp_file_name, self.ready_file_name)
                        
                    else:
                        print("File hashes differed", file_hash.hexdigest(), self.torrent_data.file_hash)
                
                    break
            except Exception as e:
                print(f"Error in fetch thread: {e}")
                time.sleep(10) 

    def load_chunk(self, chunk: DataChunk):
        chunk_hash = sha1(chunk.content).hexdigest()
        chunk.hash = chunk_hash
        if chunk_hash in self.needed_chunks_hashes:
            self.needed_chunks_hashes.remove(chunk_hash)
            self.owned_chunks.append(chunk)

    def write_chunks_to_file(self):
        with open(self.temp_file_name, "r+b") as f:
             for chunk in self.owned_chunks:
                    # set file cursor location to its offset
                    f.seek(chunk.offset)
                    # check if chunk exists at offset
                    data = f.read(self.torrent_data.chunk_size)

                    # reading moved the cursor, reset it before writing
                    f.seek(chunk.offset)
                
                    if all(byte == 0 for byte in data):
                        written = f.write(chunk.content)
                        print(f"{written} bytes written to offset {chunk.offset}")

                        with open(self.download_metadata_file_name, "a") as mf:
                            mf.write(f"{chunk.offset}:{chunk.hash}\n")
                    

    def chunkify(self, filename: str):
        with open(filename, "rb") as f:
            it = 0
            offset = 0
            
            while buffer := f.read(self.torrent_data.chunk_size):
                chunk = DataChunk(offset, buffer, sha1(buffer).hexdigest())
                it += 1
                offset = it * self.torrent_data.chunk_size
                
                yield chunk

    def start_client(self):
        # check if i have local chunks. do that by checking if i have filename in dir

        # port from which the client starts tcp server to serve chunks
        self.seed_port = util.find_free_port()
        seeding_thread = threading.Thread(target=self.seed_chunks, daemon=True)

        if os.path.exists(self.ready_file_name):
            # chunkify the existing file and only start seeding
            for chunk in self.chunkify(self.torrent_data.file_name):
                client.load_chunk(chunk)
            self.announce_chunks_to_tracker()
            
            seeding_thread.start()

        else:
            if os.path.exists(self.temp_file_name):
                # file download has stopped but some parts exists

                with open(self.download_metadata_file_name, "r") as f:
                    for line in f:
                        offset, hash = line.split(":")
                        offset = int(offset)
                        with open(self.temp_file_name, "rb") as tf:
                            tf.seek(offset)
                            content = tf.read(self.torrent_data.chunk_size)
                            client.load_chunk(DataChunk(offset, content, hash))
            else:
                with open(self.temp_file_name, "wb") as f:
                    f.truncate(self.torrent_data.file_size)
                open(self.download_metadata_file_name, "wb").close()
                    
            seeding_thread.start()
           
            for i in range(2):
                fetching_thread = threading.Thread(target=self.fetch_from_peers, daemon=True)
                fetching_thread.start()
        try:
            while True:
                time.sleep(0.1)  # Sleep to avoid high CPU usage
        except KeyboardInterrupt:
                print("Shutting down client...")


if __name__ == "__main__":
    torrent_file_name = sys.argv[1]
    
    with open(torrent_file_name, "r") as f:
        torrent_data_json = json.load(f)
        torrent_data = TorrentData(torrent_data_json)
        
    client = TorrentClient(torrent_data)
    client.start_client()

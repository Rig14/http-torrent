import base64
import json
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from random import shuffle
from threading import Thread
from uuid import uuid4
import urllib.parse as urlparse


import requests

from torrentify import chunkify
from util import get_ip, find_free_port

class FileChunk:
    orderNumber: int
    hash: str

class Provider:
    client_host: str
    client_port: int
    hashes: list[str]

class TorrentDetails:
    fileName: str
    chunkSize: int
    trackerUrl: str
    fileHash: str
    chunks: list[FileChunk]


class Client:
    def __init__(self, torrent_file_details: TorrentDetails, has_file=False):
        self.host: str = get_ip()
        self.port: int = find_free_port()
        self.torrent_file_details: TorrentDetails = torrent_file_details
        self.available_chunks: list[str] = []
        self.uploaded_chunks: int = 0

        self.id: str = uuid4().hex
        self.temp_path: str = f"/tmp/http-torrent/{self.id}"
        os.makedirs(self.temp_path, exist_ok=True)

        try:
            if not has_file: raise FileNotFoundError
            chunks = chunkify(self.torrent_file_details.fileName, self.torrent_file_details.chunkSize)
            for chunk in chunks:
                with open(f"{self.temp_path}/{chunk.hash}", "wb") as f:
                    f.write(chunk.content)
                self.available_chunks.append(chunk.hash)
        except FileNotFoundError:
            print(f"Torrent file {self.torrent_file_details.fileName} not found on system. Continuing...")

        Thread(target=self.listener, daemon=True).start()
        print(f"Torrent client listening on {self.host}:{self.port}")

        if len(self.available_chunks) > 0:
            self.announce_hashes(self.available_chunks)

        Thread(target=self.main_loop, daemon=True).start()
        Thread(target=self.metrics_service, daemon=True).start()
        print("Client started")


    def metrics_service(self) -> None:
        while True:
            payload = {
                "client_host": self.host,
                "client_port": self.port,
                "downloaded_chunks": len(self.available_chunks),
                "uploaded_chunks": self.uploaded_chunks,
                "total_chunks": len(self.torrent_file_details.chunks),
                "chunk_size": self.torrent_file_details.chunkSize
            }
            requests.post("http://localhost:8080/metrics", json=payload)

            time.sleep(3)

    def main_loop(self) -> None:
        while True:
            missing_hashes = self.get_missing_chunk_hashes()
            # request max 5 chunks at a time
            shuffle(missing_hashes)
            missing_hashes = missing_hashes[:5]
            if len(missing_hashes) > 0:
                providers = self.get_providers_for_hashes(missing_hashes)
                for provider in providers:
                    self.download_from_provider(provider)
            else:
                print("All chunks downloaded. Seeding...")

                # putting the chunks together into a file into the temp folder
                chunks = []
                for chunk in self.torrent_file_details.chunks:
                    with open(f"{self.temp_path}/{chunk.hash}", "rb") as f:
                        chunks.append(f.read())

                with open(f"{self.temp_path}/{self.torrent_file_details.fileName}", "w+") as f: pass
                with open(f"{self.temp_path}/{self.torrent_file_details.fileName}", "wb") as f:
                    f.write(b"".join(chunks))

                break
            if len(self.available_chunks) > 0:
                self.announce_hashes(self.available_chunks)
            time.sleep(5)

    def get_missing_chunk_hashes(self) -> list[str]:
        return list(set([x.hash for x in self.torrent_file_details.chunks]) - set(self.available_chunks))

    def download_from_provider(self, provider: Provider) -> None:
        print(f"Downloading {len(provider.hashes)} chunks from provider at {provider.client_host}:{provider.client_port}.")

        try:
            response = requests.post(
                f"http://{provider.client_host}:{provider.client_port}/chunk",
                json=provider.hashes
            )
            response.raise_for_status()

            for chunk in response.json():
                with open(f"{self.temp_path}/{chunk['hash']}", "wb") as f:
                    f.write(base64.b64decode(chunk["content"]))
                self.available_chunks.append(chunk["hash"])

        except Exception as e:
            print(f"Error downloading chunks from provider: {e}")


    def listener(self) -> None:
        this_client = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                parsed_url = urlparse.urlparse(self.path)

                content: str = "404 Not Found."
                status: int = 404
                headers: list[tuple[str, str]] = []
                request_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))


                # ROUTES
                if parsed_url.path == "/chunk":
                    try:
                        j = json.loads(request_body)
                        if not isinstance(j, list): raise Exception("Invalid request body")
                        if not all([isinstance(x, str) for x in j]): raise Exception("Invalid request body")
                        if not all([x in this_client.available_chunks for x in j]): raise Exception("Invalid request. I dont have your chunks :(")

                        chunks = []
                        for chunk_hash in j:
                            with open(f"{this_client.temp_path}/{chunk_hash}", "rb") as f:
                                file_content = f.read()
                                chunks.append({
                                    "hash": chunk_hash,
                                    "content": base64.b64encode(file_content).decode('ascii')
                                })

                        content = json.dumps(chunks)
                        status = 200
                        this_client.uploaded_chunks += len(chunks)
                    except Exception as e:
                        content = f"400 Bad Request: {e}"
                        print("Error parsing request body", e)
                        status = 400


                # SENDING
                self.send_response(status)
                for header in headers: self.send_header(header[0], header[1])
                self.end_headers()
                self.wfile.write(content.encode("UTF-8"))

            def do_GET(self):
                parsed_url = urlparse.urlparse(self.path)

                content: str = "404 Not Found."
                status: int = 404
                headers: list[tuple[str, str]] = []


                # ROUTES
                if parsed_url.path == "/ping":
                    content = "pong"
                    status = 200

                # SENDING
                self.send_response(status)
                for header in headers: self.send_header(header[0], header[1])
                self.end_headers()
                self.wfile.write(content.encode("UTF-8"))

        server = HTTPServer((self.host, self.port), Handler)
        server.serve_forever()

    def announce_hashes(self, hashes: list[str]) -> None:
        print(f"Announcing {len(hashes)} hashes to tracker at {self.torrent_file_details.trackerUrl}.")

        payload = {
            "client_host": self.host,
            "client_port": self.port,
            "hashes": hashes
        }

        try:
            response = requests.put(
                "http://" + self.torrent_file_details.trackerUrl + "/chunk",
                json=payload
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Error announcing hashes: {e}")


    def get_providers_for_hashes(self, hashes: list[str]) -> list[Provider]:
        print(f"Getting known clients for {len(hashes)} hashes from tracker at {self.torrent_file_details.trackerUrl}.")

        try:
            response = requests.post(
                "http://" + self.torrent_file_details.trackerUrl + "/chunk",
                json=hashes
            )
            response.raise_for_status()

            providers: list[Provider] = []
            for provider in response.json():
                p = Provider()
                p.client_host = provider["client_host"]
                p.client_port = provider["client_port"]
                p.hashes = provider["hash_list"]
                providers.append(p)

            return providers

        except Exception as e:
            print(f"Error getting known clients for hashes: {e}")
            return []

if __name__ == "__main__":
    with open("torrent.json") as f:
        content = json.load(f)
        torrent_details = TorrentDetails()
        torrent_details.fileName = content["fileName"]
        torrent_details.chunkSize = content["chunkSize"]
        torrent_details.trackerUrl = content["trackerUrl"]
        torrent_details.fileHash = content["fileHash"]
        torrent_details.chunks = [FileChunk() for _ in content["chunks"]]
        for i, chunk in enumerate(content["chunks"]):
            torrent_details.chunks[i].orderNumber = chunk["orderNumber"]
            torrent_details.chunks[i].hash = chunk["hash"]

    client = Client(torrent_details, len(sys.argv) > 1)

    while True:
        pass






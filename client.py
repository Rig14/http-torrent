import asyncio
import atexit
import base64
import json
import logging
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from random import shuffle
from threading import Thread
from uuid import uuid4
import urllib.parse as urlparse


import requests
from kademlia.network import Server

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
    def __init__(self, torrent_file_details: TorrentDetails, has_file=False, dht_enabled=False):
        self.host: str = get_ip()
        self.port: int = find_free_port()
        self.torrent_file_details: TorrentDetails = torrent_file_details
        self.available_chunks: list[str] = []
        self.dht_enabled = dht_enabled
        self.dht_port = find_free_port() if dht_enabled else None
        self.dht_server: Server | None = None
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

        if self.dht_enabled:
            asyncio.run(self.init_dht_server())

        asyncio.run(self.main_loop())
        Thread(target=self.metrics_service, daemon=True).start()
        print("Client started")

    async def init_dht_server(self) -> None:
        print("Starting DHT server...")
        self.dht_server = Server()
        await self.dht_server.listen(self.dht_port, self.host)
        print(f"DHT server listening on {self.host}:{self.dht_port}")

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

    async def main_loop(self) -> None:
        # bootstrap the DHT server with peers from the tracker
        if self.dht_enabled:
            print("Bootstrapping DHT server with peers from tracker...")
            peers = self.get_dht_peers_from_tracker()
            await self.dht_server.bootstrap(peers)
            print("Announcing DHT status to tracker...")
            self.announce_dht_status()

        if len(self.available_chunks) > 0:
            await self.announce_hashes(self.available_chunks)

        while True:
            missing_hashes = self.get_missing_chunk_hashes()
            # request max 5 chunks at a time
            shuffle(missing_hashes)
            missing_hashes = missing_hashes[:5]
            if len(missing_hashes) > 0:
                providers = await self.get_providers_for_hashes(missing_hashes)
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
                await self.announce_hashes(self.available_chunks)
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

    async def announce_hashes(self, hashes: list[str]) -> None:
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
            print(f"Error announcing hashes to tracker via http: {e}")

        if self.dht_enabled:
            print("Announcing hashes to DHT network...")
            for hash in hashes:
                try:
                    # hack to store a list in dht network as a string
                    result = await self.dht_server.get(hash)
                    print(f"Got result from DHT for {hash}: {result}")
                    result = result if result else "[]"
                    result = json.loads(result)
                    result = result if f"{self.host}:{self.port}" in result else result + [f"{self.host}:{self.port}"]
                    result = json.dumps(result)
                    await self.dht_server.set(hash, result)
                except Exception as e:
                    print(f"Error announcing hashes to DHT: {e}")

    def announce_dht_status(self) -> None:
        print(f"Announcing DHT status to tracker at {self.torrent_file_details.trackerUrl}.")

        payload = {
            "host": self.host,
            "port": self.dht_port,
        }
        try:
            response = requests.post(
                "http://" + self.torrent_file_details.trackerUrl + "/dht",
                json=payload
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Error announcing DHT status to tracker: {e}")

    def get_dht_peers_from_tracker(self) -> list[tuple[str, int]]:
        print(f"Getting DHT peers from tracker at {self.torrent_file_details.trackerUrl}.")

        try:
            response = requests.get(
                "http://" + self.torrent_file_details.trackerUrl + "/dht"
            )
            response.raise_for_status()

            # response json is in format [ {host: host, port:port} ...]
            peers = []
            for peer in response.json():
                if not peer["host"] or not peer["port"]: continue
                peers.append((peer["host"], peer["port"]))
            return peers
        except Exception as e:
            print(f"Error getting DHT peers from tracker: {e}")
            return []

    async def get_providers_for_hashes(self, hashes: list[str]) -> list[Provider]:
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
            print(f"Error getting known clients from tracker for hashes: {e}")
            if self.dht_enabled:
                # If DHT is enabled, try to get the providers from the DHT network
                print("Trying to get providers from DHT network...")
                if self.dht_server:
                    providers = []
                    for hash in hashes:
                        response = await self.dht_server.get(hash)
                        if not response: continue
                        response = json.loads(response)
                        for provider in response:
                            p = Provider()
                            p.client_host, p.client_port = provider.split(":")
                            p.hashes = [hash]
                            providers.append(p)
                    return providers
            else:
                return []

    async def close_client(self):
        if self.dht_server:
            await self.dht_server.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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

    args = sys.argv[1:]
    has_file = "has_file" in args
    dht_enabled = "dht_enabled" in args

    client = Client(
        torrent_details,
        has_file,
        dht_enabled
    )

    atexit.register(asyncio.run, client.close_client())

    while True:
        pass







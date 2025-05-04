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

from dht import KademliaDHT
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
        self.dht_server: KademliaDHT | None = None
        self.uploaded_chunks: int = 0
        self.id: str = uuid4().hex
        self.temp_path: str = f"/tmp/http-torrent/{self.id}"
        self._running = False
        self._http_server = None
        self._http_thread = None

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

    async def start(self):
        """Start the client and all its components"""
        self._running = True
        
        # Start HTTP server in a separate thread
        self._http_thread = Thread(target=self._start_http_server, daemon=True)
        self._http_thread.start()
        print(f"Torrent client listening on {self.host}:{self.port}")

        # Start metrics service
        Thread(target=self.metrics_service, daemon=True).start()

        # Initialize DHT if enabled
        if self.dht_enabled:
            await self._initialize_dht()

        # Start main loop
        await self.main_loop()

    async def _initialize_dht(self):
        """Initialize and bootstrap the DHT network"""
        print("Initializing DHT server...")
        self.dht_server = KademliaDHT(self.dht_port)
        await self.dht_server.start()
        
        # Get initial peers from tracker
        peers = self.get_dht_peers_from_tracker()
        if peers:
            print(f"Bootstrapping DHT with {len(peers)} peers...")
            for host, port in peers:
                try:
                    await self.dht_server.server.bootstrap([(host, port)])
                    print(f"Successfully bootstrapped with peer {host}:{port}")
                except Exception as e:
                    print(f"Failed to bootstrap with peer {host}:{port}: {e}")
        
        # Announce DHT status to tracker
        self.announce_dht_status()
        print("DHT initialization complete")

    def _start_http_server(self):
        """Start the HTTP server in a separate thread"""
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                parsed_url = urlparse.urlparse(self.path)
                content: str = "404 Not Found."
                status: int = 404
                headers: list[tuple[str, str]] = []
                request_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))

                if parsed_url.path == "/chunk":
                    try:
                        j = json.loads(request_body)
                        if not isinstance(j, list): raise Exception("Invalid request body")
                        if not all([isinstance(x, str) for x in j]): raise Exception("Invalid request body")
                        if not all([x in self.available_chunks for x in j]): 
                            raise Exception("Invalid request. I dont have your chunks :(")

                        chunks = []
                        for chunk_hash in j:
                            with open(f"{self.temp_path}/{chunk_hash}", "rb") as f:
                                file_content = f.read()
                                chunks.append({
                                    "hash": chunk_hash,
                                    "content": base64.b64encode(file_content).decode('ascii')
                                })

                        content = json.dumps(chunks)
                        status = 200
                        self.uploaded_chunks += len(chunks)
                    except Exception as e:
                        content = f"400 Bad Request: {e}"
                        print("Error parsing request body", e)
                        status = 400

                self.send_response(status)
                for header in headers: self.send_header(header[0], header[1])
                self.end_headers()
                self.wfile.write(content.encode("UTF-8"))

            def do_GET(self):
                parsed_url = urlparse.urlparse(self.path)
                content: str = "404 Not Found."
                status: int = 404
                headers: list[tuple[str, str]] = []

                if parsed_url.path == "/ping":
                    content = "pong"
                    status = 200

                self.send_response(status)
                for header in headers: self.send_header(header[0], header[1])
                self.end_headers()
                self.wfile.write(content.encode("UTF-8"))

        self._http_server = HTTPServer((self.host, self.port), Handler)
        self._http_server.serve_forever()

    async def main_loop(self):
        """Main client loop for downloading and sharing chunks"""
        while self._running:
            try:
                if len(self.available_chunks) > 0:
                    await self.announce_hashes(self.available_chunks)

                missing_hashes = self.get_missing_chunk_hashes()
                if missing_hashes:
                    shuffle(missing_hashes)
                    missing_hashes = missing_hashes[:5]  # request max 5 chunks at a time
                    
                    providers = await self.get_providers_for_hashes(missing_hashes)
                    for provider in providers:
                        self.download_from_provider(provider)
                else:
                    print("All chunks downloaded. Seeding...")
                    await self._assemble_file()
                    break

                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error in main loop: {e}")
                await asyncio.sleep(5)

    async def _assemble_file(self):
        """Assemble downloaded chunks into the final file"""
        chunks = []
        for chunk in self.torrent_file_details.chunks:
            with open(f"{self.temp_path}/{chunk.hash}", "rb") as f:
                chunks.append(f.read())

        with open(f"{self.temp_path}/{self.torrent_file_details.fileName}", "w+") as f: 
            pass
        with open(f"{self.temp_path}/{self.torrent_file_details.fileName}", "wb") as f:
            f.write(b"".join(chunks))

    async def announce_hashes(self, hashes: list[str]) -> None:
        """Announce available hashes to both tracker and DHT network"""
        print(f"Announcing {len(hashes)} hashes to tracker at {self.torrent_file_details.trackerUrl}.")

        # Announce to tracker
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
            print(f"Error announcing hashes to tracker: {e}")

        # Announce to DHT if enabled
        if self.dht_enabled and self.dht_server:
            print("Announcing hashes to DHT network...")
            for hash in hashes:
                try:
                    result = await self.dht_server.get(hash)
                    result = result if result else "[]"
                    result = json.loads(result)
                    
                    if f"{self.host}:{self.port}" not in result:
                        result.append(f"{self.host}:{self.port}")
                        await self.dht_server.set(hash, json.dumps(result))
                except Exception as e:
                    print(f"Error announcing hash {hash} to DHT: {e}")

    async def get_providers_for_hashes(self, hashes: list[str]) -> list[Provider]:
        """Get providers for the requested hashes from both tracker and DHT"""
        providers = []
        
        # Get providers from tracker
        try:
            response = requests.post(
                "http://" + self.torrent_file_details.trackerUrl + "/chunk",
                json=hashes
            )
            response.raise_for_status()
            tracker_providers = response.json()
            providers.extend(tracker_providers)
        except Exception as e:
            print(f"Error getting providers from tracker: {e}")

        # Get providers from DHT if enabled
        if self.dht_enabled and self.dht_server:
            for hash in hashes:
                try:
                    result = await self.dht_server.get(hash)
                    if result:
                        dht_providers = json.loads(result)
                        for provider in dht_providers:
                            host, port = provider.split(":")
                            providers.append({
                                "client_host": host,
                                "client_port": int(port),
                                "hashes": [hash]
                            })
                except Exception as e:
                    print(f"Error getting providers from DHT for hash {hash}: {e}")

        return providers

    def get_dht_peers_from_tracker(self) -> list[tuple[str, int]]:
        """Get DHT peers from the tracker"""
        try:
            response = requests.get(
                "http://" + self.torrent_file_details.trackerUrl + "/dht-peers"
            )
            response.raise_for_status()
            peers = response.json()
            return [(peer["host"], peer["port"]) for peer in peers]
        except Exception as e:
            print(f"Error getting DHT peers from tracker: {e}")
            return []

    def announce_dht_status(self):
        """Announce DHT status to tracker"""
        try:
            response = requests.post(
                "http://" + self.torrent_file_details.trackerUrl + "/dht-peer",
                json={
                    "host": self.host,
                    "port": self.dht_port
                }
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Error announcing DHT status to tracker: {e}")

    def metrics_service(self) -> None:
        """Send metrics to the metrics server"""
        while self._running:
            try:
                payload = {
                    "client_host": self.host,
                    "client_port": self.port,
                    "downloaded_chunks": len(self.available_chunks),
                    "uploaded_chunks": self.uploaded_chunks,
                    "total_chunks": len(self.torrent_file_details.chunks),
                    "chunk_size": self.torrent_file_details.chunkSize
                }
                requests.post("http://localhost:8080/metrics", json=payload)
            except Exception as e:
                print(f"Error sending metrics: {e}")
            time.sleep(3)

    async def stop(self):
        """Stop the client and clean up resources"""
        self._running = False
        if self._http_server:
            self._http_server.shutdown()
        if self.dht_server:
            await self.dht_server.stop()
        if self._http_thread:
            self._http_thread.join(timeout=5)

    def get_missing_chunk_hashes(self) -> list[str]:
        """Get list of missing chunk hashes"""
        return list(set([x.hash for x in self.torrent_file_details.chunks]) - set(self.available_chunks))

    def download_from_provider(self, provider: Provider) -> None:
        """Download chunks from a provider"""
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

# Example usage
async def main():
    # Example torrent details
    torrent_details = TorrentDetails(
        fileName="example.txt",
        chunkSize=1024,
        trackerUrl="localhost:8080",
        fileHash="example_hash",
        chunks=[]
    )

    # Create and start client
    client = Client(torrent_details, dht_enabled=True)
    try:
        await client.start()
    except KeyboardInterrupt:
        print("Shutting down client...")
        await client.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())







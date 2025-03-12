import sys
import json
import requests

class Chunk:
    orderNumber: int
    hash: str

    def __init__(self, orderNumber, hash):
        self.orderNumber = orderNumber
        self.hash = hash

    def __repr__(self):
        return f"Chunk: {self.orderNumber} Digest: {self.hash}"

class TorrentData:
    chunks: list[Chunk]
    trackerUrl: str
    fileName: str
    fileHash: str

    def __init__(self, jsonData: dict):
        self.chunks = list(map(lambda x: Chunk(x["orderNumber"], x["hash"]), jsonData["chunks"]))
        self.trackerAddr = jsonData["trackerUrl"]
        self.fileHash = jsonData["fileHash"]
        self.fileName = jsonData["fileName"]
        

    def __repr__(self):
        return f"Tracker: {self.trackerAddr}, Chunks length: {len(self.chunks)}, Filename {self.fileName}, File hash {self.fileHash}"
    

def load_torrent_file(file_name: str) -> TorrentData:
    with open(file_name, "r") as f:
        jsonData = json.load(f)
        torrentData = TorrentData(jsonData)
        print(torrentData)
        
    return torrentData


def requestChunks(torrentData: TorrentData):
    trackerUrl = torrentData.trackerAddr
    chunkSize = 5 
    for i in range(0, len(torrentData.chunks), chunkSize):
        chunk = torrentData.chunks[i:i+chunkSize]
        print(chunk)
    # ask tracker for chunks
    # response = requests.put(trackerUrl, {
    # })

    
def seedChunks():
    pass
    
if __name__ == "__main__":
    file_name = sys.argv[1]
    print(file_name)
    data = load_torrent_file(file_name)
    requestChunks(data)
    print(data.chunks[0].orderNumber)

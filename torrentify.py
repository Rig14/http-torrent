import sys
from hashlib import sha1
import json

# CHUNK_SIZE = 32768
CHUNK_SIZE = 10


class Chunk:
    orderNumber: int
    hash: str
    content: bytes

    def __init__(self, orderNumber, content):
        self.orderNumber = orderNumber
        self.content = content
        self.hash = sha1(content)

    def __repr__(self):
        return f"Chunk: {self.orderNumber} Content: ${self.content} Digest: {self.hash.digest()}"


def chunkify(filename: str):
    with open(filename, 'rb') as f:
        it = 0
        while buffer := f.read(CHUNK_SIZE):
            chunk = Chunk(it, buffer)
            it+=1
            yield chunk
        

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("invalid params")
        exit(1)
    
    filename = sys.argv[1]
    tracker_url = sys.argv[2]
    file_hash = sha1()
   
    # torrent_file = 
    with open("torrent.json", "w") as f:
        for chunk in chunkify(filename):
            file_hash.update(chunk.content)
            json.dump({
                "orderNumber": chunk.orderNumber,
                "hash": str(chunk.hash.digest())
            }, f)
       
    
    torrent_data = {
        "fileName": filename,
        "trackerUrl": tracker_url,
        "fileHash": file_hash.digest()
    }
            
        # f.write("}")
        
    print(file_hash.digest())





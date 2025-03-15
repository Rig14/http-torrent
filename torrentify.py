import math
import os
import sys
from hashlib import sha1
import json


class Chunk:
    orderNumber: int
    hash: str
    content: bytes

    def __init__(self, orderNumber, content):
        self.orderNumber = orderNumber
        self.content = content
        self.hash = sha1(content).digest().hex()

    def __repr__(self):
        return f"Chunk: {self.orderNumber} Content: ${self.content} Digest: {self.hash}"

def get_appropriate_chunk_size(file_path, min_chunks=100, max_chunks=1000, min_size=16384, max_size=4194304):
    """
    Determines an appropriate chunk size for a file based on its size.

    Parameters:
    file_path (str): Path to the file
    min_chunks (int): Minimum number of chunks to aim for
    max_chunks (int): Maximum number of chunks to aim for
    min_size (int): Minimum chunk size in bytes (16 KB default)
    max_size (int): Maximum chunk size in bytes (4 MB default)

    Returns:
    int: Recommended chunk size in bytes
    """
    try:
        # Get file size
        file_size = os.path.getsize(file_path)

        if file_size == 0:
            return min_size

        # Calculate ideal chunk size based on desired number of chunks
        ideal_chunk_size = file_size / min_chunks

        # Ensure chunk size is within bounds
        chunk_size = max(min_size, min(ideal_chunk_size, max_size))

        # Round to nearest power of 2 for efficiency
        chunk_size = 2 ** math.floor(math.log2(chunk_size))

        # Check if resulting number of chunks is too high
        num_chunks = math.ceil(file_size / chunk_size)
        if num_chunks > max_chunks:
            # Adjust chunk size to meet max_chunks constraint
            chunk_size = math.ceil(file_size / max_chunks)
            # Round to nearest power of 2 again
            chunk_size = 2 ** math.ceil(math.log2(chunk_size))

        return int(chunk_size)

    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return min_size
    except Exception as e:
        print(f"Error determining chunk size: {e}")
        return min_size


def chunkify(filename: str, chunk_size: int):
    with open(filename, "rb") as f:
        it = 0
        while buffer := f.read(chunk_size):
            chunk = Chunk(it, buffer)
            it += 1
            yield chunk


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("invalid params")
        exit(1)

    filename = sys.argv[1]
    tracker_url = sys.argv[2]
    chunk_size = get_appropriate_chunk_size(filename)
    file_hash = sha1()

    chunks = []
    with open("torrent.json", "w") as f:
        for chunk in chunkify(filename, chunk_size):
            file_hash.update(chunk.content)
            chunks.append({"orderNumber": chunk.orderNumber, "hash": chunk.hash})
        json.dump(
            {
                "fileName": filename,
                "chunkSize": chunk_size,
                "trackerUrl": tracker_url,
                "fileHash": file_hash.digest().hex(),
                "chunks": chunks,
            },
            f,
            indent=4,
        )

    print(len(chunks))
    print(file_hash.digest().hex())

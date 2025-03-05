import requests
import sys
import json

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("wrong params")
        exit(1)
        
    torrent_file = sys.argv[1]
    # torrent = ""
    with open(torrent_file, "r") as f:
        torrent = json.load(f)
   
    print("Connecting tracker at", torrent["trackerUrl"])
    response = requests.post(torrent["trackerUrl"], torrent)
    # print(torrent)

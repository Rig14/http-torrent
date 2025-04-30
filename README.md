# http-torrent


simple P2P torrent client and tracker for file sharing. With implementations in raw TCP and HTTP protocol

before running the stress test please generate a torrent file by running the torrentify program. This will generate the needed metadata file that is used by client programs to share the file.

After a suitable torrent file is generated you can start the stress test program. It will automatically startup clients and kill them to show the functionalities of the system.


## Endpoints on the tracker:

Update the tracker with chunks that the client has.
PUT /chunk

Example request body
```json
{
  "client_host": "123.42.23.12"
  "client_port": 8000
  "hashes": [
    "oc3kikx1o9x1oxo21k1x",
    ...
  ]
}
```

Response
```json
Ok
```

Endpoint to get known addresses for the chunks
POST /chunk

Example request body
```json
[
    "oc3kikx1o9x1oxo21k1x",
    ...
]
```

Response
```json
[
  {
    "client_host": "123.42.23.12"
    "client_port": 8000
    "hash_list": [
      "oc3kikx1o9x1oxo21k1x",
      ...
    ]
  },
  {
    "client_host": "123.42.23.12"
    "client_port": 8000
    "hash_list": [
      "oc3kikx1o9x1oxo21k1x",
      ...
    ]
  },
  ...
]
```


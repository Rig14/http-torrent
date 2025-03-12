curl -d '["bba424bd1e8175bc0f357a0723263d929f077523"]' \
-H "Content-Type: application/json" \
-H "Content-Length: 44" \
-X POST http://10.224.15.245:5000/chunk
#
# curl -d '{ "client_host": "127.0.0.1", "client_port": "5000", "hashes": ["bba424bd1e8175bc0f357a0723263d929f077523"] }' \
# -H "Content-Type: application/json" \
# -X PUT http://10.224.15.245:5000/chunk

# Install openvc and face_recognition

See https://github.com/ageitgey/face_recognition

# Run server

default host is 0.0.0.0 and port is 9900

`python server/daemon.py`

# Run client

Put the picture to the dir `knonw_people`  and set `known_face_names` in client/facerec.py

```
export NODE_HOST={server_host}
export DAEMON_PORT=9900

python client/facerec.py
```

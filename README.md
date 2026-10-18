# EchoDoc

```bash
brew install python@3.12
```

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

```
grpcio==1.78.0
grpcio-tools==1.78.0
protobuf==6.33.6
```

```bash
python -m pip install -r backend/requirements.txt
python -m pip check
```


```bash
mkdir -p backend/generated
python -m grpc_tools.protoc \
  -Iproto \
  --python_out=backend/generated \
  --grpc_python_out=backend/generated \
  proto/collab/system/v1/system.proto
```

```bash
source .venv/bin/activate
PYTHONPATH=backend/generated python -m backend.server
```
open a 2nd terminal and run this for the client

```bash
source .venv/bin/activate
PYTHONPATH=backend/generated python -m backend.client
```

add 2 client terminals and run for watch client .py

```bash
PYTHONPATH=backend/generated python -m backend.watch_client
```

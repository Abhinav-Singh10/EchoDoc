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
frontend setup

```bash
mkdir frontend
cd frontend
npm create vite@latest . -- --template react-ts
```

install these
```bash
npm install --save-exact @bufbuild/protobuf@2 @connectrpc/connect@2 @connectrpc/connect-web@2

npm install --save-dev --save-exact @bufbuild/buf @bufbuild/protoc-gen-es@2
```

```bash

sudo apt update
sudo apt install -y apt-transport-https gnupg2 curl lsb-release

curl -sL 'https://apt.envoyproxy.io/signing.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/envoy-keyring.gpg


echo "deb [arch=amd64 signed-by=/usr/share/keyrings/envoy-keyring.gpg] https://apt.envoyproxy.io jammy main" | sudo tee /etc/apt/sources.list.d/envoy.list

sudo apt update
sudo apt install -y envoy
```
create file .env.development
```
VITE_RPC_BASE_URL=http://127.0.0.1:8080 
```
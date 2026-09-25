# Collaborative System Project

An Advanced Operating Systems course project.

## Iteration 1

Build and verify browser-to-Python communication using unary
and server-streaming RPCs.

## Planned architecture

- Frontend: React and TypeScript.
- Gateway: Envoy translates gRPC-Web into native gRPC.
- Backend: Python implements the gRPC service.
- Deployment: currently runs locally on macOS; Docker Compose is deferred.

## Local backend setup

Prerequisite: Python 3.12. On macOS with Homebrew:

```bash
brew install python@3.12
```

Run the following commands from the repository root.

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install the recorded dependency versions:

```bash
python -m pip install -r backend/requirements.txt
python -m pip check
```

Generate Python message classes and gRPC support:

```bash
mkdir -p backend/generated
python -m grpc_tools.protoc \
  -Iproto \
  --python_out=backend/generated \
  --grpc_python_out=backend/generated \
  proto/collab/system/v1/system.proto
```

Verify that the generated modules can be imported:

```bash
PYTHONPATH=backend/generated python -c "from collab.system.v1 import system_pb2, system_pb2_grpc; print('Generated imports OK')"
```

Reactivate the environment in each new terminal session.
Regenerate the Python files after changing the protobuf definitions.
Generated files are ignored by Git and must not be edited manually.

This setup currently validates code generation and imports.
The application server is not implemented yet.

## RUN LOCALLY

1. Unary Rpc GetServerInfo

```bash
source .venv/bin/activate
PYTHONPATH=backend/generated python -m backend.server
```

open a 2nd terminal and run this for the client

```bash
source .venv/bin/activate
PYTHONPATH=backend/generated python -m backend.client
```

You should recieve something like this below

```
server_id: "app-1"
process_instance_id: "..."
application_version: "0.1.0"
uptime_seconds: 8.42
```

restarting the server will change the process_instance_id each time while 
running the client multiple times will not affect the process instance id and only the uptime will increase

1. Response Stream RPC WatchEvents 

inside the server venv, run it once. Keep it running

```
PYTHONPATH=backend/generated python -m backend.server
```

add 2 client terminals and run 

```
PYTHONPATH=backend/generated python -m backend.watch_client
```


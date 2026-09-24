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
# Collaborative System Project

An Advanced Operating Systems course project.

## Current milestone

Shared notes with authenticated accounts, live Yjs editing, editing/viewing
presence, SQLite persistence, manual reconnect/save retry, and local Qwen writing
assistance. AI results are previewed and applied only while their source is current.

- [Complete setup and launcher](docs/setup.md)
- [Five-minute demo walkthrough](docs/demo.md)
- [Learning guide and official references](docs/learning.md)

Once dependencies and demo accounts are ready:

```bash
.venv/bin/python scripts/run_local.py --config deploy/demo.json
```

Open http://127.0.0.1:5273. Demo accounts: `alice` / `bob`, password `demo1234`.
The demo uses its own ports and data under `data/demo/`.

## Architecture

- Frontend: React and TypeScript.
- Gateway: Envoy translates gRPC-Web into native gRPC.
- Backend: Python implements the gRPC service.
- Storage: SQLite stores Yjs-compatible CRDT state and deduplicated request IDs.
- AI: a separate CPU Qwen worker, reached through the authenticated backend.
- Deployment: currently runs locally on macOS; Docker Compose is deferred.

The sections below retain the early RPC exercises. Use the complete setup guide
above for the full application, including the AI worker and isolated demo ports.

## macOS prerequisites

Install [Homebrew](https://brew.sh/) if it is not already available. Run the
following in Terminal. Install Apple's command-line tools first if needed and
finish their installer before continuing:

```bash
xcode-select --install
```

```bash
brew install git python@3.12 node@24 cmake envoy
export PATH="$(brew --prefix node@24)/bin:$PATH"
python3.12 --version
node --version
npm --version
envoy --version
```

Use Python 3.12 and Node.js 24.x. Repeat the PATH export in a new terminal if
`node` is missing or resolves to an older version. Then continue to **Project setup**.

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
python scripts/generate.py
```

Verify that the generated modules can be imported:

```bash
PYTHONPATH=backend/generated python -c "from collab.system.v1 import system_pb2, system_pb2_grpc; print('Generated imports OK')"
```

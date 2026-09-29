# EchoDoc — Collaborative Notes with Local AI

An Advanced Operating Systems course project: a shared text editor that combines
real-time collaboration, persistent documents and local AI writing assistance.
The browser interface is titled **Shared Notes**.

## Features

- Alice and Bob accounts with password authentication and session expiry.
- Document creation, listing and live collaborative editing using Yjs CRDTs.
- Editing/viewing presence for each open connection.
- SQLite persistence and request deduplication for safe save retries.
- Grammar correction, continuation, summarization and enhancement using local Qwen.
- Preview before applying AI edits; stale results cannot overwrite newer changes.
- Manual reconnect and retry, with navigation guarded while saves are unconfirmed.

## Architecture

```text
React + CodeMirror + Yjs
        │ gRPC-Web via Vite /rpc proxy
        ▼
      Envoy ── native gRPC ──► Python application ──► SQLite
                                     │ authenticated writing requests
                                     ▼
                              Python AI worker ──► Qwen on CPU
```

Protobuf contracts are shared between Python and TypeScript. The application
stores an accepted CRDT update before broadcasting it to connected clients.
The AI worker runs separately so model generation does not block document RPCs.
Configuration files use JSON; the frontend uses plain CSS.

## Requirements and platform support

Use Git, **Python 3.12**, **Node.js 24.x with npm**, C/C++ build tools and Envoy.
Internet access is needed for dependencies and the first model download. Allow
several GB of free disk space and enough memory for the model plus four services;
8 GB RAM is a practical starting point, not a measured minimum.

macOS has been exercised end to end. Windows instructions use **WSL2 + Ubuntu
24.04**, because the launcher uses Unix process groups and Linux-style paths.
Native PowerShell execution is not supported. The WSL2 instructions follow the
official installation guides but have not been executed on a Windows machine.

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

## Project setup

These commands are shared by macOS Terminal and Ubuntu inside WSL2.
Clone the submission repository, or open the root of your extracted submission:

```bash
git clone https://github.com/Abhinav-Singh10/EchoDoc.git
cd EchoDoc
```

Run every command below from this directory. Keep the two Python environments
separate: `.venv` runs the application; `ai/.venv` includes the native AI runtime.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python scripts/generate.py
npm --prefix frontend ci
npm --prefix frontend run generate
python3.12 -m venv ai/.venv
CMAKE_ARGS='-DGGML_METAL=OFF' ai/.venv/bin/python -m pip install -r ai/requirements.txt
.venv/bin/python -m pip check
ai/.venv/bin/python -m pip check
```

The AI dependency may compile from source; allow time for this step. See the
[llama-cpp-python installation guide](https://github.com/abetlen/llama-cpp-python#installation)
if compilation fails. Inference uses the CPU; a GPU and hosted AI API key are not required.

Generated Python files live in `backend/generated/`; generated TypeScript lives
in `frontend/src/gen/`. Regenerate both after editing files under `proto/`.

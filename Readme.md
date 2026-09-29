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

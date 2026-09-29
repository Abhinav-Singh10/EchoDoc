# Run the complete demo

Run commands from the repository root. This setup uses macOS, Python 3.12,
Node/npm and native Envoy. All service configuration is JSON.

## Install and generate

```bash
brew install python@3.12 envoy
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python scripts/generate.py
npm --prefix frontend ci
npm --prefix frontend run generate
```

The AI worker has its own environment because it needs the native llama.cpp runtime:

```bash
python3.12 -m venv ai/.venv
CMAKE_ARGS='-DGGML_METAL=OFF' ai/.venv/bin/python -m pip install -r ai/requirements.txt
```

A source build needs Apple's command-line developer tools (`xcode-select --install`).
Inference explicitly uses the CPU. On first start, Hugging Face downloads the
Qwen2.5-1.5B-Instruct Q4_K_M GGUF model into its normal cache. Allow download time
and disk space; subsequent runs reuse it. To use an existing file instead:
`export MODEL_PATH=/absolute/path/to/qwen2.5-1.5b-instruct-q4_k_m.gguf`.

## Start

Create separate demo accounts once (the command refuses to overwrite a file):

```bash
.venv/bin/python -m backend.seed_users --demo --output data/demo/users.json
.venv/bin/python scripts/run_local.py --config deploy/demo.json
```

Open http://127.0.0.1:5273 in two tabs. Sign in as `alice` and `bob`, both with
password `demo1234`. Wait for **AI ready** in the terminal before using the assistant.
Ctrl+C stops the launcher's own four processes. Occupied ports cause an error;
choose free ports in the JSON config instead of stopping someone else's server.

`deploy/demo.json` uses ports 52051 (app), 52052 (AI), 8181 (Envoy), 5273 (Vite),
with database/accounts under ignored `data/demo/`. Your normal data stays separate.
`deploy/local.json` uses 50051/50052/8080/5173 and the original account/database paths.
Use `backend.seed_users` without `--demo` for interactive passwords on the normal setup.

## Checks

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
envoy --mode validate -c deploy/envoy.json
```

With the demo running and AI ready, exercise the real RPCs and all four AI actions:

```bash
PYTHONPATH=backend/generated .venv/bin/python scripts/check_demo.py
```

This uses the demo accounts and creates one `RPC smoke check` note per run.

The frontend build currently warns about its large editor bundle; it still builds.
This is a local course demo, with manual reconnect and in-memory sessions/drafts.
A page reload loses unconfirmed edits. Saved documents persist in SQLite.

# EchoDoc

A collaborative notes editor for the Advanced Operating Systems course project.
Open the same note in two tabs, log in as different users, and edits appear in
both. Notes are saved in SQLite. There's also a local Qwen model for grammar
fixes, continuations, summaries and rewriting a selected passage.

## How it works

The frontend uses React, TypeScript, CodeMirror and Yjs, with plain CSS for styling.
Yjs handles merging text edits. The Python backend handles accounts, document
storage and broadcasting updates to connected users.

```text
Browser → Vite /rpc → Envoy → Python backend → SQLite
                                  ↓
                            Local Qwen worker
```

Envoy converts browser gRPC-Web requests to native gRPC. Both sides generate
message types from the protobuf files in `proto/`. The model runs in a separate
process on the CPU. Its replies appear as previews; applying one sends a normal
shared edit. If the document or selection has changed, the preview must be refreshed.

## Before starting

You'll need Git, Python 3.12, Node.js 24.x, Envoy and a C/C++ compiler. The first
setup downloads dependencies and the model, so leave a few GB of disk space.
No GPU or hosted AI API key is needed.

The project has been tested on macOS. On Windows, use WSL2 with Ubuntu 24.04:
the launcher depends on Unix process groups and won't run directly in PowerShell.
The Windows steps below have not been tested on a Windows PC yet.

## Setup on macOS

These commands use [Homebrew](https://brew.sh/). If you don't have Apple's
command-line tools, install them first and wait for the installer to finish:

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

If a new terminal picks up an older Node version, run the PATH export again.
Then skip to [Installing the project](#installing-the-project).

## Setup on Windows

On Windows 11 or a WSL2-compatible Windows 10 installation, open PowerShell as
Administrator and install Ubuntu ([WSL instructions](https://learn.microsoft.com/en-us/windows/wsl/install)):

```powershell
wsl --install -d Ubuntu-24.04
```

Restart if prompted, then open Ubuntu 24.04 and create a Linux user.
Check `wsl --list --verbose` in PowerShell. If Ubuntu shows version 1, run
`wsl --set-version Ubuntu-24.04 2`.

From here on, use the Ubuntu terminal. Install everything there, including Node
and Python; don't copy virtual environments or `node_modules` from another OS.

```bash
sudo apt update
sudo apt install -y git curl ca-certificates build-essential cmake python3.12 python3.12-venv python3.12-dev
```

Install Node through [nvm](https://github.com/nvm-sh/nvm#installing-and-updating):

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh -o /tmp/install-nvm.sh
bash /tmp/install-nvm.sh
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm install 24
nvm alias default 24
```

Download Envoy from its [release page](https://github.com/envoyproxy/envoy/releases/tag/v1.38.3):

```bash
mkdir -p "$HOME/.local/bin"
ENVOY_ARCH=x86_64
# On an ARM Windows PC, use ENVOY_ARCH=aarch_64 instead.
curl -fL "https://github.com/envoyproxy/envoy/releases/download/v1.38.3/envoy-1.38.3-linux-${ENVOY_ARCH}" -o "$HOME/.local/bin/envoy"
chmod +x "$HOME/.local/bin/envoy"
export PATH="$HOME/.local/bin:$PATH"
python3.12 --version
node --version
npm --version
envoy --version
```

Check `uname -m` if you're unsure which architecture to use. Run the PATH export
again if a new terminal can't find Envoy. This uses the release binary because
Envoy's old apt repository is [no longer maintained](https://www.envoyproxy.io/docs/envoy/latest/start/install).

Keep the project in Ubuntu's home directory, rather than under `/mnt/c`:

```bash
mkdir -p ~/projects
cd ~/projects
```

Once the app is running, open `http://localhost:5273` in your Windows browser.
WSL handles this through [localhost forwarding](https://learn.microsoft.com/en-us/windows/wsl/networking).

## Installing the project

The remaining commands are the same on macOS and WSL. Clone the repo, or open
the project folder if you already have a copy:

```bash
git clone https://github.com/Abhinav-Singh10/EchoDoc.git
cd EchoDoc
```

Run these from the repo root. There are two Python environments: one for the
backend and one for the model's native dependencies.

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

Installing `llama-cpp-python` can take a while because it may compile from source.
Its [installation notes](https://github.com/abetlen/llama-cpp-python#installation)
cover compiler errors.

If you change a `.proto` file, rerun both generation commands. They write to
`backend/generated/` and `frontend/src/gen/`.

## Running it

### Accounts

Create the demo accounts once:

```bash
.venv/bin/python -m backend.seed_users --demo --output data/demo/users.json
```

Log in with `alice` or `bob`; the password for both is `demo1234`.
Skip this command if the account file already exists. Leave out `--demo` to set
your own passwords, though the smoke check below expects `demo1234`.
Existing accounts are only overwritten if you add `--replace`.

### Start the app

```bash
.venv/bin/python scripts/run_local.py --config deploy/demo.json
```

This starts the backend, AI worker, Envoy and Vite in one terminal. Leave it open.
Wait for `AI ready on 127.0.0.1:52052` before trying the writing assistant.

The first run downloads [Qwen2.5-1.5B-Instruct Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)
from Hugging Face. Later runs reuse the cached file. If you already have the GGUF,
set its path before starting the app (a Linux path when using WSL):

```bash
export MODEL_PATH="/absolute/path/to/qwen2.5-1.5b-instruct-q4_k_m.gguf"
```

### Try it in the browser

Open http://localhost:5273 in two tabs, with Alice in one and Bob in the other.
On macOS, http://127.0.0.1:5273 works too.

Wait for **Saved** before closing a note. Use Ctrl+C in the terminal to stop the
app. Next time, just run the launcher again.

### Ports and data

| Setting | Demo configuration | Normal configuration |
| --- | --- | --- |
| JSON file | `deploy/demo.json` | `deploy/local.json` |
| Browser / Vite | `5273` | `5173` |
| Envoy gateway | `8181` | `8080` |
| Application gRPC | `52051` | `50051` |
| Internal AI gRPC | `52052` | `50052` |
| SQLite database | `data/demo/documents.sqlite3` | `data/documents.sqlite3` |
| Accounts | `data/demo/users.json` | `backend/users.json` |

The two configs use separate accounts and databases. For `deploy/local.json`,
create accounts with `.venv/bin/python -m backend.seed_users`, then launch with
`--config deploy/local.json`. SQLite creates the database on first use.

Saved notes survive a restart. Sessions and pending edits don't: log in again
after a backend restart, and keep the tab open until its edits are saved.

If a port is busy, change it in the JSON config. The launcher updates the proxy
settings to match and won't stop another process to free a port. Everything runs
locally, including the model; Docker isn't needed.

## Demonstrate the project

1. Alice creates a document and opens it. Bob clicks **Refresh documents** and
   opens the same document.
2. Type in either tab. Show matching content and revisions in both tabs, then
   show presence changing from **editing** to **viewing** after a pause.
3. Select a passage and click **Fix grammar** or **Enhance**. Review the result,
   then **Apply to document**; the other tab receives the resulting shared edit.
4. Place the cursor after some text to use **Continue**. **Summarize** displays
   a summary of the selection or whole note and never inserts it automatically.
5. Request an AI result, then edit in the other tab. Applying the old result is
   disabled because its source changed. Automatic suggestions are optional and
   also require review before insertion.
6. Wait for Saved, restart the launcher, log in and reopen the document to show
   persistence. During a connection interruption, restore the service and use
   **Reconnect**, followed by **Retry save** if there are unconfirmed edits.

See the [detailed demo walkthrough](docs/demo.md) for the presentation sequence.

## Verification

Run from the repository root on macOS or inside WSL:

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
envoy --mode validate -c deploy/envoy.json
```

With the **demo configuration** running and the AI ready, open a second terminal
in the same project directory and run:

```bash
PYTHONPATH=backend/generated .venv/bin/python scripts/check_demo.py
```

The check creates one `RPC smoke check` note and verifies authentication,
persistent CRDT content, concurrent duplicate saves, all four AI actions,
stale-revision rejection and logout. Expected output consists of `PASS:` lines.
It uses demo ports/accounts, so it is not intended for `deploy/local.json`.

The recorded [verification results](docs/verification.md) cover macOS and two
browser tabs on one computer. They do not claim Windows or second-device testing.
The frontend build currently reports a large-bundle warning but completes.

## Troubleshooting

| Problem | Action |
| --- | --- |
| `python` or `node` not found | Use the explicit Python commands above; check the platform-specific PATH setup. In WSL, install Linux tools inside Ubuntu. |
| `No module named collab` | Run `scripts/generate.py`. Use the launcher, which sets `PYTHONPATH`; direct RPC checks need the prefix shown above. |
| AI dependency fails to compile | Finish Xcode command-line tools on macOS, or install `build-essential`, CMake and Python development headers in Ubuntu. Retry the AI install with `--verbose` to see the compiler error. |
| AI is unavailable or first startup is slow | Check the AI terminal output and wait for the model download/loading to finish. Verify `MODEL_PATH` if set. |
| Port already occupied | Stop your previous launcher or select free ports in the JSON configuration. |
| Saved account file already exists | Skip account creation and use its existing credentials. Do not overwrite it just to restart. |
| Editor is read-only or disconnected | Restore the services, check the session and log in again if required. Use Reconnect / Retry save while keeping the tab open. |
| Windows browser cannot reach the app | Check that Vite is running in Ubuntu, use `localhost:5273`, and consult the linked WSL networking guide. Confirm WSL version 2 with `wsl --list --verbose`. |

## Repository layout

```text
frontend/          React, TypeScript, CodeMirror, Yjs and CSS
backend/           Authentication, documents, persistence and writing RPC forwarding
ai/                CPU model loading and internal AI gRPC service
proto/             Shared protobuf service and message definitions
deploy/            JSON launcher and Envoy configuration
scripts/           Contract generation, local launcher and demo check
docs/              Demo walkthrough, learning references and verification record
data/              Local databases and demo accounts (generated, ignored by Git)
```

## Scope and limitations

This submission is a single-server learning project. It implements collaborative
plain text, presence, persistent saves and local writing assistance. It does not
implement Raft replication, user registration, rich-text formatting or durable
offline drafts. Authentication is session-based, documents are shared by the demo
users, and local RPCs run without TLS. Reconnect/retry are manual. AI suggestions
can be inaccurate and should be reviewed before applying them.

## Learning references

The [learning guide](docs/learning.md) connects implementation files to official
Protobuf, gRPC, Yjs, React and Python documentation. The [setup companion](docs/setup.md)
provides a shorter macOS demo checklist; this README is the cross-platform entry point.

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

python scripts/generate_protos.py
```

Generate both services before starting the backend. `npm run generate` generates
the frontend TypeScript definitions only; Python needs the command above.

On first setup, create the local demo accounts before starting the server:

```bash
python -m backend.seed_users
```

This prompts for passwords for `alice` and `bob` and writes their password hashes
to the Git-ignored `backend/users.json`. Run it again only to replace the local
demo accounts; the authentication service requires this file at startup.

-> .env.development

```dotenv

VITE_RPC_BASE_URL=http://127.0.0.1:8080
```

Envoy running command

```
envoy -c deploy/envoy.json --log-level info
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

Frontend setup (from the repository root):

```bash
cd frontend
npm ci
npm run generate
npm run build
cp .env.development.example .env.development
npm run dev
```

Run the npm commands from `frontend/`, where `package.json` lives. The recorded
dependencies include the Buf CLI, TypeScript generator, and Protobuf/Connect
runtimes. `npm run generate` reads `../proto` using the v2 configuration in
`buf.gen.json` and writes TypeScript definitions to `src/gen/`. Regenerate after
changing the `.proto` files, before building or starting the frontend.

The development environment file points the browser client at Envoy on port 8080. Start Python and Envoy before using the RPC buttons.

```bash

sudo apt update
sudo apt install -y apt-transport-https gnupg2 curl lsb-release

curl -sL 'https://apt.envoyproxy.io/signing.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/envoy-keyring.gpg


echo "deb [arch=amd64 signed-by=/usr/share/keyrings/envoy-keyring.gpg] https://apt.envoyproxy.io jammy main" | sudo tee /etc/apt/sources.list.d/envoy.list

sudo apt update
sudo apt install -y envoy
```

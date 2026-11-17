"""Start the local app with Raft elections. Documents do not replicate yet."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def load_config(path):
    config = json.loads((ROOT / path).read_text())
    # Expand the single-node configuration into the same list used by the cluster.
    if "nodes" not in config:
        config["nodes"] = [{
            "id": "app-1", "app_port": config["app_port"],
            "database": config["database"],
        }]
    if not config["nodes"]:
        raise ValueError("Configure at least one application node.")
    ids = [node["id"] for node in config["nodes"]]
    if any(not isinstance(node_id, str) or not node_id.strip() for node_id in ids):
        raise ValueError("Every node needs a nonempty string id.")
    if len(ids) != len(set(ids)):
        raise ValueError("Application node ids must be distinct.")
    databases = [(ROOT / node["database"]).resolve() for node in config["nodes"]]
    if len(databases) != len(set(databases)):
        raise ValueError("Each application node needs a separate database.")
    ports = [node["app_port"] for node in config["nodes"]]
    ports += [config[key] for key in ("ai_port", "gateway_port", "frontend_port")]
    if any(type(port) is not int or not 1 <= port <= 65535 for port in ports):
        raise ValueError("Ports must be integers between 1 and 65535.")
    if len(ports) != len(set(ports)):
        raise ValueError("All configured ports must be distinct.")
    return config


def check_ports(config):
    ports = [(node["id"], "127.0.0.1", node["app_port"]) for node in config["nodes"]]
    ports += [
        ("AI", "127.0.0.1", config["ai_port"]),
        ("Envoy", "127.0.0.1", config["gateway_port"]),
        ("frontend", config.get("frontend_host", "127.0.0.1"), config["frontend_port"]),
    ]
    for name, host, port in ports:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError as error:
                raise ValueError(
                    f"{name} cannot use {host}:{port}: {error}. "
                    "Stop your old stack or edit the configuration; no processes were stopped."
                ) from error


def check_setup(config):
    users = ROOT / config["users"]
    if not users.is_file():
        raise ValueError(
            f"Missing accounts: {users}. Create them first with "
            f"python -m backend.seed_users --output '{config['users']}'. "
            "Add --demo only for disposable demo accounts."
        )
    for service in ("auth", "document", "system", "ai", "raft"):
        generated = ROOT / f"backend/generated/collab/{service}/v1/{service}_pb2_grpc.py"
        if not generated.is_file():
            raise ValueError("Missing Python RPC definitions. Run python scripts/generate_protos.py.")
        if not (ROOT / f"frontend/src/gen/collab/{service}/v1/{service}_pb.ts").is_file():
            raise ValueError("Missing frontend RPC definitions. Run npm --prefix frontend run generate.")
    if not (ROOT / "frontend/node_modules/.bin/vite").is_file():
        raise ValueError("Missing frontend dependencies. Run npm --prefix frontend ci.")
    envoy, npm = shutil.which("envoy"), shutil.which("npm")
    if not envoy or not npm:
        raise ValueError("Install Envoy and Node/npm before running the launcher.")
    ai_python = ROOT / config.get("ai_python", sys.executable)
    if not ai_python.is_file() or not os.access(ai_python, os.X_OK):
        raise ValueError(f"AI Python interpreter is missing or not executable: {ai_python}")
    return envoy, npm, str(ai_python)


def gateway_config(config):
    gateway = json.loads((ROOT / "deploy/envoy.json").read_text())
    resources = gateway["static_resources"]
    listener = resources["listeners"][0]
    listener["address"]["socket_address"]["port_value"] = config["gateway_port"]
    endpoint = resources["clusters"][0]["load_assignment"]["endpoints"][0]["lb_endpoints"][0]
    endpoint["endpoint"]["address"]["socket_address"]["port_value"] = config["nodes"][0]["app_port"]
    manager = listener["filter_chains"][0]["filters"][0]["typed_config"]
    host = manager["route_config"]["virtual_hosts"][0]
    cors = host["typed_per_filter_config"]["envoy.filters.http.cors"]
    cors["allow_origin_string_match"] = [{
        "exact": f"http://{config.get('frontend_host', '127.0.0.1')}:{config['frontend_port']}",
    }]
    return gateway


def stop_processes(children):
    # Each child has its own process group, including npm's Vite subprocess.
    # Signal the group even if its original parent has already exited.
    for _, child in reversed(children):
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 10
    for _, child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for _, child in children:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="deploy/local.json")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    check_ports(config)
    envoy, npm, ai_python = check_setup(config)
    env = dict(
        os.environ, PYTHONPATH=str(ROOT / "backend/generated"),
        AI_BIND=f"127.0.0.1:{config['ai_port']}",
        AI_ADDRESS=f"127.0.0.1:{config['ai_port']}",
        USERS_PATH=str(ROOT / config["users"]),
        FRONTEND_PORT=str(config["frontend_port"]),
        FRONTEND_HOST=config.get("frontend_host", "127.0.0.1"),
        ENVOY_ADDRESS=f"http://127.0.0.1:{config['gateway_port']}",
        VITE_RPC_BASE_URL="",
    )
    children = []
    with tempfile.TemporaryDirectory(prefix="echodoc-gateway-") as folder:
        gateway = Path(folder) / "envoy.json"
        gateway.write_text(json.dumps(gateway_config(config)))
        commands = []
        members = {node["id"]: f"127.0.0.1:{node['app_port']}" for node in config["nodes"]}
        for node in config["nodes"]:
            node_env = dict(
                env, SERVER_ID=node["id"],
                APP_BIND=f"127.0.0.1:{node['app_port']}",
                DATABASE_PATH=str(ROOT / node["database"]),
                RAFT_MEMBERS=json.dumps(members),
            )
            commands.append((node["id"], [sys.executable, "-u", "-m", "backend.server"], node_env))
            print(f"{node['id']}: port {node['app_port']}, database {node_env['DATABASE_PATH']}", flush=True)
        commands += [
            ("AI", [ai_python, "-u", "-m", "ai.server"], env),
            ("Envoy", [envoy, "-c", str(gateway), "--log-level", "warning"], env),
            ("frontend", [npm, "--prefix", "frontend", "run", "dev"], env),
        ]
        try:
            for name, command, child_env in commands:
                child = subprocess.Popen(command, cwd=ROOT, env=child_env, start_new_session=True)
                children.append((name, child))
                print(f"Started {name} (PID {child.pid})", flush=True)
            print(f"Open http://{env['FRONTEND_HOST']}:{config['frontend_port']} - wait for AI ready.", flush=True)
            print(f"Gateway targets {config['nodes'][0]['id']} only. Nodes do not replicate yet.", flush=True)
            print("Ctrl+C stops only this launcher's processes.", flush=True)
            reported = set()
            while True:
                for name, child in children:
                    code = child.poll()
                    if code is not None and child.pid not in reported:
                        print(f"{name} exited with code {code}; not restarting it. Other processes remain running.", flush=True)
                        reported.add(child.pid)
                if len(reported) == len(children):
                    return 1
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping this launcher's processes...", flush=True)
            return 0
        finally:
            stop_processes(children)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Cannot start EchoDoc: {error}")

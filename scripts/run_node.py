"""Restart one configured application backend using its existing database."""

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_local import backend_environment, check_backend_setup, check_port, load_config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="deploy/local.json")
    parser.add_argument("--node", required=True)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    node = next((node for node in config["nodes"] if node["id"] == args.node), None)
    if node is None:
        raise ValueError(f"Unknown node {args.node!r}; choose a configured node ID")
    environment = backend_environment(config, node)
    if not Path(environment["DATABASE_PATH"]).is_file():
        raise ValueError(
            f"No existing database for {args.node}: {environment['DATABASE_PATH']}. "
            "Use the full launcher for initial setup; this command never replaces a lost database."
        )
    check_backend_setup(config)
    check_port(args.node, "127.0.0.1", node["app_port"])
    print(f"Restarting {args.node} (PID {os.getpid()}) on {environment['APP_BIND']}", flush=True)
    print(f"Database: {environment['DATABASE_PATH']}", flush=True)
    print("This terminal owns this backend. Ctrl+C here stops it.", flush=True)
    os.chdir(ROOT)
    os.execve(sys.executable, [sys.executable, "-u", "-m", "backend.server"], environment)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Cannot restart backend: {error}")

"""Launch this demo's four processes; never stop another user's processes."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='deploy/local.json')
    args = parser.parse_args()
    config = json.loads((ROOT / args.config).read_text())
    for key in ('app_port', 'ai_port', 'gateway_port', 'frontend_port'):
        with socket.socket() as sock:
            try: sock.bind(('127.0.0.1', config[key]))
            except OSError: raise SystemExit(f'{key} {config[key]} is occupied. Choose other ports; no processes were stopped.')
    if not (ROOT / config['users']).exists():
        raise SystemExit(f"Missing accounts: {config['users']}. Run backend.seed_users with --output first.")
    envoy = shutil.which('envoy')
    npm = shutil.which('npm')
    ai_python = ROOT / config.get('ai_python', sys.executable)
    if not envoy or not npm or not ai_python.exists():
        raise SystemExit('Envoy, npm, and the configured AI Python runtime are required.')
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'backend/generated'),
        APP_BIND=f"127.0.0.1:{config['app_port']}", AI_BIND=f"127.0.0.1:{config['ai_port']}",
        AI_ADDRESS=f"127.0.0.1:{config['ai_port']}", DATABASE_PATH=str(ROOT / config['database']),
        USERS_PATH=str(ROOT / config['users']), FRONTEND_PORT=str(config['frontend_port']),
        FRONTEND_HOST=config.get('frontend_host', '127.0.0.1'),
        ENVOY_ADDRESS=f"http://127.0.0.1:{config['gateway_port']}", VITE_RPC_BASE_URL='')
    gateway = json.loads((ROOT / 'deploy/envoy.json').read_text())
    gateway['static_resources']['listeners'][0]['address']['socket_address']['port_value'] = config['gateway_port']
    gateway['static_resources']['clusters'][0]['load_assignment']['endpoints'][0]['lb_endpoints'][0]['endpoint']['address']['socket_address']['port_value'] = config['app_port']
    children = []
    with tempfile.TemporaryDirectory(prefix='shared-notes-') as temp:
        gateway_file = Path(temp) / 'envoy.json'
        gateway_file.write_text(json.dumps(gateway))
        commands = [('application', [sys.executable, '-m', 'backend.server']),
                    ('AI', [str(ai_python), '-m', 'ai.server']),
                    ('Envoy', [envoy, '-c', str(gateway_file), '--log-level', 'error']),
                    ('Vite', [npm, '--prefix', 'frontend', 'run', 'dev'])]
        try:
            for name, command in commands:
                children.append((name, subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True)))
            print(f"Open http://127.0.0.1:{config['frontend_port']} — wait for AI ready. Ctrl+C stops this launcher’s processes.", flush=True)
            while True:
                for name, child in children:
                    if child.poll() is not None:
                        raise RuntimeError(f'{name} exited with code {child.returncode}')
                time.sleep(.5)
        except KeyboardInterrupt:
            print('\nStopping demo processes...', flush=True)
        finally:
            for _, child in reversed(children):
                if child.poll() is None: os.killpg(child.pid, signal.SIGTERM)
            for _, child in children:
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait()


if __name__ == '__main__': main()

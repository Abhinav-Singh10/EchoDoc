"""Regenerate Python RPC code from all shared contracts."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
output = root / 'backend/generated'
output.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, '-m', 'grpc_tools.protoc', f'-I{root / "proto"}',
                f'--python_out={output}', f'--grpc_python_out={output}',
                *map(str, sorted((root / 'proto').rglob('*.proto')))], check=True)

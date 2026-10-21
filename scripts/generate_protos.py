from pathlib import Path
import subprocess
import sys


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    proto_dir = root / "proto"
    output_dir = root / "backend" / "generated"
    proto_files = sorted(proto_dir.rglob("*.proto"))

    if not proto_files:
        raise SystemExit(f"No .proto files found in {proto_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{proto_dir}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            *map(str, proto_files),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()

import argparse
import json
# accepts a password without displaying it
from getpass import getpass
from pathlib import Path

from argon2 import PasswordHasher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Use public password demo1234')
    parser.add_argument('--output', default='backend/users.json')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    users_file = Path(args.output)
    if users_file.exists() and not args.replace:
        raise SystemExit(f'{users_file} already exists; choose a new --output or explicitly --replace.')
    hasher = PasswordHasher()
    users = {}

    for username in ("alice", "bob"):
        password = "demo1234" if args.demo else getpass(f"Choose a demo password for {username}: ")

        if not password:
            raise ValueError("Demo passwords cannot be empty")

        users[username] = {
            "user_id": f"user-{username}",
            "username": username,
            "password_hash": hasher.hash(password),
        }

    users_file.parent.mkdir(parents=True, exist_ok=True)
    users_file.write_text(
        json.dumps(users, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Created alice and bob in {users_file}")


if __name__ == "__main__":
    main()

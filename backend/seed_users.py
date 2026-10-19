import json
# accepts a password without displaying it
from getpass import getpass
from pathlib import Path

from argon2 import PasswordHasher


def main():
    hasher = PasswordHasher()
    users = {}

    for username in ("alice", "bob"):
        password = getpass(f"Choose a demo password for {username}: ")

        if not password:
            raise ValueError("Demo passwords cannot be empty")

        users[username] = {
            "user_id": f"user-{username}",
            "username": username,
            "password_hash": hasher.hash(password),
        }

    users_file = Path(__file__).with_name("users.json")
    users_file.write_text(
        json.dumps(users, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Created alice and bob in {users_file}")


if __name__ == "__main__":
    main()
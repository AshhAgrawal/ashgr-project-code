from __future__ import annotations

import getpass
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from retail_agent.auth import AuthError, AuthService, public_user  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a retail workspace user.")
    parser.add_argument(
        "--role",
        choices=["staff", "admin"],
        default="staff",
        help="Account role. Defaults to staff.",
    )
    return parser.parse_args()


def main() -> None:
    args = arguments()
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri or not database_name:
        raise SystemExit("MONGODB_URI and MONGODB_DATABASE are required in .env")

    name = input("Name: ").strip()
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    try:
        client.admin.command("ping")
        service = AuthService(client[database_name])
        user = service.create_user(name, email, password, role=args.role)
    except AuthError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        client.close()

    created = public_user(user)
    print(
        f"Created {created['role']} user {created['email']} ({created['id']})."
    )


if __name__ == "__main__":
    main()

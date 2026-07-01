from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from retail_agent.auth import normalize_email  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Change a workspace user's role.")
    parser.add_argument("email", help="Existing user's email address.")
    parser.add_argument("role", choices=["staff", "admin"])
    return parser.parse_args()


def main() -> None:
    args = arguments()
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri or not database_name:
        raise SystemExit("MONGODB_URI and MONGODB_DATABASE are required in .env")

    email = normalize_email(args.email)
    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    try:
        client.admin.command("ping")
        result = client[database_name].users.update_one(
            {"email": email},
            {
                "$set": {
                    "role": args.role,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    finally:
        client.close()
    if result.matched_count != 1:
        raise SystemExit(f"No user found for {email}.")
    print(f"{email}: role set to {args.role}")


if __name__ == "__main__":
    main()

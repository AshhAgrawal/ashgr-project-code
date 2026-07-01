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

from retail_agent.auth import AUTHENTICATION_FEATURE  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enable or disable an app feature.")
    parser.add_argument(
        "feature",
        choices=[AUTHENTICATION_FEATURE],
        help="Feature to update.",
    )
    parser.add_argument(
        "state",
        choices=["on", "off"],
        help="New feature state.",
    )
    return parser.parse_args()


def main() -> None:
    args = arguments()
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri or not database_name:
        raise SystemExit("MONGODB_URI and MONGODB_DATABASE are required in .env")

    enabled = args.state == "on"
    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    try:
        client.admin.command("ping")
        client[database_name].features.update_one(
            {"_id": args.feature},
            {
                "$set": {
                    "enabled": enabled,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    finally:
        client.close()

    print(f"{args.feature}: {'enabled' if enabled else 'disabled'}")


if __name__ == "__main__":
    main()

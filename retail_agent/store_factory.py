from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .store import RetailStore


def create_store(data_dir: str | Path = "data") -> RetailStore:
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")

    if bool(uri) != bool(database_name):
        raise RuntimeError(
            "MONGODB_URI and MONGODB_DATABASE must either both be set or both be absent."
        )
    if uri and database_name:
        from .mongo_store import MongoRetailStore

        return MongoRetailStore(uri, database_name)
    return RetailStore(data_dir)

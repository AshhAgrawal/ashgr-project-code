from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from bson.decimal128 import Decimal128
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, ReplaceOne
from pymongo.database import Database
from pymongo.errors import InvalidURI, PyMongoError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


Converter = Callable[[str], Any]


def as_int(value: str) -> int:
    return int(value)


def as_decimal(value: str) -> Decimal128:
    return Decimal128(Decimal(value))


def as_utc_date(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.combine(parsed, time.min, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CollectionSpec:
    filename: str
    collection: str
    key_fields: tuple[str, ...]
    converters: dict[str, Converter]
    nullable_fields: frozenset[str] = frozenset()


COLLECTIONS = (
    CollectionSpec(
        "products.csv",
        "products",
        ("sku",),
        {"retail_price": as_decimal},
        frozenset({"color", "size"}),
    ),
    CollectionSpec(
        "customers.csv",
        "customers",
        ("customer_id",),
        {"joined_date": as_utc_date},
    ),
    CollectionSpec("suppliers.csv", "suppliers", ("supplier_id",), {}),
    CollectionSpec(
        "supplier_catalog.csv",
        "supplier_catalog",
        ("supplier_id", "product_id"),
        {"unit_cost": as_decimal, "lead_time_days": as_int},
    ),
    CollectionSpec(
        "inventory.csv",
        "inventory",
        ("sku",),
        {
            "on_hand_qty": as_int,
            "reorder_point": as_int,
            "reorder_qty": as_int,
        },
    ),
    CollectionSpec(
        "orders.csv",
        "orders",
        ("order_id",),
        {"order_date": as_utc_date, "order_discount_pct": as_decimal},
        frozenset({"customer_id"}),
    ),
    CollectionSpec(
        "order_lines.csv",
        "order_lines",
        ("order_id", "line_no"),
        {"line_no": as_int, "quantity": as_int, "unit_price": as_decimal},
    ),
    CollectionSpec(
        "returns.csv",
        "returns",
        ("return_id",),
        {
            "return_date": as_utc_date,
            "quantity": as_int,
            "refund_amount": as_decimal,
        },
    ),
    CollectionSpec(
        "promotions.csv",
        "promotions",
        ("promo_id",),
        {
            "value": as_decimal,
            "start_date": as_utc_date,
            "end_date": as_utc_date,
        },
    ),
)


INDEXES: dict[str, tuple[tuple[list[tuple[str, int]], bool, str], ...]] = {
    "products": (
        ([("sku", ASCENDING)], True, "uq_products_sku"),
        ([("product_id", ASCENDING)], False, "ix_products_product_id"),
    ),
    "customers": (
        ([("customer_id", ASCENDING)], True, "uq_customers_customer_id"),
        ([("email", ASCENDING)], True, "uq_customers_email"),
    ),
    "suppliers": (
        ([("supplier_id", ASCENDING)], True, "uq_suppliers_supplier_id"),
    ),
    "supplier_catalog": (
        (
            [("supplier_id", ASCENDING), ("product_id", ASCENDING)],
            True,
            "uq_supplier_catalog_supplier_product",
        ),
        ([("product_id", ASCENDING)], False, "ix_supplier_catalog_product_id"),
    ),
    "inventory": (([("sku", ASCENDING)], True, "uq_inventory_sku"),),
    "orders": (
        ([("order_id", ASCENDING)], True, "uq_orders_order_id"),
        ([("order_date", ASCENDING)], False, "ix_orders_order_date"),
        ([("customer_id", ASCENDING)], False, "ix_orders_customer_id"),
    ),
    "order_lines": (
        (
            [("order_id", ASCENDING), ("line_no", ASCENDING)],
            True,
            "uq_order_lines_order_line",
        ),
        ([("sku", ASCENDING)], False, "ix_order_lines_sku"),
    ),
    "returns": (
        ([("return_id", ASCENDING)], True, "uq_returns_return_id"),
        ([("order_id", ASCENDING)], False, "ix_returns_order_id"),
        ([("return_date", ASCENDING)], False, "ix_returns_return_date"),
    ),
    "promotions": (
        ([("promo_id", ASCENDING)], True, "uq_promotions_promo_id"),
        (
            [("start_date", ASCENDING), ("end_date", ASCENDING)],
            False,
            "ix_promotions_date_range",
        ),
    ),
    "purchase_orders": (
        ([("po_id", ASCENDING)], True, "uq_purchase_orders_po_id"),
        (
            [("product_id", ASCENDING), ("status", ASCENDING)],
            False,
            "ix_purchase_orders_product_status",
        ),
    ),
}


def parse_csv(spec: CollectionSpec) -> list[dict[str, Any]]:
    path = DATA_DIR / spec.filename
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    documents: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        document: dict[str, Any] = {}
        try:
            for field, raw_value in row.items():
                value = raw_value.strip()
                if not value and field in spec.nullable_fields:
                    document[field] = None
                elif field in spec.converters:
                    document[field] = spec.converters[field](value)
                else:
                    document[field] = value
        except (ValueError, ArithmeticError) as exc:
            raise ValueError(f"{spec.filename}:{row_number}: {exc}") from exc
        documents.append(document)
    return documents


def create_indexes(database: Database[Any]) -> None:
    for collection_name, indexes in INDEXES.items():
        collection = database[collection_name]
        for keys, unique, name in indexes:
            collection.create_index(keys, unique=unique, name=name)


def initialize_runtime_metadata(database: Database[Any]) -> None:
    id_sources = {
        "O": ("orders", "order_id", 1000),
        "R": ("returns", "return_id", 0),
        "PR": ("promotions", "promo_id", 0),
        "PO": ("purchase_orders", "po_id", 0),
    }
    for prefix, (collection_name, field, default) in id_sources.items():
        maximum = default
        for row in database[collection_name].find({}, {field: 1, "_id": 0}):
            identifier = row.get(field, "")
            if identifier.startswith(prefix + "-"):
                tail = identifier.split("-", 1)[1]
                if tail.isdigit():
                    maximum = max(maximum, int(tail))
        database.counters.update_one(
            {"_id": prefix}, {"$max": {"value": maximum}}, upsert=True
        )

    returned: dict[tuple[str, str], int] = {}
    for row in database.returns.find({}, {"order_id": 1, "sku": 1, "quantity": 1}):
        key = (row["order_id"], row["sku"])
        returned[key] = returned.get(key, 0) + int(row["quantity"])
    for (order_id, sku), quantity in returned.items():
        database.order_lines.update_one(
            {"order_id": order_id, "sku": sku},
            {"$max": {"returned_qty": quantity}},
        )


def import_collection(
    database: Database[Any], spec: CollectionSpec, *, replace: bool
) -> tuple[int, int, int]:
    documents = parse_csv(spec)
    collection = database[spec.collection]

    if replace:
        collection.delete_many({})

    operations = []
    for document in documents:
        identity = {field: document[field] for field in spec.key_fields}
        operations.append(ReplaceOne(identity, document, upsert=True))

    if operations:
        collection.bulk_write(operations, ordered=True)

    return len(documents), collection.count_documents({}), len(operations)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import the retail CSV seed data into MongoDB Atlas."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing documents from the nine seed collections before importing.",
    )
    return parser.parse_args()


def main() -> None:
    args = arguments()
    load_dotenv(PROJECT_ROOT / ".env")

    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri:
        raise SystemExit("MONGODB_URI is missing from .env")
    if not database_name:
        raise SystemExit("MONGODB_DATABASE is missing from .env")
    if database_name in {"admin", "config", "local"}:
        raise SystemExit("MONGODB_DATABASE must be an application database")

    try:
        client: MongoClient[Any] = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    except InvalidURI as exc:
        raise SystemExit(
            "MONGODB_URI is invalid. URL-encode reserved characters in the username "
            "and password (for example, @ becomes %40)."
        ) from exc

    try:
        try:
            client.admin.command("ping")
        except PyMongoError as exc:
            raise SystemExit(f"Could not connect to MongoDB Atlas: {exc}") from exc
        database = client[database_name]

        print(f"Connected. Importing into database: {database_name}")
        for spec in COLLECTIONS:
            source_count, final_count, operation_count = import_collection(
                database, spec, replace=args.replace
            )
            print(
                f"{spec.collection}: processed {operation_count}, "
                f"CSV rows {source_count}, collection documents {final_count}"
            )

        if "purchase_orders" not in database.list_collection_names():
            database.create_collection("purchase_orders")
        create_indexes(database)
        initialize_runtime_metadata(database)
        print("Import complete. Collections and indexes are ready.")
    finally:
        client.close()


if __name__ == "__main__":
    main()

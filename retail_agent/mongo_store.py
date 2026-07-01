from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date as Date
from datetime import datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from bson.decimal128 import Decimal128
from pymongo import MongoClient, ReturnDocument
from pymongo.client_session import ClientSession
from pymongo.database import Database

from .models import (
    Customer,
    InventoryItem,
    Order,
    OrderLine,
    ProductVariant,
    Promotion,
    PurchaseOrder,
    ReturnRecord,
    Supplier,
    SupplierCatalogItem,
)
from .store import RetailStore, StoreError, money


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


def _decimal128(value: Decimal | str | int | float) -> Decimal128:
    return Decimal128(Decimal(str(value)))


def _date_string(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, Date):
        return value.isoformat()
    return str(value)


def _mongo_date(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.combine(parsed, time.min, tzinfo=timezone.utc)


class MongoRetailStore(RetailStore):
    """Retail engine backed by MongoDB while retaining the existing tool API."""

    backend = "mongodb"

    def __init__(self, uri: str, database_name: str) -> None:
        self.client: MongoClient[Any] = MongoClient(
            uri,
            serverSelectionTimeoutMS=10_000,
            appname="retail-agent",
        )
        self.client.admin.command("ping")
        self.database: Database[Any] = self.client[database_name]
        super().__init__(Path("."))
        self._initialize_counters()
        self._initialize_returned_quantities()

    def load(self) -> None:
        self.products_by_sku.clear()
        self.products_by_id.clear()
        self.customers_by_id.clear()
        self.customers_by_name.clear()
        self.suppliers_by_id.clear()
        self.suppliers_by_name.clear()
        self.catalog_by_product_id.clear()
        self.inventory_by_sku.clear()
        self.orders_by_id.clear()
        self.returns_by_id.clear()
        self.promotions.clear()
        self.purchase_orders.clear()

        for row in self.database.products.find({}, {"_id": 0}):
            product = ProductVariant(
                sku=row["sku"],
                product_id=row["product_id"],
                product_name=row["product_name"],
                category=row["category"],
                color=row.get("color") or None,
                size=row.get("size") or None,
                retail_price=money(_decimal(row["retail_price"])),
            )
            self.products_by_sku[product.sku] = product
            self.products_by_id[product.product_id].append(product)

        for row in self.database.customers.find({}, {"_id": 0}):
            customer = Customer(
                customer_id=row["customer_id"],
                name=row["name"],
                email=row["email"],
                joined_date=_date_string(row["joined_date"]),
            )
            self.customers_by_id[customer.customer_id] = customer
            self.customers_by_name[customer.name.strip().lower()] = customer

        for row in self.database.suppliers.find({}, {"_id": 0}):
            supplier = Supplier(row["supplier_id"], row["supplier_name"])
            self.suppliers_by_id[supplier.supplier_id] = supplier
            self.suppliers_by_name[supplier.supplier_name.strip().lower()] = supplier

        for row in self.database.supplier_catalog.find({}, {"_id": 0}):
            item = SupplierCatalogItem(
                supplier_id=row["supplier_id"],
                product_id=row["product_id"],
                unit_cost=money(_decimal(row["unit_cost"])),
                lead_time_days=int(row["lead_time_days"]),
            )
            self.catalog_by_product_id[item.product_id].append(item)

        for row in self.database.inventory.find({}, {"_id": 0}):
            item = InventoryItem(
                sku=row["sku"],
                on_hand_qty=int(row["on_hand_qty"]),
                reorder_point=int(row["reorder_point"]),
                reorder_qty=int(row["reorder_qty"]),
            )
            self.inventory_by_sku[item.sku] = item

        for row in self.database.orders.find({}, {"_id": 0}):
            order = Order(
                order_id=row["order_id"],
                order_date=_date_string(row["order_date"]),
                customer_id=row.get("customer_id") or None,
                order_discount_pct=_decimal(row["order_discount_pct"]),
                payment_method=row["payment_method"],
            )
            self.orders_by_id[order.order_id] = order

        order_lines = self.database.order_lines.find({}, {"_id": 0}).sort(
            [("order_id", 1), ("line_no", 1)]
        )
        for row in order_lines:
            order_id = row["order_id"]
            if order_id not in self.orders_by_id:
                raise StoreError(f"Order line references missing order {order_id}.")
            self.orders_by_id[order_id].lines.append(
                OrderLine(
                    order_id=order_id,
                    line_no=int(row["line_no"]),
                    sku=row["sku"],
                    quantity=int(row["quantity"]),
                    unit_price=money(_decimal(row["unit_price"])),
                )
            )

        for row in self.database.returns.find({}, {"_id": 0}):
            record = ReturnRecord(
                return_id=row["return_id"],
                return_date=_date_string(row["return_date"]),
                order_id=row["order_id"],
                sku=row["sku"],
                quantity=int(row["quantity"]),
                condition=row["condition"],
                refund_amount=money(_decimal(row["refund_amount"])),
            )
            self.returns_by_id[record.return_id] = record

        for row in self.database.promotions.find({}, {"_id": 0}):
            self.promotions.append(
                Promotion(
                    promo_id=row["promo_id"],
                    description=row["description"],
                    type=row["type"],
                    value=_decimal(row["value"]),
                    scope_type=row["scope_type"],
                    scope_ref=row["scope_ref"],
                    start_date=_date_string(row["start_date"]),
                    end_date=_date_string(row["end_date"]),
                )
            )

        for row in self.database.purchase_orders.find({}, {"_id": 0}):
            po = PurchaseOrder(
                po_id=row["po_id"],
                product_id=row["product_id"],
                supplier_id=row["supplier_id"],
                ordered_qty=int(row["ordered_qty"]),
                received_qty=int(row["received_qty"]),
                order_date=_date_string(row["order_date"]),
                status=row.get("status", "open"),
            )
            self.purchase_orders[po.po_id] = po

        self.last_order_id = self._latest_id("O", self.orders_by_id)
        self.last_return_id = self._latest_id("R", self.returns_by_id)
        self.last_purchase_order_id = self._latest_id("PO", self.purchase_orders)

        if not self.products_by_sku or not self.inventory_by_sku:
            raise StoreError(
                "MongoDB seed data is missing. Run scripts/import_csv_to_mongodb.py first."
            )

    def refresh(self) -> None:
        self.load()

    def ring_up_sale(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.refresh()
        result = super().ring_up_sale(*args, **kwargs)
        order = self.orders_by_id[result["order_id"]]
        quantities: Counter[str] = Counter()
        for line in order.lines:
            quantities[line.sku] += line.quantity

        def persist(session: ClientSession) -> None:
            remaining: dict[str, int] = {}
            for sku, quantity in quantities.items():
                updated = self.database.inventory.find_one_and_update(
                    {"sku": sku, "on_hand_qty": {"$gte": quantity}},
                    {"$inc": {"on_hand_qty": -quantity}},
                    return_document=ReturnDocument.AFTER,
                    session=session,
                )
                if updated is None:
                    raise StoreError(f"Inventory changed; insufficient stock for {sku}.")
                remaining[sku] = int(updated["on_hand_qty"])

            self.database.orders.insert_one(
                {
                    "order_id": order.order_id,
                    "order_date": _mongo_date(order.order_date),
                    "customer_id": order.customer_id,
                    "order_discount_pct": _decimal128(order.order_discount_pct),
                    "payment_method": order.payment_method,
                },
                session=session,
            )
            self.database.order_lines.insert_many(
                [
                    {
                        "order_id": line.order_id,
                        "line_no": line.line_no,
                        "sku": line.sku,
                        "quantity": line.quantity,
                        "unit_price": _decimal128(line.unit_price),
                        "returned_qty": 0,
                    }
                    for line in order.lines
                ],
                session=session,
            )
            for receipt_line in result["lines"]:
                receipt_line["remaining_on_hand"] = remaining[receipt_line["sku"]]

        self._persist_or_refresh(persist)
        return result

    def return_item(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.refresh()
        result = super().return_item(*args, **kwargs)
        record = self.returns_by_id[result["return_id"]]

        def persist(session: ClientSession) -> None:
            reserved = self.database.order_lines.update_one(
                {
                    "order_id": record.order_id,
                    "sku": record.sku,
                    "$expr": {
                        "$lte": [
                            {
                                "$add": [
                                    {"$ifNull": ["$returned_qty", 0]},
                                    record.quantity,
                                ]
                            },
                            "$quantity",
                        ]
                    },
                },
                {"$inc": {"returned_qty": record.quantity}},
                session=session,
            )
            if reserved.modified_count != 1:
                raise StoreError("Return quantity changed; no units remain returnable.")

            self.database.returns.insert_one(
                {
                    "return_id": record.return_id,
                    "return_date": _mongo_date(record.return_date),
                    "order_id": record.order_id,
                    "sku": record.sku,
                    "quantity": record.quantity,
                    "condition": record.condition,
                    "refund_amount": _decimal128(record.refund_amount),
                },
                session=session,
            )
            if record.condition == "good":
                updated = self.database.inventory.find_one_and_update(
                    {"sku": record.sku},
                    {"$inc": {"on_hand_qty": record.quantity}},
                    return_document=ReturnDocument.AFTER,
                    session=session,
                )
                if updated is None:
                    raise StoreError(f"Missing inventory record for {record.sku}.")
            else:
                updated = self.database.inventory.find_one(
                    {"sku": record.sku}, session=session
                )
                if updated is None:
                    raise StoreError(f"Missing inventory record for {record.sku}.")
            result["on_hand_qty"] = int(updated["on_hand_qty"])

        self._persist_or_refresh(persist)
        return result

    def create_promotion(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.refresh()
        result = super().create_promotion(*args, **kwargs)
        promo = next(p for p in self.promotions if p.promo_id == result["promo_id"])
        try:
            self.database.promotions.insert_one(
                {
                    "promo_id": promo.promo_id,
                    "description": promo.description,
                    "type": promo.type,
                    "value": _decimal128(promo.value),
                    "scope_type": promo.scope_type,
                    "scope_ref": promo.scope_ref,
                    "start_date": _mongo_date(promo.start_date),
                    "end_date": _mongo_date(promo.end_date),
                }
            )
        except Exception:
            self.refresh()
            raise
        return result

    def reorder_low_stock(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.refresh()
        result = super().reorder_low_stock(*args, **kwargs)
        purchase_orders = [
            self.purchase_orders[row["po_id"]] for row in result["purchase_orders"]
        ]
        if not purchase_orders:
            return result

        def persist(session: ClientSession) -> None:
            self.database.purchase_orders.insert_many(
                [self._purchase_order_document(po) for po in purchase_orders],
                session=session,
            )

        self._persist_or_refresh(persist)
        return result

    def receive_purchase_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.refresh()
        result = super().receive_purchase_order(*args, **kwargs)
        po = self.purchase_orders[result["po_id"]]

        def persist(session: ClientSession) -> None:
            self.database.purchase_orders.insert_one(
                self._purchase_order_document(po), session=session
            )
            updated = self.database.inventory.find_one_and_update(
                {"sku": result["received_into_sku"]},
                {"$inc": {"on_hand_qty": po.received_qty}},
                return_document=ReturnDocument.AFTER,
                session=session,
            )
            if updated is None:
                raise StoreError(
                    f"Missing inventory record for {result['received_into_sku']}."
                )
            result["on_hand_qty"] = int(updated["on_hand_qty"])

        self._persist_or_refresh(persist)
        return result

    def revenue_report(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.refresh()
        return super().revenue_report(*args, **kwargs)

    def top_products_by_margin(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.refresh()
        return super().top_products_by_margin(*args, **kwargs)

    def stockout_report(self) -> dict[str, Any]:
        self.refresh()
        return super().stockout_report()

    def inventory_report(self) -> dict[str, Any]:
        self.refresh()
        return super().inventory_report()

    def _persist_or_refresh(self, callback: Callable[[ClientSession], None]) -> None:
        try:
            with self.client.start_session() as session:
                with session.start_transaction():
                    callback(session)
        except Exception:
            self.refresh()
            raise

    def _next_id(self, prefix: str, existing: dict[str, Any]) -> str:
        del existing
        counter = self.database.counters.find_one_and_update(
            {"_id": prefix},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        width = 4 if prefix == "O" else 3
        return f"{prefix}-{int(counter['value']):0{width}d}"

    def _initialize_counters(self) -> None:
        collections = {
            "O": self.orders_by_id,
            "R": self.returns_by_id,
            "PR": {promo.promo_id: promo for promo in self.promotions},
            "PO": self.purchase_orders,
        }
        for prefix, records in collections.items():
            maximum = max(
                (
                    int(key.split("-", 1)[1])
                    for key in records
                    if key.startswith(prefix + "-")
                    and key.split("-", 1)[1].isdigit()
                ),
                default=1000 if prefix == "O" else 0,
            )
            self.database.counters.update_one(
                {"_id": prefix}, {"$max": {"value": maximum}}, upsert=True
            )

    def _initialize_returned_quantities(self) -> None:
        totals: dict[tuple[str, str], int] = defaultdict(int)
        for record in self.returns_by_id.values():
            totals[(record.order_id, record.sku)] += record.quantity
        for (order_id, sku), quantity in totals.items():
            self.database.order_lines.update_one(
                {"order_id": order_id, "sku": sku},
                {"$max": {"returned_qty": quantity}},
            )

    def _purchase_order_document(self, po: PurchaseOrder) -> dict[str, Any]:
        return {
            "po_id": po.po_id,
            "product_id": po.product_id,
            "supplier_id": po.supplier_id,
            "ordered_qty": po.ordered_qty,
            "received_qty": po.received_qty,
            "order_date": _mongo_date(po.order_date),
            "status": po.status,
        }

    @staticmethod
    def _latest_id(prefix: str, records: dict[str, Any]) -> str | None:
        matches = []
        for key in records:
            if key.startswith(prefix + "-"):
                tail = key.split("-", 1)[1]
                if tail.isdigit():
                    matches.append((int(tail), key))
        return max(matches, default=(0, None))[1]

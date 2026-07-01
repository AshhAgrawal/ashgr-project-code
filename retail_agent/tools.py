from __future__ import annotations

import json
from typing import Any, Callable

from .store import ASSIGNMENT_TODAY, RetailStore


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "ring_up_sale",
            "description": "Create a sale, apply active promotions, reduce inventory, and return a receipt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Array of item objects. Do not pass this as a JSON string.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_name": {
                                    "type": "string",
                                    "description": (
                                        "Product name or exact SKU, such as Classic Tee "
                                        "or TEE-BLU-M."
                                    ),
                                },
                                "color": {"type": ["string", "null"]},
                                "size": {"type": ["string", "null"]},
                                "quantity": {"type": "integer"},
                            },
                            "required": ["product_name", "quantity"],
                        },
                    },
                    "customer_name": {"type": ["string", "null"]},
                    "payment_method": {"type": "string", "enum": ["cash", "card"]},
                    "date": {"type": "string", "description": "YYYY-MM-DD. Use 2026-06-19 for today."},
                    "order_discount_pct": {
                        "type": "number",
                        "description": (
                            "A whole-order markdown the cashier negotiates at checkout, as a percent. "
                            "NOT for promotions: promotions from create_promotion are applied automatically "
                            "by date and are already reflected in the returned prices. Leave at 0 unless the "
                            "customer is explicitly given an order-level discount."
                        ),
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "return_item",
            "description": "Return an item from an order and refund the price originally paid.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": ["string", "null"]},
                    "sku": {"type": ["string", "null"]},
                    "product_name": {"type": ["string", "null"]},
                    "color": {"type": ["string", "null"]},
                    "size": {"type": ["string", "null"]},
                    "quantity": {"type": "integer"},
                    "condition": {"type": "string", "enum": ["good", "damaged"]},
                    "date": {"type": "string", "description": "YYYY-MM-DD. Use 2026-06-19 for today."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_promotion",
            "description": "Create a percent-off promotion for a product or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "percent_off": {"type": "number"},
                    "scope_type": {"type": "string", "enum": ["product", "category"]},
                    "scope_ref": {"type": "string", "description": "Product name/product_id or category."},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["description", "percent_off", "scope_type", "scope_ref", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_low_stock",
            "description": "Create purchase orders for inventory at or below its reorder point using the best eligible supplier.",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receive_purchase_order",
            "description": "Receive a purchase order quantity into inventory. Variant products require sku, color, or size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "supplier_name": {"type": "string"},
                    "ordered_qty": {"type": "integer"},
                    "received_qty": {"type": "integer"},
                    "date": {"type": "string"},
                    "sku": {"type": ["string", "null"]},
                    "color": {"type": ["string", "null"]},
                    "size": {"type": ["string", "null"]},
                },
                "required": ["product_name", "supplier_name", "ordered_qty", "received_qty"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "revenue_report",
            "description": "Report gross revenue, refunds issued, and net revenue kept for a date range. Last month is May 2026.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_products_by_margin",
            "description": "Report top products by profit margin for a date range. Last month is May 2026.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stockout_report",
            "description": "Find products about to stock out using reorder points and days of cover.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inventory_report",
            "description": "Show current inventory by SKU.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class ToolRunner:
    def __init__(self, store: RetailStore) -> None:
        self.store = store
        self.handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "ring_up_sale": self.store.ring_up_sale,
            "return_item": self.store.return_item,
            "create_promotion": self.store.create_promotion,
            "reorder_low_stock": self.store.reorder_low_stock,
            "receive_purchase_order": self.store.receive_purchase_order,
            "revenue_report": self.store.revenue_report,
            "top_products_by_margin": self.store.top_products_by_margin,
            "stockout_report": self.store.stockout_report,
            "inventory_report": self.store.inventory_report,
        }

    def run(self, name: str, arguments_json: str | dict[str, Any] | None) -> dict[str, Any]:
        if name not in self.handlers:
            return {"error": f"Unknown tool {name}."}
        args = arguments_json
        if args is None:
            args = {}
        if isinstance(args, str):
            args = json.loads(args or "{}")
        args = _default_dates(name, args)
        try:
            return self.handlers[name](**args)
        except Exception as exc:
            return {"error": str(exc)}


def _default_dates(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name in {"ring_up_sale", "return_item", "reorder_low_stock", "receive_purchase_order"}:
        args.setdefault("date", ASSIGNMENT_TODAY)
    if name in {"top_products_by_margin", "revenue_report"}:
        args.setdefault("start_date", "2026-05-01")
        args.setdefault("end_date", "2026-05-31")
    if name == "top_products_by_margin":
        args.setdefault("limit", 5)
    return args

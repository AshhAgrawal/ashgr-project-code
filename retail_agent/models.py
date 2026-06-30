from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ProductVariant:
    sku: str
    product_id: str
    product_name: str
    category: str
    color: str | None
    size: str | None
    retail_price: Decimal


@dataclass
class Customer:
    customer_id: str
    name: str
    email: str
    joined_date: str


@dataclass
class Supplier:
    supplier_id: str
    supplier_name: str


@dataclass
class SupplierCatalogItem:
    supplier_id: str
    product_id: str
    unit_cost: Decimal
    lead_time_days: int


@dataclass
class InventoryItem:
    sku: str
    on_hand_qty: int
    reorder_point: int
    reorder_qty: int


@dataclass
class OrderLine:
    order_id: str
    line_no: int
    sku: str
    quantity: int
    unit_price: Decimal


@dataclass
class Order:
    order_id: str
    order_date: str
    customer_id: str | None
    order_discount_pct: Decimal
    payment_method: str
    lines: list[OrderLine] = field(default_factory=list)


@dataclass
class ReturnRecord:
    return_id: str
    return_date: str
    order_id: str
    sku: str
    quantity: int
    condition: str
    refund_amount: Decimal


@dataclass
class Promotion:
    promo_id: str
    description: str
    type: str
    value: Decimal
    scope_type: str
    scope_ref: str
    start_date: str
    end_date: str


@dataclass
class PurchaseOrder:
    po_id: str
    product_id: str
    supplier_id: str
    ordered_qty: int
    received_qty: int
    order_date: str
    status: str = "open"

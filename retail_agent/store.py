from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

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


ASSIGNMENT_TODAY = "2026-06-19"
LAST_MONTH_START = "2026-05-01"
LAST_MONTH_END = "2026-05-31"
MONEY = Decimal("0.01")


class StoreError(Exception):
    """Raised when a requested store operation is not valid."""


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def norm(value: str | None) -> str:
    return (value or "").strip().lower()


class RetailStore:
    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.products_by_sku: dict[str, ProductVariant] = {}
        self.products_by_id: dict[str, list[ProductVariant]] = defaultdict(list)
        self.customers_by_id: dict[str, Customer] = {}
        self.customers_by_name: dict[str, Customer] = {}
        self.suppliers_by_id: dict[str, Supplier] = {}
        self.suppliers_by_name: dict[str, Supplier] = {}
        self.catalog_by_product_id: dict[str, list[SupplierCatalogItem]] = defaultdict(list)
        self.inventory_by_sku: dict[str, InventoryItem] = {}
        self.orders_by_id: dict[str, Order] = {}
        self.returns_by_id: dict[str, ReturnRecord] = {}
        self.promotions: list[Promotion] = []
        self.purchase_orders: dict[str, PurchaseOrder] = {}
        self.last_order_id: str | None = None
        self.last_return_id: str | None = None
        self.last_purchase_order_id: str | None = None
        self.load()

    def load(self) -> None:
        for row in self._read("products.csv"):
            product = ProductVariant(
                sku=row["sku"],
                product_id=row["product_id"],
                product_name=row["product_name"],
                category=row["category"],
                color=row["color"] or None,
                size=row["size"] or None,
                retail_price=money(row["retail_price"]),
            )
            self.products_by_sku[product.sku] = product
            self.products_by_id[product.product_id].append(product)

        for row in self._read("customers.csv"):
            customer = Customer(**row)
            self.customers_by_id[customer.customer_id] = customer
            self.customers_by_name[norm(customer.name)] = customer

        for row in self._read("suppliers.csv"):
            supplier = Supplier(**row)
            self.suppliers_by_id[supplier.supplier_id] = supplier
            self.suppliers_by_name[norm(supplier.supplier_name)] = supplier

        for row in self._read("supplier_catalog.csv"):
            item = SupplierCatalogItem(
                supplier_id=row["supplier_id"],
                product_id=row["product_id"],
                unit_cost=money(row["unit_cost"]),
                lead_time_days=int(row["lead_time_days"]),
            )
            self.catalog_by_product_id[item.product_id].append(item)

        for row in self._read("inventory.csv"):
            item = InventoryItem(
                sku=row["sku"],
                on_hand_qty=int(row["on_hand_qty"]),
                reorder_point=int(row["reorder_point"]),
                reorder_qty=int(row["reorder_qty"]),
            )
            self.inventory_by_sku[item.sku] = item

        for row in self._read("orders.csv"):
            order = Order(
                order_id=row["order_id"],
                order_date=row["order_date"],
                customer_id=row["customer_id"] or None,
                order_discount_pct=Decimal(row["order_discount_pct"]),
                payment_method=row["payment_method"],
            )
            self.orders_by_id[order.order_id] = order

        for row in self._read("order_lines.csv"):
            line = OrderLine(
                order_id=row["order_id"],
                line_no=int(row["line_no"]),
                sku=row["sku"],
                quantity=int(row["quantity"]),
                unit_price=money(row["unit_price"]),
            )
            self.orders_by_id[line.order_id].lines.append(line)

        for row in self._read("returns.csv"):
            record = ReturnRecord(
                return_id=row["return_id"],
                return_date=row["return_date"],
                order_id=row["order_id"],
                sku=row["sku"],
                quantity=int(row["quantity"]),
                condition=row["condition"],
                refund_amount=money(row["refund_amount"]),
            )
            self.returns_by_id[record.return_id] = record

        for row in self._read("promotions.csv"):
            self.promotions.append(
                Promotion(
                    promo_id=row["promo_id"],
                    description=row["description"],
                    type=row["type"],
                    value=Decimal(row["value"]),
                    scope_type=row["scope_type"],
                    scope_ref=row["scope_ref"],
                    start_date=row["start_date"],
                    end_date=row["end_date"],
                )
            )

    def _read(self, filename: str) -> list[dict[str, str]]:
        with (self.data_dir / filename).open(newline="") as file:
            return list(csv.DictReader(file))

    def find_sku(self, product_name: str, color: str | None = None, size: str | None = None) -> ProductVariant:
        candidates = [
            product
            for product in self.products_by_sku.values()
            if norm(product_name) in norm(product.product_name)
            or norm(product.product_name) in norm(product_name)
            or norm(product_name) in norm(product.sku)
        ]
        if color:
            candidates = [p for p in candidates if norm(p.color) == norm(color)]
        if size:
            candidates = [p for p in candidates if norm(p.size) in {norm(size), _size_alias(size)}]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise StoreError(f"No SKU matched product={product_name!r}, color={color!r}, size={size!r}.")
        options = ", ".join(f"{p.sku} ({p.product_name} {p.color or ''} {p.size or ''})".strip() for p in candidates)
        raise StoreError(f"That product is ambiguous. Please specify one of: {options}.")

    def price_for_sku(self, sku: str, date: str) -> Decimal:
        product = self._product(sku)
        prices = [product.retail_price]
        for promo in self.promotions:
            if not (promo.start_date <= date <= promo.end_date):
                continue
            if promo.type != "percent_off":
                continue
            applies = (
                promo.scope_type == "product"
                and promo.scope_ref == product.product_id
                or promo.scope_type == "category"
                and promo.scope_ref == product.category
            )
            if applies:
                prices.append(money(product.retail_price * (Decimal("1") - promo.value / Decimal("100"))))
        return min(prices)

    def ring_up_sale(
        self,
        items: list[dict[str, Any]],
        customer_name: str | None = None,
        payment_method: str = "cash",
        date: str = ASSIGNMENT_TODAY,
        order_discount_pct: int | float | str = 0,
    ) -> dict[str, Any]:
        if payment_method not in {"cash", "card"}:
            raise StoreError("payment_method must be cash or card.")
        customer = self._find_customer(customer_name) if customer_name else None
        parsed_items = []
        for item in items:
            product = self.find_sku(item["product_name"], item.get("color"), item.get("size"))
            quantity = int(item.get("quantity", 1))
            if quantity <= 0:
                raise StoreError("Sale quantity must be positive.")
            inventory = self.inventory_by_sku[product.sku]
            if inventory.on_hand_qty < quantity:
                raise StoreError(f"Insufficient stock for {product.sku}: requested {quantity}, on hand {inventory.on_hand_qty}.")
            parsed_items.append((product, quantity, self.price_for_sku(product.sku, date)))

        order_id = self._next_id("O", self.orders_by_id)
        discount = Decimal(str(order_discount_pct))
        order = Order(order_id, date, customer.customer_id if customer else None, discount, payment_method)
        subtotal = Decimal("0")
        total = Decimal("0")
        receipt_lines = []
        for index, (product, quantity, unit_price) in enumerate(parsed_items, start=1):
            self.inventory_by_sku[product.sku].on_hand_qty -= quantity
            line = OrderLine(order_id, index, product.sku, quantity, unit_price)
            order.lines.append(line)
            subtotal += unit_price * quantity
            paid_unit = self._paid_unit_price(unit_price, discount)
            total += paid_unit * quantity
            receipt_lines.append(
                {
                    "sku": product.sku,
                    "product_name": product.product_name,
                    "color": product.color,
                    "size": product.size,
                    "quantity": quantity,
                    "retail_price": str(product.retail_price),
                    "unit_price": str(unit_price),
                    "paid_unit_price": str(paid_unit),
                    "line_total": str(money(paid_unit * quantity)),
                    "remaining_on_hand": self.inventory_by_sku[product.sku].on_hand_qty,
                }
            )
        self.orders_by_id[order_id] = order
        self.last_order_id = order_id
        return {
            "order_id": order_id,
            "date": date,
            "customer": customer.name if customer else "walk-in",
            "payment_method": payment_method,
            "subtotal": str(money(subtotal)),
            "order_discount_pct": str(discount),
            "total": str(money(total)),
            "lines": receipt_lines,
        }

    def return_item(
        self,
        order_id: str | None = None,
        sku: str | None = None,
        product_name: str | None = None,
        color: str | None = None,
        size: str | None = None,
        quantity: int = 1,
        condition: str = "good",
        date: str = ASSIGNMENT_TODAY,
    ) -> dict[str, Any]:
        order_id = order_id or self.last_order_id
        if not order_id or order_id not in self.orders_by_id:
            raise StoreError("A valid order_id is required for a return.")
        if condition not in {"good", "damaged"}:
            raise StoreError("condition must be good or damaged.")
        order = self.orders_by_id[order_id]
        if not sku:
            if product_name:
                sku = self.find_sku(product_name, color, size).sku
            elif len(order.lines) == 1:
                sku = order.lines[0].sku
            else:
                options = ", ".join(line.sku for line in order.lines)
                raise StoreError(f"Return needs sku or product_name because order {order_id} has multiple lines: {options}.")
        quantity = int(quantity)
        if quantity <= 0:
            raise StoreError("Return quantity must be positive.")

        line = next((line for line in order.lines if line.sku == sku), None)
        if not line:
            raise StoreError(f"Order {order_id} does not contain SKU {sku}.")
        already_returned = sum(r.quantity for r in self.returns_by_id.values() if r.order_id == order_id and r.sku == sku)
        if already_returned + quantity > line.quantity:
            raise StoreError(f"Cannot return {quantity}; only {line.quantity - already_returned} remain returnable.")

        refund = money(self._paid_unit_price(line.unit_price, order.order_discount_pct) * quantity)
        return_id = self._next_id("R", self.returns_by_id)
        record = ReturnRecord(return_id, date, order_id, sku, quantity, condition, refund)
        self.returns_by_id[return_id] = record
        if condition == "good":
            self.inventory_by_sku[sku].on_hand_qty += quantity
        self.last_return_id = return_id
        return {
            "return_id": return_id,
            "order_id": order_id,
            "sku": sku,
            "quantity": quantity,
            "condition": condition,
            "refund_amount": str(refund),
            "returned_to_stock": condition == "good",
            "on_hand_qty": self.inventory_by_sku[sku].on_hand_qty,
        }

    def create_promotion(
        self,
        description: str,
        percent_off: int | float | str,
        scope_type: str,
        scope_ref: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        if scope_type not in {"product", "category"}:
            raise StoreError("scope_type must be product or category.")
        if scope_type == "product":
            scope_ref = self._resolve_product_id(scope_ref)
        promo = Promotion(
            promo_id=self._next_id("PR", {p.promo_id: p for p in self.promotions}),
            description=description,
            type="percent_off",
            value=Decimal(str(percent_off)),
            scope_type=scope_type,
            scope_ref=scope_ref,
            start_date=start_date,
            end_date=end_date,
        )
        self.promotions.append(promo)
        return asdict(promo) | {"value": str(promo.value)}

    def reorder_low_stock(self, date: str = ASSIGNMENT_TODAY) -> dict[str, Any]:
        created = []
        for sku, inventory in self.inventory_by_sku.items():
            if inventory.on_hand_qty > inventory.reorder_point:
                continue
            product = self._product(sku)
            supplier = self._best_supplier(product.product_id)
            po_id = self._next_id("PO", self.purchase_orders | {c["po_id"]: None for c in created})
            po = PurchaseOrder(po_id, product.product_id, supplier.supplier_id, inventory.reorder_qty, 0, date)
            self.purchase_orders[po_id] = po
            self.last_purchase_order_id = po_id
            created.append(
                {
                    "po_id": po_id,
                    "sku": sku,
                    "product_id": product.product_id,
                    "product_name": product.product_name,
                    "supplier": self.suppliers_by_id[supplier.supplier_id].supplier_name,
                    "unit_cost": str(supplier.unit_cost),
                    "lead_time_days": supplier.lead_time_days,
                    "quantity": inventory.reorder_qty,
                }
            )
        return {"purchase_orders": created, "count": len(created)}

    def receive_purchase_order(
        self,
        product_name: str,
        supplier_name: str,
        ordered_qty: int,
        received_qty: int,
        date: str = ASSIGNMENT_TODAY,
        sku: str | None = None,
        color: str | None = None,
        size: str | None = None,
    ) -> dict[str, Any]:
        supplier = self._find_supplier(supplier_name)
        product_id = self._resolve_product_id(product_name)
        if sku:
            product = self._product(sku)
        elif color or size:
            product = self.find_sku(product_name, color, size)
        else:
            variants = self.products_by_id[product_id]
            if len(variants) > 1:
                options = ", ".join(f"{p.sku} ({p.product_name} {p.color or ''} {p.size or ''})".strip() for p in variants)
                raise StoreError(f"That product has multiple variants. Please specify sku, color, or size: {options}.")
            product = variants[0]
        po_id = self._next_id("PO", self.purchase_orders)
        status = "closed" if int(received_qty) >= int(ordered_qty) else "partial"
        po = PurchaseOrder(po_id, product_id, supplier.supplier_id, int(ordered_qty), int(received_qty), date, status)
        self.purchase_orders[po_id] = po
        self.inventory_by_sku[product.sku].on_hand_qty += int(received_qty)
        self.last_purchase_order_id = po_id
        return {
            "po_id": po_id,
            "product_id": product_id,
            "received_into_sku": product.sku,
            "supplier": supplier.supplier_name,
            "ordered_qty": int(ordered_qty),
            "received_qty": int(received_qty),
            "status": status,
            "on_hand_qty": self.inventory_by_sku[product.sku].on_hand_qty,
        }

    def revenue_report(self, start_date: str = LAST_MONTH_START, end_date: str = LAST_MONTH_END) -> dict[str, Any]:
        gross_revenue = Decimal("0")
        refunds_issued = Decimal("0")
        order_count = 0
        units_sold = 0
        for order in self.orders_by_id.values():
            if not (start_date <= order.order_date <= end_date):
                continue
            order_count += 1
            for line in order.lines:
                paid_unit = self._paid_unit_price(line.unit_price, order.order_discount_pct)
                gross_revenue += paid_unit * line.quantity
                units_sold += line.quantity
        for record in self.returns_by_id.values():
            if start_date <= record.return_date <= end_date:
                refunds_issued += record.refund_amount
        net_revenue = gross_revenue - refunds_issued
        return {
            "start_date": start_date,
            "end_date": end_date,
            "gross_revenue": str(money(gross_revenue)),
            "refunds_issued": str(money(refunds_issued)),
            "net_revenue": str(money(net_revenue)),
            "order_count": order_count,
            "units_sold": units_sold,
        }

    def top_products_by_margin(self, start_date: str = LAST_MONTH_START, end_date: str = LAST_MONTH_END, limit: int = 5) -> dict[str, Any]:
        by_product: dict[str, dict[str, Any]] = defaultdict(lambda: {"revenue": Decimal("0"), "cost": Decimal("0"), "qty": 0})
        good_returns = defaultdict(int)
        refund_by_order_sku = defaultdict(Decimal)
        for record in self.returns_by_id.values():
            if start_date <= record.return_date <= end_date:
                refund_by_order_sku[(record.order_id, record.sku)] += record.refund_amount
                if record.condition == "good":
                    good_returns[(record.order_id, record.sku)] += record.quantity

        for order in self.orders_by_id.values():
            if not (start_date <= order.order_date <= end_date):
                continue
            for line in order.lines:
                product = self._product(line.sku)
                returned_good = good_returns[(order.order_id, line.sku)]
                sold_qty_kept = line.quantity - returned_good
                paid_unit = self._paid_unit_price(line.unit_price, order.order_discount_pct)
                revenue = paid_unit * line.quantity - refund_by_order_sku[(order.order_id, line.sku)]
                by_product[product.product_id]["revenue"] += revenue
                by_product[product.product_id]["cost"] += self.northwind_cost(product.product_id) * sold_qty_kept
                by_product[product.product_id]["qty"] += sold_qty_kept

        rows = []
        for product_id, values in by_product.items():
            product = self.products_by_id[product_id][0]
            margin = values["revenue"] - values["cost"]
            rows.append(
                {
                    "product_id": product_id,
                    "product_name": product.product_name,
                    "quantity_stayed_sold": values["qty"],
                    "revenue": str(money(values["revenue"])),
                    "cost": str(money(values["cost"])),
                    "margin": str(money(margin)),
                }
            )
        rows.sort(key=lambda row: Decimal(row["margin"]), reverse=True)
        return {"start_date": start_date, "end_date": end_date, "products": rows[: int(limit)]}

    def stockout_report(self) -> dict[str, Any]:
        raw_units_sold = defaultdict(int)
        for order in self.orders_by_id.values():
            if not (LAST_MONTH_START <= order.order_date <= LAST_MONTH_END):
                continue
            for line in order.lines:
                raw_units_sold[self._product(line.sku).product_id] += line.quantity

        flagged = []
        for product_id, variants in self.products_by_id.items():
            on_hand = sum(self.inventory_by_sku[p.sku].on_hand_qty for p in variants)
            reorder_point = sum(self.inventory_by_sku[p.sku].reorder_point for p in variants)
            monthly_units = raw_units_sold[product_id]
            days_cover = None
            if monthly_units:
                days_cover = Decimal(on_hand) / (Decimal(monthly_units) / Decimal("30"))
            is_flagged = on_hand <= reorder_point or (days_cover is not None and days_cover < Decimal("14"))
            if is_flagged:
                flagged.append(
                    {
                        "product_id": product_id,
                        "product_name": variants[0].product_name,
                        "on_hand_qty": on_hand,
                        "reorder_point": reorder_point,
                        "monthly_units_sold": monthly_units,
                        "days_cover": None if days_cover is None else str(days_cover.quantize(Decimal("0.1"))),
                        "reason": "below reorder point" if on_hand <= reorder_point else "fewer than 14 days of cover",
                    }
                )
        return {"about_to_stock_out": flagged}

    def inventory_report(self) -> dict[str, Any]:
        rows = []
        for sku, item in sorted(self.inventory_by_sku.items()):
            product = self._product(sku)
            rows.append(
                {
                    "sku": sku,
                    "product_name": product.product_name,
                    "color": product.color,
                    "size": product.size,
                    "on_hand_qty": item.on_hand_qty,
                    "reorder_point": item.reorder_point,
                    "reorder_qty": item.reorder_qty,
                }
            )
        return {"inventory": rows}

    def northwind_cost(self, product_id: str) -> Decimal:
        for item in self.catalog_by_product_id[product_id]:
            if item.supplier_id == "SUP-NW":
                return item.unit_cost
        raise StoreError(f"No Northwind cost found for {product_id}.")

    def _paid_unit_price(self, unit_price: Decimal, order_discount_pct: Decimal) -> Decimal:
        return money(unit_price * (Decimal("1") - order_discount_pct / Decimal("100")))

    def _product(self, sku: str) -> ProductVariant:
        if sku not in self.products_by_sku:
            raise StoreError(f"Unknown SKU {sku}.")
        return self.products_by_sku[sku]

    def _find_customer(self, name: str | None) -> Customer:
        if not name:
            raise StoreError("Customer name is required.")
        exact = self.customers_by_name.get(norm(name))
        if exact:
            return exact
        matches = [c for c in self.customers_by_id.values() if norm(name) in norm(c.name)]
        if len(matches) == 1:
            return matches[0]
        raise StoreError(f"Could not resolve customer {name!r}.")

    def _find_supplier(self, name: str) -> Supplier:
        exact = self.suppliers_by_name.get(norm(name))
        if exact:
            return exact
        matches = [s for s in self.suppliers_by_id.values() if norm(name) in norm(s.supplier_name)]
        if len(matches) == 1:
            return matches[0]
        raise StoreError(f"Could not resolve supplier {name!r}.")

    def _resolve_product_id(self, product_ref: str) -> str:
        if product_ref in self.products_by_id:
            return product_ref
        matches = []
        for product_id, variants in self.products_by_id.items():
            name = variants[0].product_name
            if norm(product_ref) in norm(name) or norm(name) in norm(product_ref):
                matches.append(product_id)
        if len(matches) == 1:
            return matches[0]
        raise StoreError(f"Could not resolve product {product_ref!r}.")

    def _best_supplier(self, product_id: str) -> SupplierCatalogItem:
        eligible = [item for item in self.catalog_by_product_id[product_id] if item.lead_time_days <= 10]
        if not eligible:
            raise StoreError(f"No eligible supplier can deliver {product_id} within 10 days.")
        return min(eligible, key=lambda item: item.unit_cost)

    def _next_id(self, prefix: str, existing: dict[str, Any]) -> str:
        width = 4 if prefix == "O" else 3
        numbers = []
        for key in existing:
            if key.startswith(prefix + "-"):
                tail = key.split("-", 1)[1]
                if tail.isdigit():
                    numbers.append(int(tail))
        next_number = max(numbers or [1000 if prefix == "O" else 0]) + 1
        return f"{prefix}-{next_number:0{width}d}"


def _size_alias(size: str | None) -> str:
    aliases = {"small": "s", "medium": "m", "large": "l"}
    return aliases.get(norm(size), norm(size))

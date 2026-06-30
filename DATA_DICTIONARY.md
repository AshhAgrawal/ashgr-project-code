# Data Dictionary & Business Rules

This is the seed data for the assignment. It is the raw, flat export you'd pull out of a
real store's point-of-sale and spreadsheets. It is **not** a schema. You decide how to model
it — what becomes an entity, what becomes an attribute, what relationships and constraints to
add. We document every column here so you spend your time modeling, not guessing.

Today's date for this assignment is **2026-06-19**. "Last month" means **May 2026**.

All money is in USD. Dates are `YYYY-MM-DD`.

---

## Files

### `products.csv` — the catalog
One row per **sellable unit** (what a cashier actually scans).

| column | meaning |
|---|---|
| `sku` | unique code for the sellable unit |
| `product_id` | the product this unit belongs to. Units that share a `product_id` are the same product in different variants |
| `product_name` | display name |
| `category` | `apparel` or `goods` |
| `color`, `size` | the variant axes. **Blank** for products that don't have variants (tote, mug, socks) |
| `retail_price` | the normal list price per unit, before any promotion |

> Note: a "Classic Tee" is one product (`P-TEE`) sold as six variants (Blue/Black × S/M/L). A
> "Canvas Tote" is one product sold as a single unit. Your model has to handle both without a
> special case for each.

### `customers.csv`
| column | meaning |
|---|---|
| `customer_id` | unique id |
| `name`, `email` | contact |
| `joined_date` | first became a customer |

A sale may have **no** customer (a walk-in). See `orders.customer_id`.

### `suppliers.csv`
| column | meaning |
|---|---|
| `supplier_id` | unique id |
| `supplier_name` | display name |

### `supplier_catalog.csv` — who sells us what, at what price
One row per (supplier, product) the store can buy from.

| column | meaning |
|---|---|
| `supplier_id` | the supplier |
| `product_id` | the product they supply |
| `unit_cost` | what the store pays per unit |
| `lead_time_days` | days from order to delivery |

> A product can appear under more than one supplier (the tote and the mug do). Picking the
> right one is part of the restock workflow — see the rules below.

### `inventory.csv` — current stock snapshot (as of today, 2026-06-19)
| column | meaning |
|---|---|
| `sku` | the sellable unit |
| `on_hand_qty` | units physically in the store right now |
| `reorder_point` | when on-hand falls to or below this, it's time to reorder |
| `reorder_qty` | how many units to order when restocking |

### `orders.csv` — sales headers (one row per sale)
| column | meaning |
|---|---|
| `order_id` | unique id |
| `order_date` | date of sale |
| `customer_id` | the customer, or **blank** for a walk-in |
| `order_discount_pct` | a whole-order discount applied to every line of this order (e.g. `10` = 10% off). `0` for most orders |
| `payment_method` | `cash` or `card` |

### `order_lines.csv` — sales detail (one row per line on a sale)
| column | meaning |
|---|---|
| `order_id` | the order this line belongs to |
| `line_no` | line number within the order |
| `sku` | the sellable unit sold |
| `quantity` | units sold on this line |
| `unit_price` | the per-unit price charged at the register that day, **before** the order-level discount. Any item-level promotion in effect on the order date is already reflected here (that's why early-May tee lines show 20.00 instead of 25.00 — see `promotions.csv`) |

### `returns.csv` — returns that already happened
| column | meaning |
|---|---|
| `return_id` | unique id |
| `return_date` | date of return |
| `order_id` | the original sale being returned against |
| `sku` | the unit returned |
| `quantity` | units returned |
| `condition` | `good` (went back to sellable stock) or `damaged` (did not) |
| `refund_amount` | total dollars refunded for this return |

### `promotions.csv` — promotions
| column | meaning |
|---|---|
| `promo_id` | unique id |
| `description` | human description |
| `type` | `percent_off` (the only type in the seed) |
| `value` | the percentage, e.g. `20` |
| `scope_type` | `product` or `category` |
| `scope_ref` | which product_id or category the promo applies to |
| `start_date`, `end_date` | inclusive active window |

The one seeded promotion (Spring Tee Sale) is already reflected in the historical
`order_lines.unit_price`. It is here so you can see how a promotion relates to prices, and so
you have a model to follow when the agent creates a **new** one.

---

## Business rules (frozen — so every answer is deterministic)

These remove judgment calls. Build your model and agent to follow them exactly.

1. **Cost of goods.** Every unit — on hand or already sold — was received at the **Northwind
   Supply** unit cost for its product (`P-TEE` 10.00, `P-HOOD` 28.00, `P-TOTE` 7.00, `P-MUG`
   5.00, `P-SOCK` 3.00). Use that single per-product cost wherever you need cost.

2. **Order-level discount proration.** An order's `order_discount_pct` applies to every line
   equally. The actual price paid for one unit on a line is
   `unit_price × (1 − order_discount_pct/100)`. Round each unit's discounted price to the cent,
   half-up. (The seed is built so no awkward rounding occurs.)
   - Example: order `O-1006` has a 10% order discount. A Navy-L hoodie on it was paid at
     `60.00 × 0.90 = 54.00`. The tote on it was paid at `18.00 × 0.90 = 16.20`.

3. **Refunds.** A return refunds the **price actually paid** for the returned units (rule 2),
   never the current or list price. `good` returns go back to `on_hand_qty`; `damaged` returns
   do not.

4. **Supplier selection when restocking.** Order from the **lowest `unit_cost`** supplier
   that can deliver within **10 days** (`lead_time_days ≤ 10`). A cheaper supplier that is too
   slow is not eligible.

5. **Promotion windows.** A promotion applies to a sale only if the sale's date is within
   `[start_date, end_date]` inclusive. Promotions never change past sales. If two promotions
   could apply to the same unit, the one giving the **lower price** wins (no stacking).

6. **Revenue.** "Revenue" for a period is the actual dollars paid on orders in that period
   (after order-level discounts). "Revenue kept" (a.k.a. net revenue) subtracts refunds issued
   in that period. **Margin** for a product = revenue from its units − cost of the units that
   stayed sold (a returned-and-restocked unit is neither revenue nor cost).

7. **Sales velocity / stock-out.** A product's velocity is its units sold in the trailing 30
   days; use the May sales as that window. Days of cover = `on_hand_qty ÷ (monthly_units ÷ 30)`,
   summed across a product's variants. Flag a product as "about to stock out" if it is below its
   reorder point **or** has fewer than 14 days of cover.

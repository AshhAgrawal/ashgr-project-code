# Take-Home: Build the Brain for a Retail Store Agent

You're building the system that lets an AI agent run a small retail store. The store sells
clothing and general goods, and has suppliers, customers, inventory, sales, returns, and
promotions.

We give you the store's raw data. We do not give you a schema — you decide what objects exist
and how they relate. Then you build an AI agent that can carry out instructions about the store.

## The data

The `data/` folder holds the store's records as flat CSV exports:

- `products.csv`, `customers.csv`, `suppliers.csv`, `supplier_catalog.csv`
- `inventory.csv` (current snapshot, as of today 2026-06-19)
- `orders.csv` + `order_lines.csv` (May 2026 sales)
- `returns.csv`, `promotions.csv`

`DATA_DICTIONARY.md` defines every column and the store's business rules (costing, discounts,
promotion windows, what "revenue" and "margin" mean). Today's date is 2026-06-19.

## What to submit

0. Please do feel free to use AI in any way you choose.
1. Your domain model (schema in any form, plus a brief description).
2. The tool/action layer your agent exposes, with the names, parameters, and descriptions.
3. A runnable agent we start with a **single command in the terminal**, then talk to
   interactively: we type an instruction, it answers, we keep going. It should remember earlier
   turns within a session (so a follow-up like "now refund that" works). This is a plain
   command-line program — not a web service or server.
4. A short writeup of your approach.

Include a README with the exact command to start it. Stack is your choice: any language, any
database, any LLM with tool calling.

## Prompts

Here are 10 prompts to test against. We will test on these plus **25 additional prompts not
shown here.**

1. "Ring up two Classic Tees, Blue Medium, and one Canvas Tote for a walk-in paying cash, dated today."
2. "Ring up ten Canvas Totes for a walk-in."
3. "Ring up a hoodie in medium for Sarah Chen."
4. "Reorder anything that's below its reorder point, from the best supplier. Date it today."
5. "A purchase order for 50 Canvas Totes from Northwind is open and 40 arrived — receive them, dated today."
6. "Sarah Chen is returning one Navy Large hoodie from order O-1006. It's in good condition."
7. "Return the Canvas Tote from order O-1006 — it came back damaged."
8. "Put all hoodies on 20% off from 2026-06-20 to 2026-06-22, then ring up one Gray Medium hoodie dated 2026-06-21 and tell me the price."
9. "What were my top five products by profit margin last month?"
10. "What's about to stock out?"

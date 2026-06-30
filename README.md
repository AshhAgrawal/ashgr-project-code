# Retail Store Agent

Command-line AI agent for the retail store take-home assignment.

The agent uses a simple Python retail engine for all business rules and state changes. Groq is used only to translate natural-language instructions into tool calls. If `GROQ_API_KEY` is not set, the app still runs with a small rule-based fallback for demo/testing.

See [APPROACH.md](APPROACH.md) and [DESIGN.md](DESIGN.md) for the design writeup, call traces, and architecture diagrams.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file or export your key:

```bash
export GROQ_API_KEY="your_groq_key"
```

Optional model override:

```bash
export GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"
```

## Run

### Command line

```bash
python3 main.py
```

Then type instructions interactively:

```text
Ring up two Classic Tees, Blue Medium, and one Canvas Tote for a walk-in paying cash, dated today.
```

Type `exit` or `quit` to stop.

### Web app

Start the REST API from the project root:

```bash
uvicorn api:app --reload
```

In a second terminal, install and start the React app:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` to use the **ashgr** storefront. The shopping catalog reads live inventory from
`GET /api/products`. Each submitted chat message is posted to
`POST /api/chat`, which passes it directly to the same `RetailAgent.handle()`
method used by the command-line app. The API keeps one agent instance alive,
so in-memory store changes last until the API server restarts.

## Notes

- Assignment "today" is fixed as `2026-06-19`.
- "Last month" is May 2026.
- CSV files are seed data.
- New sales, returns, promotions, and purchase orders are kept in memory for the current CLI session.
- The deterministic Python engine calculates prices, discounts, refunds, margins, supplier choices, and stockout risk.
- For variant products, sale/return/receive tools can use color and size to resolve the exact SKU.

## Domain Model

- `ProductVariant`: one sellable SKU, including product id, name, category, color, size, and retail price.
- `Customer`: customer profile.
- `Supplier`: supplier profile.
- `SupplierCatalogItem`: product-level supplier cost and lead time.
- `InventoryItem`: current stock, reorder point, and reorder quantity by SKU.
- `Order` and `OrderLine`: sales header and line items.
- `ReturnRecord`: return against an original order line.
- `Promotion`: percent-off promotion for a product or category.
- `PurchaseOrder`: in-session purchase order created or received by the agent.

## Tool Layer

The agent exposes these actions:

| Tool | Purpose |
|---|---|
| `ring_up_sale` | Create a sale, apply active promotions, reduce inventory, and return a receipt. |
| `return_item` | Refund returned units based on the original paid price. Good returns go back to stock. |
| `create_promotion` | Add a product/category percent-off promotion. |
| `reorder_low_stock` | Create purchase orders for SKUs at or below reorder point. |
| `receive_purchase_order` | Receive stock into inventory and record purchase order status. |
| `revenue_report` | Report gross revenue, refunds issued, and net revenue kept for a date range. |
| `top_products_by_margin` | Calculate product margin for a date range. |
| `stockout_report` | Find products below reorder point or below 14 days of cover. |
| `inventory_report` | Show current inventory by SKU. |

## Example Prompts

```text
Ring up ten Canvas Totes for a walk-in.
Reorder anything that's below its reorder point, from the best supplier. Date it today.
Sarah Chen is returning one Navy Large hoodie from order O-1006. It's in good condition.
Put all hoodies on 20% off from 2026-06-20 to 2026-06-22, then ring up one Gray Medium hoodie dated 2026-06-21 and tell me the price.
What were my top five products by profit margin last month?
What's about to stock out?
```

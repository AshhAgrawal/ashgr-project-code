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

## Import the CSV seed data into MongoDB Atlas

Create a `.env` file with the Atlas driver connection string and target database:

```env
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=retail_agent
```

Percent-encode reserved characters in the connection-string username or
password. For example, `@` becomes `%40` and `/` becomes `%2F`.

Import or update the nine seed collections, create their indexes, and create the
empty `purchase_orders` collection:

```bash
python3 scripts/import_csv_to_mongodb.py
```

The normal import is idempotent: documents are replaced or inserted using their
business identifiers. To delete the existing seed documents before importing an
exact snapshot, use `--replace`:

```bash
python3 scripts/import_csv_to_mongodb.py --replace
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
uvicorn retail_agent.api:app --reload
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
while MongoDB makes business-state changes visible across API instances.

### Accounts and authentication

The landing page links to signup and login pages. Signup stores a normalized
email and a salted scrypt password hash in MongoDB's `users` collection. Login
creates a random session token, stores only its SHA-256 hash in
`auth_sessions`, and sends the raw token in a seven-day HTTP-only, SameSite
cookie. MongoDB automatically expires session records through a TTL index.

Login and signup also provide a one-click **Continue as guest** option. It
creates or reuses a `users` document with `role: "staff"` and
`account_type: "guest"`. A random HTTP-only browser key identifies returning
guest browsers; MongoDB stores only its hash. Guest records include
`first_seen_at`, `last_seen_at`, and `visit_count`. Raw IP addresses are not
collected.

The product catalog and agent endpoints require an authenticated session. You
can also create an account without the browser using the interactive script:

```bash
python3 scripts/create_user.py
```

The script prompts for the password without echoing it or placing it in shell
history. Passwords must contain at least 10 characters.

New browser signups always receive the `staff` role. Admin users additionally
see protected Orders, Customers, Returns, Purchase Orders, and Suppliers tabs.
Create the first admin from the terminal:

```bash
python3 scripts/create_user.py --role admin
```

Promote or demote an existing account:

```bash
python3 scripts/set_user_role.py manager@example.com admin
python3 scripts/set_user_role.py manager@example.com staff
```

You can also edit the user's `role` field directly in Atlas Data Explorer. Only
`admin` and `staff` are recognized. Role changes take effect on the next API
request because the session resolves the current user document each time.
Admin tabs require authentication to be enabled. When authentication is off,
the public workspace remains available but all `/api/admin/*` endpoints stay
locked because there is no authenticated admin identity.

#### Disable or enable authentication

Authentication is controlled by this document in the MongoDB `features`
collection:

```javascript
{
  _id: "authentication",
  enabled: true
}
```

Change `enabled` to `false` in Atlas Data Explorer to hide login/signup and
allow direct workspace access. Change it back to `true` to restore protected
access. You can also update it from the project root:

```bash
python3 scripts/set_feature.py authentication off
python3 scripts/set_feature.py authentication on
```

The API checks MongoDB on each request, while the frontend checks on page load.
Refresh the browser after changing the flag. Disabling authentication makes the
catalog and agent endpoints publicly accessible to anyone who can reach the app.

The frontend uses same-origin `/api` requests by default. Only set
`VITE_API_URL` when the API is hosted on a different domain:

```bash
VITE_API_URL="https://your-api.example.com"
```

### Deploy to Vercel

The repository is configured as one Vercel project: Vite is served as the
static frontend and `api/index.py` exposes the FastAPI application as a Python
Function. Import the repository in Vercel with the project root set to `.`;
`vercel.json` supplies the install command, build command, output directory,
framework preset, and `/api/*` routing.

Configure these project environment variables before deploying:

```text
GROQ_API_KEY=your_groq_key
LLM_PROVIDER=groq
MONGODB_URI=mongodb+srv://...
MONGODB_DATABASE=retail_agent
```

Vercel automatically receives secure cookies over HTTPS. For another HTTPS
host, set `AUTH_COOKIE_SECURE=true`. Local HTTP development leaves this unset.

Atlas must allow connections from the deployment's outbound network. A broad
`0.0.0.0/0` access-list entry is acceptable only for a constrained demo user;
production should use fixed egress or private networking.

Do not set `VITE_API_URL` for this single-project deployment. The storefront
and API share one domain. After deployment, verify both URLs:

```text
https://your-project.vercel.app/
https://your-project.vercel.app/api/health
```

`GET /api/health` reports `"storage": "mongodb"` when the database environment
variables are active. If both MongoDB variables are absent, the application
falls back to the original CSV-backed in-memory store for offline development.

## Notes

- Assignment "today" is fixed as `2026-06-19`.
- "Last month" is May 2026.
- CSV files are seed data.
- MongoDB persists sales, returns, promotions, purchase orders, and inventory updates.
- MongoDB stores password hashes and expiring authentication sessions; plaintext passwords are never stored.
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
- `PurchaseOrder`: persisted restock or receiving record.

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

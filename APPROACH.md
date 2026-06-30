# Approach

> For a deeper walkthrough of the architecture, call traces, and sequence diagrams, see [DESIGN.md](DESIGN.md).

## Design

I split the project into two parts:

1. A deterministic retail engine in `retail_agent/store.py`.
2. A thin agent layer in `retail_agent/agent.py`.

The agent does not calculate prices or margins itself. It chooses a tool, passes structured arguments, and the Python engine applies the business rules. The LLM is used only to translate natural language into a tool call; every number in the answer comes from the engine. This makes the answers repeatable and easy to test.

## Data Model

The CSVs are loaded into in-memory dataclasses:

- Products are modeled as sellable variants keyed by SKU.
- Inventory is keyed by SKU.
- Suppliers and supplier catalog entries are keyed by supplier/product.
- Orders contain order lines.
- Returns, promotions, and purchase orders are separate records.

This handles products with variants, like tees and hoodies, and products without variants, like totes and mugs.

## Business Rules

Important rules implemented in Python:

- Use `2026-06-19` as "today".
- Use May 2026 as "last month".
- Use `Decimal` for money.
- Apply order-level discounts per unit and round half-up.
- Refund the original paid price, not the current price.
- Good returns increase stock; damaged returns do not.
- Promotions apply only inside inclusive date windows.
- Multiple promotions do not stack; the lowest resulting price wins.
- Restocking chooses the lowest-cost supplier with lead time of 10 days or less.
- Revenue reports separate gross revenue from refunds issued and net revenue kept.
- Margin is revenue minus cost for units that stayed sold.
- Stockout risk is below reorder point or fewer than 14 days of cover.

## Groq Integration

Groq is used through chat completions with tool calling. The default model is:

```text
meta-llama/llama-4-scout-17b-16e-instruct
```

The model receives the available tool schemas and decides which tool to call. The app executes the tool locally and sends the result back to the model for a concise final answer.

There is also a rule-based fallback if `GROQ_API_KEY` is not set. That fallback is intentionally small and exists so the app remains runnable without network/API access. The agent also falls back to it on Groq rate-limit and tool-validation errors so a transient API problem does not crash the session.

## Reliability and Guardrails

Because the LLM is non-deterministic, a few guardrails keep the financial output stable:

- **Promotions vs. order discounts are kept separate.** "20% off all hoodies" is a *promotion* (applied automatically by date inside the engine), not an order-level discount. The `order_discount_pct` tool parameter is documented to forbid using it for a promotion, and the system prompt reinforces this. This prevents the model from discounting a promo price a second time.
- **Sale receipts are rendered deterministically.** After a successful `ring_up_sale`, the agent formats the receipt directly from the tool result (`_format_sale_receipt`) instead of letting the model restate the numbers. The model never re-types a price, so it cannot misreport a total.
- **Combined "promote then sell" requests** create the promotion before the sale so the sale sees the active promotion in the same turn.
- **Idempotency on repeated tool calls.** The agent tracks successful tool-call signatures and stops if the model tries to repeat the same successful mutation, and caps the tool loop at five iterations.

## Sample Session

A real interactive session against the assignment prompts (Groq provider). Note the promotion
applied once at the correct $48, the variant clarification flow, and the follow-up
`"Now refund that"` resolving to the order created in the previous turn.

```text
> Ring up two Classic Tees, Blue Medium, and one Canvas Tote for a walk-in paying cash, dated today.
Order #O-1016
2026-06-19
walk-in
cash

Classic Tee Blue M x2  $50.00
Canvas Tote x1  $18.00

Subtotal: $68.00
Order discount: 0%
Total: $68.00

> Ring up ten Canvas Totes for a walk-in.
Insufficient stock for Canvas Tote: requested 10, on hand 3.

> Ring up a hoodie in medium for Sarah Chen.
The hoodie product is ambiguous. Please specify one of:
- Pullover Hoodie Gray M
- Pullover Hoodie Navy M

> Pullover Hoodie Gray M
Order #O-1017
2026-06-19
Sarah Chen
cash

Pullover Hoodie Gray M x1  $60.00

Subtotal: $60.00
Order discount: 0%
Total: $60.00

> Reorder anything that's below its reorder point, from the best supplier. Date it today.
Purchase Order #PO-001
2026-06-19

Canvas Tote x50 from Northwind Supply @ $7.00/unit

Total: $350.00

> A purchase order for 50 Canvas Totes from Northwind is open and 40 arrived — receive them, dated today.
Received 40 Canvas Totes from Northwind Supply
On hand: 43
Remaining on PO: 10

> Sarah Chen is returning one Navy Large hoodie from order O-1006. It's in good condition.
Return #R-2002
Order #O-1006

Returned 1 Navy Large Pullover Hoodie in good condition
Refund: $54.00

> Return the Canvas Tote from order O-1006 — it came back damaged.
Return #R-2003
Order #O-1006

Returned 1 Canvas Tote damaged
Refund: $16.20

> Put all hoodies on 20% off from 2026-06-20 to 2026-06-22, then ring up one Gray Medium hoodie dated 2026-06-21 and tell me the price.
Order #O-1018
2026-06-21
walk-in
cash

Pullover Hoodie Gray M x1  $48.00 (list $60.00, charged $48.00)

Subtotal: $48.00
Order discount: 0%
Total: $48.00

> What were my top five products by profit margin last month?
Top 5 products by profit margin for May 2026:

1. Classic Tee: $420.00
2. Pullover Hoodie: $282.00
3. Wool Socks: $120.00
4. Canvas Tote: $108.20
5. Ceramic Mug: $70.00

> What's about to stock out?
No products are about to stock out.

> What was my revenue last month?
Gross Revenue for May 2026: $1786.20
Refunds Issued: $54.00
Net Revenue: $1732.20

> Ring up one Canvas Tote for a walk-in.
Order #O-1019
2026-06-19
walk-in
cash

Canvas Tote x1  $18.00

Subtotal: $18.00
Order discount: 0%
Total: $18.00

> Now refund that.
Return #R-2004
Order #O-1019

Returned 1 Canvas Tote in good condition
Refund: $18.00
```

## Files

```text
main.py                 CLI entrypoint
retail_agent/models.py  Dataclasses
retail_agent/store.py   Business logic and state
retail_agent/tools.py   Tool schemas and dispatcher
retail_agent/agent.py   Groq agent and fallback parser
requirements.txt        Python dependencies
```

## Tradeoffs

The project keeps state in memory instead of writing back to CSV. That is enough for an interactive assignment session and avoids adding database complexity.

The purchase-order workflow is minimal. It records received quantities and updates inventory, but it does not persist open purchase orders across runs. For products with variants, receiving stock requires an exact SKU or variant details instead of guessing a default SKU.

Future improvements outside this assignment scope would include customer creation for new named customers, fixed-dollar promotions, and persisted purchase-order records.

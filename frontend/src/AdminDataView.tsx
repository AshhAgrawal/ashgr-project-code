import { ReactNode, useEffect, useState } from "react";

export type AdminResource =
  | "orders"
  | "customers"
  | "returns"
  | "purchase-orders"
  | "suppliers";

type DataRow = Record<string, unknown>;

type Column = {
  key: string;
  label: string;
};

const resourceConfig: Record<
  AdminResource,
  { title: string; description: string; columns: Column[]; id: string }
> = {
  orders: {
    title: "Orders",
    description: "Sales headers and every line item recorded at checkout.",
    id: "order_id",
    columns: [
      { key: "order_id", label: "Order" },
      { key: "order_date", label: "Date" },
      { key: "customer_id", label: "Customer" },
      { key: "payment_method", label: "Payment" },
      { key: "order_discount_pct", label: "Discount" },
      { key: "lines", label: "Line items" },
    ],
  },
  customers: {
    title: "Customers",
    description: "Customer identities and their original join dates.",
    id: "customer_id",
    columns: [
      { key: "customer_id", label: "Customer ID" },
      { key: "name", label: "Name" },
      { key: "email", label: "Email" },
      { key: "joined_date", label: "Joined" },
    ],
  },
  returns: {
    title: "Returns",
    description: "Refunds issued against original orders and inventory outcomes.",
    id: "return_id",
    columns: [
      { key: "return_id", label: "Return" },
      { key: "return_date", label: "Date" },
      { key: "order_id", label: "Order" },
      { key: "sku", label: "SKU" },
      { key: "quantity", label: "Qty" },
      { key: "condition", label: "Condition" },
      { key: "refund_amount", label: "Refund" },
    ],
  },
  "purchase-orders": {
    title: "Purchase orders",
    description: "Restock orders, supplier assignments, and receiving status.",
    id: "po_id",
    columns: [
      { key: "po_id", label: "PO" },
      { key: "order_date", label: "Date" },
      { key: "product_id", label: "Product" },
      { key: "supplier_id", label: "Supplier" },
      { key: "ordered_qty", label: "Ordered" },
      { key: "received_qty", label: "Received" },
      { key: "status", label: "Status" },
    ],
  },
  suppliers: {
    title: "Suppliers",
    description: "Supplier records with product cost and delivery terms.",
    id: "supplier_id",
    columns: [
      { key: "supplier_id", label: "Supplier ID" },
      { key: "supplier_name", label: "Supplier" },
      { key: "catalog", label: "Catalog terms" },
    ],
  },
};

function formattedDate(value: string): string {
  return /^\d{4}-\d{2}-\d{2}T/.test(value) ? value.slice(0, 10) : value;
}

function formatValue(key: string, value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    return (
      <div className="admin-nested-list">
        {value.map((item, index) => {
          const record = item as DataRow;
          const text = record.sku
            ? `${record.sku} ×${record.quantity} · $${record.unit_price}`
            : `${record.product_id} · $${record.unit_cost} · ${record.lead_time_days} days`;
          return <span key={`${text}-${index}`}>{text}</span>;
        })}
      </div>
    );
  }
  const text = String(value);
  if (key.includes("date")) return formattedDate(text);
  if (key === "refund_amount") return `$${text}`;
  if (key === "order_discount_pct") return `${text}%`;
  return text;
}

type AdminDataViewProps = {
  resource: AdminResource;
  apiUrl: string;
};

export default function AdminDataView({
  resource,
  apiUrl,
}: AdminDataViewProps) {
  const [rows, setRows] = useState<DataRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const config = resourceConfig[resource];

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiUrl}/api/admin/${resource}`, {
          credentials: "include",
          signal: controller.signal,
        });
        const body = (await response.json()) as DataRow[] | { detail?: string };
        if (!response.ok || !Array.isArray(body)) {
          throw new Error(
            !Array.isArray(body) && body.detail
              ? body.detail
              : "Could not load internal data.",
          );
        }
        setRows(body);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(
          caught instanceof Error ? caught.message : "Could not load internal data.",
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [apiUrl, resource]);

  return (
    <section className="admin-data-view" aria-labelledby="admin-data-title">
      <header>
        <div>
          <span>Internal data · Admin only</span>
          <h2 id="admin-data-title">{config.title}</h2>
          <p>{config.description}</p>
        </div>
        <strong>{loading ? "…" : rows.length}</strong>
      </header>

      {error && <div className="admin-data-error">{error}</div>}
      {!error && loading && <div className="admin-data-state">Loading records…</div>}
      {!error && !loading && rows.length === 0 && (
        <div className="admin-data-state">No records yet.</div>
      )}
      {!error && !loading && rows.length > 0 && (
        <div className="admin-table-shell">
          <table>
            <thead>
              <tr>
                {config.columns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={String(row[config.id])}>
                  {config.columns.map((column) => (
                    <td key={column.key} data-label={column.label}>
                      {formatValue(column.key, row[column.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

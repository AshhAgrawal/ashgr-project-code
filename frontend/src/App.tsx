import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type Product = {
  sku: string;
  product_id: string;
  product_name: string;
  category: string;
  color: string | null;
  size: string | null;
  retail_price: number;
  quantity: number;
};

type Message = {
  id: number;
  role: "user" | "assistant";
  text: string;
};

type SortOrder = "default" | "price-low" | "price-high";
type ViewMode = "grid" | "list";
type TableSortKey =
  | "product_name"
  | "category"
  | "sku"
  | "color"
  | "size"
  | "retail_price"
  | "quantity";
type SortDirection = "ascending" | "descending";

const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

const starterMessage: Message = {
  id: 0,
  role: "assistant",
  text: "Hi — I can help with sales, returns, promotions, reorders, and inventory reports. What would you like to do?",
};

const recommendedPrompts = [
  "Ring up two Classic Tees, Blue Medium, and one Canvas Tote for a walk-in paying cash, dated today.",
  "Ring up ten Canvas Totes for a walk-in.",
  "Ring up a hoodie in medium for Sarah Chen.",
  "Reorder anything that's below its reorder point, from the best supplier. Date it today.",
  "A purchase order for 50 Canvas Totes from Northwind is open and 40 arrived — receive them, dated today.",
  "Sarah Chen is returning one Navy Large hoodie from order O-1006. It's in good condition.",
  "Return the Canvas Tote from order O-1006 — it came back damaged.",
  "Put all hoodies on 20% off from 2026-06-20 to 2026-06-22, then ring up one Gray Medium hoodie dated 2026-06-21 and tell me the price.",
  "What were my top five products by profit margin last month?",
  "What's about to stock out?",
];

function pickRecommendedPrompts(excluded: string[] = []): string[] {
  const shuffled = recommendedPrompts.filter(
    (prompt) => !excluded.includes(prompt),
  );
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[randomIndex]] = [
      shuffled[randomIndex],
      shuffled[index],
    ];
  }
  return shuffled.slice(0, Math.random() < 0.5 ? 3 : 4);
}

const productImages: Record<string, string> = {
  "P-TEE-Blue": "/assets/ashgr-tee-blue.webp",
  "P-TEE-Black": "/assets/ashgr-tee-black.webp",
  "P-HOOD-Gray": "/assets/ashgr-hoodie-gray.webp",
  "P-HOOD-Navy": "/assets/ashgr-hoodie-navy.webp",
  "P-TOTE": "/assets/canvas-tote.webp",
  "P-MUG": "/assets/ceramic-mug.webp",
  "P-SOCK": "/assets/wool-socks.webp",
};

const titleCase = (value: string) =>
  value.charAt(0).toUpperCase() + value.slice(1);
const productImage = (product: Product) =>
  productImages[`${product.product_id}-${product.color ?? ""}`] ??
  productImages[product.product_id];

export default function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [size, setSize] = useState("all");
  const [color, setColor] = useState("all");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("default");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [tableSort, setTableSort] = useState<{
    key: TableSortKey;
    direction: SortDirection;
  }>({ key: "product_name", direction: "ascending" });
  const [messages, setMessages] = useState<Message[]>([starterMessage]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [suggestions, setSuggestions] = useState(pickRecommendedPrompts);
  const messageId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const loadProducts = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/products`);
      if (!response.ok) throw new Error("Could not load inventory.");
      setProducts((await response.json()) as Product[]);
      setCatalogError(null);
    } catch (caught) {
      setCatalogError(
        caught instanceof Error ? caught.message : "Could not load inventory.",
      );
    }
  }, []);

  useEffect(() => {
    void loadProducts();
  }, [loadProducts]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);
  useEffect(() => {
    if (!isChatOpen) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setIsChatOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [isChatOpen]);

  const sizes = useMemo(
    () => [
      ...new Set(
        products.flatMap((product) => (product.size ? [product.size] : [])),
      ),
    ],
    [products],
  );
  const colors = useMemo(
    () => [
      ...new Set(
        products.flatMap((product) => (product.color ? [product.color] : [])),
      ),
    ],
    [products],
  );

  const groupedProducts = useMemo(() => {
    const query = search.trim().toLowerCase();
    const minimum = minPrice === "" ? -Infinity : Number(minPrice);
    const maximum = maxPrice === "" ? Infinity : Number(maxPrice);
    const filtered = products.filter(
      (product) =>
        (!query ||
          `${product.product_name} ${product.category} ${product.color ?? ""} ${product.size ?? ""}`
            .toLowerCase()
            .includes(query)) &&
        (size === "all" || product.size === size) &&
        (color === "all" || product.color === color) &&
        product.retail_price >= minimum &&
        product.retail_price <= maximum,
    );

    if (sortOrder === "price-low")
      filtered.sort((a, b) => a.retail_price - b.retail_price);
    if (sortOrder === "price-high")
      filtered.sort((a, b) => b.retail_price - a.retail_price);

    return filtered.reduce<Record<string, Product[]>>((groups, product) => {
      (groups[product.category] ??= []).push(product);
      return groups;
    }, {});
  }, [products, search, size, color, minPrice, maxPrice, sortOrder]);

  const visibleCount = Object.values(groupedProducts).reduce(
    (count, items) => count + items.length,
    0,
  );

  const listProducts = useMemo(() => {
    const items = Object.values(groupedProducts).flat();
    return items.sort((first, second) => {
      const firstValue = first[tableSort.key] ?? "";
      const secondValue = second[tableSort.key] ?? "";
      const comparison =
        typeof firstValue === "number" && typeof secondValue === "number"
          ? firstValue - secondValue
          : String(firstValue).localeCompare(String(secondValue), undefined, {
              numeric: true,
              sensitivity: "base",
            });
      return tableSort.direction === "ascending" ? comparison : -comparison;
    });
  }, [groupedProducts, tableSort]);

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const message = input.trim();
    if (!message || isSending) return;

    setMessages((current) => [
      ...current,
      { id: messageId.current++, role: "user", text: message },
    ]);
    setInput("");
    setSuggestions((current) => pickRecommendedPrompts(current));
    setChatError(null);
    setIsSending(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const body = (await response.json()) as {
        reply?: string;
        detail?: string;
      };
      if (!response.ok) throw new Error(body.detail || "The request failed.");
      setMessages((current) => [
        ...current,
        { id: messageId.current++, role: "assistant", text: body.reply ?? "" },
      ]);
      await loadProducts();
    } catch (caught) {
      setChatError(
        caught instanceof Error ? caught.message : "Could not reach the agent.",
      );
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  function selectSuggestion(prompt: string) {
    setInput(prompt);
    setChatError(null);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function changeTableSort(key: TableSortKey) {
    setSortOrder("default");
    setTableSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "ascending"
          ? "descending"
          : "ascending",
    }));
  }

  function changeSortOrder(value: SortOrder) {
    setSortOrder(value);
    if (value === "price-low") {
      setTableSort({ key: "retail_price", direction: "ascending" });
    } else if (value === "price-high") {
      setTableSort({ key: "retail_price", direction: "descending" });
    }
  }

  function tableHeader(key: TableSortKey, label: string) {
    const isActive = tableSort.key === key;
    return (
      <th aria-sort={isActive ? tableSort.direction : "none"}>
        <button type="button" onClick={() => changeTableSort(key)}>
          {label}
          <span aria-hidden="true">
            {isActive
              ? tableSort.direction === "ascending"
                ? "↑"
                : "↓"
              : "↕"}
          </span>
        </button>
      </th>
    );
  }

  function clearFilters() {
    setSearch("");
    setSize("all");
    setColor("all");
    setMinPrice("");
    setMaxPrice("");
    setSortOrder("default");
  }

  return (
    <main className="storefront">
      <section className="catalog-panel">
        <header className="store-header">
          <div className="brand">
            <img
              className="brand-wordmark"
              src="/assets/ashgr-wordmark.webp"
              alt="ashgr"
            />
            <p>
              Be the trendsetter. <br />
              Premium wear for the modern individual.
            </p>
          </div>
          <div className="header-actions">
            <span className="shop-pill">Fresh finds</span>
            <div className="inventory-count">
              <strong>{visibleCount}</strong> variants in view
            </div>
          </div>
        </header>

        <section className="filter-bar" aria-label="Product filters">
          <label className="search-field">
            <span className="sr-only">Search products</span>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m21 20-5.2-5.2a7.5 7.5 0 1 0-1 1L20 21l1-1ZM5.5 10a4.5 4.5 0 1 1 9 0 4.5 4.5 0 0 1-9 0Z" />
            </svg>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search the store"
            />
          </label>
          <div className="filter-controls">
            <label>
              <span>Size</span>
              <select
                value={size}
                onChange={(event) => setSize(event.target.value)}
              >
                <option value="all">All sizes</option>
                {sizes.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Color</span>
              <select
                value={color}
                onChange={(event) => setColor(event.target.value)}
              >
                <option value="all">All colors</option>
                {colors.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <fieldset className="price-filter">
              <legend>Price range</legend>
              <div>
                <span>$</span>
                <input
                  aria-label="Minimum price"
                  type="number"
                  min="0"
                  placeholder="Min"
                  value={minPrice}
                  onChange={(event) => setMinPrice(event.target.value)}
                />
                <i>—</i>
                <span>$</span>
                <input
                  aria-label="Maximum price"
                  type="number"
                  min="0"
                  placeholder="Max"
                  value={maxPrice}
                  onChange={(event) => setMaxPrice(event.target.value)}
                />
              </div>
            </fieldset>
            <label>
              <span>Sort</span>
              <select
                value={sortOrder}
                onChange={(event) =>
                  changeSortOrder(event.target.value as SortOrder)
                }
              >
                <option value="default">Featured</option>
                <option value="price-low">Price: Low to high</option>
                <option value="price-high">Price: High to low</option>
              </select>
            </label>
            <div className="view-control">
              <span>View</span>
              <div className="view-toggle" role="group" aria-label="Catalog view">
                <button
                  type="button"
                  className={viewMode === "grid" ? "active" : ""}
                  onClick={() => setViewMode("grid")}
                  aria-label="Grid view"
                  aria-pressed={viewMode === "grid"}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 4h6v6H4V4Zm10 0h6v6h-6V4ZM4 14h6v6H4v-6Zm10 0h6v6h-6v-6Z" />
                  </svg>
                </button>
                <button
                  type="button"
                  className={viewMode === "list" ? "active" : ""}
                  onClick={() => setViewMode("list")}
                  aria-label="List view"
                  aria-pressed={viewMode === "list"}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 5h3v3H4V5Zm5 0h11v3H9V5ZM4 10.5h3v3H4v-3Zm5 0h11v3H9v-3ZM4 16h3v3H4v-3Zm5 0h11v3H9v-3Z" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </section>

        <div className="catalog-scroll">
          <section className="hero-banner">
            <div className="hero-copy">
              <span className="eyebrow">ashgr / drop 01</span>
              <h2>
                Less noise.
                <br />
                <em>More presence.</em>
              </h2>
              <p>
                Premium essentials shaped by minimalist design, exceptional
                quality, and lasting comfort—for a generation that sets trends
                instead of following them.
              </p>
              <div className="hero-badges">
                <span>✦ Premium quality, made to last</span>
                <span>✦ Minimal design, maximum impact</span>
              </div>
            </div>
            <div className="hero-art" aria-hidden="true">
              <div className="hero-orb orb-one" />
              <div className="hero-orb orb-two" />
              <div className="drop-stamp">
                <b>01</b>
                <span>
                  limited
                  <br />
                  drop
                </span>
              </div>
              <span>
                WEAR
                <br />
                IT YOUR WAY
              </span>
            </div>
          </section>
          {catalogError && (
            <div className="catalog-alert">
              {catalogError} Make sure the API is running.
            </div>
          )}
          {!catalogError && products.length === 0 && (
            <div className="catalog-state">Loading inventory…</div>
          )}
          {viewMode === "grid" ? (
            Object.entries(groupedProducts).map(([category, items]) => (
              <section className="category-section" key={category}>
                <div className="section-heading">
                  <div>
                    <span>
                      {String(
                        Object.keys(groupedProducts).indexOf(category) + 1,
                      ).padStart(2, "0")}
                    </span>
                    <h2>{titleCase(category)}</h2>
                  </div>
                  <p>
                    {items.length}{" "}
                    {items.length === 1 ? "variant" : "variants"}
                  </p>
                </div>
                <div className="product-grid">
                  {items.map((product) => (
                    <article className="product-card" key={product.sku}>
                      <div
                        className={`product-art art-${product.product_id.toLowerCase().replace("p-", "")}`}
                      >
                        <img
                          src={productImage(product)}
                          alt={`${product.color ?? ""} ${product.product_name}`.trim()}
                        />
                        <small>
                          {product.color ?? titleCase(product.category)}
                        </small>
                        <button
                          type="button"
                          className="quick-view"
                          aria-label={`View ${product.product_name}`}
                        >
                          ↗
                        </button>
                      </div>
                      <div className="product-info">
                        <div>
                          <p className="product-kicker">{product.sku}</p>
                          <h3>{product.product_name}</h3>
                        </div>
                        <strong className="price">
                          ${product.retail_price.toFixed(2)}
                        </strong>
                      </div>
                      <div className="product-meta">
                        <div className="variant-tags">
                          {product.color && (
                            <span>
                              <i
                                className={`swatch swatch-${product.color.toLowerCase()}`}
                              />
                              {product.color}
                            </span>
                          )}
                          {product.size && <span>Size {product.size}</span>}
                        </div>
                        <span
                          className={`stock ${product.quantity <= 5 ? "low" : ""}`}
                        >
                          <i />
                          {product.quantity} in stock
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))
          ) : visibleCount > 0 ? (
            <section className="inventory-list" aria-label="Product inventory">
              <div className="list-heading">
                <div>
                  <span>Inventory</span>
                  <h2>All product variants</h2>
                </div>
                <p>{visibleCount} results</p>
              </div>
              <div className="table-shell">
                <table>
                  <thead>
                    <tr>
                      {tableHeader("product_name", "Product")}
                      {tableHeader("category", "Category")}
                      {tableHeader("sku", "SKU")}
                      {tableHeader("color", "Color")}
                      {tableHeader("size", "Size")}
                      {tableHeader("retail_price", "Price")}
                      {tableHeader("quantity", "Stock")}
                    </tr>
                  </thead>
                  <tbody>
                    {listProducts.map((product) => (
                      <tr key={product.sku}>
                        <td>
                          <div className="table-product">
                            <img
                              src={productImage(product)}
                              alt=""
                              aria-hidden="true"
                            />
                            <strong>{product.product_name}</strong>
                          </div>
                        </td>
                        <td>{titleCase(product.category)}</td>
                        <td className="sku-cell">{product.sku}</td>
                        <td>
                          {product.color ? (
                            <span className="table-color">
                              <i
                                className={`swatch swatch-${product.color.toLowerCase()}`}
                              />
                              {product.color}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>{product.size ?? "—"}</td>
                        <td className="table-price">
                          ${product.retail_price.toFixed(2)}
                        </td>
                        <td>
                          <span
                            className={`table-stock ${product.quantity <= 5 ? "low" : ""}`}
                          >
                            <i />
                            {product.quantity}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
          {!catalogError && products.length > 0 && visibleCount === 0 && (
            <div className="empty-state">
              <h2>No products found</h2>
              <p>Try adjusting your search or filters.</p>
              <button onClick={clearFilters}>Clear all filters</button>
            </div>
          )}
        </div>
      </section>

      {isChatOpen && (
        <button
          className="chat-backdrop"
          aria-label="Close chat"
          onClick={() => setIsChatOpen(false)}
        />
      )}
      <aside
        className={`chat-panel ${isChatOpen ? "open" : ""}`}
        aria-label="ashgr Assistant chat"
      >
        <header className="chat-header">
          <div>
            <div className="agent-avatar">
              <b>a</b>
              <span />
            </div>
            <div>
              <h2>ashgr Assistant</h2>
              <p>Online · Here to help</p>
            </div>
          </div>
          <button
            className="close-chat"
            onClick={() => setIsChatOpen(false)}
            aria-label="Close chat"
          >
            ×
          </button>
        </header>
        <div className="messages" aria-live="polite">
          <div className="date-label">Today</div>
          {messages.map((message) => (
            <article key={message.id} className={`message-row ${message.role}`}>
              {message.role === "assistant" && (
                <div className="message-avatar">a</div>
              )}
              <div className="message-bubble">{message.text}</div>
            </article>
          ))}
          <section
            className="prompt-suggestions"
            aria-label="Recommended prompts"
          >
            <div className="suggestions-heading">
              <span>Try asking</span>
              <small>Click to edit</small>
            </div>
            <div className="suggestion-list">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => selectSuggestion(suggestion)}
                >
                  <span>{suggestion}</span>
                  <i aria-hidden="true">↗</i>
                </button>
              ))}
            </div>
          </section>
          {isSending && (
            <article className="message-row assistant">
              <div className="message-avatar">a</div>
              <div
                className="message-bubble typing"
                aria-label="ashgr Assistant is responding"
              >
                <span />
                <span />
                <span />
              </div>
            </article>
          )}
          <div ref={endRef} />
        </div>
        <form className="composer" onSubmit={sendMessage}>
          {chatError && (
            <div className="error-message" role="alert">
              {chatError}
            </div>
          )}
          <div className="input-wrap">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about inventory, sales…"
              aria-label="Message ashgr Assistant"
              rows={1}
              disabled={isSending}
            />
            <button
              type="submit"
              disabled={!input.trim() || isSending}
              aria-label="Send message"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m4 4 17 8-17 8 3-8-3-8Zm3.5 2.8L9.45 11H17L7.5 6.8Zm1.95 6.2L7.5 17.2 17 13H9.45Z" />
              </svg>
            </button>
          </div>
          <p>Enter to send · Shift + Enter for a new line</p>
        </form>
      </aside>

      <button
        className="mobile-chat-button"
        onClick={() => setIsChatOpen(true)}
        aria-label="Open ashgr Assistant chat"
      >
        <span className="mobile-chat-icon">a</span>
        <span>Ask ashgr</span>
        {messages.length > 1 && <i />}
      </button>
    </main>
  );
}

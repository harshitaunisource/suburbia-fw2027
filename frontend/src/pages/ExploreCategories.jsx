import { useEffect, useState } from "react";
import CartBar from "../components/CartBar";
import { cartItemFromGenericProduct, useCart } from "../lib/cart";

function imageSrc(p) {
  if (p.local_image_path) {
    const normalized = p.local_image_path.replace(/\\/g, "/");
    const idx = normalized.indexOf("storage/");
    return "/" + (idx >= 0 ? normalized.slice(idx) : normalized);
  }
  return p.image_url || null;
}

export default function ExploreCategories() {
  const [tree, setTree] = useState({});
  const [itemType, setItemType] = useState("");
  const [category, setCategory] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [sources, setSources] = useState([]);
  const [products, setProducts] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [running, setRunning] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [elapsedMs, setElapsedMs] = useState(null);
  const cart = useCart();

  async function generatePPT() {
    const res = await fetch("/api/catalogue/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "PPT generation failed");
    cart.refresh();
    return data;
  }

  useEffect(() => {
    fetch("/api/generic/hierarchy")
      .then((r) => r.json())
      .then(setTree);
  }, []);

  const itemTypes = Object.keys(tree).sort();
  const categories = itemType ? Object.keys(tree[itemType] || {}).sort() : [];
  const subCategories = itemType && category ? tree[itemType][category] || [] : [];

  function refreshResults(id) {
    if (!id) return;
    fetch(`/api/generic/sources?sub_category_id=${id}`).then((r) => r.json()).then(setSources);
    fetch(`/api/generic/products?sub_category_id=${id}`).then((r) => r.json()).then(setProducts);
    fetch(`/api/generic/analytics?sub_category_id=${id}`).then((r) => r.json()).then(setAnalytics);
  }

  useEffect(() => {
    if (subCategoryId) refreshResults(subCategoryId);
  }, [subCategoryId]);

  async function runSource(sourceId) {
    setRunning(sourceId);
    setLastResult(null);
    setElapsedMs(null);
    const startedAt = Date.now();
    try {
      const res = await fetch("/api/generic/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_config_id: sourceId }),
      });
      setLastResult(await res.json());
    } finally {
      setElapsedMs(Date.now() - startedAt);
      setRunning(null);
      refreshResults(subCategoryId);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Explore Categories</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Pick any item type, category, and sub-category to see scraped products across brands. This is a
        standalone lookup tool — no comparison baseline, just what's been found.
      </p>

      <CartBar count={cart.count} onGenerate={generatePPT} />

      <div className="flex gap-3 mb-6">
        <select
          value={itemType}
          onChange={(e) => {
            setItemType(e.target.value);
            setCategory("");
            setSubCategoryId("");
          }}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          <option value="">Select Item Type</option>
          {itemTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setSubCategoryId("");
          }}
          disabled={!itemType}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
        >
          <option value="">Select Category</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <select
          value={subCategoryId}
          onChange={(e) => setSubCategoryId(e.target.value)}
          disabled={!category}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
        >
          <option value="">Select Item</option>
          {subCategories.map((s) => (
            <option key={s.id} value={s.id}>
              {s.sub_category}
            </option>
          ))}
        </select>
      </div>

      {subCategoryId && (
        <>
          {lastResult && (
            <div
              className={`mb-4 p-3 rounded-md text-sm ${
                lastResult.status === "success" ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
              }`}
            >
              {lastResult.status === "success"
                ? `✓ ${lastResult.products_found} products found${elapsedMs != null ? ` in ${(elapsedMs / 1000).toFixed(1)}s` : ""}.`
                : `✗ Failed${elapsedMs != null ? ` after ${(elapsedMs / 1000).toFixed(1)}s` : ""}: ${lastResult.error_message}`}
            </div>
          )}
          {running && (
            <div className="mb-4 p-3 rounded-md text-sm bg-neutral-100 text-neutral-600">
              Loading the page and scanning it for products — this usually takes 10–60 seconds
              depending on the site.
            </div>
          )}

          <div className="bg-white border border-neutral-200 rounded-lg p-4 mb-6">
            <div className="text-sm font-medium mb-3">Configured Sources</div>
            {sources.length === 0 ? (
              <div className="text-sm text-neutral-500">
                No brand sources configured yet for this item — these need to be added (with a real,
                working category URL) before anything can be scraped here.
              </div>
            ) : (
              <div className="space-y-2">
                {sources.map((s) => (
                  <div key={s.id} className="flex items-center justify-between border-t border-neutral-100 pt-2">
                    <div>
                      <div className="text-sm font-medium">{s.brand}</div>
                      <div className="text-xs text-neutral-400 truncate max-w-md">{s.category_url}</div>
                    </div>
                    <button
                      onClick={() => runSource(s.id)}
                      disabled={running === s.id}
                      className="px-3 py-1.5 bg-neutral-900 text-white rounded-md text-xs disabled:opacity-50"
                    >
                      {running === s.id ? "Running…" : "Run Scraper"}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {analytics && analytics.total_products > 0 && (
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="bg-white border border-neutral-200 rounded-lg p-5">
                <div className="text-sm font-medium mb-3">Price Distribution (MRP, by currency)</div>
                {Object.keys(analytics.price_distribution).length === 0 ? (
                  <div className="text-xs text-neutral-400">No priced products yet.</div>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(analytics.price_distribution).map(([currency, stats]) => (
                      <div key={currency}>
                        <div className="text-xs font-semibold text-neutral-600 mb-1">
                          {currency} ({stats.count} product{stats.count === 1 ? "" : "s"})
                        </div>
                        <div className="grid grid-cols-3 gap-3 text-center">
                          <div>
                            <div className="text-xs text-neutral-500">Min</div>
                            <div className="text-base font-semibold">{currency} {stats.min}</div>
                          </div>
                          <div>
                            <div className="text-xs text-neutral-500">Avg</div>
                            <div className="text-base font-semibold">{currency} {stats.avg}</div>
                          </div>
                          <div>
                            <div className="text-xs text-neutral-500">Max</div>
                            <div className="text-base font-semibold">{currency} {stats.max}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="bg-white border border-neutral-200 rounded-lg p-5">
                <div className="text-sm font-medium mb-3">Products by Brand</div>
                {Object.entries(analytics.by_brand).map(([brand, count]) => (
                  <div key={brand} className="flex justify-between text-sm py-1">
                    <span>{brand}</span>
                    <span className="text-neutral-500">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-4 gap-4">
            {products.map((p) => {
              const src = imageSrc(p);
              const item = cartItemFromGenericProduct(p);
              const checked = cart.isInCart(item.source_ref);
              return (
                <div
                  key={p.id}
                  className={`bg-white border rounded-lg overflow-hidden hover:shadow-sm relative ${
                    checked ? "border-neutral-900 ring-1 ring-neutral-900" : "border-neutral-200"
                  }`}
                >
                  <label className="absolute top-2 left-2 z-10 bg-white/90 rounded-md p-1 flex items-center gap-1 text-[10px] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => cart.toggle(item)}
                      className="w-3.5 h-3.5"
                    />
                    PPT
                  </label>
                  <a href={p.product_url} target="_blank" rel="noreferrer">
                    <div className="aspect-square bg-neutral-100 flex items-center justify-center overflow-hidden">
                      {src ? (
                        <img src={src} alt={p.product_name} className="object-cover w-full h-full" />
                      ) : (
                        <span className="text-neutral-400 text-xs">No image</span>
                      )}
                    </div>
                    <div className="p-3">
                      <div className="text-xs text-neutral-500">{p.brand}</div>
                      <div className="text-sm font-medium truncate">{p.product_name}</div>
                      <div className="text-sm mt-1">{p.mrp ? `${p.currency} ${p.mrp}` : "Price unknown"}</div>
                    </div>
                  </a>
                </div>
              );
            })}
            {products.length === 0 && sources.length > 0 && (
              <div className="col-span-4 text-sm text-neutral-500">
                No products scraped yet — click "Run Scraper" on a source above.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
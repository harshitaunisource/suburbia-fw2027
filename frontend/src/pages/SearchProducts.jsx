import { useEffect, useMemo, useState } from "react";
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

export default function SearchProducts() {
  const [tree, setTree] = useState({});
  const [itemType, setItemType] = useState("");
  const [category, setCategory] = useState("");
  const [subCategory, setSubCategory] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [categoryMode, setCategoryMode] = useState("existing"); // "existing" | "new"

  const [brand, setBrand] = useState("");
  const [url, setUrl] = useState("");
  const [existingSource, setExistingSource] = useState(null); // a matching source for this brand+category, if any
  // Defaults to reusing the existing source when one is found, but this
  // can be overridden -- e.g. "Textilon" already has a women's pajamas
  // URL registered, but someone searching Textilon's MEN'S pajamas needs
  // a different URL entirely. Without this override, the form would
  // silently reuse the wrong (women's) URL with no way to change it.
  const [useExisting, setUseExisting] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pdpPattern, setPdpPattern] = useState("");

  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);
  const [products, setProducts] = useState([]);
  const [lastRun, setLastRun] = useState(null);
  const [elapsedMs, setElapsedMs] = useState(null);
  const cart = useCart();

  useEffect(() => {
    fetch("/api/generic/hierarchy").then((r) => r.json()).then(setTree);
  }, []);

  const itemTypes = useMemo(() => Object.keys(tree).sort(), [tree]);
  const categories = itemType ? Object.keys(tree[itemType] || {}).sort() : [];
  const subCategories = itemType && category ? tree[itemType][category] || [] : [];

  // Whenever brand + sub-category are both chosen, check whether this
  // exact brand name has already been searched for this category.
  useEffect(() => {
    setExistingSource(null);
    setUseExisting(true);
    if (!brand.trim() || !subCategoryId) return;
    const params = new URLSearchParams({ sub_category_id: subCategoryId });
    fetch(`/api/generic/sources?${params.toString()}`)
      .then((r) => r.json())
      .then((sources) => {
        const match = sources.find((s) => s.brand.toLowerCase() === brand.trim().toLowerCase());
        if (match) setExistingSource(match);
      });
  }, [brand, subCategoryId]);

  const needsUrl = !existingSource || !useExisting;

  const canSearch =
    brand.trim() &&
    (categoryMode === "existing" ? subCategoryId : itemType && category && subCategory.trim()) &&
    (!needsUrl || url.trim());

  async function handleSearch(e) {
    e.preventDefault();
    setSearching(true);
    setError(null);
    setProducts([]);
    setLastRun(null);
    setElapsedMs(null);
    const startedAt = Date.now();
    try {
      let source = existingSource && useExisting ? existingSource : null;
      if (!source) {
        const body = {
          brand,
          category_url: url,
          // No buyer/role -- Search Products is deliberately standalone.
          // Brand Setup's "add competitor/buyer" flow can attach this
          // exact source to a real buyer later without duplicating it.
        };
        if (pdpPattern.trim()) body.pdp_link_pattern = pdpPattern.trim();
        if (categoryMode === "existing") {
          body.sub_category_id = Number(subCategoryId);
        } else {
          body.item_type = itemType;
          body.category = category;
          body.sub_category = subCategory;
        }
        const res = await fetch("/api/generic/sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Couldn't create this source.");
        source = data;
        setExistingSource(data);
        fetch("/api/generic/hierarchy").then((r) => r.json()).then(setTree);
      }

      const scrapeRes = await fetch("/api/generic/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_config_id: source.id }),
      });
      const run = await scrapeRes.json();
      setLastRun(run);
      setElapsedMs(Date.now() - startedAt);
      if (!scrapeRes.ok) throw new Error(run.detail || "Scrape failed.");

      const prodParams = new URLSearchParams({ sub_category_id: source.sub_category_id, brand: source.brand });
      const prodRes = await fetch(`/api/generic/products?${prodParams.toString()}`);
      setProducts(await prodRes.json());
    } catch (err) {
      setElapsedMs(Date.now() - startedAt);
      setError(String(err.message || err));
    } finally {
      setSearching(false);
    }
  }

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

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Search Products</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Type a company name, tell us the category, and we'll pull its products. If this brand's
        already been searched for this category before, we'll offer to reuse that URL instead of
        asking for it again.
      </p>

      <CartBar count={cart.count} onGenerate={generatePPT} />

      <form onSubmit={handleSearch} className="bg-white border border-neutral-200 rounded-lg p-6 space-y-5 mb-6">
        <div>
          <label className="block text-sm font-medium mb-2">Company / Brand Name</label>
          <input
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            placeholder="e.g. Mango"
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          />
          <p className="text-xs text-neutral-400 mt-1">
            Tip: if a brand has separate men's/women's (or other) listings under the same category,
            give each one a distinct name here -- e.g. "Textilon" and "Textilon (Men)" -- so each
            keeps its own URL instead of sharing one.
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium">Category</label>
            <div className="flex gap-3 text-xs">
              <button
                type="button"
                onClick={() => setCategoryMode("existing")}
                className={`underline-offset-2 ${categoryMode === "existing" ? "underline font-medium" : "text-neutral-400"}`}
              >
                Pick existing
              </button>
              <button
                type="button"
                onClick={() => setCategoryMode("new")}
                className={`underline-offset-2 ${categoryMode === "new" ? "underline font-medium" : "text-neutral-400"}`}
              >
                Add new category
              </button>
            </div>
          </div>

          {categoryMode === "existing" ? (
            <div className="flex gap-2">
              <select
                value={itemType}
                onChange={(e) => {
                  setItemType(e.target.value);
                  setCategory("");
                  setSubCategoryId("");
                }}
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
              >
                <option value="">Item Type</option>
                {itemTypes.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setSubCategoryId("");
                }}
                disabled={!itemType}
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
              >
                <option value="">Category</option>
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select
                value={subCategoryId}
                onChange={(e) => setSubCategoryId(e.target.value)}
                disabled={!category}
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
              >
                <option value="">Sub Category</option>
                {subCategories.map((s) => (
                  <option key={s.id} value={s.id}>{s.sub_category}</option>
                ))}
              </select>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                value={itemType}
                onChange={(e) => setItemType(e.target.value)}
                placeholder="Item Type (e.g. GARMENT)"
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Category (e.g. APPAREL)"
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
              <input
                value={subCategory}
                onChange={(e) => setSubCategory(e.target.value)}
                placeholder="Sub Category (e.g. Jackets)"
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Website URL</label>
          {existingSource && useExisting ? (
            <div className="text-xs text-green-700 bg-green-50 rounded-md px-3 py-2">
              ✓ "{existingSource.brand}" was already searched for this category — using{" "}
              <a href={existingSource.category_url} target="_blank" rel="noreferrer" className="underline">
                {existingSource.category_url}
              </a>
              .{" "}
              <button
                type="button"
                onClick={() => setUseExisting(false)}
                className="underline font-medium"
              >
                This isn't the right listing — use a different URL instead
              </button>
            </div>
          ) : (
            <>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/women/sweaters"
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
              {existingSource && (
                <button
                  type="button"
                  onClick={() => setUseExisting(true)}
                  className="text-xs underline text-neutral-500 mt-1"
                >
                  Actually, reuse the existing "{existingSource.brand}" URL instead
                </button>
              )}
            </>
          )}
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-xs underline text-neutral-500"
          >
            {showAdvanced ? "Hide" : "Show"} advanced options
          </button>
          {showAdvanced && (
            <div className="mt-2">
              <label className="block text-xs text-neutral-500 mb-1">
                Product-link pattern (optional) — only needed if a first search finds 0 products.
                After searching, a debug HTML file is saved next to your backend (named like
                generic_&lt;brand&gt;_&lt;category&gt;_debug.html) — open it, find how the site's real
                product links look, and enter a regex matching them here to try again.
              </label>
              <input
                value={pdpPattern}
                onChange={(e) => setPdpPattern(e.target.value)}
                placeholder="e.g. /product/[a-z0-9-]+"
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm font-mono"
              />
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={!canSearch || searching}
          className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-40"
        >
          {searching ? "Searching…" : "Search Products"}
        </button>

        {searching && (
          <div className="text-xs text-neutral-500">
            Loading the page and scanning it for products — this usually takes 10–60 seconds
            depending on the site.
          </div>
        )}

        {error && (
          <div className="text-sm text-red-700 bg-red-50 rounded-md p-3">
            ✗ {error}
            {elapsedMs != null && <span className="text-red-400"> (after {(elapsedMs / 1000).toFixed(1)}s)</span>}
          </div>
        )}
        {lastRun && lastRun.status === "success" && lastRun.products_found > 0 && (
          <div className="text-sm text-green-700">
            ✓ Found {lastRun.products_found} product{lastRun.products_found === 1 ? "" : "s"}
            {elapsedMs != null && ` in ${(elapsedMs / 1000).toFixed(1)}s`}.
          </div>
        )}
        {lastRun && lastRun.status === "success" && lastRun.products_found === 0 && (
          <div className="text-sm text-amber-700 bg-amber-50 rounded-md p-3">
            The page loaded fine, but nothing matched as a product
            {elapsedMs != null && ` (took ${(elapsedMs / 1000).toFixed(1)}s)`}. This site's link
            pattern is probably different from the default guess — open "Show advanced options"
            above, check the debug HTML file it just saved, and try again with a specific link
            pattern.
          </div>
        )}
      </form>

      {products.length > 0 && (
        <div className="grid grid-cols-4 gap-4">
          {products.map((p) => {
            const src = imageSrc(p);
            const item = cartItemFromGenericProduct(p);
            const checked = cart.isInCart(item.source_ref);
            return (
              <div
                key={p.id}
                className={`bg-white border rounded-lg overflow-hidden relative ${
                  checked ? "border-neutral-900 ring-1 ring-neutral-900" : "border-neutral-200"
                }`}
              >
                <label className="absolute top-2 left-2 z-10 bg-white/90 rounded-md p-1 flex items-center gap-1 text-[10px] cursor-pointer">
                  <input type="checkbox" checked={checked} onChange={() => cart.toggle(item)} className="w-3.5 h-3.5" />
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
        </div>
      )}
    </div>
  );
}
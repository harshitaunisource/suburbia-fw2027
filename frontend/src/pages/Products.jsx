import { useEffect, useState } from "react";
import CartBar from "../components/CartBar";
import { cartItemFromProduct, useCart } from "../lib/cart";

function imageSrc(p) {
  if (p.local_image_path) {
    // Normalize backslashes first: some rows (scraped on Windows before
    // a since-fixed backend bug) have local_image_path stored with
    // Windows-style "storage\products\..." separators instead of
    // "storage/products/...". Without this, the "storage/" search below
    // would silently miss those rows and try to load a broken URL
    // containing literal backslashes -- normalizing here means already
    //-scraped data displays correctly without needing to re-scrape.
    const normalized = p.local_image_path.replace(/\\/g, "/");
    const idx = normalized.indexOf("storage/");
    return "/" + (idx >= 0 ? normalized.slice(idx) : normalized);
  }
  return p.image_url || null;
}

export default function Products() {
  const [products, setProducts] = useState([]);
  const [filters, setFilters] = useState({ source: "", category: "", brand: "" });
  const [categories, setCategories] = useState([]);
  const [sources, setSources] = useState([]);
  const cart = useCart();

  useEffect(() => {
    fetch("/api/products/meta/categories").then((r) => r.json()).then(setCategories);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (filters.category) params.set("category", filters.category);
    fetch(`/api/products/meta/sources?${params.toString()}`).then((r) => r.json()).then(setSources);
  }, [filters.category]);

  useEffect(() => {
    const params = new URLSearchParams({ limit: "100" });
    if (filters.source) params.set("source", filters.source);
    if (filters.category) params.set("category", filters.category);
    if (filters.brand) params.set("brand", filters.brand);
    fetch(`/api/products?${params.toString()}`)
      .then((r) => r.json())
      .then(setProducts);
  }, [filters]);

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
      <h1 className="text-2xl font-semibold mb-6">Products</h1>

      <CartBar count={cart.count} onGenerate={generatePPT} />

      <div className="flex gap-3 mb-6">
        <select
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          <option value="">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={filters.source}
          onChange={(e) => setFilters({ ...filters, source: e.target.value })}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          <option value="">All Sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {products.map((p) => {
          const src = imageSrc(p);
          const item = cartItemFromProduct(p);
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
                  <div className="text-xs text-neutral-500">
                    {p.source} {p.brand ? `· ${p.brand}` : ""}
                  </div>
                  <div className="text-sm font-medium truncate">{p.product_name}</div>
                  <div className="text-sm mt-1">
                    {/* Always show MRP (server-computed, never the discounted
                        price) -- see ProductOut.mrp in schemas.py. Previously
                        this showed the discounted price as primary with MRP
                        only struck through as an afterthought, which is
                        exactly backwards per the project's MRP-only rule. */}
                    {p.mrp ? `${p.currency} ${p.mrp}` : "Price unknown"}
                  </div>
                </div>
              </a>
            </div>
          );
        })}
        {products.length === 0 && (
          <div className="text-neutral-500 text-sm">No products yet — run a scraper first.</div>
        )}
      </div>
    </div>
  );
}
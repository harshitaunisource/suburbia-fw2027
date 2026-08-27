import { useEffect, useState } from "react";

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

  useEffect(() => {
    const params = new URLSearchParams({ limit: "100" });
    if (filters.source) params.set("source", filters.source);
    if (filters.category) params.set("category", filters.category);
    if (filters.brand) params.set("brand", filters.brand);
    fetch(`/api/products?${params.toString()}`)
      .then((r) => r.json())
      .then(setProducts);
  }, [filters]);

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Products</h1>

      <div className="flex gap-3 mb-6">
        <select
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          <option value="">All Categories</option>
          <option value="sweaters">Sweaters</option>
          <option value="blouses">Blouses</option>
        </select>
        <select
          value={filters.source}
          onChange={(e) => setFilters({ ...filters, source: e.target.value })}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          <option value="">All Sources</option>
          {["suburbia", "zara", "hm", "c_and_a", "primark", "target", "old_navy", "shein", "boohoo", "asos"].map(
            (s) => (
              <option key={s} value={s}>
                {s}
              </option>
            )
          )}
        </select>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {products.map((p) => {
          const src = imageSrc(p);
          return (
            <a
              key={p.id}
              href={p.product_url}
              target="_blank"
              rel="noreferrer"
              className="bg-white border border-neutral-200 rounded-lg overflow-hidden hover:shadow-sm"
            >
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
                  {p.price ? `${p.currency} ${p.price}` : "Price unknown"}
                  {p.original_price && p.original_price !== p.price && (
                    <span className="line-through text-neutral-400 ml-1">
                      {p.currency} {p.original_price}
                    </span>
                  )}
                </div>
              </div>
            </a>
          );
        })}
        {products.length === 0 && (
          <div className="text-neutral-500 text-sm">No products yet — run a scraper first.</div>
        )}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";

function Bar({ label, count, max }) {
  const pct = max ? Math.round((count / max) * 100) : 0;
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-neutral-600 mb-1">
        <span className="capitalize">{String(label).replace(/_/g, " ")}</span>
        <span>{count}</span>
      </div>
      <div className="w-full h-2 bg-neutral-100 rounded">
        <div className="h-2 bg-neutral-900 rounded" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DistributionCard({ title, rows }) {
  const max = rows.length ? Math.max(...rows.map((r) => r.count)) : 0;
  return (
    <div className="bg-white border border-neutral-200 rounded-lg p-5">
      <div className="text-sm font-medium mb-3">{title}</div>
      {rows.length === 0 && <div className="text-xs text-neutral-400">No data yet.</div>}
      {rows.map((r) => (
        <Bar key={r.value} label={r.value} count={r.count} max={max} />
      ))}
    </div>
  );
}

export default function Analytics() {
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState("");
  const [availableBrands, setAvailableBrands] = useState([]);
  // Empty selection = "all brands in this category" -- this list grows
  // on its own as new brands get scraped, replacing the old fixed
  // "Suburbia Only / Competitors Only / All" dropdown.
  const [brands, setBrands] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/products/meta/categories")
      .then((r) => r.json())
      .then((cats) => {
        setCategories(cats);
        if (cats.length && !category) setCategory(cats[0]);
      });
  }, []);

  useEffect(() => {
    if (!category) return;
    fetch(`/api/products/meta/sources?category=${encodeURIComponent(category)}`)
      .then((r) => r.json())
      .then((list) => {
        setAvailableBrands(list);
        setBrands([]); // reset selection when category changes
      });
  }, [category]);

  useEffect(() => {
    if (!category) return;
    // Guards against a real race: picking a category fires one fetch,
    // then picking a brand fires a second fetch moments later. If the
    // backend is slow (or mid-restart) those two responses can arrive
    // OUT OF ORDER -- without this guard, the older "all brands"
    // response can land after the newer "just this brand" one and
    // silently overwrite it, which looked like the page "auto-reverting"
    // on its own a moment after making a selection.
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams({ category });
    if (brands.length) params.set("sources", brands.join(","));
    fetch(`/api/analytics?${params.toString()}`)
      .then((r) => r.json())
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [category, brands]);

  function toggleBrand(b) {
    setBrands((prev) => (prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]));
  }

  function downloadExcel() {
    const params = new URLSearchParams({ category });
    if (brands.length) params.set("sources", brands.join(","));
    window.location.href = `/api/analytics/export?${params.toString()}`;
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Market Analytics</h1>

      <div className="bg-white border border-neutral-200 rounded-lg p-4 mb-6 space-y-4">
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Category</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={downloadExcel}
            disabled={!category}
            className="px-4 py-2 border border-neutral-300 rounded-md text-sm disabled:opacity-50"
          >
            Download Excel
          </button>
        </div>

        <div>
          <label className="block text-xs text-neutral-500 mb-2">
            Brands ({brands.length === 0 ? "all" : `${brands.length} selected`})
          </label>
          <div className="flex flex-wrap gap-2">
            {availableBrands.map((b) => (
              <label
                key={b}
                className={`text-xs px-2.5 py-1.5 rounded-full border cursor-pointer ${
                  brands.includes(b)
                    ? "bg-neutral-900 text-white border-neutral-900"
                    : "bg-white text-neutral-600 border-neutral-300"
                }`}
              >
                <input type="checkbox" checked={brands.includes(b)} onChange={() => toggleBrand(b)} className="hidden" />
                {b}
              </label>
            ))}
            {availableBrands.length === 0 && (
              <span className="text-xs text-neutral-400">No brands scraped for this category yet.</span>
            )}
          </div>
        </div>
      </div>

      {loading && <div className="text-sm text-neutral-500">Loading…</div>}

      {data && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white border border-neutral-200 rounded-lg p-5">
            <div className="text-sm font-medium mb-3">Price Distribution (MRP, by currency)</div>
            {Object.keys(data.price_distribution).length === 0 ? (
              <div className="text-xs text-neutral-400">No priced products yet.</div>
            ) : (
              <div className="space-y-3">
                {Object.entries(data.price_distribution).map(([currency, stats]) => (
                  <div key={currency}>
                    <div className="text-xs font-semibold text-neutral-600 mb-1">
                      {currency} ({stats.count} product{stats.count === 1 ? "" : "s"})
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-center">
                      <div>
                        <div className="text-xs text-neutral-500">Min</div>
                        <div className="text-base font-semibold">
                          {currency} {stats.min}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-neutral-500">Avg</div>
                        <div className="text-base font-semibold">
                          {currency} {stats.avg}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-neutral-500">Max</div>
                        <div className="text-base font-semibold">
                          {currency} {stats.max}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-white border border-neutral-200 rounded-lg p-5">
            <div className="text-sm font-medium mb-3">Product Count by Source</div>
            {Object.entries(data.product_counts.by_source).length === 0 && (
              <div className="text-xs text-neutral-400">No products yet.</div>
            )}
            {Object.entries(data.product_counts.by_source).map(([source, count]) => (
              <Bar
                key={source}
                label={source}
                count={count}
                max={Math.max(...Object.values(data.product_counts.by_source), 1)}
              />
            ))}
          </div>

          <DistributionCard title="Top Colors" rows={data.colors} />
          <DistributionCard title="Silhouette / Fit Analysis" rows={data.silhouettes} />
          <DistributionCard title="Pattern Analysis" rows={data.patterns} />
          <DistributionCard title="Neckline Analysis" rows={data.necklines} />
        </div>
      )}
    </div>
  );
}
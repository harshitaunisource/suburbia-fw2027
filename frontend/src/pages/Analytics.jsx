import { useEffect, useState } from "react";

const CATEGORIES = [
  { value: "", label: "All Categories" },
  { value: "sweaters", label: "Sweaters" },
  { value: "blouses", label: "Blouses" },
];

const GROUPS = [
  { value: "", label: "All Sources" },
  { value: "suburbia", label: "Suburbia Only" },
  { value: "competitors", label: "Competitors Only" },
];

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
  const [category, setCategory] = useState("");
  // Defaults to competitors-only, not "all sources": mixing Suburbia's
  // own assortment into these breakdowns dilutes the competitor trend
  // signal these charts exist to surface (the gap-analysis page already
  // treats "the market" as competitors vs. Suburbia separately -- this
  // should match that framing by default). Switch to "All Sources" or
  // "Suburbia Only" any time from the dropdown.
  const [group, setGroup] = useState("competitors");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (group) params.set("group", group);
    fetch(`/api/analytics?${params.toString()}`)
      .then((r) => r.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, [category, group]);

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Market Analytics</h1>

      <div className="flex gap-3 mb-6">
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <select
          value={group}
          onChange={(e) => setGroup(e.target.value)}
          className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          {GROUPS.map((g) => (
            <option key={g.value} value={g.value}>
              {g.label}
            </option>
          ))}
        </select>
      </div>

      {loading && <div className="text-sm text-neutral-500">Loading…</div>}

      {data && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white border border-neutral-200 rounded-lg p-5">
            <div className="text-sm font-medium mb-3">Price Distribution</div>
            {data.price_distribution.count === 0 ? (
              <div className="text-xs text-neutral-400">No priced products yet.</div>
            ) : (
              <div className="grid grid-cols-4 gap-3 text-center">
                <div>
                  <div className="text-xs text-neutral-500">Min</div>
                  <div className="text-lg font-semibold">${data.price_distribution.min}</div>
                </div>
                <div>
                  <div className="text-xs text-neutral-500">Avg</div>
                  <div className="text-lg font-semibold">${data.price_distribution.avg}</div>
                </div>
                <div>
                  <div className="text-xs text-neutral-500">Median</div>
                  <div className="text-lg font-semibold">${data.price_distribution.median}</div>
                </div>
                <div>
                  <div className="text-xs text-neutral-500">Max</div>
                  <div className="text-lg font-semibold">${data.price_distribution.max}</div>
                </div>
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
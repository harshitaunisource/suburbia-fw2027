import { useEffect, useState } from "react";

function imageSrc(p) {
  if (p.local_image_path) {
    const normalized = p.local_image_path.replace(/\\/g, "/");
    const idx = normalized.indexOf("storage/");
    return "/" + (idx >= 0 ? normalized.slice(idx) : normalized);
  }
  return p.image_url || null;
}

export default function BuyerOpportunities() {
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState("");
  const [sources, setSources] = useState([]); // every source available for the chosen category
  const [buyer, setBuyer] = useState("");
  const [competitors, setCompetitors] = useState([]); // selected subset of sources (excluding buyer)

  const [opportunities, setOpportunities] = useState([]);
  const [gapTable, setGapTable] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [suggestionsFor, setSuggestionsFor] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // Categories: whatever's actually been scraped, not a fixed list.
  useEffect(() => {
    fetch("/api/products/meta/categories")
      .then((r) => r.json())
      .then((cats) => {
        setCategories(cats);
        if (cats.length && !category) setCategory(cats[0]);
      });
  }, []);

  // Sources available for the chosen category -- this list grows on its
  // own as new brands get scraped for this category, no code change
  // needed. Picking a category resets the buyer/competitor selection
  // since last category's choices may not exist in the new one.
  useEffect(() => {
    if (!category) return;
    fetch(`/api/products/meta/sources?category=${encodeURIComponent(category)}`)
      .then((r) => r.json())
      .then((list) => {
        setSources(list);
        setBuyer((prev) => (list.includes(prev) ? prev : list[0] || ""));
        setCompetitors([]);
      });
  }, [category]);

  const competitorChoices = sources.filter((s) => s !== buyer);

  function toggleCompetitor(source) {
    setCompetitors((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  }

  useEffect(() => {
    // Same race-condition guard as Analytics.jsx -- picking a buyer then
    // quickly toggling a competitor fires two overlapping fetches; without
    // this, an out-of-order response can silently overwrite the correct,
    // newer one a moment after you made the selection.
    if (!category || !buyer) return;
    let cancelled = false;

    fetch(`/api/opportunities?category=${encodeURIComponent(category)}`)
      .then((r) => r.json())
      .then((result) => {
        if (!cancelled) setOpportunities(result);
      });

    const gapParams = new URLSearchParams({ category, our_source: buyer });
    if (competitors.length) gapParams.set("competitor_sources", competitors.join(","));
    fetch(`/api/analytics/gap?${gapParams.toString()}`)
      .then((r) => r.json())
      .then((result) => {
        if (!cancelled) setGapTable(result);
      });

    return () => {
      cancelled = true;
    };
  }, [category, buyer, competitors]);

  function refresh() {
    if (!category || !buyer) return;
    fetch(`/api/opportunities?category=${encodeURIComponent(category)}`)
      .then((r) => r.json())
      .then(setOpportunities);

    const gapParams = new URLSearchParams({ category, our_source: buyer });
    if (competitors.length) gapParams.set("competitor_sources", competitors.join(","));
    fetch(`/api/analytics/gap?${gapParams.toString()}`)
      .then((r) => r.json())
      .then(setGapTable);
  }

  async function generate() {
    setGenerating(true);
    try {
      await fetch("/api/opportunities/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          top_n: 15,
          our_source: buyer,
          // Empty selection = "everyone else" (matches the original
          // Suburbia-vs-market behavior); a specific selection = exactly
          // those competitors.
          competitor_sources: competitors.length ? competitors : null,
        }),
      });
    } finally {
      setGenerating(false);
      refresh();
    }
  }

  function downloadExcel() {
    const params = new URLSearchParams({ category, our_source: buyer });
    if (competitors.length) params.set("competitor_sources", competitors.join(","));
    window.location.href = `/api/opportunities/export?${params.toString()}`;
  }

  async function setStatus(id, status) {
    await fetch(`/api/opportunities/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    refresh();
  }

  async function showSuggestions(opportunityId) {
    if (suggestionsFor === opportunityId) {
      setSuggestionsFor(null);
      return;
    }
    setSuggestionsFor(opportunityId);
    setLoadingSuggestions(true);
    try {
      const res = await fetch(`/api/opportunities/${opportunityId}/suggested-products`);
      setSuggestions(await res.json());
    } finally {
      setLoadingSuggestions(false);
    }
  }

  async function pickProduct(opportunityId, productId) {
    await fetch("/api/catalogue/products/from-product", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ opportunity_id: opportunityId, product_id: productId }),
    });
    setSuggestionsFor(null);
    refresh();
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Buyer Opportunities</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Pick a buyer and which competitors to compare it against — any brand that's been scraped for
        this category is available, no fixed list.
      </p>

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
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Buyer</label>
            <select
              value={buyer}
              onChange={(e) => setBuyer(e.target.value)}
              className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
            >
              {sources.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={generate}
            disabled={generating || !buyer}
            className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate / Refresh Opportunities"}
          </button>
          <button
            onClick={downloadExcel}
            disabled={!buyer}
            className="px-4 py-2 border border-neutral-300 rounded-md text-sm disabled:opacity-50"
          >
            Download Excel
          </button>
        </div>

        <div>
          <label className="block text-xs text-neutral-500 mb-2">
            Competitors ({competitors.length === 0 ? "all others" : `${competitors.length} selected`})
          </label>
          <div className="flex flex-wrap gap-2">
            {competitorChoices.map((s) => (
              <label
                key={s}
                className={`text-xs px-2.5 py-1.5 rounded-full border cursor-pointer ${
                  competitors.includes(s)
                    ? "bg-neutral-900 text-white border-neutral-900"
                    : "bg-white text-neutral-600 border-neutral-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={competitors.includes(s)}
                  onChange={() => toggleCompetitor(s)}
                  className="hidden"
                />
                {s}
              </label>
            ))}
            {competitorChoices.length === 0 && (
              <span className="text-xs text-neutral-400">No other brands scraped for this category yet.</span>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-3">
          {opportunities.length === 0 && (
            <div className="text-sm text-neutral-500">
              No opportunities yet — run scrapers + AI attribute extraction for both sides of this
              comparison, then click "Generate / Refresh Opportunities".
            </div>
          )}
          {opportunities.map((o, idx) => (
            <div key={o.id} className="bg-white border border-neutral-200 rounded-lg p-5">
              <div className="flex justify-between items-start">
                <div>
                  <div className="text-xs text-neutral-400">{String(idx + 1).padStart(2, "0")}</div>
                  <div className="text-lg font-semibold">{o.concept_name}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold">{Math.round(o.opportunity_score)}</div>
                  <div className="text-xs text-neutral-400">/ 100</div>
                </div>
              </div>

              <div className="mt-2">
                <span
                  className={`inline-block text-xs px-2 py-1 rounded-full ${
                    o.status === "shortlisted"
                      ? "bg-green-100 text-green-700"
                      : o.status === "rejected"
                      ? "bg-red-100 text-red-700"
                      : o.status === "selected" || o.status === "catalogue"
                      ? "bg-blue-100 text-blue-700"
                      : "bg-neutral-100 text-neutral-600"
                  }`}
                >
                  {o.status}
                </span>
              </div>

              {expanded === o.id && (
                <div className="mt-3 text-sm text-neutral-600 bg-neutral-50 rounded-md p-3">
                  <div className="mb-2">{o.reason}</div>
                  <div className="grid grid-cols-5 gap-2 text-xs text-center">
                    <div>
                      <div className="text-neutral-400">Trend</div>
                      <div className="font-medium">{o.trend_score}</div>
                    </div>
                    <div>
                      <div className="text-neutral-400">Competitor</div>
                      <div className="font-medium">{o.competitor_score}</div>
                    </div>
                    <div>
                      <div className="text-neutral-400">Gap</div>
                      <div className="font-medium">{o.suburbia_gap_score}</div>
                    </div>
                    <div>
                      <div className="text-neutral-400">Price</div>
                      <div className="font-medium">{o.price_score}</div>
                    </div>
                    <div>
                      <div className="text-neutral-400">Commercial</div>
                      <div className="font-medium">{o.commercial_score}</div>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-2 mt-3 flex-wrap">
                <button
                  onClick={() => setStatus(o.id, "shortlisted")}
                  className="px-3 py-1.5 text-xs rounded-md bg-green-600 text-white"
                >
                  Shortlist
                </button>
                <button
                  onClick={() => setStatus(o.id, "rejected")}
                  className="px-3 py-1.5 text-xs rounded-md bg-neutral-200 text-neutral-700"
                >
                  Reject
                </button>
                <button
                  onClick={() => setExpanded(expanded === o.id ? null : o.id)}
                  className="px-3 py-1.5 text-xs rounded-md border border-neutral-300"
                >
                  {expanded === o.id ? "Hide Evidence" : "View Evidence"}
                </button>
                {(o.status === "shortlisted" || o.status === "selected") && (
                  <button
                    onClick={() => showSuggestions(o.id)}
                    className="px-3 py-1.5 text-xs rounded-md bg-blue-600 text-white"
                  >
                    {suggestionsFor === o.id ? "Hide Suggestions" : "Suggest Products"}
                  </button>
                )}
              </div>

              {suggestionsFor === o.id && (
                <div className="mt-4 border-t border-neutral-100 pt-4">
                  <div className="text-xs text-neutral-500 mb-2">
                    Real competitor products matching this concept — pick the closest one to add it to the
                    catalogue.
                  </div>
                  {loadingSuggestions && <div className="text-xs text-neutral-400">Loading…</div>}
                  <div className="grid grid-cols-4 gap-3">
                    {suggestions.map((p) => {
                      const src = imageSrc(p);
                      return (
                        <div key={p.id} className="border border-neutral-200 rounded-md overflow-hidden">
                          <div className="aspect-square bg-neutral-100 flex items-center justify-center overflow-hidden">
                            {src ? (
                              <img src={src} alt={p.product_name} className="object-cover w-full h-full" />
                            ) : (
                              <span className="text-neutral-400 text-[10px]">No image</span>
                            )}
                          </div>
                          <div className="p-2">
                            <div className="text-[11px] text-neutral-500">{p.source}</div>
                            <div className="text-xs font-medium truncate">{p.product_name}</div>
                            <button
                              onClick={() => pickProduct(o.id, p.id)}
                              className="w-full mt-1.5 px-2 py-1 text-[11px] rounded bg-neutral-900 text-white"
                            >
                              Use this product
                            </button>
                          </div>
                        </div>
                      );
                    })}
                    {!loadingSuggestions && suggestions.length === 0 && (
                      <div className="col-span-4 text-xs text-neutral-400">
                        No matching competitor products found with this concept's attributes.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        <div>
          <div className="bg-white border border-neutral-200 rounded-lg p-4">
            <div className="text-sm font-medium mb-3">
              Gap Table ({buyer || "—"} vs {competitors.length ? competitors.join(", ") : "market"})
            </div>
            <table className="w-full text-xs">
              <thead className="text-neutral-500">
                <tr>
                  <th className="text-left pb-2">Concept</th>
                  <th className="text-right pb-2">Market</th>
                  <th className="text-right pb-2">Ours</th>
                  <th className="text-right pb-2">Gap</th>
                </tr>
              </thead>
              <tbody>
                {gapTable.slice(0, 15).map((row, i) => (
                  <tr key={i} className="border-t border-neutral-100">
                    <td className="py-1.5 capitalize">{row.value?.replace(/_/g, " ")}</td>
                    <td className="text-right">{row.market_pct}%</td>
                    <td className="text-right">{row.suburbia_pct}%</td>
                    <td
                      className={`text-right font-medium ${
                        row.gap_label === "High"
                          ? "text-red-600"
                          : row.gap_label === "Medium"
                          ? "text-amber-600"
                          : "text-neutral-500"
                      }`}
                    >
                      {row.gap}
                    </td>
                  </tr>
                ))}
                {gapTable.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-3 text-neutral-400">
                      No data yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
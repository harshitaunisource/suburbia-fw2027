import { useEffect, useState } from "react";

// verified: true  -> this exact category URL was confirmed working by
//                    opening it in a real browser (2026-08-26)
// verified: false -> best-effort guess; not yet confirmed
// Even "verified" URLs can still fail to SCRAPE (bot protection,
// selector drift) -- verified only means the page itself is real.
const SCRAPER_CATEGORIES = [
  { source: "suburbia", label: "Suburbia — Sweaters", category: "sweaters", url: "https://www.suburbia.com.mx/tienda/su%C3%A9teres/cat_SB_3008", verified: true },
  { source: "suburbia", label: "Suburbia — Blouses", category: "blouses", url: "https://www.suburbia.com.mx/tienda/blusas/cat_SB_3001", verified: true },

  { source: "zara", label: "Zara (India) — Knitwear", category: "sweaters", url: "https://www.zara.com/in/en/woman-knitwear-l1152.html", verified: true },
  { source: "zara", label: "Zara (India) — Shirts & Blouses", category: "blouses", url: "https://www.zara.com/in/en/woman-shirts-blouses-l1221.html", verified: true },

  { source: "hm", label: "H&M (India) — Jumpers", category: "sweaters", url: "https://www2.hm.com/en_in/women/shop-by-product/cardigans-jumpers/jumpers.html", verified: true },
  { source: "hm", label: "H&M (India) — Shirts & Blouses", category: "blouses", url: "https://www2.hm.com/en_in/women/shop-by-product/shirts-blouses.html", verified: true },

  { source: "c_and_a", label: "C&A — Sweaters", category: "sweaters", url: "https://www.cyamoda.com/mujer/ropa/sueteres/", verified: true },
  { source: "c_and_a", label: "C&A — Blouses", category: "blouses", url: "https://www.cyamoda.com/mujer/ropa/blusas/", verified: false },

  { source: "primark", label: "Primark (US) — Sweaters & Cardigans", category: "sweaters", url: "https://www.primark.com/en-us/c/women/clothing/sweaters-and-cardigans", verified: true },
  { source: "primark", label: "Primark (UK) — Blouses", category: "blouses", url: "https://www.primark.com/en-gb/c/women/clothing/shirts-and-blouses/blouses", verified: true },

  { source: "target", label: "Target — Sweaters", category: "sweaters", url: "https://www.target.com/c/sweaters-women-s-clothing/-/N-5xtbx", verified: true },
  { source: "target", label: "Target — Shirts & Blouses", category: "blouses", url: "https://www.target.com/c/shirts-blouses-women-s-clothing/-/N-m7sh2", verified: true },

  { source: "old_navy", label: "Old Navy (Gap) — Sweaters & Cardigans", category: "sweaters", url: "https://oldnavy.gap.com/browse/women/sweaters-and-cardigans?cid=20408#department=136", verified: true },
  { source: "old_navy", label: "Old Navy (Gap) — Blouses", category: "blouses", url: "https://oldnavy.gap.com/shop/womens-fashion-blouses-0aaz22b", verified: true },

  { source: "shein", label: "SHEIN (MX) — Sweaters", category: "sweaters", url: "https://www.shein.com.mx/category/Sweaters-sc-00831455.html", verified: true },
  { source: "shein", label: "SHEIN (MX) — Blouses", category: "blouses", url: "https://www.shein.com.mx/style/Women-Blouses-sc-00122967.html", verified: true },

  { source: "boohoo", label: "Boohoo (US) — Knitwear", category: "sweaters", url: "https://us.boohoo.com/categories/womens-knitwear-jumpers", verified: true },
  { source: "boohoo", label: "Boohoo (UK) — Tops, Shirts & Blouses", category: "blouses", url: "https://www.boohoo.com/categories/womens-tops-shirts-and-blouses", verified: true },

  { source: "asos", label: "ASOS — Jumpers & Cardigans", category: "sweaters", url: "https://www.asos.com/us/women/jumpers-cardigans/cat/?cid=2637", verified: true },
  { source: "asos", label: "ASOS — Shirts & Blouses", category: "blouses", url: "https://www.asos.com/us/women/shirts-blouses/cat/?cid=15200", verified: true },

  { source: "textilon", label: "Textilon — Women's Pajamas", category: "pajamas", url: "https://bo.textilon.com/articulos/categoria/mujer/subcategoria/pijamas", verified: true },
  { source: "textilon", label: "Textilon — Men's Pajamas", category: "pajamas", url: "https://bo.textilon.com/articulos/categoria/hombre/subcategoria/pijamas", verified: true },
];

export default function DataCollection() {
  const [rows, setRows] = useState([]);
  const [running, setRunning] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  function refresh() {
    fetch("/api/scrapers/status")
      .then((r) => r.json())
      .then(setRows);
  }

  useEffect(refresh, []);

  async function runScraper(source, category, url) {
    // Must match the 3-part key format used in the table below
    // (source-category-url) -- otherwise this would never equal the
    // `running === key` check on the button, and the loading state
    // would silently never show.
    const key = `${source}-${category}-${url}`;
    setRunning(key);
    setLastResult(null);
    try {
      const res = await fetch("/api/scrapers/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, category, category_url: url, max_pages: 2 }),
      });
      const data = await res.json();
      setLastResult({ key, ...data });
    } finally {
      setRunning(null);
      refresh();
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Data Collection</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Rows marked <span className="text-amber-600">●</span> have an unconfirmed category URL. Even verified
        rows can still fail to scrape (bot protection, page structure changes) — "verified" only means the page
        itself is real, checked in a browser.
      </p>

      {lastResult && (
        <div
          className={`mb-4 p-3 rounded-md text-sm ${
            lastResult.status === "success" ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
          }`}
        >
          {lastResult.status === "success"
            ? `✓ ${lastResult.products_found} products found (${lastResult.products_new} new, ${lastResult.products_updated} updated, ${lastResult.images_downloaded} images).`
            : `✗ Failed: ${lastResult.error_message}`}
        </div>
      )}

      <table className="w-full bg-white border border-neutral-200 rounded-lg overflow-hidden text-sm">
        <thead className="bg-neutral-100 text-left">
          <tr>
            <th className="p-3"></th>
            <th className="p-3">Source</th>
            <th className="p-3">Category</th>
            <th className="p-3">Products</th>
            <th className="p-3">Last Run</th>
            <th className="p-3">Status</th>
            <th className="p-3">Action</th>
          </tr>
        </thead>
        <tbody>
          {SCRAPER_CATEGORIES.map((c) => {
            // Keyed on url too, not just source+category: Textilon has
            // two rows (women's/men's) that share the same category
            // ("pajamas"), which would otherwise produce a duplicate
            // React key and make both rows' "Run Scraper" buttons show
            // as loading together when either one was clicked.
            const key = `${c.source}-${c.category}-${c.url}`;
            // NOTE: the status/last-run/product-count columns below are
            // looked up by source+category only (matching the backend's
            // /api/scrapers/status grouping) -- for Textilon specifically,
            // this means the women's and men's rows will show the SAME
            // aggregate status, since both share category="pajamas" and
            // the backend doesn't currently track per-URL run history
            // within one category. Not a display bug for any other
            // source (each has a unique category), just a known
            // limitation for this one case.
            const statusRow = rows.find((r) => r.source === c.source && r.category === c.category);
            return (
              <tr key={key} className="border-t border-neutral-200">
                <td className="p-3">{!c.verified && <span className="text-amber-600">●</span>}</td>
                <td className="p-3">{c.label}</td>
                <td className="p-3 capitalize">{c.category}</td>
                <td className="p-3">{statusRow?.products ?? 0}</td>
                <td className="p-3">
                  {statusRow?.last_run ? new Date(statusRow.last_run).toLocaleString() : "—"}
                </td>
                <td className="p-3">{statusRow?.status === "success" ? "✓" : statusRow?.status || "never_run"}</td>
                <td className="p-3">
                  <button
                    onClick={() => runScraper(c.source, c.category, c.url)}
                    disabled={running === key}
                    className="px-3 py-1.5 bg-neutral-900 text-white rounded-md text-xs disabled:opacity-50"
                  >
                    {running === key ? "Running…" : "Run Scraper"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
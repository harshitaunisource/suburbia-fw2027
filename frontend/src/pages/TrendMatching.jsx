import { useEffect, useRef, useState } from "react";
import CartBar from "../components/CartBar";
import { useCart } from "../lib/cart";

const SOURCE_LABELS = { CATALOGUE: "Your data", WEB: "Web" };

function imageSrc(path) {
  if (!path) return null;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return path.startsWith("/") ? path : `/${path}`;
}

/** Every backend error in this app can come back as either JSON (a
 * normal FastAPI error) or plain HTML/text (a raw 500 from the
 * webserver/proxy, e.g. if the database connection drops mid-request) --
 * calling res.json() unconditionally on the latter throws "Unexpected
 * token 'I', 'Internal S'... is not valid JSON" instead of showing the
 * actual problem. This reads the body once as text and only parses it
 * as JSON if it looks like JSON, so failures always show a readable
 * message instead of crashing on the error-handling path itself. */
async function safeJson(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text.slice(0, 300) || `Request failed with status ${res.status}` };
  }
}

export default function TrendMatching() {
  const cart = useCart();

  const [buyerLabel, setBuyerLabel] = useState("");
  const [trendFile, setTrendFile] = useState(null);
  const [trendUpload, setTrendUpload] = useState(null); // polled, has status/total_products/products_classified
  const [trendProducts, setTrendProducts] = useState([]);
  const [uploading, setUploading] = useState(false);

  const [matching, setMatching] = useState(false);
  const [matchData, setMatchData] = useState(null); // [{product, matches}]
  const [error, setError] = useState(null);
  const [selectingId, setSelectingId] = useState(null);

  const pollRef = useRef(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleUploadTrend() {
    if (!trendFile) return;
    setUploading(true);
    setError(null);
    setMatchData(null);
    setTrendProducts([]);
    try {
      const form = new FormData();
      form.append("file", trendFile);
      if (buyerLabel) form.append("buyer_label", buyerLabel);
      const res = await fetch("/api/trends/upload", { method: "POST", body: form });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      setTrendUpload(data);

      if (data.status === "failed") {
        setError(data.error_message);
        setUploading(false);
        return;
      }

      // Classification runs in the background (a large deck can take
      // real time -- see routers/trends.py) -- poll every 1.5s for
      // live "X / Y classified" progress until it's done.
      pollRef.current = setInterval(async () => {
        const pollRes = await fetch(`/api/trends/${data.id}`);
        const polled = await safeJson(pollRes);
        if (!pollRes.ok) {
          clearInterval(pollRef.current);
          setError(polled.detail || "Lost track of this upload's progress");
          setUploading(false);
          return;
        }
        setTrendUpload(polled);
        if (polled.status === "ready" || polled.status === "failed") {
          clearInterval(pollRef.current);
          setUploading(false);
          if (polled.status === "failed") {
            setError(polled.error_message);
          } else {
            const productsRes = await fetch(`/api/trends/${data.id}/products`);
            setTrendProducts(await safeJson(productsRes));
          }
        }
      }, 1500);
    } catch (err) {
      setError(String(err.message || err));
      setUploading(false);
    }
  }

  async function handleFindMatches() {
    if (!trendUpload || trendUpload.status !== "ready") return;
    setMatching(true);
    setError(null);
    try {
      const res = await fetch(`/api/trends/${trendUpload.id}/match`, { method: "POST" });
      const summary = await safeJson(res);
      if (!res.ok) throw new Error(summary.detail || "Matching failed");
      const matchesRes = await fetch(`/api/trends/${trendUpload.id}/matches`);
      setMatchData(await safeJson(matchesRes));
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setMatching(false);
    }
  }

  async function toggleMatch(matchId) {
    setSelectingId(matchId);
    try {
      const res = await fetch(`/api/trends/matches/${matchId}/select`, { method: "POST" });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.detail || "Could not update selection");
      // The trend-match cart row lives in the same CatalogueProduct table
      // as every other "Add to PPT" checkbox in this app -- refreshing
      // the shared cart here keeps CartBar's count and isInCart() in
      // sync without a second, parallel selection-tracking mechanism.
      await cart.refresh();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setSelectingId(null);
    }
  }

  async function generatePPT() {
    const res = await fetch("/api/catalogue/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data.detail || "PPT generation failed");
    cart.refresh();
    return data;
  }

  const isProcessing = trendUpload?.status === "processing";
  const progressPct = trendUpload?.total_products
    ? Math.round((100 * (trendUpload.products_classified || 0)) / trendUpload.total_products)
    : 0;

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Trend Matching</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Upload a buyer trend deck (PPT or PDF, image-heavy is fine) -- every product photo gets
        AI-classified, then matched against your already-scraped competitor data (ASOS, C&amp;A,
        Primark, etc.) and the open web. Select whichever matches actually fit, per trend product,
        then generate a PPT.
      </p>

      <CartBar count={cart.count} onGenerate={generatePPT} />

      {error && (
        <div className="mb-6 text-sm text-red-700 bg-red-50 rounded-md p-3">✗ {error}</div>
      )}

      <div className="bg-white border border-neutral-200 rounded-lg p-4 mb-8 max-w-xl">
        <div className="text-sm font-semibold mb-3">Step 1 — Upload buyer trend deck</div>
        <input
          type="text"
          placeholder="Buyer / season label (optional)"
          value={buyerLabel}
          onChange={(e) => setBuyerLabel(e.target.value)}
          className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm mb-2"
        />
        <input
          type="file"
          accept=".pptx,.pdf"
          onChange={(e) => setTrendFile(e.target.files?.[0] || null)}
          className="w-full text-sm mb-3"
        />
        <button
          onClick={handleUploadTrend}
          disabled={!trendFile || uploading}
          className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "Upload & Classify"}
        </button>

        {isProcessing && (
          <div className="mt-4">
            <div className="flex justify-between text-xs text-neutral-500 mb-1">
              <span>
                Classifying {trendUpload.products_classified || 0} / {trendUpload.total_products} products…
              </span>
              <span>{progressPct}%</span>
            </div>
            <div className="w-full h-2 bg-neutral-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-neutral-900 transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="text-xs text-neutral-400 mt-1">
              A large deck can take a few minutes -- this page will update automatically.
            </div>
          </div>
        )}

        {trendUpload?.status === "ready" && (
          <div className="mt-3 text-xs text-green-700">
            ✓ {trendProducts.length} product{trendProducts.length === 1 ? "" : "s"} classified from {trendUpload.filename}
          </div>
        )}
      </div>

      {trendProducts.length > 0 && !matchData && (
        <div className="mb-8">
          <div className="text-sm font-semibold mb-3">Buyer trend products</div>
          <div className="grid grid-cols-6 gap-3 mb-4">
            {trendProducts.map((p) => (
              <div key={p.id} className="bg-white border border-neutral-200 rounded-lg overflow-hidden">
                <div className="aspect-square bg-neutral-100 overflow-hidden">
                  <img src={imageSrc(p.image_path)} alt={p.ai_name} className="object-cover w-full h-full" />
                </div>
                <div className="p-2 text-[11px] leading-tight">{p.ai_name}</div>
              </div>
            ))}
          </div>
          <button
            onClick={handleFindMatches}
            disabled={matching}
            className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-50"
          >
            {matching ? "Searching your data + the web…" : "Step 2 — Find Matching Products"}
          </button>
        </div>
      )}

      {matchData && (
        <div>
          <div className="text-sm font-semibold mb-4">Step 3 — Review and select matches</div>
          {matchData.map((tp) => (
            <div key={tp.product.id} className="mb-8 bg-white border border-neutral-200 rounded-lg p-4">
              <div className="flex gap-4 mb-4">
                <div className="w-24 h-24 shrink-0 bg-neutral-100 rounded-md overflow-hidden">
                  <img src={imageSrc(tp.product.image_path)} alt={tp.product.ai_name} className="object-cover w-full h-full" />
                </div>
                <div>
                  <div className="text-sm font-semibold">{tp.product.ai_name}</div>
                  <div className="text-xs text-neutral-500 mt-1">
                    {tp.product.ai_category} {tp.product.ai_color ? `· ${tp.product.ai_color}` : ""}{" "}
                    {tp.product.ai_pattern ? `· ${tp.product.ai_pattern}` : ""}
                  </div>
                  <div className="text-xs text-neutral-400 mt-1">{tp.matches.length} candidate match{tp.matches.length === 1 ? "" : "es"}</div>
                </div>
              </div>

              {tp.matches.length === 0 ? (
                <div className="text-xs text-neutral-500">No candidates found for this product.</div>
              ) : (
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {tp.matches.map((m) => {
                    const checked = cart.isInCart(`trend_match:${m.id}`);
                    return (
                      <div
                        key={m.id}
                        className={`w-36 shrink-0 border rounded-lg overflow-hidden relative ${
                          checked ? "border-neutral-900 ring-1 ring-neutral-900" : "border-neutral-200"
                        }`}
                      >
                        <label className="absolute top-1.5 left-1.5 z-10 bg-white/90 rounded-md p-1 flex items-center gap-1 text-[10px] cursor-pointer">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={selectingId === m.id}
                            onChange={() => toggleMatch(m.id)}
                            className="w-3.5 h-3.5"
                          />
                          Select
                        </label>
                        <span className="absolute top-1.5 right-1.5 z-10 text-[9px] bg-black/70 text-white px-1.5 py-0.5 rounded-full">
                          {SOURCE_LABELS[m.source_type] || m.source_type}
                        </span>
                        <div className="aspect-square bg-neutral-100 overflow-hidden">
                          {m.display_image_url ? (
                            <img src={m.display_image_url} alt={m.display_name || ""} className="object-cover w-full h-full" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-[10px] text-neutral-400">No image</div>
                          )}
                        </div>
                        <div className="p-2">
                          <div className="text-[11px] leading-tight line-clamp-2">{m.display_name || "Untitled"}</div>
                          {m.score != null && (
                            <div className="text-[10px] text-neutral-400 mt-1">match {Math.round(m.score * 100)}%</div>
                          )}
                          {m.display_source_url && (
                            <a
                              href={m.display_source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[10px] text-blue-600 underline mt-1 block truncate"
                              onClick={(e) => e.stopPropagation()}
                            >
                              View source
                            </a>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
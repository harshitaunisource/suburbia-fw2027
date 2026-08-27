import { useEffect, useState } from "react";

export default function Catalogue() {
  const [approvedCount, setApprovedCount] = useState(null);
  const [referenceCount, setReferenceCount] = useState(0);
  const [collectionTitle, setCollectionTitle] = useState("SUBURBIA MEXICO");
  const [seasonTitle, setSeasonTitle] = useState("FW2027 WOMEN'S COLLECTION");
  const [marketDirection, setMarketDirection] = useState("");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/catalogue/products?approved=true")
      .then((r) => r.json())
      .then((rows) => {
        setApprovedCount(rows.length);
        setReferenceCount(rows.filter((r) => r.image_kind === "COMPETITOR_IMAGE").length);
      });
  }, [result]);

  async function generate() {
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/catalogue/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection_title: collectionTitle,
          season_title: seasonTitle,
          market_direction: marketDirection || undefined,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setResult(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Generate FW2027 Catalogue</h1>

      <div className="bg-white border border-neutral-200 rounded-lg p-5 max-w-xl space-y-4">
        <div className="text-sm text-neutral-600">
          {approvedCount === null
            ? "Loading…"
            : approvedCount === 0
            ? "No products yet — go to Suburbia Opportunities, shortlist a concept, and click \"Suggest Products\" to pick a competitor reference for it."
            : `${approvedCount} product(s) will be included in the deck.`}
        </div>

        {referenceCount > 0 && (
          <div className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-md p-3">
            {referenceCount} of these use a competitor's product photo as a placeholder reference (from the
            Suggest Products picker). Those slides are stamped "REFERENCE — competitor sourced" in the deck.
            Swap in your own photo on the Our Products page before sending this externally.
          </div>
        )}

        <div>
          <label className="text-xs text-neutral-500 block mb-1">Collection Title</label>
          <input
            value={collectionTitle}
            onChange={(e) => setCollectionTitle(e.target.value)}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-neutral-500 block mb-1">Season Title</label>
          <input
            value={seasonTitle}
            onChange={(e) => setSeasonTitle(e.target.value)}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-neutral-500 block mb-1">Market Direction Summary (optional)</label>
          <textarea
            value={marketDirection}
            onChange={(e) => setMarketDirection(e.target.value)}
            rows={3}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            placeholder="Short summary of the identified FW2027 opportunity — shown to the buyer, no internal scores or competitor data."
          />
        </div>

        <button
          onClick={generate}
          disabled={generating || !approvedCount}
          className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-50"
        >
          {generating ? "Generating deck…" : "Generate Catalogue (PowerPoint)"}
        </button>

        {error && <div className="text-sm text-red-600">{error}</div>}

        {result && (
          <div className="text-sm bg-green-50 border border-green-200 rounded-md p-3">
            Catalogue generated:{" "}
            <a
              href={`/api/catalogue/download/${result.filename}`}
              className="underline font-medium"
              target="_blank"
              rel="noreferrer"
            >
              {result.filename}
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
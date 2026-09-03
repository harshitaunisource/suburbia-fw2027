import { useEffect, useState } from "react";

function imageSrc(imagePath) {
  if (!imagePath) return null;
  // Normalize backslashes first -- see Products.jsx's imageSrc for why
  // (rows scraped on Windows before a since-fixed backend bug store
  // "storage\products\..." instead of "storage/products/...").
  const normalized = imagePath.replace(/\\/g, "/");
  const idx = normalized.indexOf("storage/");
  return "/" + (idx >= 0 ? normalized.slice(idx) : normalized);
}

export default function OurProducts() {
  const [products, setProducts] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [result, setResult] = useState(null);

  function refresh() {
    fetch("/api/catalogue/products")
      .then((r) => r.json())
      .then(setProducts);
  }

  useEffect(refresh, []);

  async function generate() {
    setGenerating(true);
    setResult(null);
    try {
      const res = await fetch("/api/catalogue/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}), // clear_after defaults to true on the backend
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "PPT generation failed");
      setResult({ ok: true, filename: data.filename });
    } catch (err) {
      setResult({ ok: false, error: String(err.message || err) });
    } finally {
      setGenerating(false);
      refresh();
    }
  }

  async function clearAll() {
    if (!confirm("Remove every product from this batch? This does not delete a generated PPT, just this selection.")) return;
    setClearing(true);
    try {
      await fetch("/api/catalogue/cart", { method: "DELETE" });
    } finally {
      setClearing(false);
      refresh();
    }
  }

  async function toggleApprove(product) {
    await fetch(`/api/catalogue/products/${product.id}/approve?approved=${!product.approved}`, {
      method: "POST",
    });
    refresh();
  }

  async function remove(id) {
    await fetch(`/api/catalogue/products/${id}`, { method: "DELETE" });
    refresh();
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Our Products</h1>
      <p className="text-sm text-neutral-500 mb-6">
        This is the current PPT batch — products you selected from Products, Search Products, or
        Explore Categories. Generating a PPT automatically clears this list so you can start
        selecting the next batch right away.
      </p>

      <div className="flex gap-2 mb-6">
        <button
          onClick={generate}
          disabled={generating || products.length === 0}
          className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-50"
        >
          {generating ? "Generating…" : `Generate PPT (${products.length})`}
        </button>
        <button
          onClick={clearAll}
          disabled={clearing || products.length === 0}
          className="px-4 py-2 border border-neutral-300 rounded-md text-sm disabled:opacity-50"
        >
          {clearing ? "Clearing…" : "Clear All"}
        </button>
      </div>

      {result?.ok && (
        <div className="mb-6 text-sm text-green-700 bg-green-50 rounded-md p-3">
          ✓ Generated {result.filename}. This batch has been cleared — pick your next set of products
          whenever you're ready.
        </div>
      )}
      {result?.ok === false && (
        <div className="mb-6 text-sm text-red-700 bg-red-50 rounded-md p-3">✗ {result.error}</div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {products.map((p) => (
          <div key={p.id} className="bg-white border border-neutral-200 rounded-lg overflow-hidden">
            <div className="aspect-square bg-neutral-100 flex items-center justify-center overflow-hidden relative">
              {p.image_path ? (
                <img src={imageSrc(p.image_path)} alt={p.product_name} className="object-cover w-full h-full" />
              ) : (
                <span className="text-neutral-400 text-xs">No image</span>
              )}
              <span className="absolute top-2 left-2 text-[10px] bg-black/70 text-white px-2 py-0.5 rounded-full">
                {p.image_kind || "OUR_PRODUCT"}
              </span>
            </div>
            <div className="p-3">
              <div className="text-sm font-medium truncate">{p.product_name}</div>
              <div className="text-xs text-neutral-500">{p.category}</div>
              {p.target_price && (
                <div className="text-sm mt-1">
                  {p.currency || "USD"} {p.target_price}
                </div>
              )}

              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => toggleApprove(p)}
                  className={`flex-1 px-2 py-1.5 text-xs rounded-md ${
                    p.approved ? "bg-green-600 text-white" : "bg-neutral-200 text-neutral-700"
                  }`}
                >
                  {p.approved ? "In Deck ✓" : "Excluded — click to include"}
                </button>
                <button onClick={() => remove(p.id)} className="px-2 py-1.5 text-xs rounded-md border border-neutral-300">
                  Remove
                </button>
              </div>
            </div>
          </div>
        ))}
        {products.length === 0 && (
          <div className="text-sm text-neutral-500">
            Nothing selected yet — go to Products, Search Products, or Explore Categories and check
            "Add to PPT" on anything you want in the next deck.
          </div>
        )}
      </div>
    </div>
  );
}
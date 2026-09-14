import { useState } from "react";
import { Link } from "react-router-dom";

/**
 * Shown at the top of any page that lists selectable products (Products,
 * Search Products, Explore Categories). Reflects the same cart every one
 * of those pages shares (see lib/cart.js) -- selecting a product here and
 * then navigating to a different page keeps it selected, and "Our
 * Products" is where the full cart across all pages can be reviewed
 * before generating.
 */
export default function CartBar({ count, onGenerate }) {
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);

  async function handleGenerate() {
    setGenerating(true);
    setResult(null);
    try {
      const data = await onGenerate();
      setResult({ ok: true, filename: data.filename });
    } catch (err) {
      setResult({ ok: false, error: String(err) });
    } finally {
      setGenerating(false);
    }
  }

  // A successful generate clears the cart on the backend (clear_after
  // defaults to true), which drops `count` to 0 right after -- if this
  // bar disappeared whenever count is 0, the success message and
  // download link would vanish in the same instant they appeared,
  // before anyone could actually click "Download PPT". So: hide only
  // when there's truly nothing selected AND nothing to report.
  if (count === 0 && !result) return null;

  return (
    <div className="sticky top-0 z-10 mb-4 bg-neutral-900 text-white rounded-lg px-4 py-3 flex items-center justify-between text-sm">
      <div>
        {count > 0 ? (
          <>
            <strong>{count}</strong> product{count === 1 ? "" : "s"} selected for PPT
          </>
        ) : (
          <span className="text-neutral-300">Batch generated — select products for the next one.</span>
        )}
        {result?.ok && (
          <span className="ml-3 text-green-300">
            ✓ Generated {result.filename} —{" "}
            <a
              href={`/api/catalogue/download/${encodeURIComponent(result.filename)}`}
              download={result.filename}
              className="underline"
            >
              Download PPT
            </a>{" "}
            or review it on{" "}
            <Link to="/our-products" className="underline">
              Our Products
            </Link>
          </span>
        )}
        {result?.ok === false && <span className="ml-3 text-red-300">✗ {result.error}</span>}
      </div>
      <div className="flex gap-2">
        {result && (
          <button
            onClick={() => setResult(null)}
            className="px-3 py-1.5 rounded-md border border-white/30 text-xs"
          >
            Dismiss
          </button>
        )}
        <Link to="/our-products" className="px-3 py-1.5 rounded-md border border-white/30 text-xs">
          Review Selection
        </Link>
        {count > 0 && (
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="px-3 py-1.5 rounded-md bg-white text-neutral-900 text-xs font-medium disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate PPT Now"}
          </button>
        )}
      </div>
    </div>
  );
}
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

const COMMON_CURRENCIES = ["USD", "MXN", "EUR", "GBP", "BRL", "INR"];

export default function AddBrand() {
  const [searchParams] = useSearchParams();
  const preselectedBuyerId = searchParams.get("buyer_id");
  const preselectedRole = searchParams.get("role"); // "BUYER" | "COMPETITOR"

  const [buyers, setBuyers] = useState([]);
  const [tree, setTree] = useState({});
  const [unassignedSources, setUnassignedSources] = useState([]);

  const [entryMode, setEntryMode] = useState("new"); // "new" | "existing_unassigned"
  const [selectedUnassignedId, setSelectedUnassignedId] = useState("");

  const [role, setRole] = useState(preselectedRole === "BUYER" ? "BUYER" : "COMPETITOR");
  const [buyerMode, setBuyerMode] = useState(preselectedBuyerId ? "existing" : "existing");
  const [buyerId, setBuyerId] = useState(preselectedBuyerId || "");
  const [newBuyerName, setNewBuyerName] = useState("");

  const [brand, setBrand] = useState("");
  const [url, setUrl] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [notes, setNotes] = useState("");

  const [itemType, setItemType] = useState("");
  const [category, setCategory] = useState("");
  const [subCategory, setSubCategory] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [categoryMode, setCategoryMode] = useState("existing"); // "existing" | "new"

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { ok, source, error }
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState(null);

  function loadUnassigned() {
    fetch("/api/generic/sources/unassigned").then((r) => r.json()).then(setUnassignedSources);
  }

  useEffect(() => {
    fetch("/api/generic/buyers").then((r) => r.json()).then(setBuyers);
    fetch("/api/generic/hierarchy").then((r) => r.json()).then(setTree);
    loadUnassigned();
  }, []);

  const selectedUnassigned = unassignedSources.find((s) => String(s.id) === String(selectedUnassignedId));

  const itemTypes = useMemo(() => Object.keys(tree).sort(), [tree]);
  const categories = itemType ? Object.keys(tree[itemType] || {}).sort() : [];
  const subCategories = itemType && category ? tree[itemType][category] || [] : [];

  function resetForNextEntry() {
    setBrand("");
    setUrl("");
    setNotes("");
    setResult(null);
    setRunResult(null);
    // Deliberately keep buyer + category selected -- adding several
    // competitors in a row for the same buyer/category is the common
    // case, and re-picking both every time would be tedious.
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    setRunResult(null);
    try {
      // Resolve the buyer first in both modes -- PATCH (used for the
      // "existing unassigned brand" path below) only accepts a real
      // buyer_id, not a buyer_name to find-or-create, so a brand-new
      // buyer name has to become a real buyer row before either path
      // can attach anything to it.
      let resolvedBuyerId = buyerMode === "existing" ? Number(buyerId) : null;
      if (buyerMode === "new") {
        const buyerRes = await fetch("/api/generic/buyers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newBuyerName }),
        });
        const buyerData = await buyerRes.json();
        if (!buyerRes.ok) throw new Error(buyerData.detail || "Couldn't create buyer.");
        resolvedBuyerId = buyerData.id;
      }

      let data;
      if (entryMode === "existing_unassigned") {
        if (!selectedUnassignedId) throw new Error("Pick a brand from the list.");
        const res = await fetch(`/api/generic/sources/${selectedUnassignedId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ buyer_id: resolvedBuyerId, role }),
        });
        data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Couldn't attach this brand.");
      } else {
        const body = {
          brand,
          category_url: url,
          role,
          currency,
          notes: notes || null,
          buyer_id: resolvedBuyerId,
        };
        if (categoryMode === "existing") {
          body.sub_category_id = Number(subCategoryId);
        } else {
          body.item_type = itemType;
          body.category = category;
          body.sub_category = subCategory;
        }
        const res = await fetch("/api/generic/sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      }

      setResult({ ok: true, source: data });
      // Refresh dropdown data in case a new buyer/category was created,
      // or a previously-unassigned brand just got claimed.
      fetch("/api/generic/buyers").then((r) => r.json()).then(setBuyers);
      fetch("/api/generic/hierarchy").then((r) => r.json()).then(setTree);
      loadUnassigned();
      setSelectedUnassignedId("");
    } catch (err) {
      setResult({ ok: false, error: String(err.message || err) });
    } finally {
      setSubmitting(false);
    }
  }

  async function runScraperNow() {
    if (!result?.source) return;
    setRunning(true);
    setRunResult(null);
    try {
      const res = await fetch("/api/generic/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_config_id: result.source.id }),
      });
      setRunResult(await res.json());
    } finally {
      setRunning(false);
    }
  }

  const canSubmit =
    (buyerMode === "existing" ? buyerId : newBuyerName.trim()) &&
    (entryMode === "existing_unassigned"
      ? !!selectedUnassignedId
      : brand.trim() &&
        url.trim() &&
        (categoryMode === "existing" ? subCategoryId : itemType && category && subCategory.trim()));

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-semibold mb-2">Add a Brand</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Type a brand name and a link to its product listing page (e.g. "all sweaters"), tell us what
        category it is, and we'll scrape it. No code changes needed.
      </p>

      {unassignedSources.length > 0 && (
        <div className="flex gap-3 text-xs mb-4">
          <button
            type="button"
            onClick={() => setEntryMode("new")}
            className={`underline-offset-2 ${entryMode === "new" ? "underline font-medium" : "text-neutral-400"}`}
          >
            Enter a new brand
          </button>
          <button
            type="button"
            onClick={() => setEntryMode("existing_unassigned")}
            className={`underline-offset-2 ${entryMode === "existing_unassigned" ? "underline font-medium" : "text-neutral-400"}`}
          >
            Use an already-searched brand ({unassignedSources.length})
          </button>
        </div>
      )}

      {entryMode === "existing_unassigned" && (
        <div className="bg-white border border-neutral-200 rounded-lg p-6 mb-4">
          <label className="block text-sm font-medium mb-2">
            Pick a brand that's already been searched but not yet assigned to a buyer
          </label>
          <select
            value={selectedUnassignedId}
            onChange={(e) => setSelectedUnassignedId(e.target.value)}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
          >
            <option value="">Select a brand…</option>
            {unassignedSources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.brand} — {s.item_type} / {s.category} / {s.sub_category}
              </option>
            ))}
          </select>
          {selectedUnassigned && (
            <div className="text-xs text-neutral-500 mt-2">
              URL:{" "}
              <a href={selectedUnassigned.category_url} target="_blank" rel="noreferrer" className="underline">
                {selectedUnassigned.category_url}
              </a>
            </div>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white border border-neutral-200 rounded-lg p-6 space-y-5">
        {/* What is this brand */}
        <div>
          <label className="block text-sm font-medium mb-2">What is this brand?</label>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" checked={role === "BUYER"} onChange={() => setRole("BUYER")} />
              This is our own brand
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" checked={role === "COMPETITOR"} onChange={() => setRole("COMPETITOR")} />
              This is a competitor
            </label>
          </div>
        </div>

        {/* Buyer picker */}
        <div>
          <label className="block text-sm font-medium mb-2">
            {role === "BUYER" ? "Brand name (this becomes a new or existing buyer)" : "Which buyer is this a competitor of?"}
          </label>
          {role === "COMPETITOR" && buyers.length > 0 && (
            <div className="flex gap-3 text-xs mb-2">
              <button
                type="button"
                onClick={() => setBuyerMode("existing")}
                className={`underline-offset-2 ${buyerMode === "existing" ? "underline font-medium" : "text-neutral-400"}`}
              >
                Pick existing buyer
              </button>
              <button
                type="button"
                onClick={() => setBuyerMode("new")}
                className={`underline-offset-2 ${buyerMode === "new" ? "underline font-medium" : "text-neutral-400"}`}
              >
                Add a new buyer
              </button>
            </div>
          )}
          {buyerMode === "existing" && buyers.length > 0 ? (
            <select
              value={buyerId}
              onChange={(e) => setBuyerId(e.target.value)}
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
            >
              <option value="">Select a buyer…</option>
              {buyers.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={newBuyerName}
              onChange={(e) => setNewBuyerName(e.target.value)}
              placeholder="e.g. Suburbia"
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            />
          )}
        </div>

        {/* Brand + URL -- not needed when attaching an already-searched brand */}
        {entryMode === "new" && (
          <div>
            <label className="block text-sm font-medium mb-2">
              {role === "BUYER" ? "This buyer's own product page URL" : "Competitor brand name"}
            </label>
            {role === "COMPETITOR" && (
              <input
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="e.g. Zara"
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm mb-3"
              />
            )}
            <label className="block text-xs text-neutral-500 mb-1">Website URL (a category/listing page, not a single product)</label>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/women/sweaters"
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            />
          </div>
        )}

        {/* Category picker -- not needed when attaching an already-searched brand, it already has one */}
        {entryMode === "new" && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium">Category</label>
            <div className="flex gap-3 text-xs">
              <button
                type="button"
                onClick={() => setCategoryMode("existing")}
                className={`underline-offset-2 ${categoryMode === "existing" ? "underline font-medium" : "text-neutral-400"}`}
              >
                Pick existing
              </button>
              <button
                type="button"
                onClick={() => setCategoryMode("new")}
                className={`underline-offset-2 ${categoryMode === "new" ? "underline font-medium" : "text-neutral-400"}`}
              >
                Add new category
              </button>
            </div>
          </div>

          {categoryMode === "existing" ? (
            <div className="flex gap-2">
              <select
                value={itemType}
                onChange={(e) => {
                  setItemType(e.target.value);
                  setCategory("");
                  setSubCategoryId("");
                }}
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
              >
                <option value="">Item Type</option>
                {itemTypes.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setSubCategoryId("");
                }}
                disabled={!itemType}
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
              >
                <option value="">Category</option>
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select
                value={subCategoryId}
                onChange={(e) => setSubCategoryId(e.target.value)}
                disabled={!category}
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
              >
                <option value="">Sub Category</option>
                {subCategories.map((s) => (
                  <option key={s.id} value={s.id}>{s.sub_category}</option>
                ))}
              </select>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                value={itemType}
                onChange={(e) => setItemType(e.target.value)}
                placeholder="Item Type (e.g. GARMENT)"
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Category (e.g. APPAREL)"
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
              <input
                value={subCategory}
                onChange={(e) => setSubCategory(e.target.value)}
                placeholder="Sub Category (e.g. Jackets)"
                className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
            </div>
          )}
        </div>
        )}

        {/* Currency + notes -- not applicable when attaching an already-searched brand, it already has these */}
        {entryMode === "new" && (
        <div className="flex gap-4">
          <div className="w-32">
            <label className="block text-sm font-medium mb-2">Currency</label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
            >
              {COMMON_CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium mb-2">Notes (optional)</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Women's, US site"
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            />
          </div>
        </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit || submitting}
          className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-40"
        >
          {submitting ? "Adding…" : "Add Brand"}
        </button>
      </form>

      {result && (
        <div
          className={`mt-4 p-4 rounded-md text-sm ${
            result.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
          }`}
        >
          {result.ok ? (
            <div className="space-y-3">
              <div>
                ✓ Added <strong>{result.source.brand}</strong> ({result.source.role === "BUYER" ? "buyer" : "competitor"})
                under {result.source.item_type} / {result.source.category} / {result.source.sub_category}.
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={runScraperNow}
                  disabled={running}
                  className="px-3 py-1.5 bg-neutral-900 text-white rounded-md text-xs disabled:opacity-50"
                >
                  {running ? "Running…" : "Run Scraper Now"}
                </button>
                <button
                  onClick={resetForNextEntry}
                  className="px-3 py-1.5 border border-neutral-300 rounded-md text-xs text-neutral-700"
                >
                  Add another brand
                </button>
              </div>
              {runResult && (
                <div className={runResult.status === "success" ? "text-green-800" : "text-red-800"}>
                  {runResult.status === "success"
                    ? `✓ ${runResult.products_found} products found.`
                    : `✗ Failed: ${runResult.error_message}`}
                </div>
              )}
            </div>
          ) : (
            <>✗ {result.error}</>
          )}
        </div>
      )}
    </div>
  );
}
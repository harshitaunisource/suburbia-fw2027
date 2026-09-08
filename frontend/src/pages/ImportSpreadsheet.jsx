import { useEffect, useMemo, useState } from "react";

export default function ImportSpreadsheet() {
  const [tree, setTree] = useState({});
  const [buyers, setBuyers] = useState([]);
  const [itemType, setItemType] = useState("");
  const [category, setCategory] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");

  const [brand, setBrand] = useState("");
  const [role, setRole] = useState("COMPETITOR");
  const [buyerId, setBuyerId] = useState("");
  const [gender, setGender] = useState("");
  const [currencyFallback, setCurrencyFallback] = useState("USD");
  const [hasHeaderRow, setHasHeaderRow] = useState(true);

  const [file, setFile] = useState(null);
  const [nameCol, setNameCol] = useState("");
  const [priceCol, setPriceCol] = useState("");
  const [originalPriceCol, setOriginalPriceCol] = useState("");
  const [imageCol, setImageCol] = useState("");
  const [productUrlCol, setProductUrlCol] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    fetch("/api/generic/hierarchy").then((r) => r.json()).then(setTree);
    fetch("/api/generic/buyers").then((r) => r.json()).then(setBuyers);
  }, []);

  const itemTypes = useMemo(() => Object.keys(tree).sort(), [tree]);
  const categories = itemType ? Object.keys(tree[itemType] || {}).sort() : [];
  const subCategories = itemType && category ? tree[itemType][category] || [] : [];

  const canSubmit = file && brand.trim() && subCategoryId && nameCol;

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("brand", brand);
      form.append("sub_category_id", subCategoryId);
      form.append("role", role);
      if (gender) form.append("gender", gender);
      if (buyerId) form.append("buyer_id", buyerId);
      form.append("currency_fallback", currencyFallback);
      form.append("has_header_row", hasHeaderRow);
      form.append("name_col", nameCol);
      if (priceCol) form.append("price_col", priceCol);
      if (originalPriceCol) form.append("original_price_col", originalPriceCol);
      if (imageCol) form.append("image_col", imageCol);
      if (productUrlCol) form.append("product_url_col", productUrlCol);

      const res = await fetch("/api/generic/products/import-spreadsheet", {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Import failed.");
      setResult({ ok: true, ...data });
    } catch (err) {
      setResult({ ok: false, error: String(err.message || err) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-semibold mb-2">Import Spreadsheet</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Upload a CSV or XLSX export (e.g. from the "Web Scraper" Chrome extension) and tell us
        which column holds what — we'll turn each row into a product. No product-page link needed;
        we'll use the image link as a fallback if you don't have one.
      </p>

      <form onSubmit={handleSubmit} className="bg-white border border-neutral-200 rounded-lg p-6 space-y-5">
        <div>
          <label className="block text-sm font-medium mb-2">File (.csv or .xlsx)</label>
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="w-full text-sm"
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="header-row"
            checked={hasHeaderRow}
            onChange={(e) => setHasHeaderRow(e.target.checked)}
          />
          <label htmlFor="header-row" className="text-sm">First row is a header row (skip it)</label>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Brand Name</label>
          <input
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            placeholder="e.g. H&M"
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          />
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-2">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
            >
              <option value="COMPETITOR">Competitor</option>
              <option value="BUYER">Buyer (our own brand)</option>
            </select>
          </div>
          {role === "COMPETITOR" && (
            <div className="flex-1">
              <label className="block text-sm font-medium mb-2">Competitor of (buyer)</label>
              <select
                value={buyerId}
                onChange={(e) => setBuyerId(e.target.value)}
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
              >
                <option value="">Not assigned yet</option>
                {buyers.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Gender / product line</label>
          <select
            value={gender}
            onChange={(e) => setGender(e.target.value)}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
          >
            <option value="">Not specified</option>
            <option value="WOMENS">Women's</option>
            <option value="MENS">Men's</option>
            <option value="UNISEX">Unisex</option>
            <option value="KIDS">Kids</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Category</label>
          <div className="flex gap-2">
            <select
              value={itemType}
              onChange={(e) => { setItemType(e.target.value); setCategory(""); setSubCategoryId(""); }}
              className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
            >
              <option value="">Item Type</option>
              {itemTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select
              value={category}
              onChange={(e) => { setCategory(e.target.value); setSubCategoryId(""); }}
              disabled={!itemType}
              className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
            >
              <option value="">Category</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select
              value={subCategoryId}
              onChange={(e) => setSubCategoryId(e.target.value)}
              disabled={!category}
              className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white disabled:opacity-50"
            >
              <option value="">Sub Category</option>
              {subCategories.map((s) => <option key={s.id} value={s.id}>{s.sub_category}</option>)}
            </select>
          </div>
        </div>

        <div className="border-t border-neutral-200 pt-4">
          <p className="text-sm font-medium mb-3">
            Which column is which? Count columns starting at 1 (including any ID/order columns the
            extension adds at the start).
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-neutral-500 mb-1">Name column *</label>
              <input
                type="number" min="1" value={nameCol}
                onChange={(e) => setNameCol(e.target.value)}
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-neutral-500 mb-1">Image column</label>
              <input
                type="number" min="1" value={imageCol}
                onChange={(e) => setImageCol(e.target.value)}
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-neutral-500 mb-1">Price column</label>
              <input
                type="number" min="1" value={priceCol}
                onChange={(e) => setPriceCol(e.target.value)}
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-neutral-500 mb-1">Original price column (optional)</label>
              <input
                type="number" min="1" value={originalPriceCol}
                onChange={(e) => setOriginalPriceCol(e.target.value)}
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-neutral-500 mb-1">
                Product page URL column (optional — falls back to the image link if left blank)
              </label>
              <input
                type="number" min="1" value={productUrlCol}
                onChange={(e) => setProductUrlCol(e.target.value)}
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Currency (fallback only)</label>
          <select
            value={currencyFallback}
            onChange={(e) => setCurrencyFallback(e.target.value)}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
          >
            {["USD", "MXN", "GBP", "EUR", "BOB", "INR"].map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <p className="text-xs text-neutral-400 mt-1">
            We read the real currency from each row's price text and the sheet's own source URL
            automatically (handles Mexican $ vs. US $ correctly). This is only used if a row gives
            no usable signal at all.
          </p>
        </div>

        <button
          type="submit"
          disabled={!canSubmit || submitting}
          className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-40"
        >
          {submitting ? "Importing…" : "Import"}
        </button>
      </form>

      {result && (
        <div
          className={`mt-4 p-4 rounded-md text-sm ${
            result.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
          }`}
        >
          {result.ok ? (
            <div>
              <div>✓ Imported {result.inserted} product(s), skipped {result.skipped} already-present.</div>
              {result.error_count > 0 && (
                <div className="mt-2 text-amber-700">
                  {result.error_count} row(s) had a problem and were skipped:
                  <ul className="list-disc list-inside mt-1">
                    {result.errors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
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
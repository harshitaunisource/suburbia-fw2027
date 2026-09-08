import { useEffect, useMemo, useRef, useState } from "react";
import CartBar from "../components/CartBar";
import { cartItemFromGenericProduct, useCart } from "../lib/cart";

function imageSrc(p) {
  // Prefer the ORIGINAL remote image_url (the brand's own CDN link) over
  // the locally-downloaded copy. A locally-downloaded file only exists
  // on whichever machine/container actually ran the scrape -- on a
  // stateless deployment (Railway) with a shared external database,
  // that's almost never the same machine serving the request, so
  // local_image_path routinely 404s in production even though the row
  // itself is visible everywhere. image_url is a normal CDN link and
  // displays fine hotlinked in a browser <img> tag regardless of which
  // server rendered the page -- that's the whole reason the local-
  // download step exists at all (some sites block a Python SCRIPT from
  // downloading, not a browser from displaying), not a signal that the
  // local copy is more reliable to show.
  if (p.image_url) return p.image_url;
  if (p.local_image_path) {
    const normalized = p.local_image_path.replace(/\\/g, "/");
    const idx = normalized.indexOf("storage/");
    return "/" + (idx >= 0 ? normalized.slice(idx) : normalized);
  }
  return null;
}

export default function SearchProducts() {
  const [tree, setTree] = useState({});
  const [itemType, setItemType] = useState("");
  const [category, setCategory] = useState("");
  const [subCategory, setSubCategory] = useState("");
  const [subCategoryId, setSubCategoryId] = useState("");
  const [categoryMode, setCategoryMode] = useState("existing"); // "existing" | "new"

  const [brand, setBrand] = useState("");
  const [url, setUrl] = useState("");
  const [gender, setGender] = useState(""); // "" | "WOMENS" | "MENS" | "UNISEX" | "KIDS"
  const [existingSource, setExistingSource] = useState(null); // a matching source for this brand+category+gender, if any
  // Defaults to reusing the existing source when one is found, but this
  // can still be overridden manually. Before the `gender` field existed,
  // this match was on (brand, sub_category) ALONE -- so "Textilon" +
  // Pajamas always matched the same single source no matter which
  // gender was actually being searched, meaning a men's search would
  // silently reuse (and scrape into) the already-registered women's
  // source. Matching on gender too is the actual fix for that.
  const [useExisting, setUseExisting] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pdpPattern, setPdpPattern] = useState("");

  const [searching, setSearching] = useState(false);
  // Ticking display clock -- separate from elapsedMs (which is only
  // set once the scrape finishes). This is what makes the "how long
  // has it been running" text actually update live while polling,
  // instead of sitting frozen on one static sentence the whole time.
  const searchStartedAtRef = useRef(null);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  useEffect(() => {
    if (!searching) return;
    const interval = setInterval(() => {
      if (searchStartedAtRef.current) {
        setLiveElapsedMs(Date.now() - searchStartedAtRef.current);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [searching]);
  const [error, setError] = useState(null);
  const [products, setProducts] = useState([]);
  const [lastRun, setLastRun] = useState(null);
  const [elapsedMs, setElapsedMs] = useState(null);

  // "Browse the real site yourself, paste one link" path -- for sites
  // whose category page won't reliably render its product grid for an
  // automated browser (confirmed live on Textilon: the grid stays
  // empty even after a long wait). Scrapes exactly the one pasted URL.
  const [singleUrl, setSingleUrl] = useState("");
  const [addingSingle, setAddingSingle] = useState(false);
  const [singleError, setSingleError] = useState(null);
  const cart = useCart();

  useEffect(() => {
    fetch("/api/generic/hierarchy").then((r) => r.json()).then(setTree);
  }, []);

  const itemTypes = useMemo(() => Object.keys(tree).sort(), [tree]);
  const categories = itemType ? Object.keys(tree[itemType] || {}).sort() : [];
  const subCategories = itemType && category ? tree[itemType][category] || [] : [];

  // Whenever brand + sub-category + gender are all chosen, check
  // whether this exact combination has already been searched. Matching
  // on gender too (not just brand + sub-category) is what lets a
  // brand's Men's and Women's lines in the same category be tracked as
  // two distinct sources instead of one merging into the other.
  useEffect(() => {
    setExistingSource(null);
    setUseExisting(true);
    if (!brand.trim() || !subCategoryId) return;
    const params = new URLSearchParams({ sub_category_id: subCategoryId });
    fetch(`/api/generic/sources?${params.toString()}`)
      .then((r) => r.json())
      .then((sources) => {
        const match = sources.find(
          (s) =>
            s.brand.toLowerCase() === brand.trim().toLowerCase() &&
            (s.gender || "") === (gender || "")
        );
        if (match) setExistingSource(match);
      });
  }, [brand, subCategoryId, gender]);

  const needsUrl = !existingSource || !useExisting;

  const canSearch =
    brand.trim() &&
    (categoryMode === "existing" ? subCategoryId : itemType && category && subCategory.trim()) &&
    (!needsUrl || url.trim());

  async function handleSearch(e) {
    e.preventDefault();
    setSearching(true);
    setError(null);
    setProducts([]);
    setLastRun(null);
    setElapsedMs(null);
    const startedAt = Date.now();
    searchStartedAtRef.current = startedAt;
    setLiveElapsedMs(0);
    try {
      let source = existingSource && useExisting ? existingSource : null;
      if (!source) {
        const body = {
          brand,
          category_url: url,
          gender: gender || null,
          // No buyer/role -- Search Products is deliberately standalone.
          // Brand Setup's "add competitor/buyer" flow can attach this
          // exact source to a real buyer later without duplicating it.
        };
        if (pdpPattern.trim()) body.pdp_link_pattern = pdpPattern.trim();
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
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Couldn't create this source.");
        source = data;
        setExistingSource(data);
        fetch("/api/generic/hierarchy").then((r) => r.json()).then(setTree);
      }

      const scrapeRes = await fetch("/api/generic/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_config_id: source.id }),
      });
      let run = await scrapeRes.json();
      if (!scrapeRes.ok) throw new Error(run.detail || "Couldn't start the scrape.");
      setLastRun(run);

      // The scrape now runs in the BACKGROUND on the server -- this
      // POST returns almost instantly with status "running", not the
      // finished result. Poll until it's actually done instead of
      // trusting the immediate response. This is what makes a slow
      // site (many product pages) survive: no single request stays
      // open long enough for a platform proxy to kill it (confirmed
      // live: GymShark and Walmart both got killed by Vercel's ~120s
      // proxy timeout under the old one-long-request design).
      while (run.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const pollRes = await fetch(`/api/generic/scrape-runs/${run.id}`);
        if (!pollRes.ok) throw new Error("Lost track of the scrape run -- try searching again.");
        run = await pollRes.json();
        setLastRun(run);
      }
      setElapsedMs(Date.now() - startedAt);

      // Backend reports a failed run as a normal 200 response with
      // status: "failed" and a real error_message (a failed run is
      // still a valid, complete result, not a server error) -- so the
      // check here is on run.status, not on any HTTP status code.
      if (run.status === "failed") {
        throw new Error(run.error_message || "Scrape failed.");
      }

      const prodParams = new URLSearchParams({ sub_category_id: source.sub_category_id, brand: source.brand });
      if (source.gender) prodParams.set("gender", source.gender);
      const prodRes = await fetch(`/api/generic/products?${prodParams.toString()}`);
      setProducts(await prodRes.json());
    } catch (err) {
      setElapsedMs(Date.now() - startedAt);
      setError(String(err.message || err));
    } finally {
      setSearching(false);
    }
  }

  async function handleAddSingleUrl(e) {
    e.preventDefault();
    if (!existingSource) {
      setSingleError("Search (or create) a source above first, so this product has a brand/category/gender to attach to.");
      return;
    }
    setAddingSingle(true);
    setSingleError(null);
    try {
      const res = await fetch("/api/generic/products/add-by-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_config_id: existingSource.id, product_url: singleUrl.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Couldn't add this product.");
      setProducts((prev) => (prev.some((p) => p.id === data.id) ? prev : [data, ...prev]));
      setSingleUrl("");
    } catch (err) {
      setSingleError(String(err.message || err));
    } finally {
      setAddingSingle(false);
    }
  }

  async function generatePPT() {
    const res = await fetch("/api/catalogue/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "PPT generation failed");
    cart.refresh();
    return data;
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Search Products</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Type a company name, tell us the category, and we'll pull its products. If this brand's
        already been searched for this category before, we'll offer to reuse that URL instead of
        asking for it again.
      </p>

      <CartBar count={cart.count} onGenerate={generatePPT} />

      <form onSubmit={handleSearch} className="bg-white border border-neutral-200 rounded-lg p-6 space-y-5 mb-6">
        <div>
          <label className="block text-sm font-medium mb-2">Company / Brand Name</label>
          <input
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            placeholder="e.g. Mango"
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          />
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
          <p className="text-xs text-neutral-400 mt-1">
            If this brand has separate men's/women's/kids listings in the same category, set this
            so each is tracked as its own source instead of one overwriting the other.
          </p>
        </div>

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

        <div>
          <label className="block text-sm font-medium mb-2">Website URL</label>
          {existingSource && useExisting ? (
            <div className="text-xs text-green-700 bg-green-50 rounded-md px-3 py-2">
              ✓ "{existingSource.brand}" was already searched for this category — using{" "}
              <a href={existingSource.category_url} target="_blank" rel="noreferrer" className="underline">
                {existingSource.category_url}
              </a>
              .{" "}
              <button
                type="button"
                onClick={() => setUseExisting(false)}
                className="underline font-medium"
              >
                This isn't the right listing — use a different URL instead
              </button>
            </div>
          ) : (
            <>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/women/sweaters"
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              />
              {existingSource && (
                <button
                  type="button"
                  onClick={() => setUseExisting(true)}
                  className="text-xs underline text-neutral-500 mt-1"
                >
                  Actually, reuse the existing "{existingSource.brand}" URL instead
                </button>
              )}
            </>
          )}
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-xs underline text-neutral-500"
          >
            {showAdvanced ? "Hide" : "Show"} advanced options
          </button>
          {showAdvanced && (
            <div className="mt-2">
              <label className="block text-xs text-neutral-500 mb-1">
                Product-link pattern (optional) — only needed if a first search finds 0 products.
                After searching, a debug HTML file is saved next to your backend (named like
                generic_&lt;brand&gt;_&lt;category&gt;_debug.html) — open it, find how the site's real
                product links look, and enter a regex matching them here to try again.
              </label>
              <input
                value={pdpPattern}
                onChange={(e) => setPdpPattern(e.target.value)}
                placeholder="e.g. /product/[a-z0-9-]+"
                className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm font-mono"
              />
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={!canSearch || searching}
          className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-40"
        >
          {searching ? "Searching…" : "Search Products"}
        </button>

        {searching && (
          <div className="text-xs text-neutral-500 space-y-1">
            <div>
              {lastRun?.current_step || "Starting…"}
              {" — "}
              {Math.floor(liveElapsedMs / 1000)}s elapsed
              {lastRun?.candidates_total ? ` · ${lastRun.candidates_total} candidate(s) found` : ""}
            </div>
            <div className="text-neutral-400">
              Runs in the background, up to ~4 minutes for a large category before it stops itself
              automatically. Feel free to leave this tab open — this updates every couple of
              seconds on its own.
            </div>
          </div>
        )}

        {error && (
          <div className="text-sm text-red-700 bg-red-50 rounded-md p-3">
            ✗ {error}
            {elapsedMs != null && <span className="text-red-400"> (after {(elapsedMs / 1000).toFixed(1)}s)</span>}
          </div>
        )}
        {lastRun && lastRun.status === "success" && lastRun.products_found > 0 && (
          <div className="text-sm text-green-700">
            ✓ Found {lastRun.products_found} product{lastRun.products_found === 1 ? "" : "s"}
            {elapsedMs != null && ` in ${(elapsedMs / 1000).toFixed(1)}s`}.
            {products.length > 0 && (
              <span className="block text-neutral-600 mt-1">
                {products.slice(0, 8).map((p) => p.product_name).join(", ")}
                {products.length > 8 ? `, +${products.length - 8} more` : ""}
              </span>
            )}
          </div>
        )}
        {lastRun && lastRun.status === "success" && lastRun.products_found === 0 && (
          <div className="text-sm text-amber-700 bg-amber-50 rounded-md p-3">
            The page loaded fine, but nothing matched as a product
            {elapsedMs != null && ` (took ${(elapsedMs / 1000).toFixed(1)}s)`}. This site's link
            pattern is probably different from the default guess — open "Show advanced options"
            above, check the debug HTML file it just saved, and try again with a specific link
            pattern.
          </div>
        )}
      </form>

      {existingSource && (
        <form
          onSubmit={handleAddSingleUrl}
          className="bg-white border border-neutral-200 rounded-lg p-4 mb-6 flex items-end gap-3"
        >
          <div className="flex-1">
            <label className="block text-sm font-medium mb-2">
              Add one product by link (for sites where auto-search finds nothing)
            </label>
            <input
              value={singleUrl}
              onChange={(e) => setSingleUrl(e.target.value)}
              placeholder="Paste a single product page URL you found by browsing the site yourself"
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            />
            <p className="text-xs text-neutral-400 mt-1">
              Open "{existingSource.brand}"'s site in a normal browser tab, click into one product,
              copy its URL, and paste it here -- this scrapes just that page instead of relying on
              automatic discovery across the whole category.
            </p>
          </div>
          <button
            type="submit"
            disabled={!singleUrl.trim() || addingSingle}
            className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-40 shrink-0"
          >
            {addingSingle ? "Adding…" : "Add Product"}
          </button>
        </form>
      )}
      {singleError && (
        <div className="text-sm text-red-700 bg-red-50 rounded-md p-3 mb-6">✗ {singleError}</div>
      )}

      {products.length > 0 && (
        <div className="grid grid-cols-4 gap-4">
          {products.map((p) => {
            const src = imageSrc(p);
            const item = cartItemFromGenericProduct(p);
            const checked = cart.isInCart(item.source_ref);
            return (
              <div
                key={p.id}
                className={`bg-white border rounded-lg overflow-hidden relative ${
                  checked ? "border-neutral-900 ring-1 ring-neutral-900" : "border-neutral-200"
                }`}
              >
                <label className="absolute top-2 left-2 z-10 bg-white/90 rounded-md p-1 flex items-center gap-1 text-[10px] cursor-pointer">
                  <input type="checkbox" checked={checked} onChange={() => cart.toggle(item)} className="w-3.5 h-3.5" />
                  PPT
                </label>
                <a href={p.product_url} target="_blank" rel="noreferrer">
                  <div className="aspect-square bg-neutral-100 flex items-center justify-center overflow-hidden">
                    {src ? (
                      <img src={src} alt={p.product_name} className="object-cover w-full h-full" />
                    ) : (
                      <span className="text-neutral-400 text-xs">No image</span>
                    )}
                  </div>
                  <div className="p-3">
                    <div className="text-xs text-neutral-500">{p.brand}</div>
                    <div className="text-sm font-medium truncate">{p.product_name}</div>
                    <div className="text-sm mt-1">{p.mrp ? `${p.currency} ${p.mrp}` : "Price unknown"}</div>
                  </div>
                </a>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
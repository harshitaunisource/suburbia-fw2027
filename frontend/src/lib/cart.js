import { useCallback, useEffect, useState } from "react";

/**
 * Backs the "Add to PPT" checkbox shown on Products / Search Products /
 * Explore Categories. The cart itself lives entirely on the backend (see
 * /api/catalogue/cart/*) as CatalogueProduct rows with a source_ref --
 * this hook just hydrates which refs are currently in it, and exposes a
 * toggle() that flips one and updates local state to match.
 *
 * Storing it server-side (instead of frontend-only state) is what makes
 * it a real "running cart across pages": navigating to a different page,
 * or even refreshing the browser, doesn't lose the selection.
 */
export function useCart() {
  const [refs, setRefs] = useState(new Set());
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() => {
    fetch("/api/catalogue/cart/refs")
      .then((r) => r.json())
      .then((list) => setRefs(new Set(list)))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const isInCart = useCallback((sourceRef) => refs.has(sourceRef), [refs]);

  const toggle = useCallback(async (item) => {
    // item: { source_ref, product_name, category, description, image_path,
    //         colorways, fabric, size_range, target_price, currency, notes }
    //
    // Flips the checkbox state immediately (optimistic update) instead of
    // waiting on the round-trip to /cart/toggle -- previously the checkbox
    // only visually changed once the fetch resolved, which reads as a
    // multi-second lag on anything but a very fast connection. If the
    // request turns out to fail, the optimistic flip is rolled back below.
    const wasInCart = refs.has(item.source_ref);
    setRefs((prev) => {
      const next = new Set(prev);
      if (wasInCart) next.delete(item.source_ref);
      else next.add(item.source_ref);
      return next;
    });

    try {
      const res = await fetch("/api/catalogue/cart/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update cart");
      // Reconcile with what the server actually did, in case it disagrees
      // with our optimistic guess (e.g. two tabs toggling the same item).
      setRefs((prev) => {
        const next = new Set(prev);
        if (data.in_cart === false) next.delete(item.source_ref);
        else next.add(item.source_ref);
        return next;
      });
      return data;
    } catch (err) {
      // Roll back the optimistic flip -- the server never actually
      // recorded the change. Surfaced to the console (not just silently
      // reverted) so a real failure here is visible instead of looking
      // identical to "nothing happened."
      console.error("Failed to update PPT cart for", item.source_ref, err);
      setRefs((prev) => {
        const next = new Set(prev);
        if (wasInCart) next.add(item.source_ref);
        else next.delete(item.source_ref);
        return next;
      });
      throw err;
    }
  }, [refs]);

  return { refs, count: refs.size, loaded, isInCart, toggle, refresh };
}

/** Picks the best available image reference for a scraped product to
 * carry into the cart/catalogue. Prefers the remote image_url over the
 * locally-downloaded copy for the same reason Products.jsx's imageSrc()
 * does (see that file): local_image_path only exists on whichever
 * machine/container ran the scrape, which on a stateless deployment is
 * almost never the one serving this request -- or the one generating the
 * PPT later. Stored as-is (a full URL, or a legacy local path); whatever
 * reads it back (OurProducts.jsx, the PPT generator) is responsible for
 * telling the two apart. */
function bestImageRef(p) {
  return p.image_url || p.local_image_path || null;
}

/** Builds the payload toggle() needs from a classic Products-table row. */
export function cartItemFromProduct(p) {
  return {
    source_ref: `product:${p.id}`,
    product_name: p.product_name,
    category: p.category || null,
    description: p.description || null,
    image_path: bestImageRef(p),
    colorways: p.colors || null,
    fabric: p.material || null,
    size_range: p.sizes || null,
    target_price: p.mrp ?? p.price ?? null,
    currency: p.currency || "USD",
    notes: p.source ? `Reference product from ${p.source}${p.brand ? ` (${p.brand})` : ""}. Original: ${p.product_url}` : null,
  };
}

/** Builds the payload toggle() needs from a GenericProduct row (Search
 * Products / Explore Categories). */
export function cartItemFromGenericProduct(p) {
  return {
    source_ref: `generic_product:${p.id}`,
    product_name: p.product_name,
    category: p.category || null,
    description: p.description || null,
    image_path: bestImageRef(p),
    colorways: p.color || null,
    fabric: p.material || null,
    size_range: null,
    target_price: p.mrp ?? p.price ?? null,
    currency: p.currency || "USD",
    notes: p.brand ? `Reference product from ${p.brand}. Original: ${p.product_url}` : null,
  };
}
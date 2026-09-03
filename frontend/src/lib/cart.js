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
    const res = await fetch("/api/catalogue/cart/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item),
    });
    const data = await res.json();
    setRefs((prev) => {
      const next = new Set(prev);
      if (data.in_cart === false) {
        next.delete(item.source_ref);
      } else {
        next.add(item.source_ref);
      }
      return next;
    });
    return data;
  }, []);

  return { refs, count: refs.size, loaded, isInCart, toggle, refresh };
}

/** Builds the payload toggle() needs from a classic Products-table row. */
export function cartItemFromProduct(p) {
  return {
    source_ref: `product:${p.id}`,
    product_name: p.product_name,
    category: p.category || null,
    description: p.description || null,
    image_path: p.local_image_path || null,
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
    image_path: p.local_image_path || null,
    colorways: p.color || null,
    fabric: p.material || null,
    size_range: null,
    target_price: p.mrp ?? p.price ?? null,
    currency: p.currency || "USD",
    notes: p.brand ? `Reference product from ${p.brand}. Original: ${p.product_url}` : null,
  };
}
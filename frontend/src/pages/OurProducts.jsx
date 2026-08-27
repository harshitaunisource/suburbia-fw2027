import { useEffect, useState } from "react";

const EMPTY = {
  product_name: "",
  our_product_code: "",
  category: "sweaters",
  description: "",
  colorways: "",
  fabric: "",
  size_range: "",
  target_price: "",
  moq: "",
  lead_time: "",
  packaging: "",
  notes: "",
};

export default function OurProducts() {
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  function refresh() {
    fetch("/api/catalogue/products")
      .then((r) => r.json())
      .then(setProducts);
  }

  useEffect(refresh, []);

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        target_price: form.target_price ? parseFloat(form.target_price) : null,
        moq: form.moq ? parseInt(form.moq, 10) : null,
      };
      await fetch("/api/catalogue/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setForm(EMPTY);
    } finally {
      setSaving(false);
      refresh();
    }
  }

  async function uploadImage(productId, file) {
    const body = new FormData();
    body.append("file", file);
    await fetch(`/api/catalogue/products/${productId}/image?kind=OUR_PRODUCT`, {
      method: "POST",
      body,
    });
    refresh();
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
      <h1 className="text-2xl font-semibold mb-6">Add Our Product</h1>

      <form onSubmit={submit} className="bg-white border border-neutral-200 rounded-lg p-5 mb-8 grid grid-cols-3 gap-3">
        {[
          ["product_name", "Product Name", true],
          ["our_product_code", "Product Code"],
          ["colorways", "Colorways (comma separated)"],
          ["fabric", "Fabric"],
          ["size_range", "Size Range (e.g. XS-XL)"],
          ["target_price", "Target Price"],
          ["moq", "MOQ"],
          ["lead_time", "Lead Time"],
          ["packaging", "Packaging"],
        ].map(([key, label, required]) => (
          <div key={key}>
            <label className="text-xs text-neutral-500 block mb-1">{label}</label>
            <input
              value={form[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              required={!!required}
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            />
          </div>
        ))}

        <div>
          <label className="text-xs text-neutral-500 block mb-1">Category</label>
          <select
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
          >
            <option value="sweaters">Sweaters</option>
            <option value="blouses">Blouses</option>
          </select>
        </div>

        <div className="col-span-3">
          <label className="text-xs text-neutral-500 block mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            rows={2}
          />
        </div>
        <div className="col-span-3">
          <label className="text-xs text-neutral-500 block mb-1">Notes</label>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            rows={2}
          />
        </div>

        <div className="col-span-3">
          <button disabled={saving} className="px-4 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-50">
            {saving ? "Saving…" : "Add Product"}
          </button>
        </div>
      </form>

      <h2 className="text-lg font-semibold mb-4">Our Products</h2>
      <div className="grid grid-cols-3 gap-4">
        {products.map((p) => (
          <div key={p.id} className="bg-white border border-neutral-200 rounded-lg overflow-hidden">
            <div className="aspect-square bg-neutral-100 flex items-center justify-center overflow-hidden relative">
              {p.image_path ? (
                <img src={`/storage/${p.image_path.split("storage/")[1] || p.image_path}`} alt={p.product_name} className="object-cover w-full h-full" />
              ) : (
                <span className="text-neutral-400 text-xs">No image — upload below</span>
              )}
              <span className="absolute top-2 left-2 text-[10px] bg-black/70 text-white px-2 py-0.5 rounded-full">
                {p.image_kind || "OUR_PRODUCT"}
              </span>
            </div>
            <div className="p-3">
              <div className="text-sm font-medium truncate">{p.product_name}</div>
              <div className="text-xs text-neutral-500">{p.our_product_code}</div>
              {p.target_price && <div className="text-sm mt-1">${p.target_price}</div>}

              <input
                type="file"
                accept="image/*"
                onChange={(e) => e.target.files[0] && uploadImage(p.id, e.target.files[0])}
                className="text-xs mt-2 w-full"
              />

              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => toggleApprove(p)}
                  className={`flex-1 px-2 py-1.5 text-xs rounded-md ${
                    p.approved ? "bg-green-600 text-white" : "bg-neutral-200 text-neutral-700"
                  }`}
                >
                  {p.approved ? "Approved ✓" : "Approve for Catalogue"}
                </button>
                <button onClick={() => remove(p.id)} className="px-2 py-1.5 text-xs rounded-md border border-neutral-300">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
        {products.length === 0 && <div className="text-sm text-neutral-500">No products added yet.</div>}
      </div>
    </div>
  );
}

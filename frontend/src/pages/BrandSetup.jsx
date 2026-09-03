import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

export default function BrandSetup() {
  const [buyers, setBuyers] = useState([]);
  const [sourcesByBuyer, setSourcesByBuyer] = useState({}); // buyerId -> sources[]
  const [expanded, setExpanded] = useState({}); // buyerId -> bool
  const [running, setRunning] = useState(null); // sourceId
  const [lastRun, setLastRun] = useState(null); // { sourceId, ...run }

  const [showNewBuyer, setShowNewBuyer] = useState(false);
  const [newBuyerName, setNewBuyerName] = useState("");
  const [newBuyerNotes, setNewBuyerNotes] = useState("");
  const [creatingBuyer, setCreatingBuyer] = useState(false);

  const [editingId, setEditingId] = useState(null);
  const [editUrl, setEditUrl] = useState("");

  function refreshBuyers() {
    fetch("/api/generic/buyers")
      .then((r) => r.json())
      .then(setBuyers);
  }

  useEffect(refreshBuyers, []);

  function loadSources(buyerId) {
    fetch(`/api/generic/buyers/${buyerId}/sources`)
      .then((r) => r.json())
      .then((data) => setSourcesByBuyer((prev) => ({ ...prev, [buyerId]: data })));
  }

  function toggleExpand(buyerId) {
    const next = !expanded[buyerId];
    setExpanded((prev) => ({ ...prev, [buyerId]: next }));
    if (next && !sourcesByBuyer[buyerId]) loadSources(buyerId);
  }

  async function createBuyer(e) {
    e.preventDefault();
    setCreatingBuyer(true);
    try {
      await fetch("/api/generic/buyers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newBuyerName, notes: newBuyerNotes || null }),
      });
      setNewBuyerName("");
      setNewBuyerNotes("");
      setShowNewBuyer(false);
      refreshBuyers();
    } finally {
      setCreatingBuyer(false);
    }
  }

  async function runScraper(sourceId, buyerId) {
    setRunning(sourceId);
    setLastRun(null);
    try {
      const res = await fetch("/api/generic/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_config_id: sourceId }),
      });
      const data = await res.json();
      setLastRun({ sourceId, ...data });
    } finally {
      setRunning(null);
      loadSources(buyerId);
    }
  }

  async function deleteSource(sourceId, buyerId) {
    if (!confirm("Remove this source?")) return;
    const res = await fetch(`/api/generic/sources/${sourceId}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.detail || "Couldn't remove this source.");
      return;
    }
    loadSources(buyerId);
  }

  function startEdit(source) {
    setEditingId(source.id);
    setEditUrl(source.category_url);
  }

  async function saveEdit(source, buyerId) {
    await fetch(`/api/generic/sources/${source.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category_url: editUrl }),
    });
    setEditingId(null);
    loadSources(buyerId);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-semibold">Brand Setup</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowNewBuyer((v) => !v)}
            className="px-3 py-1.5 border border-neutral-300 rounded-md text-xs text-neutral-700"
          >
            + New Buyer
          </button>
          <Link
            to="/add-brand"
            className="px-3 py-1.5 bg-neutral-900 text-white rounded-md text-xs"
          >
            + Add Brand
          </Link>
        </div>
      </div>
      <p className="text-sm text-neutral-500 mb-6">
        Every buyer (your own brands) and their tracked competitors, all in one place. Click a buyer to
        see and manage its sources.
      </p>

      {showNewBuyer && (
        <form
          onSubmit={createBuyer}
          className="bg-white border border-neutral-200 rounded-lg p-4 mb-6 flex gap-3 items-end"
        >
          <div className="flex-1">
            <label className="block text-xs text-neutral-500 mb-1">Buyer name</label>
            <input
              value={newBuyerName}
              onChange={(e) => setNewBuyerName(e.target.value)}
              placeholder="e.g. Suburbia"
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              required
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-neutral-500 mb-1">Notes (optional)</label>
            <input
              value={newBuyerNotes}
              onChange={(e) => setNewBuyerNotes(e.target.value)}
              className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={creatingBuyer || !newBuyerName.trim()}
            className="px-3 py-2 bg-neutral-900 text-white rounded-md text-sm disabled:opacity-50"
          >
            {creatingBuyer ? "Adding…" : "Add Buyer"}
          </button>
        </form>
      )}

      <div className="space-y-4">
        {buyers.map((buyer) => {
          const sources = sourcesByBuyer[buyer.id] || [];
          const ownSources = sources.filter((s) => s.role === "BUYER");
          const competitors = sources.filter((s) => s.role === "COMPETITOR");
          const isOpen = !!expanded[buyer.id];
          return (
            <div key={buyer.id} className="bg-white border border-neutral-200 rounded-lg overflow-hidden">
              <button
                onClick={() => toggleExpand(buyer.id)}
                className="w-full flex items-center justify-between p-4 text-left hover:bg-neutral-50"
              >
                <div>
                  <div className="font-medium">{buyer.name}</div>
                  {buyer.notes && <div className="text-xs text-neutral-500">{buyer.notes}</div>}
                </div>
                <span className="text-neutral-400 text-sm">{isOpen ? "▲" : "▼"}</span>
              </button>

              {isOpen && (
                <div className="border-t border-neutral-200 p-4">
                  <div className="flex justify-end mb-3">
                    <Link
                      to={`/add-brand?buyer_id=${buyer.id}&role=COMPETITOR`}
                      className="px-3 py-1.5 border border-neutral-300 rounded-md text-xs text-neutral-700"
                    >
                      + Add competitor to {buyer.name}
                    </Link>
                  </div>

                  <SourceTable
                    title="This buyer's own products"
                    rows={ownSources}
                    emptyText="No source added yet for this buyer's own products."
                    running={running}
                    lastRun={lastRun}
                    editingId={editingId}
                    editUrl={editUrl}
                    setEditUrl={setEditUrl}
                    onRun={(id) => runScraper(id, buyer.id)}
                    onDelete={(id) => deleteSource(id, buyer.id)}
                    onEdit={startEdit}
                    onSaveEdit={(s) => saveEdit(s, buyer.id)}
                    onCancelEdit={() => setEditingId(null)}
                  />

                  <div className="mt-5">
                    <SourceTable
                      title={`Competitors (${competitors.length})`}
                      rows={competitors}
                      emptyText="No competitors added yet."
                      running={running}
                      lastRun={lastRun}
                      editingId={editingId}
                      editUrl={editUrl}
                      setEditUrl={setEditUrl}
                      onRun={(id) => runScraper(id, buyer.id)}
                      onDelete={(id) => deleteSource(id, buyer.id)}
                      onEdit={startEdit}
                      onSaveEdit={(s) => saveEdit(s, buyer.id)}
                      onCancelEdit={() => setEditingId(null)}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {buyers.length === 0 && (
          <div className="text-sm text-neutral-500">
            No buyers yet — click "+ New Buyer" or "+ Add Brand" to create the first one.
          </div>
        )}
      </div>
    </div>
  );
}

function SourceTable({
  title,
  rows,
  emptyText,
  running,
  lastRun,
  editingId,
  editUrl,
  setEditUrl,
  onRun,
  onDelete,
  onEdit,
  onSaveEdit,
  onCancelEdit,
}) {
  return (
    <div>
      <div className="text-sm font-medium mb-2">{title}</div>
      {rows.length === 0 ? (
        <div className="text-xs text-neutral-400">{emptyText}</div>
      ) : (
        <table className="w-full text-sm border border-neutral-100 rounded-md overflow-hidden">
          <thead className="bg-neutral-50 text-left text-xs text-neutral-500">
            <tr>
              <th className="p-2">Brand</th>
              <th className="p-2">Category</th>
              <th className="p-2">URL</th>
              <th className="p-2">Currency</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="border-t border-neutral-100">
                <td className="p-2 font-medium">{s.brand}</td>
                <td className="p-2 text-xs text-neutral-500">
                  {s.item_type} / {s.category} / {s.sub_category}
                </td>
                <td className="p-2 max-w-xs">
                  {editingId === s.id ? (
                    <input
                      value={editUrl}
                      onChange={(e) => setEditUrl(e.target.value)}
                      className="w-full border border-neutral-300 rounded px-2 py-1 text-xs"
                    />
                  ) : (
                    <a
                      href={s.category_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-blue-600 truncate block max-w-xs hover:underline"
                    >
                      {s.category_url}
                    </a>
                  )}
                </td>
                <td className="p-2 text-xs">{s.currency}</td>
                <td className="p-2">
                  <div className="flex gap-2 justify-end">
                    {editingId === s.id ? (
                      <>
                        <button onClick={() => onSaveEdit(s)} className="text-xs text-green-700">
                          Save
                        </button>
                        <button onClick={onCancelEdit} className="text-xs text-neutral-500">
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => onRun(s.id)}
                          disabled={running === s.id}
                          className="px-2 py-1 bg-neutral-900 text-white rounded text-xs disabled:opacity-50"
                        >
                          {running === s.id ? "Running…" : "Run"}
                        </button>
                        <button onClick={() => onEdit(s)} className="text-xs text-neutral-500">
                          Edit
                        </button>
                        <button onClick={() => onDelete(s.id)} className="text-xs text-red-600">
                          Remove
                        </button>
                      </>
                    )}
                  </div>
                  {lastRun?.sourceId === s.id && (
                    <div className={`text-xs mt-1 ${lastRun.status === "success" ? "text-green-700" : "text-red-700"}`}>
                      {lastRun.status === "success"
                        ? `✓ ${lastRun.products_found} found`
                        : `✗ ${lastRun.error_message}`}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
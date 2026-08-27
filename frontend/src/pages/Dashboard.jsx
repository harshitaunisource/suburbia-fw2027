import { useEffect, useState } from "react";

const LABELS = {
  products_analysed: "Products Analysed",
  images_collected: "Images Collected",
  ai_classified: "AI Classified",
  opportunities: "Opportunities",
  shortlisted_styles: "Shortlisted Styles",
  catalogue_styles: "Catalogue Styles",
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/dashboard/stats")
      .then((r) => r.json())
      .then(setStats)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Mexico — Suburbia FW2027</h1>
      {error && <div className="text-red-600 text-sm mb-4">Could not reach API: {error}</div>}
      <div className="grid grid-cols-3 gap-4">
        {stats &&
          Object.entries(LABELS).map(([key, label]) => (
            <div key={key} className="bg-white border border-neutral-200 rounded-lg p-5">
              <div className="text-sm text-neutral-500">{label}</div>
              <div className="text-3xl font-semibold mt-1">{stats[key]}</div>
            </div>
          ))}
      </div>
    </div>
  );
}

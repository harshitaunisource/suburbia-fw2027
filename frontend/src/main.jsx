import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import "./index.css";
import Dashboard from "./pages/Dashboard";
import DataCollection from "./pages/DataCollection";
import Products from "./pages/Products";
import Analytics from "./pages/Analytics";
import Opportunities from "./pages/Opportunities";
import OurProducts from "./pages/OurProducts";
import Catalogue from "./pages/Catalogue";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/data-collection", label: "Data Collection" },
  { to: "/products", label: "Products" },
  { to: "/analytics", label: "Market Analytics" },
  { to: "/opportunities", label: "Suburbia Opportunities" },
  { to: "/our-products", label: "Our Products" },
  { to: "/catalogue", label: "Generate Catalogue" },
];

function Shell() {
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <div className="flex">
        <aside className="w-60 shrink-0 border-r border-neutral-200 min-h-screen p-4">
          <div className="font-semibold text-sm tracking-wide text-neutral-500 mb-4">
            MEXICO — SUBURBIA FW2027
          </div>
          <nav className="flex flex-col gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm ${
                    isActive ? "bg-neutral-900 text-white" : "hover:bg-neutral-100"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="flex-1 p-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/data-collection" element={<DataCollection />} />
            <Route path="/products" element={<Products />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/opportunities" element={<Opportunities />} />
            <Route path="/our-products" element={<OurProducts />} />
            <Route path="/catalogue" element={<Catalogue />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </React.StrictMode>
);

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import "./index.css";
import Dashboard from "./pages/Dashboard";
import DataCollection from "./pages/DataCollection";
import Products from "./pages/Products";
import SearchProducts from "./pages/SearchProducts";
import Analytics from "./pages/Analytics";
import BuyerOpportunities from "./pages/BuyerOpportunities";
import OurProducts from "./pages/OurProducts";
import Catalogue from "./pages/Catalogue";
import ExploreCategories from "./pages/ExploreCategories";
import BrandSetup from "./pages/BrandSetup";
import AddBrand from "./pages/AddBrand";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/brand-setup", label: "Brand Setup" },
  { to: "/add-brand", label: "Add Brand" },
  { to: "/data-collection", label: "Data Collection" },
  { to: "/products", label: "Products" },
  { to: "/search-products", label: "Search Products" },
  { to: "/analytics", label: "Market Analytics" },
  { to: "/opportunities", label: "Buyer Opportunities" },
  { to: "/our-products", label: "Our Products" },
  { to: "/catalogue", label: "Generate Catalogue" },
  { to: "/explore-categories", label: "Explore Categories" },
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
            <Route path="/brand-setup" element={<BrandSetup />} />
            <Route path="/add-brand" element={<AddBrand />} />
            <Route path="/data-collection" element={<DataCollection />} />
            <Route path="/products" element={<Products />} />
            <Route path="/search-products" element={<SearchProducts />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/opportunities" element={<BuyerOpportunities />} />
            <Route path="/our-products" element={<OurProducts />} />
            <Route path="/catalogue" element={<Catalogue />} />
            <Route path="/explore-categories" element={<ExploreCategories />} />
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
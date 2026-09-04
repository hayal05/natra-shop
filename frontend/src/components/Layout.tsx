import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

/**
 * Shared page shell for every route.
 *
 * Task 70 replaces the earlier blood-red top header/nav (Tasks
 * 50/55/66 — a "Seller"/"Admin" link row on a brand-red bar) with a
 * sidebar: persistent (always visible, fixed width, sticky) on
 * desktop, and a slide-in overlay on mobile toggled from a slim
 * mobile-only top bar. Sidebar.tsx owns the nav links themselves;
 * this file only owns the open/closed state, the mobile top bar, and
 * the backdrop that closes the overlay on an outside tap.
 */
function Layout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar isOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      {mobileNavOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}
      <div className="app-content">
        <header className="mobile-topbar">
          <button
            type="button"
            className="mobile-topbar__menu-btn"
            aria-label="Open menu"
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen(true)}
          >
            <span />
            <span />
            <span />
          </button>
          <span className="mobile-topbar__logo">NATRA</span>
        </header>
        <main
          className="container"
          style={{ padding: "var(--space-6) var(--space-4)" }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default Layout;

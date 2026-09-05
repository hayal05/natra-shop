import { Link, NavLink, useLocation } from "react-router-dom";
import { getSellerSession } from "../lib/session";
import { getAdminSession } from "../lib/adminSession";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Task 70: sidebar navigation, replacing the earlier top header/nav
 * (Tasks 50/55/66) that lived in Layout.tsx.
 *
 * - Desktop (>=768px, see index.css): always visible, fixed width,
 *   sticky down the viewport as the page scrolls — "persistent" per
 *   the task ask. `isOpen`/`onClose` have no effect at this
 *   breakpoint; CSS overrides the mobile transform back to none.
 * - Mobile (<768px): hidden off-canvas by default and slid in as an
 *   overlay when `isOpen` is true (Layout.tsx owns that state and
 *   renders the backdrop). Every link and the close button call
 *   `onClose` so the drawer doesn't stay open after navigating.
 *
 * Cream-white background per the task ask (--color-sidebar-bg in
 * tokens.css), not the blood-red --color-brand used elsewhere for
 * buttons/prices/links — that stays unchanged outside this component.
 *
 * Ad hoc addition (not a numbered PROJECT_ROADMAP.md task): a
 * role-scoped sub-section listing that role's own pages — the same
 * "functions" each dashboard already links to internally (see
 * SellerHome.tsx / AdminHome.tsx), just reachable from the sidebar
 * too. Shown only when BOTH conditions hold, so a logged-out visitor
 * or a seller browsing the storefront never sees another role's
 * pages:
 *   - the session exists (`getSellerSession()` / `getAdminSession()`
 *     — read fresh on every render, same "no expiry check, just
 *     presence" contract those modules already document)
 *   - the current route is inside that role's area
 *     (`/seller...` / `/admin-portal...`)
 * Reads localStorage directly rather than lifting session state up
 * into Layout/App — matches how every existing page (SellerHome,
 * AdminHome, etc.) already reads these session helpers standalone,
 * and a route change (e.g. after login redirects) already remounts
 * this component's location via `useLocation`, so the sub-section
 * appears/disappears correctly without extra plumbing.
 */
function Sidebar({ isOpen, onClose }: SidebarProps) {
  const location = useLocation();
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    "sidebar__link" + (isActive ? " sidebar__link--active" : "");
  const subLinkClass = ({ isActive }: { isActive: boolean }) =>
    "sidebar__link sidebar__link--sub" +
    (isActive ? " sidebar__link--active" : "");

  const inSellerArea = location.pathname.startsWith("/seller");
  const inAdminArea = location.pathname.startsWith("/admin-portal");
  const showSellerFunctions = inSellerArea && getSellerSession() !== null;
  const showAdminFunctions = inAdminArea && getAdminSession() !== null;

  return (
    <aside className={"sidebar" + (isOpen ? " is-open" : "")}>
      <div className="sidebar__header">
        <Link to="/" className="sidebar__logo" onClick={onClose}>
          NATRA
        </Link>
        <button
          type="button"
          className="sidebar__close-btn"
          aria-label="Close menu"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <nav className="sidebar__nav">
        <NavLink to="/" end className={linkClass} onClick={onClose}>
          Home
        </NavLink>
        <NavLink to="/seller" className={linkClass} onClick={onClose}>
          Seller
        </NavLink>
        {showSellerFunctions && (
          <div className="sidebar__section">
            <span className="sidebar__section-title">Seller</span>
            <NavLink to="/seller" end className={subLinkClass} onClick={onClose}>
              Dashboard
            </NavLink>
            <NavLink
              to="/seller/payment-methods"
              className={subLinkClass}
              onClick={onClose}
            >
              Payment Methods &amp; Earnings
            </NavLink>
          </div>
        )}
        <NavLink to="/admin-portal" className={linkClass} onClick={onClose}>
          Admin
        </NavLink>
        {showAdminFunctions && (
          <div className="sidebar__section">
            <span className="sidebar__section-title">Admin</span>
            <NavLink
              to="/admin-portal"
              end
              className={subLinkClass}
              onClick={onClose}
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/admin-portal/settings"
              className={subLinkClass}
              onClick={onClose}
            >
              Settings
            </NavLink>
            <NavLink
              to="/admin-portal/settlements"
              className={subLinkClass}
              onClick={onClose}
            >
              Settlements
            </NavLink>
            <NavLink
              to="/admin-portal/reports"
              end
              className={subLinkClass}
              onClick={onClose}
            >
              Reports
            </NavLink>
            <NavLink
              to="/admin-portal/reports/by-seller"
              className={subLinkClass}
              onClick={onClose}
            >
              Reports by Seller
            </NavLink>
          </div>
        )}
      </nav>
    </aside>
  );
}

export default Sidebar;

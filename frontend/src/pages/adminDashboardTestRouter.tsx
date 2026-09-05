import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";
import AdminHome from "./AdminHome";
import AdminSettings from "./AdminSettings";
import AdminSettlements from "./AdminSettlements";
import AdminReports from "./AdminReports";
import AdminReportsBySeller from "./AdminReportsBySeller";

/**
 * Task 83: shared render helper for AdminHome/AdminSettings/
 * AdminSettlements/AdminReports/AdminReportsBySeller's `*.test.tsx`
 * files — mirrors `sellerDashboardTestRouter.tsx` (Task 81), one
 * level up: these five pages all link to each other
 * (`/admin-portal` &harr; `/admin-portal/settings` &harr;
 * `/admin-portal/settlements` &harr; `/admin-portal/reports` &harr;
 * `/admin-portal/reports/by-seller`), so registering all five as real
 * routes behind one `MemoryRouter` lets a test assert on *where*
 * navigation/redirects actually land, the same reasoning as
 * `authTestRouter.tsx`/`sellerDashboardTestRouter.tsx`.
 *
 * `/admin-portal/login` is a plain placeholder here (not the real
 * `AdminLogin`, which has its own coverage in `AdminLogin.test.tsx`
 * from Task 81) — asserting a 401/403-triggered redirect landed on it
 * doesn't need `AdminLogin`'s own rendering or `api/admin.loginAdmin`
 * mock, and pulling that in would blur what each of these five test
 * files is actually covering.
 */
export function renderAdminDashboardPage(
  options: { route?: string; state?: unknown } = {},
): ReturnType<typeof render> {
  const { route = "/admin-portal", state } = options;

  return render(
    <MemoryRouter initialEntries={[{ pathname: route, state }]}>
      <Routes>
        <Route path="/admin-portal/login" element={<div>ADMIN_LOGIN_PLACEHOLDER</div>} />
        <Route path="/admin-portal" element={<AdminHome />} />
        <Route path="/admin-portal/settings" element={<AdminSettings />} />
        <Route path="/admin-portal/settlements" element={<AdminSettlements />} />
        <Route path="/admin-portal/reports" element={<AdminReports />} />
        <Route
          path="/admin-portal/reports/by-seller"
          element={<AdminReportsBySeller />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

/** Shared placeholder text asserted on wherever a test needs to
 * confirm a 401/403 redirect reached `/admin-portal/login`. */
export const ADMIN_LOGIN_PLACEHOLDER = "ADMIN_LOGIN_PLACEHOLDER";

/**
 * `lib/adminSession.ts` reads/writes real `localStorage` (jsdom
 * provides a real implementation, not mocked here), so tests that
 * need a pre-existing session write to it directly with this same
 * key/shape rather than importing `saveAdminSession` — keeping this
 * helper decoupled from that module's own Task 84 test coverage, same
 * pattern as `authTestRouter.tsx`'s `seedSellerSession`.
 */
export const ADMIN_SESSION_STORAGE_KEY = "natra_admin_session";

export function seedAdminSession(session: { token: string; email: string }): void {
  localStorage.setItem(ADMIN_SESSION_STORAGE_KEY, JSON.stringify(session));
}

import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";
import SellerLogin from "./SellerLogin";
import SellerRegister from "./SellerRegister";
import VerifyEmail from "./VerifyEmail";
import ForgotPassword from "./ForgotPassword";

/**
 * Task 80: shared render helper for the seller auth pages'
 * `*.test.tsx` files (SellerLogin, SellerRegister, VerifyEmail,
 * ForgotPassword all navigate to one another, plus `/seller` itself
 * once logged in or verified).
 *
 * Registers real routes for all four pages behind a `MemoryRouter`,
 * plus a visible placeholder for `/seller`, so a test can assert on
 * *where* navigation actually landed (by looking for that placeholder
 * or another page's own heading) instead of reaching into
 * `useNavigate`/router internals — and so `<Link state={...}>` /
 * `navigate(path, { state })` calls between these pages carry real
 * router state end to end, the same state each page reads back via
 * `useLocation().state`.
 */
export function renderAuthPage(
  options: { route?: string; state?: unknown } = {},
): ReturnType<typeof render> {
  const { route = "/seller/login", state } = options;

  return render(
    <MemoryRouter initialEntries={[{ pathname: route, state }]}>
      <Routes>
        <Route path="/seller" element={<div>SELLER_HOME_PLACEHOLDER</div>} />
        <Route path="/seller/login" element={<SellerLogin />} />
        <Route path="/seller/register" element={<SellerRegister />} />
        <Route path="/seller/verify-email" element={<VerifyEmail />} />
        <Route path="/seller/forgot-password" element={<ForgotPassword />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Shared placeholder text asserted on wherever a test needs to
 * confirm navigation reached `/seller`. */
export const SELLER_HOME_PLACEHOLDER = "SELLER_HOME_PLACEHOLDER";

/**
 * `lib/session.ts` reads/writes real `localStorage` (not mocked here
 * — jsdom provides a real implementation), so tests that need a
 * pre-existing session write to it directly with this same key/shape
 * rather than importing `saveSellerSession` (keeping this helper
 * decoupled from that module's own Task 84 test coverage).
 */
export const SELLER_SESSION_STORAGE_KEY = "natra_seller_session";

export function seedSellerSession(session: { token: string; email: string }): void {
  localStorage.setItem(SELLER_SESSION_STORAGE_KEY, JSON.stringify(session));
}

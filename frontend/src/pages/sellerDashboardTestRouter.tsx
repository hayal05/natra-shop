import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";
import SellerHome from "./SellerHome";
import SellerPayments from "./SellerPayments";

/**
 * Task 81: shared render helper for SellerHome.test.tsx and
 * SellerPayments.test.tsx. Distinct from `authTestRouter.tsx` (Task
 * 80's helper for the four *logged-out* seller auth pages): these two
 * pages are the logged-in dashboard, so `/seller/login` is registered
 * here only as a plain placeholder (not the real `SellerLogin`) —
 * asserting a redirect landed on it doesn't need `SellerLogin`'s own
 * rendering or its `api/sellers.loginSeller` mock, and pulling in a
 * second page's mocks would blur what each test file is actually
 * covering.
 */
export function renderSellerDashboardPage(
  options: { route?: string; state?: unknown } = {},
): ReturnType<typeof render> {
  const { route = "/seller", state } = options;

  return render(
    <MemoryRouter initialEntries={[{ pathname: route, state }]}>
      <Routes>
        <Route path="/seller/login" element={<div>SELLER_LOGIN_PLACEHOLDER</div>} />
        <Route path="/seller" element={<SellerHome />} />
        <Route path="/seller/payment-methods" element={<SellerPayments />} />
      </Routes>
    </MemoryRouter>,
  );
}

export const SELLER_LOGIN_PLACEHOLDER = "SELLER_LOGIN_PLACEHOLDER";

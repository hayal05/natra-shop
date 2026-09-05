import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import BuyerHome from "./pages/BuyerHome";
import ProductDetail from "./pages/ProductDetail";
import BuyNow from "./pages/BuyNow";
import ReceiptStatus from "./pages/ReceiptStatus";
import SellerHome from "./pages/SellerHome";
import SellerLogin from "./pages/SellerLogin";
import SellerRegister from "./pages/SellerRegister";
import VerifyEmail from "./pages/VerifyEmail";
import ForgotPassword from "./pages/ForgotPassword";
import SellerPayments from "./pages/SellerPayments";
import AdminLogin from "./pages/AdminLogin";
import AdminHome from "./pages/AdminHome";
import AdminSettings from "./pages/AdminSettings";
import AdminSettlements from "./pages/AdminSettlements";
import AdminReports from "./pages/AdminReports";
import AdminReportsBySeller from "./pages/AdminReportsBySeller";
import RolePlaceholder from "./pages/RolePlaceholder";

/**
 * Task 50: routing foundation. Most routes below were placeholders —
 * real views land in Tasks 51-67 per PROJECT_ROADMAP.md's Phase 5
 * table (renumbered/split after Task 58 — see that table's own note).
 * Route *paths* are fixed since later tasks build inside them;
 * placeholder *content* is expected to be replaced, not the paths.
 *
 * Task 55 filled in seller/login and seller/register. Task 56 turned
 * the seller index (`/seller`) into the add/list-products dashboard.
 * Task 57 fills in seller/payment-methods (payment methods + earnings
 * UI). Seller is now fully built; any unmatched `seller/*` sub-path
 * still falls through to RolePlaceholder.
 *
 * Task 58 fills in admin-portal/login. Task 59 turns the admin-portal
 * index into the products overview dashboard. Task 60 fills in
 * admin-portal/settings. Task 61 fills in admin-portal/settlements.
 * Task 62 fills in admin-portal/reports with platform totals; Task 63
 * fills in admin-portal/reports/by-seller with the per-seller
 * breakdown. Admin is now fully built; every other admin-portal
 * sub-path still falls through to RolePlaceholder.
 *
 * Task 69 (Phase 6): adds seller/verify-email and
 * seller/forgot-password — frontend for Task 68's backend-only email
 * OTP endpoints. Both fall inside the existing seller/* wildcard's
 * "otherwise built" area, so no change to RolePlaceholder's props.
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<BuyerHome />} />
        <Route path="product/:productId" element={<ProductDetail />} />
        <Route path="product/:productId/buy" element={<BuyNow />} />
        <Route path="receipt/:receiptId" element={<ReceiptStatus />} />
        <Route path="seller">
          <Route index element={<SellerHome />} />
          <Route path="login" element={<SellerLogin />} />
          <Route path="register" element={<SellerRegister />} />
          <Route path="verify-email" element={<VerifyEmail />} />
          <Route path="forgot-password" element={<ForgotPassword />} />
          <Route path="payment-methods" element={<SellerPayments />} />
          <Route
            path="*"
            element={
              <RolePlaceholder role="Seller" nextTask={58} roleOtherwiseBuilt />
            }
          />
        </Route>
        {/* "admin-portal", not "admin": deploy/nginx/natra.conf proxies
            any /admin/... path to the backend API. A frontend route at
            /admin/* would never reach the SPA in production — Nginx
            would hand it to Uvicorn first, which has no matching route
            for e.g. /admin/login as a page request. */}
        <Route path="admin-portal">
          <Route index element={<AdminHome />} />
          <Route path="login" element={<AdminLogin />} />
          <Route path="settings" element={<AdminSettings />} />
          <Route path="settlements" element={<AdminSettlements />} />
          <Route path="reports" element={<AdminReports />} />
          <Route
            path="reports/by-seller"
            element={<AdminReportsBySeller />}
          />
          <Route
            path="*"
            element={
              <RolePlaceholder role="Admin" nextTask={64} roleOtherwiseBuilt />
            }
          />
        </Route>
      </Route>
    </Routes>
  );
}

export default App;

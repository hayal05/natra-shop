import { apiFetch } from "./client";

/** Mirrors backend/app/main.py's AdminLoginResponse. */
export type AdminLoginResult = {
  access_token: string;
  token_type: string;
};

/**
 * POST /admin/login — verifies the Master Admin credentials (there is
 * exactly one admin identity, provisioned via ADMIN_EMAIL/
 * ADMIN_PASSWORD_HASH env vars, not a database row — see
 * backend/app/main.py's login_admin docstring) and returns a JWT with
 * role="admin", valid for 24h same as a seller's token.
 *
 * Throws ApiError with status 401 for a wrong email/password *or* the
 * admin account not being configured at all — the backend deliberately
 * returns one generic message for all three, the same
 * anti-enumeration behavior as POST /sellers/login — or 429 if this
 * client IP has hit the (separately-tracked) admin-login rate limit.
 */
export function loginAdmin(
  email: string,
  password: string,
): Promise<AdminLoginResult> {
  return apiFetch<AdminLoginResult>("/admin/login", {
    method: "POST",
    body: { email, password },
  });
}

/**
 * Mirrors backend/app/main.py's AdminProductItem — the admin-wide
 * counterpart to the buyer-facing product shape from api/products.ts.
 * Deliberately fuller: includes `seller_id` and `drive_link`, which a
 * buyer must never see before a verified purchase, but which the
 * Master Admin needs for platform management.
 */
export type AdminProductItem = {
  id: string;
  seller_id: string;
  name: string;
  price: number;
  description: string;
  thumbnail_ref: string | null;
  drive_link: string;
};

/**
 * GET /admin/products — admin-only, platform-wide, via the admin
 * session token. Read-only: no edit/delete/publish here, same as the
 * backend endpoint itself (Task 15's docstring).
 */
export function getAdminProducts(token: string): Promise<AdminProductItem[]> {
  return apiFetch<AdminProductItem[]>("/admin/products", { token });
}

/**
 * Mirrors backend/app/main.py's AdminSettingsResponse — NATRA's own
 * CBE/Telebirr payment account (the one buyers pay into, shown to them
 * via the public GET /payment-info) plus `commission_rate`, which is
 * admin-only and never exposed to buyers or sellers. Payment fields
 * are nullable: null until an admin sets them. `commission_rate` is
 * never null — the backend column is NOT NULL, seeded at 10.00.
 */
export type AdminSettings = {
  cbe_account_name: string | null;
  cbe_account_number: string | null;
  telebirr_account_name: string | null;
  telebirr_account_number: string | null;
  commission_rate: number;
};

/** GET /admin/settings — admin-only, via the admin session token. */
export function getAdminSettings(token: string): Promise<AdminSettings> {
  return apiFetch<AdminSettings>("/admin/settings", { token });
}

/**
 * PUT /admin/settings — admin-only. Same "omit/null = leave unchanged,
 * empty string = clear" backend convention as
 * sellers.ts's updatePaymentMethods, and the same approach here: this
 * app always sends all four payment fields as plain strings (pre-filled
 * from the last GET), so resubmitting the same value is a no-op and
 * blanking a field clears it. `commission_rate` has no "clear" — the
 * column is NOT NULL — so it's always sent as a number, never omitted.
 */
export function updateAdminSettings(
  token: string,
  settings: AdminSettings,
): Promise<AdminSettings> {
  return apiFetch<AdminSettings>("/admin/settings", {
    method: "PUT",
    body: settings,
    token,
  });
}

/**
 * Mirrors backend/app/main.py's SettlementResponse — one record of
 * NATRA settling (or intending to settle) `amount` to `seller_id`,
 * paid manually outside this system to the payout account the seller
 * set via PUT /sellers/payment-methods. `status` is `"pending"` until
 * an admin calls completeSettlement(), which stamps `completed_at`.
 */
export type Settlement = {
  id: string;
  seller_id: string;
  amount: number;
  status: string;
  created_at: string;
  completed_at: string | null;
};

/**
 * POST /admin/settlements — admin-only. Records a settlement as
 * `'pending'`; this call moves no money itself. Throws ApiError with
 * status 404 for an unknown seller_id, 422 if `amount` exceeds that
 * seller's unsettled balance (backend/app/main.py's create_settlement,
 * Task 42).
 */
export function createSettlement(
  token: string,
  sellerId: string,
  amount: number,
): Promise<Settlement> {
  return apiFetch<Settlement>("/admin/settlements", {
    method: "POST",
    body: { seller_id: sellerId, amount },
    token,
  });
}

/**
 * GET /admin/settlements — admin-only, every settlement across every
 * seller, newest first.
 */
export function getSettlements(token: string): Promise<Settlement[]> {
  return apiFetch<Settlement[]>("/admin/settlements", { token });
}

/**
 * POST /admin/settlements/{id}/complete — admin-only. Call only after
 * NATRA has actually paid the seller manually, outside this system —
 * this endpoint just records that the payout happened. Idempotent: a
 * settlement that's already `'completed'` is returned unchanged.
 */
export function completeSettlement(
  token: string,
  settlementId: string,
): Promise<Settlement> {
  return apiFetch<Settlement>(`/admin/settlements/${settlementId}/complete`, {
    method: "POST",
    token,
  });
}

/**
 * Mirrors backend/app/main.py's AdminReportsResponse — the same six
 * fields as sellers.ts's SellerEarnings, but summed across every
 * seller platform-wide instead of filtered to one. `total_sales` is a
 * count of rows in `sales`, everything else is an ETB amount.
 */
export type AdminReports = {
  total_sales: number;
  gross_amount_total: number;
  commission_total: number;
  seller_payable_total: number;
  settled_total: number;
  unsettled_total: number;
};

/** GET /admin/reports — admin-only, platform totals. */
export function getAdminReports(token: string): Promise<AdminReports> {
  return apiFetch<AdminReports>("/admin/reports", { token });
}

/**
 * Mirrors backend/app/main.py's AdminSellerReportItem — the same six
 * fields as AdminReports above, plus `seller_id`, one row per seller
 * instead of one platform-wide row. Only sellers with at least one
 * sale appear (see the backend endpoint's docstring); summing every
 * row's fields reproduces exactly what GET /admin/reports returns.
 */
export type AdminSellerReportItem = {
  seller_id: string;
  total_sales: number;
  gross_amount_total: number;
  commission_total: number;
  seller_payable_total: number;
  settled_total: number;
  unsettled_total: number;
};

/**
 * GET /admin/reports/by-seller — admin-only, per-seller breakdown of
 * the same figures GET /admin/reports sums platform-wide. Already
 * sorted by the backend, `unsettled_total` descending (most-owed
 * seller first), so no client-side sort is needed.
 */
export function getAdminReportsBySeller(
  token: string,
): Promise<AdminSellerReportItem[]> {
  return apiFetch<AdminSellerReportItem[]>("/admin/reports/by-seller", {
    token,
  });
}

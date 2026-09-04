import { apiFetch } from "./client";

/** Mirrors backend/app/main.py's SellerRegisterResponse. */
export type SellerRegisterResult = {
  id: string;
  email: string;
};

/**
 * POST /sellers/register — creates the seller account. Does NOT log
 * the seller in (the backend doesn't return a token here); callers
 * that want to land the seller in a logged-in state after registering
 * should follow up with loginSeller() using the same credentials, the
 * same way a seller filling in a login form after registering would.
 * Throws ApiError with status 409 if the email is already registered,
 * 422 for an invalid email.
 */
export function registerSeller(
  email: string,
  password: string,
): Promise<SellerRegisterResult> {
  return apiFetch<SellerRegisterResult>("/sellers/register", {
    method: "POST",
    body: { email, password },
  });
}

/** Mirrors backend/app/main.py's SellerLoginResponse. */
export type SellerLoginResult = {
  access_token: string;
  token_type: string;
};

/**
 * POST /sellers/login — verifies credentials and returns a JWT valid
 * for 24h (see backend/app/auth.py). Throws ApiError with status 401
 * for a wrong email/password (the backend deliberately uses one
 * generic message for both, so it can't be used to enumerate
 * registered emails), 429 if this client IP has hit the login rate
 * limit, or — Task 71 — 403 if the credentials are correct but the
 * seller hasn't completed email verification yet
 * (`sellers.email_verified = 'N'`). SellerLogin.tsx branches on that
 * 403 specifically to point the seller at `/seller/verify-email`
 * instead of showing it as a generic error.
 */
export function loginSeller(
  email: string,
  password: string,
): Promise<SellerLoginResult> {
  return apiFetch<SellerLoginResult>("/sellers/login", {
    method: "POST",
    body: { email, password },
  });
}

/**
 * Task 69: frontend for Task 68's email-OTP endpoints.
 *
 * All four functions below are deliberately untyped beyond the one
 * field each caller actually branches on (`verified`/`reset`, or
 * nothing at all for the two generic-message endpoints) — mirroring
 * how the backend itself keeps these responses minimal (see
 * main.py's VerifyEmailResponse etc.). None of these take a session
 * token: every one of them is reachable before or without a login
 * (a seller verifying right after registering already has a token
 * from the auto-login in SellerRegister.tsx, but verification itself
 * doesn't require it — same unauthenticated design as the backend).
 */

/** Mirrors backend/app/main.py's VerifyEmailResponse. */
export type VerifyEmailResult = { verified: boolean };

/**
 * POST /sellers/verify-email — confirms a seller's email using the
 * 6-digit code sent by registerSeller() (or resendVerificationEmail()
 * below). Throws ApiError with status 400 for a wrong/expired/
 * already-used code (message is backend-supplied and safe to show
 * as-is — see main.py's _OTP_RESULT_MESSAGES) or 429 if this client
 * IP has hit the rate limit.
 */
export function verifyEmail(email: string, otp: string): Promise<VerifyEmailResult> {
  return apiFetch<VerifyEmailResult>("/sellers/verify-email", {
    method: "POST",
    body: { email, otp },
  });
}

/** Mirrors backend/app/main.py's ResendVerificationResponse. */
export type ResendVerificationResult = { message: string };

/**
 * POST /sellers/verify-email/resend — always resolves with the same
 * generic message regardless of whether the email is registered or
 * already verified (anti-enumeration — see main.py's docstring), so
 * callers should show that message as-is rather than branching on
 * whether a code was "actually" sent.
 */
export function resendVerificationEmail(email: string): Promise<ResendVerificationResult> {
  return apiFetch<ResendVerificationResult>("/sellers/verify-email/resend", {
    method: "POST",
    body: { email },
  });
}

/** Mirrors backend/app/main.py's PasswordResetRequestResponse. */
export type PasswordResetRequestResult = { message: string };

/**
 * POST /sellers/password-reset/request — same anti-enumeration shape
 * as resendVerificationEmail(): always the same generic message, so
 * this alone can't confirm whether an account exists.
 */
export function requestPasswordReset(email: string): Promise<PasswordResetRequestResult> {
  return apiFetch<PasswordResetRequestResult>("/sellers/password-reset/request", {
    method: "POST",
    body: { email },
  });
}

/** Mirrors backend/app/main.py's PasswordResetConfirmResponse. */
export type PasswordResetConfirmResult = { reset: boolean };

/**
 * POST /sellers/password-reset/confirm — verifies the OTP from
 * requestPasswordReset() and sets `newPassword` as the account's new
 * password. Throws ApiError with status 400 for a wrong/expired code
 * (same messages as verifyEmail()) or 429 for the rate limit.
 */
export function confirmPasswordReset(
  email: string,
  otp: string,
  newPassword: string,
): Promise<PasswordResetConfirmResult> {
  return apiFetch<PasswordResetConfirmResult>("/sellers/password-reset/confirm", {
    method: "POST",
    body: { email, otp, new_password: newPassword },
  });
}

/**
 * Mirrors backend/app/main.py's SellerPaymentMethodsResponse — the
 * seller's own payout account (where NATRA will eventually send a
 * settlement). Every field nullable: null until the seller sets it.
 * Never shown to buyers, never the account buyers pay into (that's
 * always NATRA's own account via GET /payment-info — see
 * ARCHITECTURE.md's payment architecture).
 */
export type SellerPaymentMethods = {
  cbe_account_name: string | null;
  cbe_account_number: string | null;
  telebirr_account_name: string | null;
  telebirr_account_number: string | null;
};

/** GET /sellers/payment-methods — seller-only, via the session token. */
export function getPaymentMethods(token: string): Promise<SellerPaymentMethods> {
  return apiFetch<SellerPaymentMethods>("/sellers/payment-methods", { token });
}

/**
 * PUT /sellers/payment-methods — seller-only. Backend convention: a
 * field sent as `null`/omitted leaves that column unchanged; an empty
 * string `""` clears it. This app always sends all four fields as
 * plain strings (never omits/nulls), pre-filled from the last GET —
 * so "unchanged" happens naturally by resubmitting the same value,
 * and "clear" happens by blanking the input, without this function
 * needing to track which fields the seller actually touched.
 */
export function updatePaymentMethods(
  token: string,
  methods: SellerPaymentMethods,
): Promise<SellerPaymentMethods> {
  return apiFetch<SellerPaymentMethods>("/sellers/payment-methods", {
    method: "PUT",
    body: methods,
    token,
  });
}

/**
 * Mirrors backend/app/main.py's SellerEarningsResponse. `settled_total`
 * sums this seller's completed settlements; `unsettled_total` is
 * `seller_payable_total - settled_total` and, per the backend's own
 * docstring, is not clamped to zero (a negative value is possible and
 * deliberately left visible rather than hidden — see main.py).
 */
export type SellerEarnings = {
  total_sales: number;
  gross_amount_total: number;
  commission_total: number;
  seller_payable_total: number;
  settled_total: number;
  unsettled_total: number;
};

/** GET /sellers/earnings — seller-only, via the session token. */
export function getEarnings(token: string): Promise<SellerEarnings> {
  return apiFetch<SellerEarnings>("/sellers/earnings", { token });
}

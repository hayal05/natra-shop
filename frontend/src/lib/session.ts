/**
 * Task 55: seller session handling.
 *
 * The backend issues a plain JWT (see backend/app/auth.py) with no
 * refresh mechanism yet — it's just carried as a Bearer token and
 * expires after 24h server-side. This module is the one place that
 * knows how it's persisted client-side (localStorage) so every page
 * that needs "am I logged in as a seller" goes through the same
 * read/write/clear functions instead of touching localStorage
 * directly.
 *
 * `POST /sellers/login` only returns `access_token` (no email — see
 * api/sellers.ts), so the email shown in the UI is simply the one the
 * seller typed into the login/register form and is stored alongside
 * the token at that moment. It's for display only; every real
 * authorization decision is made server-side from the token itself.
 */

const STORAGE_KEY = "natra_seller_session";

export type SellerSession = {
  token: string;
  email: string;
};

export function saveSellerSession(session: SellerSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

/**
 * Returns the stored session, or null if there isn't one or it's
 * malformed (e.g. hand-edited or from an older/incompatible shape).
 * Does not check token expiry — an expired token is simply rejected
 * with 401 the next time it's sent to a protected endpoint, which is
 * the seller dashboard's job to handle (Task 56), not this helper's.
 */
export function getSellerSession(): SellerSession | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      typeof parsed.token === "string" &&
      typeof parsed.email === "string"
    ) {
      return { token: parsed.token, email: parsed.email };
    }
  } catch {
    // Malformed JSON — treat the same as "no session".
  }
  return null;
}

export function clearSellerSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}

/**
 * Task 58: admin session handling.
 *
 * Deliberately a separate module (and separate localStorage key) from
 * lib/session.ts's seller session, not a shared "role session" helper —
 * there is exactly one Master Admin identity (see backend/app/main.py's
 * login_admin docstring), its token carries role="admin" rather than a
 * seller_id, and mixing the two storage slots would let a leftover
 * admin session bleed into seller-only pages (or vice versa) if
 * someone used both roles in the same browser. Same token shape and
 * same "no refresh, 24h server-side expiry, not checked client-side"
 * behavior as the seller session, though.
 */

const STORAGE_KEY = "natra_admin_session";

export type AdminSession = {
  token: string;
  email: string;
};

export function saveAdminSession(session: AdminSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

/**
 * Returns the stored session, or null if there isn't one or it's
 * malformed. Does not check token expiry — an expired token is simply
 * rejected with 401 the next time it's sent to an admin-only endpoint,
 * which is that endpoint's caller's job to handle, not this helper's.
 */
export function getAdminSession(): AdminSession | null {
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

export function clearAdminSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}

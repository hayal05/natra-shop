import { afterEach, describe, expect, it } from "vitest";
import {
  clearAdminSession,
  getAdminSession,
  saveAdminSession,
} from "./adminSession";

const STORAGE_KEY = "natra_admin_session";

afterEach(() => {
  localStorage.clear();
});

/**
 * Mirrors `session.test.ts` — same read/write/clear/malformed-data
 * contract, just against the separate admin storage key
 * (`lib/adminSession.ts`'s own docstring explains why it's a distinct
 * module/key rather than a shared "role session" helper).
 */
describe("adminSession", () => {
  it("returns null when nothing is stored", () => {
    expect(getAdminSession()).toBeNull();
  });

  it("round-trips a saved session", () => {
    saveAdminSession({ token: "tok123", email: "admin@example.com" });

    expect(getAdminSession()).toEqual({ token: "tok123", email: "admin@example.com" });
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null")).toEqual({
      token: "tok123",
      email: "admin@example.com",
    });
  });

  it("clears the stored session", () => {
    saveAdminSession({ token: "tok123", email: "admin@example.com" });
    clearAdminSession();

    expect(getAdminSession()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("treats malformed JSON the same as no session", () => {
    localStorage.setItem(STORAGE_KEY, "{not valid json");

    expect(getAdminSession()).toBeNull();
  });

  it("treats a stored value missing required fields as no session", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ email: "admin@example.com" }));

    expect(getAdminSession()).toBeNull();
  });

  it("treats a stored non-object value (e.g. a JSON array) as no session", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(["tok123", "admin@example.com"]));

    expect(getAdminSession()).toBeNull();
  });

  it("is stored under a different key than the seller session, so the two never collide", () => {
    saveAdminSession({ token: "admin-tok", email: "admin@example.com" });

    expect(localStorage.getItem("natra_seller_session")).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull();
  });
});

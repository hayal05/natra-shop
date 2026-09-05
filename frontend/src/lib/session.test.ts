import { afterEach, describe, expect, it } from "vitest";
import { clearSellerSession, getSellerSession, saveSellerSession } from "./session";

const STORAGE_KEY = "natra_seller_session";

afterEach(() => {
  localStorage.clear();
});

describe("session (seller)", () => {
  it("returns null when nothing is stored", () => {
    expect(getSellerSession()).toBeNull();
  });

  it("round-trips a saved session", () => {
    saveSellerSession({ token: "tok123", email: "seller@example.com" });

    expect(getSellerSession()).toEqual({ token: "tok123", email: "seller@example.com" });
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null")).toEqual({
      token: "tok123",
      email: "seller@example.com",
    });
  });

  it("clears the stored session", () => {
    saveSellerSession({ token: "tok123", email: "seller@example.com" });
    clearSellerSession();

    expect(getSellerSession()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("treats malformed JSON the same as no session", () => {
    localStorage.setItem(STORAGE_KEY, "{not valid json");

    expect(getSellerSession()).toBeNull();
  });

  it("treats a stored value missing required fields as no session", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "tok123" }));

    expect(getSellerSession()).toBeNull();
  });

  it("treats a stored non-object value (e.g. a JSON array) as no session", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(["tok123", "seller@example.com"]));

    expect(getSellerSession()).toBeNull();
  });

  it("a later save overwrites an earlier one", () => {
    saveSellerSession({ token: "old-token", email: "old@example.com" });
    saveSellerSession({ token: "new-token", email: "new@example.com" });

    expect(getSellerSession()).toEqual({ token: "new-token", email: "new@example.com" });
  });
});

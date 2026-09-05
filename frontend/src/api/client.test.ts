import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, ApiError } from "./client";

/**
 * No fake backend exists for the frontend suite (see
 * `test/README.md`'s "Conventions for Tasks 80-84") — `apiFetch` is
 * the one module that actually calls `fetch`, so here (unlike every
 * other Task 80-84 file, which mocks a page's `api/*.ts` module)
 * `fetch` itself is stubbed globally per test, with a small helper
 * building just enough of a `Response`-shaped object for
 * `apiFetch`'s own header/`.json()`/`.text()` usage.
 */
function mockFetchOnce(options: {
  ok: boolean;
  status: number;
  contentType?: string | null;
  json?: unknown;
  text?: string;
}) {
  const { ok, status, contentType = "application/json", json, text } = options;
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    headers: { get: (name: string) => (name === "content-type" ? contentType : null) },
    json: () => Promise.resolve(json),
    text: () => Promise.resolve(text ?? ""),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("apiFetch", () => {
  it("GETs a path and returns the parsed JSON body", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 200, json: { id: "abc" } });

    const result = await apiFetch("/products", {});

    expect(result).toEqual({ id: "abc" });
    // BASE_URL comes from VITE_API_BASE_URL (empty/same-origin unless
    // set), so only the path suffix is asserted here rather than an
    // exact URL — see client.ts's own docstring.
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/products$/);
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ method: "GET", body: undefined }),
    );
    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers).toEqual({ "Content-Type": "application/json" });
  });

  it("sends no Authorization header when no token is given", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 200, json: {} });

    await apiFetch("/products", {});

    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty("Authorization");
  });

  it("sends a Bearer Authorization header when a token is given", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 200, json: {} });

    await apiFetch("/sellers/earnings", { token: "tok123" });

    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({
      Authorization: "Bearer tok123",
    });
  });

  it("sends a JSON-stringified body and the right method on POST", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 201, json: { id: "new-1" } });

    await apiFetch("/products", {
      method: "POST",
      body: { name: "E-book", price: 150 },
    });

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/products$/);
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "E-book", price: 150 }),
      }),
    );
  });

  it("throws an ApiError using the JSON body's detail message on a non-2xx response", async () => {
    mockFetchOnce({
      ok: false,
      status: 422,
      json: { detail: "drive_link must be a URL" },
    });

    await expect(apiFetch("/products", { method: "POST", body: {} })).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "drive_link must be a URL",
    });
  });

  it("throws an ApiError instance carrying the parsed body", async () => {
    mockFetchOnce({ ok: false, status: 401, json: { detail: "Not authenticated" } });

    let caught: unknown;
    try {
      await apiFetch("/sellers/earnings", { token: "bad-token" });
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).body).toEqual({ detail: "Not authenticated" });
  });

  it("falls back to a generic message when a non-2xx JSON body has no detail field", async () => {
    mockFetchOnce({ ok: false, status: 500, json: { message: "oops" } });

    await expect(apiFetch("/admin/reports", {})).rejects.toMatchObject({
      status: 500,
      message: "Request to /admin/reports failed with status 500",
    });
  });

  it("falls back to a generic message when the non-2xx response isn't JSON", async () => {
    mockFetchOnce({
      ok: false,
      status: 502,
      contentType: "text/plain",
      text: "Bad Gateway",
    });

    await expect(apiFetch("/health", {})).rejects.toMatchObject({
      status: 502,
      message: "Request to /health failed with status 502",
    });
  });

  it("returns raw text for a successful non-JSON response", async () => {
    mockFetchOnce({ ok: true, status: 200, contentType: "text/plain", text: "ok" });

    const result = await apiFetch("/health", {});

    expect(result).toBe("ok");
  });
});

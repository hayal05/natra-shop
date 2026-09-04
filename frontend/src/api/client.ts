/**
 * Shared API client for talking to the NATRA backend.
 *
 * Base URL comes from VITE_API_BASE_URL (see frontend/.env.example),
 * so local dev, and the production build served by Nginx per
 * deploy/nginx/natra.conf, can each point at the right backend without
 * a code change. Falls back to same-origin (empty string) if the env
 * var isn't set, matching how Nginx proxies /sellers, /products, etc.
 * on the same host in production (see SETUP.md's Deployment section).
 */

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  token?: string | null;
};

/**
 * Minimal fetch wrapper: JSON in, JSON out, throws ApiError on non-2xx
 * so callers can catch one error type instead of checking res.ok
 * everywhere. Real endpoint-specific functions (getProducts,
 * sellerLogin, etc.) get added in the tasks that build each view —
 * this file only provides the shared plumbing.
 */
export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, token } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const message =
      isJson && data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : `Request to ${path} failed with status ${res.status}`;
    throw new ApiError(res.status, data, message);
  }

  return data as T;
}

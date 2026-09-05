import { apiFetch } from "./client";

/**
 * Mirrors backend/app/main.py's ProductGridItem exactly. Deliberately
 * minimal (no seller_id/description/drive_link) — that's the backend's
 * own choice for this public, unauthenticated endpoint, not something
 * to work around here.
 */
export type ProductGridItem = {
  id: string;
  name: string;
  price: number;
  thumbnail_ref: string | null;
};

/** GET /products — public buyer-facing grid, no auth required. */
export function getProducts(): Promise<ProductGridItem[]> {
  return apiFetch<ProductGridItem[]>("/products");
}

/**
 * Mirrors backend/app/main.py's ProductDetailResponse. Adds `description`
 * over the grid item; still never includes seller_id/drive_link — the
 * backend deliberately withholds those from every buyer-facing endpoint.
 */
export type ProductDetail = {
  id: string;
  name: string;
  price: number;
  description: string;
  thumbnail_ref: string | null;
};

/**
 * GET /products/{id} — public buyer-facing details page, no auth
 * required. Throws ApiError with status 404 if the id doesn't match
 * any product (including a malformed id — the backend 404s that too
 * rather than erroring, see its own docstring).
 */
export function getProductDetail(productId: string): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${encodeURIComponent(productId)}`);
}

/**
 * Mirrors backend/app/main.py's ProductResponse — the seller-facing
 * shape, used by both POST /products and GET /products/mine.
 * Deliberately omits `thumbnail_ref` here: the backend's own
 * ProductResponse has surfaced it since Task 97, but no frontend task
 * yet displays a thumbnail on the seller dashboard (Tasks 104-105
 * only cover the two buyer-facing views) — this type is left as-is
 * until one does, rather than adding an unused field speculatively.
 */
export type SellerProduct = {
  id: string;
  seller_id: string;
  name: string;
  price: number;
  description: string;
  drive_link: string;
};

export type ProductCreateInput = {
  name: string;
  price: number;
  description: string;
  drive_link: string;
};

/**
 * POST /products — Seller Add Product (Task 56). Protected: requires
 * the seller's JWT. Throws ApiError with status 401/403 for a
 * missing/expired/wrong-role token, 422 for backend-side validation
 * failures (e.g. a `drive_link` that isn't a URL — checked here too
 * before submitting, but the backend's check is what actually matters).
 */
export function createProduct(
  token: string,
  input: ProductCreateInput,
): Promise<SellerProduct> {
  return apiFetch<SellerProduct>("/products", {
    method: "POST",
    body: input,
    token,
  });
}

/**
 * GET /products/mine — Seller View Products (Task 56). Protected the
 * same way as createProduct(); returns only the authenticated
 * seller's own products, newest first (backend orders by
 * created_at DESC).
 */
export function getMyProducts(token: string): Promise<SellerProduct[]> {
  return apiFetch<SellerProduct[]>("/products/mine", { token });
}

/** Mirrors backend/app/main.py's ThumbnailUploadResponse (Task 94). */
export type ThumbnailUploadResult = {
  thumbnail_ref: string;
};

/**
 * POST /products/{id}/thumbnail — uploads a thumbnail image for one of
 * the authenticated seller's own products (Task 94), called by
 * `SellerHome.tsx` right after `createProduct()` succeeds, using the
 * file picked/validated/previewed by Task 102. Protected the same way
 * as `createProduct()`/`getMyProducts()`; the backend also 403s if the
 * seller doesn't own `productId`, and 400/502 for the two thumbnail-
 * specific failure cases (invalid file / storage upload failure — see
 * `backend/app/thumbnail.py`).
 *
 * Sent as `multipart/form-data` (a single `file` field), not JSON —
 * `apiFetch()` passes a `FormData` body straight through untouched
 * (see client.ts's Task 103 note).
 */
export function uploadThumbnail(
  token: string,
  productId: string,
  file: File,
): Promise<ThumbnailUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<ThumbnailUploadResult>(
    `/products/${encodeURIComponent(productId)}/thumbnail`,
    { method: "POST", body: formData, token },
  );
}

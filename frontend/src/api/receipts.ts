import { apiFetch } from "./client";

/**
 * Mirrors backend/app/main.py's PaymentInfoResponse — NATRA's own
 * CBE/Telebirr account, shown to a buyer after "Buy Now" (buyers pay
 * NATRA directly, never a seller). Every field is nullable: NULL until
 * an admin sets it via PUT /admin/settings, which hasn't been built in
 * the frontend yet (Task 59) — so "not configured" is a real state
 * this UI must handle, not just a loading edge case.
 */
export type PaymentInfo = {
  cbe_account_name: string | null;
  cbe_account_number: string | null;
  telebirr_account_name: string | null;
  telebirr_account_number: string | null;
};

/** GET /payment-info — public, no auth required. */
export function getPaymentInfo(): Promise<PaymentInfo> {
  return apiFetch<PaymentInfo>("/payment-info");
}

/** Mirrors backend/app/main.py's ReceiptSubmitResponse. */
export type ReceiptSubmitResult = {
  id: string;
  product_id: string;
  receipt_url: string;
};

/**
 * POST /products/{id}/receipt — buyer pastes their payment receipt URL
 * after paying NATRA's account above. Storage only at this step: no
 * verification happens here (that's a separate call, `POST
 * /receipts/{id}/verify`, owned by Task 54's status page, not this
 * form). A product can receive more than one submission by design
 * (e.g. a corrected link) — the backend doesn't reject a resubmission.
 */
export function submitReceipt(
  productId: string,
  receiptUrl: string,
): Promise<ReceiptSubmitResult> {
  return apiFetch<ReceiptSubmitResult>(
    `/products/${encodeURIComponent(productId)}/receipt`,
    { method: "POST", body: { receipt_url: receiptUrl } },
  );
}

/** Mirrors backend/app/main.py's ReceiptVerifyResponse. */
export type ReceiptVerifyResult = {
  id: string;
  product_id: string;
  status: "verified" | "rejected";
  reason: string | null;
  transaction_ref: string | null;
  verified_amount: number | null;
  provider: string | null;
};

/**
 * POST /receipts/{id}/verify — public, buyer-triggered, idempotent for
 * an already-verified receipt (safe to call every time this page
 * loads, per the endpoint's own docstring — it won't re-run the
 * pipeline or risk a duplicate-transaction false positive against
 * itself).
 */
export function verifyReceipt(receiptId: string): Promise<ReceiptVerifyResult> {
  return apiFetch<ReceiptVerifyResult>(
    `/receipts/${encodeURIComponent(receiptId)}/verify`,
    { method: "POST" },
  );
}

/** Mirrors backend/app/main.py's ReceiptDeliveryResponse. */
export type ReceiptDelivery = {
  receipt_id: string;
  product_id: string;
  drive_link: string;
};

/**
 * GET /receipts/{id}/delivery — only call after verifyReceipt() has
 * returned status "verified". The backend 403s ("Receipt is not
 * verified") for pending/rejected receipts rather than 404ing, so a
 * caller can tell "wrong state" apart from "no such receipt" — but
 * this function should simply not be called in that case; the status
 * page checks verify's own response first.
 */
export function getReceiptDelivery(receiptId: string): Promise<ReceiptDelivery> {
  return apiFetch<ReceiptDelivery>(
    `/receipts/${encodeURIComponent(receiptId)}/delivery`,
  );
}

/**
 * Human-readable text for each REASON_* code the backend can return
 * on a rejected receipt (see verify_receipt/validate_payment/
 * duplicate_check.py). Falls back to a generic message for any code
 * not listed here, so a future backend-added reason never renders as
 * literally undefined/blank.
 */
const REJECTION_REASONS: Record<string, string> = {
  fetch_failed: "We couldn't reach the receipt page. Double-check the URL and try again.",
  unsupported_provider: "This URL isn't a supported CBE or Telebirr receipt link.",
  not_found: "The receipt page didn't contain a recognizable transaction.",
  not_completed: "This transaction isn't marked as completed on the provider's page yet.",
  amount_missing: "We couldn't read a paid amount from the receipt.",
  amount_mismatch: "The paid amount doesn't match this product's price.",
  unknown_provider: "This payment provider isn't supported.",
  duplicate_transaction: "This transaction has already been used for another purchase.",
};

export function describeRejectionReason(reason: string | null): string {
  if (!reason) return "This receipt could not be verified.";
  return REJECTION_REASONS[reason] ?? "This receipt could not be verified.";
}

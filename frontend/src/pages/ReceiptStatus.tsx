import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  verifyReceipt,
  getReceiptDelivery,
  describeRejectionReason,
} from "../api/receipts";
import { ApiError } from "../api/client";

type State =
  | { status: "checking" }
  | { status: "not-found" }
  | { status: "error"; message: string }
  | { status: "rejected"; productId: string; reasonText: string }
  | { status: "verified-loading"; productId: string }
  | { status: "delivered"; productId: string; driveLink: string }
  | { status: "delivery-error"; productId: string; message: string };

/**
 * Task 54: receipt status + delivery link view. Calls the idempotent
 * POST /receipts/{id}/verify on load (safe to re-run — see its own
 * docstring), then, only if that comes back "verified", follows up
 * with GET /receipts/{id}/delivery for the seller's Drive link. A
 * rejected receipt shows a human-readable reason (see
 * describeRejectionReason) and a way back to resubmit, rather than a
 * raw backend reason code.
 */
function ReceiptStatus() {
  const { receiptId } = useParams();
  const [state, setState] = useState<State>({ status: "checking" });

  useEffect(() => {
    if (!receiptId) return;
    let cancelled = false;

    verifyReceipt(receiptId)
      .then((result) => {
        if (cancelled) return;
        if (result.status === "rejected") {
          setState({
            status: "rejected",
            productId: result.product_id,
            reasonText: describeRejectionReason(result.reason),
          });
          return;
        }
        setState({ status: "verified-loading", productId: result.product_id });
        return getReceiptDelivery(receiptId)
          .then((delivery) => {
            if (!cancelled) {
              setState({
                status: "delivered",
                productId: result.product_id,
                driveLink: delivery.drive_link,
              });
            }
          })
          .catch((err: unknown) => {
            if (cancelled) return;
            const message =
              err instanceof ApiError
                ? err.message
                : "Verified, but the download link couldn't be loaded. Try reloading this page.";
            setState({ status: "delivery-error", productId: result.product_id, message });
          });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ status: "not-found" });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not check this receipt. Check your connection and try again.";
        setState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [receiptId]);

  if (state.status === "checking" || state.status === "verified-loading") {
    return <p>Checking your receipt…</p>;
  }

  if (state.status === "not-found") {
    return (
      <div className="card">
        <p>We couldn't find a receipt with that reference.</p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="card" role="alert">
        <p>{state.message}</p>
      </div>
    );
  }

  if (state.status === "rejected") {
    return (
      <div className="card" role="alert">
        <p>{state.reasonText}</p>
        <p>
          <Link to={`/product/${state.productId}/buy`}>
            Go back and submit a corrected receipt
          </Link>
        </p>
      </div>
    );
  }

  if (state.status === "delivery-error") {
    return (
      <div className="card" role="alert">
        <p>Your payment is verified! {state.message}</p>
      </div>
    );
  }

  return (
    <div className="card" role="status">
      <p>Your payment is verified. Here's your download link:</p>
      <p>
        <a className="btn-primary btn-link" href={state.driveLink} target="_blank" rel="noreferrer">
          Open your download
        </a>
      </p>
      <p>
        <Link to={`/product/${state.productId}`}>Back to product</Link>
      </p>
    </div>
  );
}

export default ReceiptStatus;

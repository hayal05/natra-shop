import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { getPaymentInfo, submitReceipt, type PaymentInfo } from "../api/receipts";
import { ApiError } from "../api/client";

type InfoState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; info: PaymentInfo };

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string }
  | { status: "submitted"; receiptId: string };

/**
 * Task 53: Buy Now flow. Shows NATRA's own CBE/Telebirr account (never
 * a seller's — buyers pay NATRA directly, per ARCHITECTURE.md), then
 * lets the buyer paste a receipt URL. Stops at submission confirmation
 * — actually *verifying* the receipt (POST /receipts/{id}/verify) and
 * showing the delivery link belong to Task 54's status page, not this
 * form.
 */
function BuyNow() {
  const { productId } = useParams();
  const [infoState, setInfoState] = useState<InfoState>({ status: "loading" });
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle" });
  const [receiptUrl, setReceiptUrl] = useState("");

  useEffect(() => {
    let cancelled = false;

    getPaymentInfo()
      .then((info) => {
        if (!cancelled) setInfoState({ status: "ready", info });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load payment info. Check your connection and try again.";
        setInfoState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!productId) return;

    const trimmed = receiptUrl.trim();
    if (!trimmed) return;

    setSubmitState({ status: "submitting" });
    submitReceipt(productId, trimmed)
      .then((result) => {
        setSubmitState({ status: "submitted", receiptId: result.id });
      })
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not submit the receipt. Check your connection and try again.";
        setSubmitState({ status: "error", message });
      });
  }

  return (
    <div className="buy-now">
      <p>
        <Link to={`/product/${productId}`}>&larr; Back to product</Link>
      </p>
      <h1>Pay NATRA to complete your purchase</h1>

      {infoState.status === "loading" && <p>Loading payment details…</p>}

      {infoState.status === "error" && (
        <div className="card" role="alert">
          <p>{infoState.message}</p>
        </div>
      )}

      {infoState.status === "ready" && (
        <PaymentAccounts info={infoState.info} />
      )}

      <h2>Already paid? Submit your receipt</h2>

      {submitState.status === "submitted" ? (
        <div className="card" role="status">
          <p>
            Receipt submitted. Reference: <code>{submitState.receiptId}</code>
          </p>
          <p>
            <Link to={`/receipt/${submitState.receiptId}`}>
              Check verification status &rarr;
            </Link>
          </p>
        </div>
      ) : (
        <form className="card" onSubmit={handleSubmit}>
          <label htmlFor="receipt-url">Receipt URL</label>
          <input
            id="receipt-url"
            type="url"
            required
            placeholder="https://..."
            value={receiptUrl}
            onChange={(e) => setReceiptUrl(e.target.value)}
            disabled={submitState.status === "submitting"}
          />
          {submitState.status === "error" && (
            <p className="form-error" role="alert">
              {submitState.message}
            </p>
          )}
          <button
            className="btn-primary"
            type="submit"
            disabled={submitState.status === "submitting"}
          >
            {submitState.status === "submitting" ? "Submitting…" : "Submit receipt"}
          </button>
        </form>
      )}
    </div>
  );
}

function PaymentAccounts({ info }: { info: PaymentInfo }) {
  const hasCbe = info.cbe_account_name || info.cbe_account_number;
  const hasTelebirr = info.telebirr_account_name || info.telebirr_account_number;

  if (!hasCbe && !hasTelebirr) {
    return (
      <div className="card" role="alert">
        <p>
          Payment accounts haven't been configured yet. Please check back
          later.
        </p>
      </div>
    );
  }

  return (
    <div className="payment-accounts">
      {hasCbe && (
        <div className="card">
          <h3>CBE</h3>
          <p>{info.cbe_account_name ?? "—"}</p>
          <p>{info.cbe_account_number ?? "—"}</p>
        </div>
      )}
      {hasTelebirr && (
        <div className="card">
          <h3>Telebirr</h3>
          <p>{info.telebirr_account_name ?? "—"}</p>
          <p>{info.telebirr_account_number ?? "—"}</p>
        </div>
      )}
    </div>
  );
}

export default BuyNow;

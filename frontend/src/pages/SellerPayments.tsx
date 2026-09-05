import { Link, Navigate, useNavigate } from "react-router-dom";
import { useEffect, useState, type FormEvent } from "react";
import { getSellerSession, clearSellerSession } from "../lib/session";
import {
  getPaymentMethods,
  updatePaymentMethods,
  getEarnings,
  type SellerPaymentMethods,
  type SellerEarnings,
} from "../api/sellers";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type MethodsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; methods: SellerPaymentMethods };

type EarningsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; earnings: SellerEarnings };

type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "error"; message: string }
  | { status: "saved" };

const EMPTY_METHODS: SellerPaymentMethods = {
  cbe_account_name: "",
  cbe_account_number: "",
  telebirr_account_name: "",
  telebirr_account_number: "",
};

/**
 * Task 57: `/seller/payment-methods` — where NATRA will eventually
 * send this seller a settlement (`GET`/`PUT /sellers/payment-methods`)
 * plus a read-only earnings summary (`GET /sellers/earnings`). Two
 * independent loads on one page since they're both simple GETs the
 * seller wants to see together, not because either depends on the
 * other.
 *
 * Session handling matches SellerHome (Task 56): a 401/403 from any
 * of the three calls clears the session and redirects to
 * `/seller/login` instead of showing a raw error.
 */
function SellerPayments() {
  const navigate = useNavigate();
  const [session] = useState(getSellerSession());

  const [methodsState, setMethodsState] = useState<MethodsState>({
    status: "loading",
  });
  const [earningsState, setEarningsState] = useState<EarningsState>({
    status: "loading",
  });
  const [saveState, setSaveState] = useState<SaveState>({ status: "idle" });
  const [form, setForm] = useState<SellerPaymentMethods>(EMPTY_METHODS);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;

    function handleAuthError(err: unknown): boolean {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        clearSellerSession();
        navigate("/seller/login", { replace: true });
        return true;
      }
      return false;
    }

    getPaymentMethods(session.token)
      .then((methods) => {
        if (cancelled) return;
        setMethodsState({ status: "ready", methods });
        setForm({
          cbe_account_name: methods.cbe_account_name ?? "",
          cbe_account_number: methods.cbe_account_number ?? "",
          telebirr_account_name: methods.telebirr_account_name ?? "",
          telebirr_account_number: methods.telebirr_account_number ?? "",
        });
      })
      .catch((err: unknown) => {
        if (cancelled || handleAuthError(err)) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load your payment methods. Check your connection and try again.";
        setMethodsState({ status: "error", message });
      });

    getEarnings(session.token)
      .then((earnings) => {
        if (!cancelled) setEarningsState({ status: "ready", earnings });
      })
      .catch((err: unknown) => {
        if (cancelled || handleAuthError(err)) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load your earnings. Check your connection and try again.";
        setEarningsState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [session, navigate]);

  if (!session) {
    return <Navigate to="/seller" replace />;
  }

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;

    setSaveState({ status: "saving" });
    updatePaymentMethods(session.token, {
      cbe_account_name: form.cbe_account_name?.trim() ?? "",
      cbe_account_number: form.cbe_account_number?.trim() ?? "",
      telebirr_account_name: form.telebirr_account_name?.trim() ?? "",
      telebirr_account_number: form.telebirr_account_number?.trim() ?? "",
    })
      .then((methods) => {
        setMethodsState({ status: "ready", methods });
        setSaveState({ status: "saved" });
      })
      .catch((err: unknown) => {
        if (
          err instanceof ApiError &&
          (err.status === 401 || err.status === 403)
        ) {
          clearSellerSession();
          navigate("/seller/login", { replace: true });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not save your payment methods. Check your connection and try again.";
        setSaveState({ status: "error", message });
      });
  }

  function updateField(field: keyof SellerPaymentMethods, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (saveState.status === "saved") setSaveState({ status: "idle" });
  }

  return (
    <div className="seller-dashboard">
      <p>
        <Link to="/seller">&larr; Back to dashboard</Link>
      </p>
      <h1>Payment methods &amp; earnings</h1>

      <h2>Earnings</h2>
      {earningsState.status === "loading" && <p>Loading your earnings…</p>}
      {earningsState.status === "error" && (
        <div className="card" role="alert">
          <p>{earningsState.message}</p>
        </div>
      )}
      {earningsState.status === "ready" && (
        <EarningsSummary earnings={earningsState.earnings} />
      )}

      <h2>Payout account</h2>
      <p>
        This is where NATRA will send a future settlement. It's never shown
        to buyers, who always pay NATRA directly.
      </p>

      {methodsState.status === "loading" && <p>Loading your payout account…</p>}
      {methodsState.status === "error" && (
        <div className="card" role="alert">
          <p>{methodsState.message}</p>
        </div>
      )}

      {methodsState.status === "ready" && (
        <form className="card auth-form" onSubmit={handleSave}>
          <label htmlFor="cbe-account-name">CBE account name</label>
          <input
            id="cbe-account-name"
            type="text"
            value={form.cbe_account_name ?? ""}
            onChange={(e) => updateField("cbe_account_name", e.target.value)}
            disabled={saveState.status === "saving"}
          />

          <label htmlFor="cbe-account-number">CBE account number</label>
          <input
            id="cbe-account-number"
            type="text"
            value={form.cbe_account_number ?? ""}
            onChange={(e) => updateField("cbe_account_number", e.target.value)}
            disabled={saveState.status === "saving"}
          />

          <label htmlFor="telebirr-account-name">Telebirr account name</label>
          <input
            id="telebirr-account-name"
            type="text"
            value={form.telebirr_account_name ?? ""}
            onChange={(e) =>
              updateField("telebirr_account_name", e.target.value)
            }
            disabled={saveState.status === "saving"}
          />

          <label htmlFor="telebirr-account-number">
            Telebirr account number
          </label>
          <input
            id="telebirr-account-number"
            type="text"
            value={form.telebirr_account_number ?? ""}
            onChange={(e) =>
              updateField("telebirr_account_number", e.target.value)
            }
            disabled={saveState.status === "saving"}
          />

          {saveState.status === "error" && (
            <p className="form-error" role="alert">
              {saveState.message}
            </p>
          )}
          {saveState.status === "saved" && (
            <p role="status">Saved.</p>
          )}

          <button
            className="btn-primary"
            type="submit"
            disabled={saveState.status === "saving"}
          >
            {saveState.status === "saving" ? "Saving…" : "Save"}
          </button>
        </form>
      )}
    </div>
  );
}

function EarningsSummary({ earnings }: { earnings: SellerEarnings }) {
  return (
    <div className="earnings-summary">
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Total sales</p>
        <p className="earnings-summary__value">{earnings.total_sales}</p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Gross amount</p>
        <p className="earnings-summary__value">
          {formatPrice(earnings.gross_amount_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">NATRA commission</p>
        <p className="earnings-summary__value">
          {formatPrice(earnings.commission_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Your payable total</p>
        <p className="earnings-summary__value">
          {formatPrice(earnings.seller_payable_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Settled</p>
        <p className="earnings-summary__value">
          {formatPrice(earnings.settled_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Unsettled</p>
        <p className="earnings-summary__value">
          {formatPrice(earnings.unsettled_total)}
        </p>
      </div>
    </div>
  );
}

export default SellerPayments;

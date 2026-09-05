import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState, type FormEvent } from "react";
import { clearAdminSession, getAdminSession } from "../lib/adminSession";
import {
  createSettlement,
  completeSettlement,
  getSettlements,
  type Settlement,
} from "../api/admin";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type ListState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; settlements: Settlement[] };

type FormState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

// Tracks which single settlement row's "Mark completed" button is
// mid-request, so only that row shows a busy state and the others
// stay clickable — completing one settlement has no bearing on any
// other row.
type CompletingState = { id: string; status: "submitting" | "error" } | null;

/**
 * Task 61: `/admin-portal/settlements` — record that NATRA settled (or
 * intends to settle) an amount to a seller (`POST /admin/settlements`),
 * list every settlement platform-wide (`GET /admin/settlements`), and
 * mark a pending one completed once the admin has actually paid the
 * seller outside this system (`POST
 * /admin/settlements/{id}/complete`).
 *
 * There's no seller-picker here — NATRA has no "list sellers" endpoint
 * yet, so the admin pastes the seller ID shown in the products table
 * on `/admin-portal` (Task 59). The backend itself validates it (404
 * for an unknown seller, 422 if the amount exceeds that seller's
 * unsettled balance, per Task 42) and this form surfaces either error
 * as-is.
 *
 * Session/auth handling matches AdminHome/AdminSettings: a 401/403 on
 * any of the three calls clears the session and redirects to
 * `/admin-portal/login`.
 */
function AdminSettlements() {
  const navigate = useNavigate();
  const [session] = useState(getAdminSession());

  const [listState, setListState] = useState<ListState>({ status: "loading" });
  const [formState, setFormState] = useState<FormState>({ status: "idle" });
  const [completingState, setCompletingState] = useState<CompletingState>(null);
  const [sellerId, setSellerId] = useState("");
  const [amount, setAmount] = useState("");

  useEffect(() => {
    if (!session) {
      navigate("/admin-portal/login", { replace: true });
      return;
    }

    function handleAuthError(err: unknown): boolean {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        clearAdminSession();
        navigate("/admin-portal/login", { replace: true });
        return true;
      }
      return false;
    }

    let cancelled = false;
    setListState({ status: "loading" });
    getSettlements(session.token)
      .then((settlements) => {
        if (!cancelled) setListState({ status: "ready", settlements });
      })
      .catch((err: unknown) => {
        if (cancelled || handleAuthError(err)) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load settlements. Check your connection and try again.";
        setListState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [session, navigate]);

  if (!session) return null;

  function handleAuthError(err: unknown): boolean {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      clearAdminSession();
      navigate("/admin-portal/login", { replace: true });
      return true;
    }
    return false;
  }

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;

    const trimmedSellerId = sellerId.trim();
    const parsedAmount = Number(amount);
    if (!trimmedSellerId || !Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      return;
    }

    setFormState({ status: "submitting" });
    createSettlement(session.token, trimmedSellerId, parsedAmount)
      .then((settlement) => {
        setFormState({ status: "idle" });
        setSellerId("");
        setAmount("");
        setListState((prev) =>
          prev.status === "ready"
            ? { status: "ready", settlements: [settlement, ...prev.settlements] }
            : prev,
        );
      })
      .catch((err: unknown) => {
        if (handleAuthError(err)) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not record the settlement. Check your connection and try again.";
        setFormState({ status: "error", message });
      });
  }

  function handleComplete(settlementId: string) {
    if (!session) return;

    setCompletingState({ id: settlementId, status: "submitting" });
    completeSettlement(session.token, settlementId)
      .then((updated) => {
        setCompletingState(null);
        setListState((prev) =>
          prev.status === "ready"
            ? {
                status: "ready",
                settlements: prev.settlements.map((s) =>
                  s.id === updated.id ? updated : s,
                ),
              }
            : prev,
        );
      })
      .catch((err: unknown) => {
        if (handleAuthError(err)) return;
        setCompletingState({ id: settlementId, status: "error" });
      });
  }

  return (
    <div className="admin-dashboard">
      <p>
        <Link to="/admin-portal">&larr; Back to dashboard</Link>
      </p>
      <h1>Settlements</h1>

      <h2>Record a settlement</h2>
      <p>
        NATRA pays the seller manually, outside this system, then this
        form records that it happened (or is about to).
      </p>
      <form className="card auth-form" onSubmit={handleCreate}>
        <label htmlFor="settlement-seller-id">Seller ID</label>
        <input
          id="settlement-seller-id"
          type="text"
          required
          placeholder="32-character seller ID, from the products table"
          value={sellerId}
          onChange={(e) => setSellerId(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="settlement-amount">Amount (ETB)</label>
        <input
          id="settlement-amount"
          type="number"
          required
          min="0.01"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        {formState.status === "error" && (
          <p className="form-error" role="alert">
            {formState.message}
          </p>
        )}

        <button
          className="btn-primary"
          type="submit"
          disabled={formState.status === "submitting"}
        >
          {formState.status === "submitting" ? "Recording…" : "Record settlement"}
        </button>
      </form>

      <h2>All settlements</h2>

      {listState.status === "loading" && <p>Loading settlements…</p>}

      {listState.status === "error" && (
        <div className="card" role="alert">
          <p>{listState.message}</p>
        </div>
      )}

      {listState.status === "ready" && listState.settlements.length === 0 && (
        <p>No settlements have been recorded yet.</p>
      )}

      {listState.status === "ready" && listState.settlements.length > 0 && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Seller ID</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Created</th>
                <th>Completed</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {listState.settlements.map((settlement) => (
                <tr key={settlement.id}>
                  <td className="admin-table__mono">{settlement.seller_id}</td>
                  <td>{formatPrice(settlement.amount)}</td>
                  <td>{settlement.status}</td>
                  <td>{settlement.created_at}</td>
                  <td>
                    {settlement.completed_at ?? (
                      <span className="admin-table__muted">—</span>
                    )}
                  </td>
                  <td>
                    {settlement.status !== "completed" && (
                      <button
                        className="btn-primary"
                        type="button"
                        onClick={() => handleComplete(settlement.id)}
                        disabled={
                          completingState?.id === settlement.id &&
                          completingState.status === "submitting"
                        }
                      >
                        {completingState?.id === settlement.id &&
                        completingState.status === "submitting"
                          ? "Marking…"
                          : "Mark completed"}
                      </button>
                    )}
                    {completingState?.id === settlement.id &&
                      completingState.status === "error" && (
                        <p className="form-error" role="alert">
                          Could not mark this settlement completed. Try
                          again.
                        </p>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default AdminSettlements;

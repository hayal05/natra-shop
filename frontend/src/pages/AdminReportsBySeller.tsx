import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { clearAdminSession, getAdminSession } from "../lib/adminSession";
import {
  getAdminReportsBySeller,
  type AdminSellerReportItem,
} from "../api/admin";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type ListState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: AdminSellerReportItem[] };

/**
 * Task 63: `/admin-portal/reports/by-seller` — the per-seller
 * breakdown `GET /admin/reports/by-seller` deliberately left out of
 * Task 62's `AdminReports.tsx` (platform totals). Same six fields as
 * that page, one row per seller instead of one platform-wide row, in
 * the `.admin-table` style `AdminHome.tsx`'s products table already
 * uses (no new CSS). The backend already sorts by `unsettled_total`
 * descending and only includes sellers with at least one sale — both
 * surfaced as-is, no client-side sort/filter.
 *
 * Session/auth handling matches every other admin page: no session →
 * redirect to `/admin-portal/login`; a 401/403 from the fetch clears
 * the session and redirects there too.
 */
function AdminReportsBySeller() {
  const navigate = useNavigate();
  const [session] = useState(getAdminSession());
  const [listState, setListState] = useState<ListState>({ status: "loading" });

  useEffect(() => {
    if (!session) {
      navigate("/admin-portal/login", { replace: true });
      return;
    }

    let cancelled = false;
    setListState({ status: "loading" });
    getAdminReportsBySeller(session.token)
      .then((items) => {
        if (!cancelled) setListState({ status: "ready", items });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          clearAdminSession();
          navigate("/admin-portal/login", { replace: true });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load reports. Check your connection and try again.";
        setListState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [session, navigate]);

  if (!session) return null;

  return (
    <div className="admin-dashboard">
      <p>
        <Link to="/admin-portal/reports">&larr; Back to platform reports</Link>
      </p>
      <h1>Reports by seller</h1>

      {listState.status === "loading" && <p>Loading reports…</p>}

      {listState.status === "error" && (
        <div className="card" role="alert">
          <p>{listState.message}</p>
        </div>
      )}

      {listState.status === "ready" && listState.items.length === 0 && (
        <p>No seller has any recorded sales yet.</p>
      )}

      {listState.status === "ready" && listState.items.length > 0 && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Seller ID</th>
                <th>Sales</th>
                <th>Gross amount</th>
                <th>Commission</th>
                <th>Seller payable</th>
                <th>Settled</th>
                <th>Unsettled</th>
              </tr>
            </thead>
            <tbody>
              {listState.items.map((item) => (
                <tr key={item.seller_id}>
                  <td className="admin-table__mono">{item.seller_id}</td>
                  <td>{item.total_sales}</td>
                  <td>{formatPrice(item.gross_amount_total)}</td>
                  <td>{formatPrice(item.commission_total)}</td>
                  <td>{formatPrice(item.seller_payable_total)}</td>
                  <td>{formatPrice(item.settled_total)}</td>
                  <td>{formatPrice(item.unsettled_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default AdminReportsBySeller;

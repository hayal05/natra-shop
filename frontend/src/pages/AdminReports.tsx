import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { clearAdminSession, getAdminSession } from "../lib/adminSession";
import { getAdminReports, type AdminReports as AdminReportsData } from "../api/admin";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type ReportsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; reports: AdminReportsData };

/**
 * Task 62: `/admin-portal/reports` — platform-wide financial totals
 * (`GET /admin/reports`), the same six fields as sellers.ts's
 * SellerEarnings/SellerPayments.tsx's EarningsSummary, just summed
 * across every seller instead of one. Reuses the `.earnings-summary`
 * card grid as-is — same shape of data, just platform-wide instead of
 * per-seller.
 *
 * Per-seller breakdown (`GET /admin/reports/by-seller`) is Task 63,
 * linked below at `/admin-portal/reports/by-seller`
 * (`AdminReportsBySeller.tsx`).
 *
 * Session/auth handling matches every other admin page: no session →
 * redirect to `/admin-portal/login`; a 401/403 from the fetch clears
 * the session and redirects there too.
 */
function AdminReports() {
  const navigate = useNavigate();
  const [session] = useState(getAdminSession());
  const [reportsState, setReportsState] = useState<ReportsState>({
    status: "loading",
  });

  useEffect(() => {
    if (!session) {
      navigate("/admin-portal/login", { replace: true });
      return;
    }

    let cancelled = false;
    setReportsState({ status: "loading" });
    getAdminReports(session.token)
      .then((reports) => {
        if (!cancelled) setReportsState({ status: "ready", reports });
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
        setReportsState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [session, navigate]);

  if (!session) return null;

  return (
    <div className="admin-dashboard">
      <p>
        <Link to="/admin-portal">&larr; Back to dashboard</Link>
      </p>
      <h1>Platform reports</h1>

      {reportsState.status === "loading" && <p>Loading reports…</p>}

      {reportsState.status === "error" && (
        <div className="card" role="alert">
          <p>{reportsState.message}</p>
        </div>
      )}

      {reportsState.status === "ready" && (
        <ReportsSummary reports={reportsState.reports} />
      )}

      <p>
        <Link to="/admin-portal/reports/by-seller">
          View breakdown by seller &rarr;
        </Link>
      </p>
    </div>
  );
}

function ReportsSummary({ reports }: { reports: AdminReportsData }) {
  return (
    <div className="earnings-summary">
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Total sales</p>
        <p className="earnings-summary__value">{reports.total_sales}</p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Gross amount</p>
        <p className="earnings-summary__value">
          {formatPrice(reports.gross_amount_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">NATRA commission</p>
        <p className="earnings-summary__value">
          {formatPrice(reports.commission_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Seller payable total</p>
        <p className="earnings-summary__value">
          {formatPrice(reports.seller_payable_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Settled</p>
        <p className="earnings-summary__value">
          {formatPrice(reports.settled_total)}
        </p>
      </div>
      <div className="card earnings-summary__item">
        <p className="earnings-summary__label">Unsettled</p>
        <p className="earnings-summary__value">
          {formatPrice(reports.unsettled_total)}
        </p>
      </div>
    </div>
  );
}

export default AdminReports;

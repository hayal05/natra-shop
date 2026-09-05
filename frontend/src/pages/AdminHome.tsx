import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clearAdminSession, getAdminSession } from "../lib/adminSession";
import { getAdminProducts, type AdminProductItem } from "../api/admin";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type ListState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; products: AdminProductItem[] };

/**
 * `/admin-portal` index. Task 59: the platform-wide products overview
 * (`GET /admin/products`) — the first real admin dashboard view, now
 * that Task 58 has a session to gate it on. Settlements and reports
 * land in later tasks as their own sections/pages; settings (Task 60)
 * is now linked from here as its own page at `/admin-portal/settings`.
 *
 * Same 401/403-clears-session-and-redirects pattern as SellerHome —
 * an expired or wrong-role token isn't an "error" to show, it's just
 * "log in again".
 */
function AdminHome() {
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
    getAdminProducts(session.token)
      .then((products) => {
        if (!cancelled) setListState({ status: "ready", products });
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
            : "Could not load products. Check your connection and try again.";
        setListState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [session, navigate]);

  function handleLogout() {
    clearAdminSession();
    navigate("/admin-portal/login", { replace: true });
  }

  // Session check above redirects before first paint in practice, but
  // keeps TypeScript honest and avoids a flash of the table with no
  // token to have fetched it with.
  if (!session) return null;

  return (
    <div className="admin-dashboard">
      <div className="card">
        <h1>Admin dashboard</h1>
        <p>
          Logged in as <strong>{session.email}</strong>.
        </p>
        <p>
          <Link to="/admin-portal/settings">NATRA settings</Link>
          {" · "}
          <Link to="/admin-portal/settlements">Settlements</Link>
          {" · "}
          <Link to="/admin-portal/reports">Reports</Link>
        </p>
        <button className="btn-primary" onClick={handleLogout}>
          Log out
        </button>
      </div>

      <h2>All products</h2>

      {listState.status === "loading" && <p>Loading products…</p>}

      {listState.status === "error" && (
        <div className="card" role="alert">
          <p>{listState.message}</p>
        </div>
      )}

      {listState.status === "ready" && listState.products.length === 0 && (
        <p>No products have been listed yet.</p>
      )}

      {listState.status === "ready" && listState.products.length > 0 && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Price</th>
                <th>Description</th>
                <th>Seller ID</th>
                <th>Drive link</th>
              </tr>
            </thead>
            <tbody>
              {listState.products.map((product) => (
                <tr key={product.id}>
                  <td>{product.name}</td>
                  <td>{formatPrice(product.price)}</td>
                  <td className="admin-table__description">
                    {product.description || (
                      <span className="admin-table__muted">—</span>
                    )}
                  </td>
                  <td className="admin-table__mono">{product.seller_id}</td>
                  <td>
                    <a href={product.drive_link} target="_blank" rel="noreferrer">
                      Open
                    </a>
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

export default AdminHome;

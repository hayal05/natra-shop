import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { loginAdmin } from "../api/admin";
import { ApiError } from "../api/client";
import { getAdminSession, saveAdminSession } from "../lib/adminSession";

type FormState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

/**
 * Task 58: admin login. On success, stores the token (plus the typed
 * email, for display — same "server is the real source of truth"
 * convention as SellerLogin) and sends the admin to `/admin-portal`.
 * That index route is still Task 50's routing placeholder until the
 * real dashboard lands in Task 59 — this task is only the login form
 * and the POST /admin/login wiring, per PROJECT_ROADMAP.md's Phase 5
 * task order.
 */
function AdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formState, setFormState] = useState<FormState>({ status: "idle" });

  // Already logged in — no reason to show the form again.
  if (getAdminSession()) {
    return <Navigate to="/admin-portal" replace />;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) return;

    setFormState({ status: "submitting" });
    loginAdmin(trimmedEmail, password)
      .then((result) => {
        saveAdminSession({ token: result.access_token, email: trimmedEmail });
        navigate("/admin-portal", { replace: true });
      })
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not log in. Check your connection and try again.";
        setFormState({ status: "error", message });
      });
  }

  return (
    <div className="auth-page">
      <p>
        <Link to="/">&larr; Back to NATRA</Link>
      </p>
      <h1>Admin login</h1>

      <form className="card auth-form" onSubmit={handleSubmit}>
        <label htmlFor="admin-login-email">Email</label>
        <input
          id="admin-login-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="admin-login-password">Password</label>
        <input
          id="admin-login-password"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
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
          {formState.status === "submitting" ? "Logging in…" : "Log in"}
        </button>
      </form>

      {/* No "register" link — there is exactly one Master Admin
          identity, provisioned via env vars, never self-registered. */}
    </div>
  );
}

export default AdminLogin;

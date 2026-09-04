import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { loginSeller } from "../api/sellers";
import { ApiError } from "../api/client";
import { getSellerSession, saveSellerSession } from "../lib/session";

type FormState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string }
  | { status: "unverified"; email: string };

/**
 * Task 55: seller login. On success, stores the token (plus the typed
 * email, for display — see lib/session.ts) and sends the seller to
 * `/seller`, which shows the logged-in state until the real dashboard
 * lands in Task 56.
 *
 * Task 69: added a "Forgot password?" link to the new
 * `/seller/forgot-password` flow, and a one-time success banner when
 * arriving here straight from a completed reset (ForgotPassword.tsx
 * navigates here with `state: { passwordResetDone: true }` since its
 * own endpoint returns no session token to auto-log-in with).
 *
 * Task 71: `POST /sellers/login` now returns 403 (distinct from the
 * generic 401 for wrong credentials) when the credentials are correct
 * but `email_verified` is still 'N'. That's the one ApiError case this
 * form branches on specifically, rather than just showing
 * err.message like every other failure: a plain error message would
 * leave the seller stuck with no way forward, so this state instead
 * offers a direct link into `/seller/verify-email` (pre-filled with
 * the email they just typed) where they can enter or resend the code.
 */
function SellerLogin() {
  const navigate = useNavigate();
  const location = useLocation();
  const passwordResetDone = Boolean(
    (location.state as { passwordResetDone?: boolean } | null)?.passwordResetDone,
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formState, setFormState] = useState<FormState>({ status: "idle" });

  // Already logged in — no reason to show the form again.
  if (getSellerSession()) {
    return <Navigate to="/seller" replace />;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) return;

    setFormState({ status: "submitting" });
    loginSeller(trimmedEmail, password)
      .then((result) => {
        saveSellerSession({ token: result.access_token, email: trimmedEmail });
        navigate("/seller", { replace: true });
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 403) {
          setFormState({ status: "unverified", email: trimmedEmail });
          return;
        }
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
        <Link to="/seller">&larr; Back to seller area</Link>
      </p>
      <h1>Seller login</h1>

      {passwordResetDone && (
        <p className="form-success" role="status">
          Your password has been reset. Log in with your new password.
        </p>
      )}

      <form className="card auth-form" onSubmit={handleSubmit}>
        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="login-password">Password</label>
        <input
          id="login-password"
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

        {formState.status === "unverified" && (
          <p className="form-error" role="alert">
            Please verify your email before logging in.{" "}
            <Link
              to="/seller/verify-email"
              state={{ email: formState.email }}
            >
              Verify now
            </Link>
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

      <p>
        <Link to="/seller/forgot-password">Forgot password?</Link>
      </p>

      <p>
        Don't have a seller account? <Link to="/seller/register">Register</Link>
      </p>
    </div>
  );
}

export default SellerLogin;

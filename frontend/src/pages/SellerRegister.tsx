import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { registerSeller } from "../api/sellers";
import { ApiError } from "../api/client";
import { getSellerSession } from "../lib/session";

type FormState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

/**
 * Task 55: seller registration. Backend's `POST /sellers/register`
 * (min 8-char password, matching the form's own `minLength`) creates
 * the account but doesn't return a token.
 *
 * Task 69: on success, lands on `/seller/verify-email` (with the
 * just-registered email passed via router state) — `POST
 * /sellers/register` already fires the first verification-code email
 * (Task 68), so this is where the seller enters it.
 *
 * Task 71: no longer chains into `loginSeller()` after registering.
 * That auto-login used to work because `POST /sellers/login` didn't
 * check `email_verified`; now that it does (Task 71's backend
 * change), a freshly-registered account is unverified by definition
 * and that call would just fail with a 403. The seller instead lands
 * on `/seller/verify-email` logged out, verifies, and logs in
 * afterward — verifyEmail() there doesn't require a session, and a
 * real login attempt right after verifying will succeed normally.
 */
function SellerRegister() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formState, setFormState] = useState<FormState>({ status: "idle" });

  if (getSellerSession()) {
    return <Navigate to="/seller" replace />;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) return;

    if (password !== confirmPassword) {
      setFormState({ status: "error", message: "Passwords don't match." });
      return;
    }

    setFormState({ status: "submitting" });
    registerSeller(trimmedEmail, password)
      .then(() => {
        navigate("/seller/verify-email", {
          replace: true,
          state: { email: trimmedEmail },
        });
      })
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not register. Check your connection and try again.";
        setFormState({ status: "error", message });
      });
  }

  return (
    <div className="auth-page">
      <p>
        <Link to="/seller">&larr; Back to seller area</Link>
      </p>
      <h1>Seller registration</h1>

      <form className="card auth-form" onSubmit={handleSubmit}>
        <label htmlFor="register-email">Email</label>
        <input
          id="register-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="register-password">Password</label>
        <input
          id="register-password"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="register-confirm-password">Confirm password</label>
        <input
          id="register-confirm-password"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
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
          {formState.status === "submitting" ? "Registering…" : "Register"}
        </button>
      </form>

      <p>
        Already have a seller account? <Link to="/seller/login">Log in</Link>
      </p>
    </div>
  );
}

export default SellerRegister;

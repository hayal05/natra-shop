import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { verifyEmail, resendVerificationEmail } from "../api/sellers";
import { ApiError } from "../api/client";
import { getSellerSession } from "../lib/session";

type FormState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string }
  | { status: "verified" };

type ResendState =
  | { status: "idle" }
  | { status: "sending" }
  | { status: "sent" }
  | { status: "error"; message: string };

/**
 * Task 69: OTP-entry screen for Task 68's signup verification. Reads
 * the email to verify from router state — SellerRegister.tsx passes
 * it after a successful register — and falls back to asking for it
 * directly if the page is opened another way (e.g. a refresh, which
 * clears router state).
 *
 * Task 71: `POST /sellers/login` now requires `email_verified`, so
 * this screen is the real checkpoint a seller has to clear before
 * they can log in at all — SellerRegister.tsx no longer auto-logs-in,
 * so there's normally no session yet when this page is reached. The
 * "Skip for now" link to `/seller` is still here (a seller can always
 * come back and verify/log in later instead of finishing right now),
 * but it no longer implies unverified access to the dashboard the way
 * it did before Task 71 — `/seller` just shows the logged-out
 * login/register links until they actually verify and log in.
 */
function VerifyEmail() {
  const navigate = useNavigate();
  const location = useLocation();
  const stateEmail =
    (location.state as { email?: string } | null)?.email ?? "";

  const [email, setEmail] = useState(stateEmail);
  const [otp, setOtp] = useState("");
  const [formState, setFormState] = useState<FormState>({ status: "idle" });
  const [resendState, setResendState] = useState<ResendState>({ status: "idle" });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedEmail = email.trim();
    const trimmedOtp = otp.trim();
    if (!trimmedEmail || trimmedOtp.length !== 6) return;

    setFormState({ status: "submitting" });
    verifyEmail(trimmedEmail, trimmedOtp)
      .then(() => setFormState({ status: "verified" }))
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not verify your email. Check your connection and try again.";
        setFormState({ status: "error", message });
      });
  }

  function handleResend() {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) return;

    setResendState({ status: "sending" });
    resendVerificationEmail(trimmedEmail)
      .then(() => setResendState({ status: "sent" }))
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not resend the code. Check your connection and try again.";
        setResendState({ status: "error", message });
      });
  }

  if (formState.status === "verified") {
    return (
      <div className="auth-page">
        <div className="card" role="status">
          <p className="form-success">Your email is verified.</p>
          {getSellerSession() ? (
            <p>
              <Link className="btn-primary btn-link" to="/seller">
                Continue to your dashboard
              </Link>
            </p>
          ) : (
            <p>
              <Link className="btn-primary btn-link" to="/seller/login">
                Continue to log in
              </Link>
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <p>
        <Link to="/seller">&larr; Back to seller area</Link>
      </p>
      <h1>Verify your email</h1>
      <p>
        Enter the 6-digit code we emailed to your address. It expires 10
        minutes after being sent.
      </p>

      <form className="card auth-form" onSubmit={handleSubmit}>
        <label htmlFor="verify-email-address">Email</label>
        <input
          id="verify-email-address"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="verify-email-otp">Verification code</label>
        <input
          id="verify-email-otp"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          minLength={6}
          maxLength={6}
          pattern="[0-9]{6}"
          value={otp}
          onChange={(e) => setOtp(e.target.value.replace(/[^0-9]/g, ""))}
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
          {formState.status === "submitting" ? "Verifying…" : "Verify email"}
        </button>
      </form>

      <p>
        Didn't get a code?{" "}
        <button
          type="button"
          className="btn-text"
          onClick={handleResend}
          disabled={resendState.status === "sending" || !email.trim()}
        >
          {resendState.status === "sending" ? "Sending…" : "Resend code"}
        </button>
      </p>
      {resendState.status === "sent" && (
        <p className="form-success" role="status">
          If that email needs verification, a new code has been sent.
        </p>
      )}
      {resendState.status === "error" && (
        <p className="form-error" role="alert">
          {resendState.message}
        </p>
      )}

      <p>
        <Link to="/seller">Skip for now</Link>
      </p>
    </div>
  );
}

export default VerifyEmail;

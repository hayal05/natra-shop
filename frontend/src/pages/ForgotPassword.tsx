import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { requestPasswordReset, confirmPasswordReset } from "../api/sellers";
import { ApiError } from "../api/client";

type Step =
  | { step: "request" }
  | { step: "confirm"; infoMessage: string };

type FormState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

/**
 * Task 69: frontend for Task 68's password-reset OTP endpoints.
 * Two steps in one page rather than two routes, since the second step
 * is meaningless without having just completed the first (there's
 * nothing to navigate back to or bookmark independently):
 *
 * 1. Email only -> POST /sellers/password-reset/request. Always
 *    succeeds with the same generic message (anti-enumeration — see
 *    api/sellers.ts), so this step always advances to step 2
 *    regardless of whether the email is actually registered.
 * 2. Code + new password -> POST /sellers/password-reset/confirm. On
 *    success, sends the seller to /seller/login to sign in with the
 *    new password (this endpoint doesn't return a session token, so
 *    there's nothing to auto-log-in with, unlike SellerRegister.tsx).
 */
function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [step, setStep] = useState<Step>({ step: "request" });
  const [formState, setFormState] = useState<FormState>({ status: "idle" });

  function handleRequestSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) return;

    setFormState({ status: "submitting" });
    requestPasswordReset(trimmedEmail)
      .then((result) => {
        setFormState({ status: "idle" });
        setStep({ step: "confirm", infoMessage: result.message });
      })
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not request a reset code. Check your connection and try again.";
        setFormState({ status: "error", message });
      });
  }

  function handleConfirmSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedEmail = email.trim();
    const trimmedOtp = otp.trim();
    if (!trimmedEmail || trimmedOtp.length !== 6 || !newPassword) return;

    if (newPassword !== confirmNewPassword) {
      setFormState({ status: "error", message: "Passwords don't match." });
      return;
    }

    setFormState({ status: "submitting" });
    confirmPasswordReset(trimmedEmail, trimmedOtp, newPassword)
      .then(() => {
        navigate("/seller/login", {
          replace: true,
          state: { passwordResetDone: true },
        });
      })
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not reset your password. Check your connection and try again.";
        setFormState({ status: "error", message });
      });
  }

  return (
    <div className="auth-page">
      <p>
        <Link to="/seller/login">&larr; Back to log in</Link>
      </p>
      <h1>Reset your password</h1>

      {step.step === "request" && (
        <form className="card auth-form" onSubmit={handleRequestSubmit}>
          <p>Enter your account email and we'll send you a reset code.</p>

          <label htmlFor="forgot-password-email">Email</label>
          <input
            id="forgot-password-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
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
            {formState.status === "submitting" ? "Sending…" : "Send reset code"}
          </button>
        </form>
      )}

      {step.step === "confirm" && (
        <>
          <p className="form-success" role="status">
            {step.infoMessage}
          </p>
          <form className="card auth-form" onSubmit={handleConfirmSubmit}>
            <label htmlFor="forgot-password-otp">Reset code</label>
            <input
              id="forgot-password-otp"
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

            <label htmlFor="forgot-password-new">New password</label>
            <input
              id="forgot-password-new"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={formState.status === "submitting"}
            />

            <label htmlFor="forgot-password-confirm">Confirm new password</label>
            <input
              id="forgot-password-confirm"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={confirmNewPassword}
              onChange={(e) => setConfirmNewPassword(e.target.value)}
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
              {formState.status === "submitting" ? "Resetting…" : "Reset password"}
            </button>
          </form>

          <p>
            Didn't get a code?{" "}
            <button
              type="button"
              className="btn-text"
              onClick={() => setStep({ step: "request" })}
              disabled={formState.status === "submitting"}
            >
              Start over
            </button>
          </p>
        </>
      )}
    </div>
  );
}

export default ForgotPassword;

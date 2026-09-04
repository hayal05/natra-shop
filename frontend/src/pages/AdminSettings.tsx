import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState, type FormEvent } from "react";
import { clearAdminSession, getAdminSession } from "../lib/adminSession";
import {
  getAdminSettings,
  updateAdminSettings,
  type AdminSettings as AdminSettingsData,
} from "../api/admin";
import { ApiError } from "../api/client";

type SettingsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; settings: AdminSettingsData };

type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "error"; message: string }
  | { status: "saved" };

const EMPTY_FORM: AdminSettingsData = {
  cbe_account_name: "",
  cbe_account_number: "",
  telebirr_account_name: "",
  telebirr_account_number: "",
  commission_rate: 0,
};

/**
 * Task 60: `/admin-portal/settings` — NATRA's own CBE/Telebirr payment
 * account info (what buyers see and pay into after "Buy Now", per
 * PaymentInfoResponse/GET /payment-info) plus the platform commission
 * rate, both admin-only (`GET`/`PUT /admin/settings`). One combined
 * form since both live on the same backend row and the admin manages
 * them together.
 *
 * Session/auth handling matches AdminHome (Task 59): a 401/403 clears
 * the session and redirects to `/admin-portal/login` instead of
 * showing a raw error, on both the initial load and on save.
 */
function AdminSettings() {
  const navigate = useNavigate();
  const [session] = useState(getAdminSession());

  const [settingsState, setSettingsState] = useState<SettingsState>({
    status: "loading",
  });
  const [saveState, setSaveState] = useState<SaveState>({ status: "idle" });
  const [form, setForm] = useState<AdminSettingsData>(EMPTY_FORM);

  useEffect(() => {
    if (!session) {
      navigate("/admin-portal/login", { replace: true });
      return;
    }

    let cancelled = false;
    setSettingsState({ status: "loading" });
    getAdminSettings(session.token)
      .then((settings) => {
        if (cancelled) return;
        setSettingsState({ status: "ready", settings });
        setForm({
          cbe_account_name: settings.cbe_account_name ?? "",
          cbe_account_number: settings.cbe_account_number ?? "",
          telebirr_account_name: settings.telebirr_account_name ?? "",
          telebirr_account_number: settings.telebirr_account_number ?? "",
          commission_rate: settings.commission_rate,
        });
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
            : "Could not load settings. Check your connection and try again.";
        setSettingsState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [session, navigate]);

  if (!session) return null;

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;

    setSaveState({ status: "saving" });
    updateAdminSettings(session.token, {
      cbe_account_name: form.cbe_account_name?.trim() ?? "",
      cbe_account_number: form.cbe_account_number?.trim() ?? "",
      telebirr_account_name: form.telebirr_account_name?.trim() ?? "",
      telebirr_account_number: form.telebirr_account_number?.trim() ?? "",
      commission_rate: form.commission_rate,
    })
      .then((settings) => {
        setSettingsState({ status: "ready", settings });
        setSaveState({ status: "saved" });
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          clearAdminSession();
          navigate("/admin-portal/login", { replace: true });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not save settings. Check your connection and try again.";
        setSaveState({ status: "error", message });
      });
  }

  function updateField(field: keyof AdminSettingsData, value: string) {
    setForm((prev) => ({
      ...prev,
      [field]: field === "commission_rate" ? Number(value) : value,
    }));
    if (saveState.status === "saved") setSaveState({ status: "idle" });
  }

  return (
    <div className="admin-dashboard">
      <p>
        <Link to="/admin-portal">&larr; Back to dashboard</Link>
      </p>
      <h1>NATRA settings</h1>

      {settingsState.status === "loading" && <p>Loading settings…</p>}
      {settingsState.status === "error" && (
        <div className="card" role="alert">
          <p>{settingsState.message}</p>
        </div>
      )}

      {settingsState.status === "ready" && (
        <form className="card auth-form" onSubmit={handleSave}>
          <h2>Payment account shown to buyers</h2>
          <p>
            This is NATRA's own CBE/Telebirr account — buyers pay this
            directly, never a seller's account.
          </p>

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

          <h2>Commission</h2>
          <p>Percentage of each sale NATRA keeps; the rest is seller payable.</p>

          <label htmlFor="commission-rate">Commission rate (%)</label>
          <input
            id="commission-rate"
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={form.commission_rate}
            onChange={(e) => updateField("commission_rate", e.target.value)}
            disabled={saveState.status === "saving"}
          />

          {saveState.status === "error" && (
            <p className="form-error" role="alert">
              {saveState.message}
            </p>
          )}
          {saveState.status === "saved" && <p role="status">Saved.</p>}

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

export default AdminSettings;

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import {
  ADMIN_LOGIN_PLACEHOLDER,
  ADMIN_SESSION_STORAGE_KEY,
  renderAdminDashboardPage,
  seedAdminSession,
} from "./adminDashboardTestRouter";

const { getAdminSettings, updateAdminSettings } = vi.hoisted(() => ({
  getAdminSettings: vi.fn(),
  updateAdminSettings: vi.fn(),
}));
vi.mock("../api/admin", () => ({ getAdminSettings, updateAdminSettings }));

const SESSION = { token: "tok123", email: "admin@example.com" };

const SAMPLE_SETTINGS = {
  cbe_account_name: "NATRA Ltd",
  cbe_account_number: "1000999888",
  telebirr_account_name: null,
  telebirr_account_number: null,
  commission_rate: 10,
};

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

/** Renders with the load resolved, and waits for the form to appear. */
async function renderReady() {
  seedAdminSession(SESSION);
  getAdminSettings.mockResolvedValueOnce(SAMPLE_SETTINGS);

  renderAdminDashboardPage({ route: "/admin-portal/settings" });
  await screen.findByLabelText("CBE account name");
}

describe("AdminSettings", () => {
  it("redirects to /admin-portal/login when there is no session", () => {
    renderAdminDashboardPage({ route: "/admin-portal/settings" });

    expect(screen.getByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(getAdminSettings).not.toHaveBeenCalled();
  });

  it("loads and shows the settings form, nulls rendered as blank", async () => {
    await renderReady();

    expect(getAdminSettings).toHaveBeenCalledWith("tok123");
    expect(screen.getByLabelText("CBE account name")).toHaveValue("NATRA Ltd");
    expect(screen.getByLabelText("CBE account number")).toHaveValue("1000999888");
    expect(screen.getByLabelText("Telebirr account name")).toHaveValue("");
    expect(screen.getByLabelText("Telebirr account number")).toHaveValue("");
    expect(screen.getByLabelText("Commission rate (%)")).toHaveValue(10);
  });

  it("shows the backend's message on a non-auth ApiError loading settings", async () => {
    seedAdminSession(SESSION);
    getAdminSettings.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/settings" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("clears the session and redirects to /admin-portal/login on a 401 loading settings", async () => {
    seedAdminSession(SESSION);
    getAdminSettings.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/settings" });

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("saves the form and shows a saved confirmation", async () => {
    await renderReady();
    updateAdminSettings.mockResolvedValueOnce({
      ...SAMPLE_SETTINGS,
      telebirr_account_name: "NATRA Ltd",
      telebirr_account_number: "0911223344",
    });
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Telebirr account name"), "NATRA Ltd");
    await user.type(screen.getByLabelText("Telebirr account number"), "0911223344");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateAdminSettings).toHaveBeenCalledWith("tok123", {
      cbe_account_name: "NATRA Ltd",
      cbe_account_number: "1000999888",
      telebirr_account_name: "NATRA Ltd",
      telebirr_account_number: "0911223344",
      commission_rate: 10,
    });
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("clears the 'Saved.' confirmation as soon as a field is edited again", async () => {
    await renderReady();
    updateAdminSettings.mockResolvedValueOnce(SAMPLE_SETTINGS);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved.");

    await user.type(screen.getByLabelText("CBE account name"), "!");

    expect(screen.queryByText("Saved.")).not.toBeInTheDocument();
  });

  it("clears the session and redirects to /admin-portal/login on a 401 saving", async () => {
    await renderReady();
    updateAdminSettings.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("shows the backend's message when saving fails (non-auth error)", async () => {
    await renderReady();
    updateAdminSettings.mockRejectedValueOnce(
      new ApiError(422, { detail: "commission_rate must be between 0 and 100" }, "commission_rate must be between 0 and 100"),
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "commission_rate must be between 0 and 100",
    );
  });
});

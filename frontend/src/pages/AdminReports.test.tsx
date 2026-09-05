import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { ApiError } from "../api/client";
import {
  ADMIN_LOGIN_PLACEHOLDER,
  ADMIN_SESSION_STORAGE_KEY,
  renderAdminDashboardPage,
  seedAdminSession,
} from "./adminDashboardTestRouter";

const { getAdminReports } = vi.hoisted(() => ({ getAdminReports: vi.fn() }));
vi.mock("../api/admin", () => ({ getAdminReports }));

const SESSION = { token: "tok123", email: "admin@example.com" };

const SAMPLE_REPORTS = {
  total_sales: 12,
  gross_amount_total: 6000,
  commission_total: 600,
  seller_payable_total: 5400,
  settled_total: 2000,
  unsettled_total: 3400,
};

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("AdminReports", () => {
  it("redirects to /admin-portal/login when there is no session", () => {
    renderAdminDashboardPage({ route: "/admin-portal/reports" });

    expect(screen.getByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(getAdminReports).not.toHaveBeenCalled();
  });

  it("loads and shows the platform totals summary and the by-seller link", async () => {
    seedAdminSession(SESSION);
    getAdminReports.mockResolvedValueOnce(SAMPLE_REPORTS);

    renderAdminDashboardPage({ route: "/admin-portal/reports" });

    expect(screen.getByText("Loading reports…")).toBeInTheDocument();
    expect(getAdminReports).toHaveBeenCalledWith("tok123");

    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("6000.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("600.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("5400.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("2000.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("3400.00 ETB")).toBeInTheDocument();

    expect(
      screen.getByRole("link", { name: /view breakdown by seller/i }),
    ).toHaveAttribute("href", "/admin-portal/reports/by-seller");
  });

  it("shows the by-seller link even while the summary failed to load", async () => {
    seedAdminSession(SESSION);
    getAdminReports.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/reports" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
    expect(
      screen.getByRole("link", { name: /view breakdown by seller/i }),
    ).toHaveAttribute("href", "/admin-portal/reports/by-seller");
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    seedAdminSession(SESSION);
    getAdminReports.mockRejectedValueOnce(new Error("network down"));

    renderAdminDashboardPage({ route: "/admin-portal/reports" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load reports. Check your connection and try again.",
    );
  });

  it("clears the session and redirects to /admin-portal/login on a 401", async () => {
    seedAdminSession(SESSION);
    getAdminReports.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/reports" });

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });
});

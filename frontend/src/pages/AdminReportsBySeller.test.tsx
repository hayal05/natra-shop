import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { ApiError } from "../api/client";
import {
  ADMIN_LOGIN_PLACEHOLDER,
  ADMIN_SESSION_STORAGE_KEY,
  renderAdminDashboardPage,
  seedAdminSession,
} from "./adminDashboardTestRouter";

const { getAdminReportsBySeller } = vi.hoisted(() => ({
  getAdminReportsBySeller: vi.fn(),
}));
vi.mock("../api/admin", () => ({ getAdminReportsBySeller }));

const SESSION = { token: "tok123", email: "admin@example.com" };

const SAMPLE_ITEM = {
  seller_id: "seller-1",
  total_sales: 4,
  gross_amount_total: 600,
  commission_total: 60,
  seller_payable_total: 540,
  settled_total: 200,
  unsettled_total: 340,
};

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("AdminReportsBySeller", () => {
  it("redirects to /admin-portal/login when there is no session", () => {
    renderAdminDashboardPage({ route: "/admin-portal/reports/by-seller" });

    expect(screen.getByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(getAdminReportsBySeller).not.toHaveBeenCalled();
  });

  it("loads and shows one row per seller, and links back to platform reports", async () => {
    seedAdminSession(SESSION);
    getAdminReportsBySeller.mockResolvedValueOnce([SAMPLE_ITEM]);

    renderAdminDashboardPage({ route: "/admin-portal/reports/by-seller" });

    expect(screen.getByText("Loading reports…")).toBeInTheDocument();
    expect(getAdminReportsBySeller).toHaveBeenCalledWith("tok123");

    const sellerCell = await screen.findByText("seller-1");
    const row = sellerCell.closest("tr")!;
    expect(within(row).getByText("4")).toBeInTheDocument();
    expect(within(row).getByText("600.00 ETB")).toBeInTheDocument();
    expect(within(row).getByText("60.00 ETB")).toBeInTheDocument();
    expect(within(row).getByText("540.00 ETB")).toBeInTheDocument();
    expect(within(row).getByText("200.00 ETB")).toBeInTheDocument();
    expect(within(row).getByText("340.00 ETB")).toBeInTheDocument();

    expect(
      screen.getByRole("link", { name: /back to platform reports/i }),
    ).toHaveAttribute("href", "/admin-portal/reports");
  });

  it("shows an empty-state message when no seller has any sales", async () => {
    seedAdminSession(SESSION);
    getAdminReportsBySeller.mockResolvedValueOnce([]);

    renderAdminDashboardPage({ route: "/admin-portal/reports/by-seller" });

    expect(
      await screen.findByText("No seller has any recorded sales yet."),
    ).toBeInTheDocument();
  });

  it("shows the backend's message on a non-auth ApiError", async () => {
    seedAdminSession(SESSION);
    getAdminReportsBySeller.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/reports/by-seller" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    seedAdminSession(SESSION);
    getAdminReportsBySeller.mockRejectedValueOnce(new Error("network down"));

    renderAdminDashboardPage({ route: "/admin-portal/reports/by-seller" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load reports. Check your connection and try again.",
    );
  });

  it("clears the session and redirects to /admin-portal/login on a 401", async () => {
    seedAdminSession(SESSION);
    getAdminReportsBySeller.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/reports/by-seller" });

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });
});

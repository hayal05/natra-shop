import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import {
  ADMIN_LOGIN_PLACEHOLDER,
  ADMIN_SESSION_STORAGE_KEY,
  renderAdminDashboardPage,
  seedAdminSession,
} from "./adminDashboardTestRouter";

const { getSettlements, createSettlement, completeSettlement } = vi.hoisted(() => ({
  getSettlements: vi.fn(),
  createSettlement: vi.fn(),
  completeSettlement: vi.fn(),
}));
vi.mock("../api/admin", () => ({ getSettlements, createSettlement, completeSettlement }));

const SESSION = { token: "tok123", email: "admin@example.com" };

const PENDING_SETTLEMENT = {
  id: "settle-1",
  seller_id: "seller-1",
  amount: 450,
  status: "pending",
  created_at: "2026-01-01T00:00:00Z",
  completed_at: null,
};

const COMPLETED_SETTLEMENT = {
  id: "settle-2",
  seller_id: "seller-2",
  amount: 900,
  status: "completed",
  created_at: "2026-01-01T00:00:00Z",
  completed_at: "2026-01-02T00:00:00Z",
};

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

async function fillAndSubmitSettlement(sellerId: string, amount: string) {
  const user = userEvent.setup();
  if (sellerId) {
    await user.type(screen.getByLabelText("Seller ID"), sellerId);
  }
  if (amount) {
    await user.type(screen.getByLabelText("Amount (ETB)"), amount);
  }
  await user.click(screen.getByRole("button", { name: "Record settlement" }));
}

describe("AdminSettlements", () => {
  it("redirects to /admin-portal/login when there is no session", () => {
    renderAdminDashboardPage({ route: "/admin-portal/settlements" });

    expect(screen.getByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(getSettlements).not.toHaveBeenCalled();
  });

  it("loads and shows the settlements table", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([PENDING_SETTLEMENT, COMPLETED_SETTLEMENT]);

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });

    expect(screen.getByText("Loading settlements…")).toBeInTheDocument();
    expect(getSettlements).toHaveBeenCalledWith("tok123");

    const pendingCell = await screen.findByText("seller-1");
    const pendingRow = pendingCell.closest("tr")!;
    expect(within(pendingRow).getByText("450.00 ETB")).toBeInTheDocument();
    expect(within(pendingRow).getByText("pending")).toBeInTheDocument();
    expect(within(pendingRow).getByText("—")).toBeInTheDocument();
    expect(
      within(pendingRow).getByRole("button", { name: "Mark completed" }),
    ).toBeInTheDocument();

    const completedRow = screen.getByText("seller-2").closest("tr")!;
    expect(within(completedRow).getByText("900.00 ETB")).toBeInTheDocument();
    expect(within(completedRow).getByText("2026-01-02T00:00:00Z")).toBeInTheDocument();
    expect(
      within(completedRow).queryByRole("button", { name: "Mark completed" }),
    ).not.toBeInTheDocument();
  });

  it("shows an empty-state message when there are no settlements", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([]);

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });

    expect(
      await screen.findByText("No settlements have been recorded yet."),
    ).toBeInTheDocument();
  });

  it("clears the session and redirects to /admin-portal/login on a 401 loading settlements", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("does not submit the record-settlement form with no seller ID or amount entered", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([]);

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });
    await screen.findByText("No settlements have been recorded yet.");

    await fillAndSubmitSettlement("", "");

    expect(createSettlement).not.toHaveBeenCalled();
  });

  it("records a settlement, prepends it to the list, and clears the form", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([]);
    createSettlement.mockResolvedValueOnce(PENDING_SETTLEMENT);

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });
    await screen.findByText("No settlements have been recorded yet.");

    await fillAndSubmitSettlement("  seller-1  ", "450");

    expect(createSettlement).toHaveBeenCalledWith("tok123", "seller-1", 450);
    expect(await screen.findByText("seller-1")).toBeInTheDocument();
    expect(screen.getByLabelText("Seller ID")).toHaveValue("");
    expect(screen.getByLabelText("Amount (ETB)")).toHaveValue(null);
  });

  it("clears the session and redirects to /admin-portal/login on a 401 recording a settlement", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([]);
    createSettlement.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });
    await screen.findByText("No settlements have been recorded yet.");

    await fillAndSubmitSettlement("seller-1", "450");

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("shows the backend's message when recording a settlement fails (non-auth error)", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([]);
    createSettlement.mockRejectedValueOnce(
      new ApiError(422, { detail: "amount exceeds unsettled balance" }, "amount exceeds unsettled balance"),
    );

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });
    await screen.findByText("No settlements have been recorded yet.");

    await fillAndSubmitSettlement("seller-1", "450");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "amount exceeds unsettled balance",
    );
  });

  it("marks a settlement completed and updates that row in place", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([PENDING_SETTLEMENT]);
    completeSettlement.mockResolvedValueOnce({
      ...PENDING_SETTLEMENT,
      status: "completed",
      completed_at: "2026-01-03T00:00:00Z",
    });
    const user = userEvent.setup();

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });
    await screen.findByText("seller-1");

    await user.click(screen.getByRole("button", { name: "Mark completed" }));

    expect(completeSettlement).toHaveBeenCalledWith("tok123", "settle-1");
    expect(await screen.findByText("2026-01-03T00:00:00Z")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Mark completed" }),
    ).not.toBeInTheDocument();
  });

  it("clears the session and redirects to /admin-portal/login on a 401 completing a settlement", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([PENDING_SETTLEMENT]);
    completeSettlement.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );
    const user = userEvent.setup();

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });
    await screen.findByText("seller-1");

    await user.click(screen.getByRole("button", { name: "Mark completed" }));

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("shows an inline error and keeps the row completable on a non-auth complete failure", async () => {
    seedAdminSession(SESSION);
    getSettlements.mockResolvedValueOnce([PENDING_SETTLEMENT]);
    completeSettlement.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );
    const user = userEvent.setup();

    renderAdminDashboardPage({ route: "/admin-portal/settlements" });
    await screen.findByText("seller-1");

    await user.click(screen.getByRole("button", { name: "Mark completed" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not mark this settlement completed. Try again.",
    );
    expect(screen.getByRole("button", { name: "Mark completed" })).toBeInTheDocument();
  });
});

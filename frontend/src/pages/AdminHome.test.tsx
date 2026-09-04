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

const { getAdminProducts } = vi.hoisted(() => ({ getAdminProducts: vi.fn() }));
vi.mock("../api/admin", () => ({ getAdminProducts }));

const SESSION = { token: "tok123", email: "admin@example.com" };

const SAMPLE_PRODUCT = {
  id: "prod-1",
  seller_id: "seller-1",
  name: "E-book: Learn Amharic",
  price: 150,
  description: "A beginner's guide.",
  thumbnail_ref: null,
  drive_link: "https://drive.google.com/file/d/abc",
};

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("AdminHome", () => {
  it("redirects to /admin-portal/login when there is no session", () => {
    renderAdminDashboardPage({ route: "/admin-portal" });

    expect(screen.getByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(getAdminProducts).not.toHaveBeenCalled();
  });

  it("loads and shows the products table", async () => {
    seedAdminSession(SESSION);
    getAdminProducts.mockResolvedValueOnce([SAMPLE_PRODUCT]);

    renderAdminDashboardPage({ route: "/admin-portal" });

    expect(screen.getByText("Loading products…")).toBeInTheDocument();
    expect(getAdminProducts).toHaveBeenCalledWith("tok123");

    const nameCell = await screen.findByText("E-book: Learn Amharic");
    const row = nameCell.closest("tr")!;
    expect(within(row).getByText("150.00 ETB")).toBeInTheDocument();
    expect(within(row).getByText("A beginner's guide.")).toBeInTheDocument();
    expect(within(row).getByText("seller-1")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "https://drive.google.com/file/d/abc",
    );
  });

  it("shows a muted dash instead of a blank description cell", async () => {
    seedAdminSession(SESSION);
    getAdminProducts.mockResolvedValueOnce([{ ...SAMPLE_PRODUCT, description: "" }]);

    renderAdminDashboardPage({ route: "/admin-portal" });

    const nameCell = await screen.findByText("E-book: Learn Amharic");
    const row = nameCell.closest("tr")!;
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("shows an empty-state message when there are no products", async () => {
    seedAdminSession(SESSION);
    getAdminProducts.mockResolvedValueOnce([]);

    renderAdminDashboardPage({ route: "/admin-portal" });

    expect(
      await screen.findByText("No products have been listed yet."),
    ).toBeInTheDocument();
  });

  it("shows the backend's message on a non-auth ApiError", async () => {
    seedAdminSession(SESSION);
    getAdminProducts.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderAdminDashboardPage({ route: "/admin-portal" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    seedAdminSession(SESSION);
    getAdminProducts.mockRejectedValueOnce(new Error("network down"));

    renderAdminDashboardPage({ route: "/admin-portal" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load products. Check your connection and try again.",
    );
  });

  it("clears the session and redirects to /admin-portal/login on a 401", async () => {
    seedAdminSession(SESSION);
    getAdminProducts.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderAdminDashboardPage({ route: "/admin-portal" });

    expect(await screen.findByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("logs out and redirects to /admin-portal/login", async () => {
    seedAdminSession(SESSION);
    getAdminProducts.mockResolvedValueOnce([]);
    const user = userEvent.setup();

    renderAdminDashboardPage({ route: "/admin-portal" });
    await screen.findByText("No products have been listed yet.");

    await user.click(screen.getByRole("button", { name: "Log out" }));

    expect(screen.getByText(ADMIN_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { seedSellerSession, SELLER_SESSION_STORAGE_KEY } from "./authTestRouter";
import {
  renderSellerDashboardPage,
  SELLER_LOGIN_PLACEHOLDER,
} from "./sellerDashboardTestRouter";

const { getPaymentMethods, updatePaymentMethods, getEarnings } = vi.hoisted(() => ({
  getPaymentMethods: vi.fn(),
  updatePaymentMethods: vi.fn(),
  getEarnings: vi.fn(),
}));
vi.mock("../api/sellers", () => ({ getPaymentMethods, updatePaymentMethods, getEarnings }));

const SESSION = { token: "tok123", email: "seller@example.com" };

const SAMPLE_METHODS = {
  cbe_account_name: "Jane Seller",
  cbe_account_number: "1000123456789",
  telebirr_account_name: null,
  telebirr_account_number: null,
};

const SAMPLE_EARNINGS = {
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

/** Renders with both loads resolved, and waits for the form to appear. */
async function renderReady() {
  seedSellerSession(SESSION);
  getPaymentMethods.mockResolvedValueOnce(SAMPLE_METHODS);
  getEarnings.mockResolvedValueOnce(SAMPLE_EARNINGS);

  renderSellerDashboardPage({ route: "/seller/payment-methods" });
  await screen.findByLabelText("CBE account name");
}

describe("SellerPayments", () => {
  it("redirects to /seller when there is no session", () => {
    renderSellerDashboardPage({ route: "/seller/payment-methods" });

    expect(screen.getByRole("heading", { name: "Seller area" })).toBeInTheDocument();
    expect(getPaymentMethods).not.toHaveBeenCalled();
    expect(getEarnings).not.toHaveBeenCalled();
  });

  it("loads and shows earnings and the payout account form, nulls rendered as blank", async () => {
    await renderReady();

    expect(getPaymentMethods).toHaveBeenCalledWith("tok123");
    expect(getEarnings).toHaveBeenCalledWith("tok123");

    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("600.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("60.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("540.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("200.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("340.00 ETB")).toBeInTheDocument();

    expect(screen.getByLabelText("CBE account name")).toHaveValue("Jane Seller");
    expect(screen.getByLabelText("CBE account number")).toHaveValue("1000123456789");
    expect(screen.getByLabelText("Telebirr account name")).toHaveValue("");
    expect(screen.getByLabelText("Telebirr account number")).toHaveValue("");
  });

  it("clears the session and redirects to /seller/login on a 401 loading payment methods", async () => {
    seedSellerSession(SESSION);
    getPaymentMethods.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );
    getEarnings.mockResolvedValueOnce(SAMPLE_EARNINGS);

    renderSellerDashboardPage({ route: "/seller/payment-methods" });

    expect(await screen.findByText(SELLER_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(SELLER_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("shows an earnings error independently while the payout form still loads", async () => {
    seedSellerSession(SESSION);
    getPaymentMethods.mockResolvedValueOnce(SAMPLE_METHODS);
    getEarnings.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderSellerDashboardPage({ route: "/seller/payment-methods" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
    expect(screen.getByLabelText("CBE account name")).toHaveValue("Jane Seller");
  });

  it("saves the form and shows a saved confirmation", async () => {
    await renderReady();
    updatePaymentMethods.mockResolvedValueOnce({
      ...SAMPLE_METHODS,
      telebirr_account_name: "Jane Seller",
      telebirr_account_number: "0911223344",
    });
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Telebirr account name"), "Jane Seller");
    await user.type(screen.getByLabelText("Telebirr account number"), "0911223344");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updatePaymentMethods).toHaveBeenCalledWith("tok123", {
      cbe_account_name: "Jane Seller",
      cbe_account_number: "1000123456789",
      telebirr_account_name: "Jane Seller",
      telebirr_account_number: "0911223344",
    });
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("clears the 'Saved.' confirmation as soon as a field is edited again", async () => {
    await renderReady();
    updatePaymentMethods.mockResolvedValueOnce(SAMPLE_METHODS);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved.");

    await user.type(screen.getByLabelText("CBE account name"), "!");

    expect(screen.queryByText("Saved.")).not.toBeInTheDocument();
  });

  it("clears the session and redirects to /seller/login on a 401 saving", async () => {
    await renderReady();
    updatePaymentMethods.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(SELLER_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(SELLER_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("shows the backend's message when saving fails (non-auth error)", async () => {
    await renderReady();
    updatePaymentMethods.mockRejectedValueOnce(
      new ApiError(422, { detail: "Invalid account number" }, "Invalid account number"),
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid account number");
  });
});

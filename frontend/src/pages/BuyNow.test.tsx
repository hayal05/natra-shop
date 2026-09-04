import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import BuyNow from "./BuyNow";

const { getPaymentInfo, submitReceipt } = vi.hoisted(() => ({
  getPaymentInfo: vi.fn(),
  submitReceipt: vi.fn(),
}));
vi.mock("../api/receipts", () => ({ getPaymentInfo, submitReceipt }));

afterEach(() => {
  vi.clearAllMocks();
});

const FULL_INFO = {
  cbe_account_name: "NATRA PLC",
  cbe_account_number: "1000123456789",
  telebirr_account_name: "NATRA PLC",
  telebirr_account_number: "0911223344",
};

function renderBuyNow(productId = "prod-1") {
  return render(
    <MemoryRouter initialEntries={[`/product/${productId}/buy`]}>
      <Routes>
        <Route path="/product/:productId/buy" element={<BuyNow />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function typeReceiptUrl(value: string) {
  const user = userEvent.setup();
  if (value) {
    await user.type(screen.getByLabelText("Receipt URL"), value);
  }
  await user.click(screen.getByRole("button", { name: "Submit receipt" }));
}

describe("BuyNow", () => {
  it("shows a loading state for payment info and a back link to the product", () => {
    getPaymentInfo.mockReturnValue(new Promise(() => {}));

    renderBuyNow("prod-1");

    expect(screen.getByText("Loading payment details…")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to product/ })).toHaveAttribute(
      "href",
      "/product/prod-1",
    );
  });

  it("shows both CBE and Telebirr accounts when both are configured", async () => {
    getPaymentInfo.mockResolvedValueOnce(FULL_INFO);

    renderBuyNow();

    expect(await screen.findByRole("heading", { name: "CBE" })).toBeInTheDocument();
    expect(screen.getByText("1000123456789")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Telebirr" })).toBeInTheDocument();
    expect(screen.getByText("0911223344")).toBeInTheDocument();
  });

  it("shows only the CBE account when Telebirr isn't configured", async () => {
    getPaymentInfo.mockResolvedValueOnce({
      ...FULL_INFO,
      telebirr_account_name: null,
      telebirr_account_number: null,
    });

    renderBuyNow();

    expect(await screen.findByRole("heading", { name: "CBE" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Telebirr" })).not.toBeInTheDocument();
  });

  it("shows a not-configured message when neither account is set", async () => {
    getPaymentInfo.mockResolvedValueOnce({
      cbe_account_name: null,
      cbe_account_number: null,
      telebirr_account_name: null,
      telebirr_account_number: null,
    });

    renderBuyNow();

    expect(
      await screen.findByText(/Payment accounts haven't been configured yet/),
    ).toBeInTheDocument();
  });

  it("shows the backend's message when loading payment info fails", async () => {
    getPaymentInfo.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderBuyNow();

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("does not submit when the receipt URL is only whitespace", async () => {
    getPaymentInfo.mockResolvedValueOnce(FULL_INFO);

    renderBuyNow();
    await screen.findByRole("heading", { name: "CBE" });

    await typeReceiptUrl("   ");

    expect(submitReceipt).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Submit receipt" })).toBeInTheDocument();
  });

  it("submits a trimmed receipt URL and shows the confirmation with a status link", async () => {
    getPaymentInfo.mockResolvedValueOnce(FULL_INFO);
    submitReceipt.mockResolvedValueOnce({
      id: "receipt-1",
      product_id: "prod-1",
      receipt_url: "https://example.com/receipt",
    });

    renderBuyNow("prod-1");
    await screen.findByRole("heading", { name: "CBE" });

    await typeReceiptUrl("  https://example.com/receipt  ");

    expect(submitReceipt).toHaveBeenCalledWith("prod-1", "https://example.com/receipt");
    expect(await screen.findByRole("status")).toHaveTextContent("Receipt submitted");
    expect(screen.getByText("receipt-1")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Check verification status →" }),
    ).toHaveAttribute("href", "/receipt/receipt-1");
  });

  it("shows the backend's message when submitting the receipt fails", async () => {
    getPaymentInfo.mockResolvedValueOnce(FULL_INFO);
    submitReceipt.mockRejectedValueOnce(
      new ApiError(422, { detail: "receipt_url must be a URL" }, "receipt_url must be a URL"),
    );

    renderBuyNow();
    await screen.findByRole("heading", { name: "CBE" });

    await typeReceiptUrl("https://example.com/receipt");

    expect(await screen.findByRole("alert")).toHaveTextContent("receipt_url must be a URL");
  });

  it("shows a generic fallback message when submitting fails with a non-ApiError", async () => {
    getPaymentInfo.mockResolvedValueOnce(FULL_INFO);
    submitReceipt.mockRejectedValueOnce(new Error("network down"));

    renderBuyNow();
    await screen.findByRole("heading", { name: "CBE" });

    await typeReceiptUrl("https://example.com/receipt");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not submit the receipt. Check your connection and try again.",
    );
  });
});

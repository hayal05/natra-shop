import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { ApiError } from "../api/client";
import ReceiptStatus from "./ReceiptStatus";

const { verifyReceipt, getReceiptDelivery } = vi.hoisted(() => ({
  verifyReceipt: vi.fn(),
  getReceiptDelivery: vi.fn(),
}));

/**
 * `ReceiptStatus` imports `describeRejectionReason` directly from
 * `../api/receipts` alongside the two functions this task needs to
 * stub — it's a pure lookup table, not a network call, so there's no
 * reason to mock it too. `importOriginal` keeps it (and any other
 * real export) intact while only `verifyReceipt`/`getReceiptDelivery`
 * are replaced, rather than duplicating the reason-text table in this
 * test file.
 */
vi.mock("../api/receipts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/receipts")>();
  return { ...actual, verifyReceipt, getReceiptDelivery };
});

afterEach(() => {
  vi.clearAllMocks();
});

function renderReceiptStatus(receiptId = "receipt-1") {
  return render(
    <MemoryRouter initialEntries={[`/receipt/${receiptId}`]}>
      <Routes>
        <Route path="/receipt/:receiptId" element={<ReceiptStatus />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ReceiptStatus", () => {
  it("shows a checking state while verification is in flight", () => {
    verifyReceipt.mockReturnValue(new Promise(() => {}));

    renderReceiptStatus();

    expect(screen.getByText("Checking your receipt…")).toBeInTheDocument();
  });

  it("shows the human-readable reason and a way to resubmit when rejected", async () => {
    verifyReceipt.mockResolvedValueOnce({
      id: "receipt-1",
      product_id: "prod-1",
      status: "rejected",
      reason: "amount_mismatch",
      transaction_ref: null,
      verified_amount: null,
      provider: "cbe",
    });

    renderReceiptStatus("receipt-1");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The paid amount doesn't match this product's price.",
    );
    expect(
      screen.getByRole("link", { name: "Go back and submit a corrected receipt" }),
    ).toHaveAttribute("href", "/product/prod-1/buy");
    expect(verifyReceipt).toHaveBeenCalledWith("receipt-1");
    expect(getReceiptDelivery).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when rejected with no reason code", async () => {
    verifyReceipt.mockResolvedValueOnce({
      id: "receipt-1",
      product_id: "prod-1",
      status: "rejected",
      reason: null,
      transaction_ref: null,
      verified_amount: null,
      provider: null,
    });

    renderReceiptStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This receipt could not be verified.",
    );
  });

  it("shows the download link once verified and delivery succeeds", async () => {
    verifyReceipt.mockResolvedValueOnce({
      id: "receipt-1",
      product_id: "prod-1",
      status: "verified",
      reason: null,
      transaction_ref: "TXN123",
      verified_amount: 150,
      provider: "cbe",
    });
    getReceiptDelivery.mockResolvedValueOnce({
      receipt_id: "receipt-1",
      product_id: "prod-1",
      drive_link: "https://drive.google.com/file/d/xyz",
    });

    renderReceiptStatus("receipt-1");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Your payment is verified. Here's your download link:",
    );
    expect(screen.getByRole("link", { name: "Open your download" })).toHaveAttribute(
      "href",
      "https://drive.google.com/file/d/xyz",
    );
    expect(screen.getByRole("link", { name: "Back to product" })).toHaveAttribute(
      "href",
      "/product/prod-1",
    );
    expect(getReceiptDelivery).toHaveBeenCalledWith("receipt-1");
  });

  it("shows the backend's message when verified but delivery fails with an ApiError", async () => {
    verifyReceipt.mockResolvedValueOnce({
      id: "receipt-1",
      product_id: "prod-1",
      status: "verified",
      reason: null,
      transaction_ref: "TXN123",
      verified_amount: 150,
      provider: "cbe",
    });
    getReceiptDelivery.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderReceiptStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your payment is verified! Internal server error",
    );
  });

  it("shows a generic fallback message when verified but delivery fails with a non-ApiError", async () => {
    verifyReceipt.mockResolvedValueOnce({
      id: "receipt-1",
      product_id: "prod-1",
      status: "verified",
      reason: null,
      transaction_ref: "TXN123",
      verified_amount: 150,
      provider: "cbe",
    });
    getReceiptDelivery.mockRejectedValueOnce(new Error("network down"));

    renderReceiptStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Verified, but the download link couldn't be loaded. Try reloading this page.",
    );
  });

  it("shows a not-found message for a 404", async () => {
    verifyReceipt.mockRejectedValueOnce(new ApiError(404, { detail: "Not found" }, "Not found"));

    renderReceiptStatus();

    expect(
      await screen.findByText("We couldn't find a receipt with that reference."),
    ).toBeInTheDocument();
  });

  it("shows the backend's message on a non-404 ApiError", async () => {
    verifyReceipt.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderReceiptStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("shows a generic fallback message for a non-ApiError verification failure", async () => {
    verifyReceipt.mockRejectedValueOnce(new Error("network down"));

    renderReceiptStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not check this receipt. Check your connection and try again.",
    );
  });
});

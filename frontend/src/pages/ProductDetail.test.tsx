import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { ApiError } from "../api/client";
import ProductDetail from "./ProductDetail";

const { getProductDetail } = vi.hoisted(() => ({ getProductDetail: vi.fn() }));
vi.mock("../api/products", () => ({ getProductDetail }));

afterEach(() => {
  vi.clearAllMocks();
});

const PRODUCT = {
  id: "prod-1",
  name: "E-book: Learn Amharic",
  price: 150,
  description: "A beginner's guide.",
  thumbnail_ref: null,
};

function renderProductDetail(productId = "prod-1") {
  return render(
    <MemoryRouter initialEntries={[`/product/${productId}`]}>
      <Routes>
        <Route path="/product/:productId" element={<ProductDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProductDetail", () => {
  it("shows a loading state while the product is being fetched", () => {
    getProductDetail.mockReturnValue(new Promise(() => {}));

    renderProductDetail();

    expect(screen.getByText("Loading product…")).toBeInTheDocument();
  });

  it("renders the product's name, formatted price, description, and Buy Now link", async () => {
    getProductDetail.mockResolvedValueOnce(PRODUCT);

    renderProductDetail("prod-1");

    expect(await screen.findByRole("heading", { name: "E-book: Learn Amharic" })).toBeInTheDocument();
    expect(screen.getByText("150.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("A beginner's guide.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Buy Now" })).toHaveAttribute(
      "href",
      "/product/prod-1/buy",
    );
    expect(getProductDetail).toHaveBeenCalledWith("prod-1");
  });

  it("shows a fallback message when the product has no description", async () => {
    getProductDetail.mockResolvedValueOnce({ ...PRODUCT, description: "" });

    renderProductDetail();

    expect(await screen.findByText("No description provided.")).toBeInTheDocument();
  });

  it("shows a not-found message for a 404", async () => {
    getProductDetail.mockRejectedValueOnce(
      new ApiError(404, { detail: "Not found" }, "Not found"),
    );

    renderProductDetail();

    expect(
      await screen.findByText("This product doesn't exist or may have been removed."),
    ).toBeInTheDocument();
  });

  it("shows the backend's message on a non-404 ApiError", async () => {
    getProductDetail.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderProductDetail();

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    getProductDetail.mockRejectedValueOnce(new Error("network down"));

    renderProductDetail();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load this product. Check your connection and try again.",
    );
  });
});

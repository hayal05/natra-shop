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

  /**
   * Task 109: tests for Task 105's thumbnail display, mirroring Task
   * 108's approach on `BuyerHome.test.tsx`. The base `PRODUCT` fixture
   * above has `thumbnail_ref: null`, so the previous test only ever
   * exercised the placeholder branch — this one overrides it with a
   * real-looking URL to exercise the `<img>` branch. `alt=""` images
   * have no accessible name/role, so queried by class via
   * `container.querySelector` rather than `screen.getByRole("img")`.
   */
  it("renders the thumbnail image when the product has one, instead of the placeholder", async () => {
    getProductDetail.mockResolvedValueOnce({
      ...PRODUCT,
      thumbnail_ref: "https://storage.example/thumbnails/prod-1.png",
    });

    const { container } = renderProductDetail();

    await screen.findByRole("heading", { name: "E-book: Learn Amharic" });

    const img = container.querySelector("img.product-detail__thumb-img");
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute("src", "https://storage.example/thumbnails/prod-1.png");
    expect(img).toHaveAttribute("alt", "");
    expect(screen.queryByText("No image")).not.toBeInTheDocument();
  });

  it("shows the placeholder, not an image, when the product has no thumbnail", async () => {
    getProductDetail.mockResolvedValueOnce(PRODUCT);

    const { container } = renderProductDetail();

    await screen.findByRole("heading", { name: "E-book: Learn Amharic" });

    expect(screen.getByText("No image")).toBeInTheDocument();
    expect(container.querySelector("img.product-detail__thumb-img")).toBeNull();
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

import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { ApiError } from "../api/client";
import BuyerHome from "./BuyerHome";

const { getProducts } = vi.hoisted(() => ({ getProducts: vi.fn() }));
vi.mock("../api/products", () => ({ getProducts }));

afterEach(() => {
  vi.clearAllMocks();
});

const PRODUCT_1 = { id: "prod-1", name: "E-book: Learn Amharic", price: 150, thumbnail_ref: null };
const PRODUCT_2 = { id: "prod-2", name: "Instagram Growth Guide", price: 300, thumbnail_ref: null };
const PRODUCT_WITH_THUMB = {
  id: "prod-3",
  name: "Digital Sticker Pack",
  price: 75,
  thumbnail_ref: "https://storage.example/thumbnails/prod-3.png",
};

/**
 * Task 82: unit tests for `BuyerHome`. No shared test router file for
 * this task's four pages (unlike `authTestRouter.tsx`/
 * `sellerDashboardTestRouter.tsx` for Tasks 80-81's pages) — the buyer
 * pages only ever navigate to each other via `<Link>`, never
 * `useNavigate()`-driven redirects, so asserting on each link's `href`
 * is enough; there's no cross-page redirect behavior that would need
 * a second real page mounted in the same router to observe.
 */
function renderBuyerHome() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <BuyerHome />
    </MemoryRouter>,
  );
}

describe("BuyerHome", () => {
  it("shows a loading state while products are being fetched", () => {
    getProducts.mockReturnValue(new Promise(() => {}));

    renderBuyerHome();

    expect(screen.getByText("Loading products…")).toBeInTheDocument();
  });

  it("renders the product grid with formatted prices and detail links", async () => {
    getProducts.mockResolvedValueOnce([PRODUCT_1, PRODUCT_2]);

    renderBuyerHome();

    expect(await screen.findByText("E-book: Learn Amharic")).toBeInTheDocument();
    expect(screen.getByText("150.00 ETB")).toBeInTheDocument();
    expect(screen.getByText("Instagram Growth Guide")).toBeInTheDocument();
    expect(screen.getByText("300.00 ETB")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /E-book: Learn Amharic/ })).toHaveAttribute(
      "href",
      "/product/prod-1",
    );
    expect(screen.getByRole("link", { name: /Instagram Growth Guide/ })).toHaveAttribute(
      "href",
      "/product/prod-2",
    );
    expect(screen.getAllByText("No image")).toHaveLength(2);
    expect(getProducts).toHaveBeenCalledTimes(1);
  });

  /**
   * Task 108: tests for Task 104's thumbnail display. Neither of
   * `PRODUCT_1`/`PRODUCT_2` above has a `thumbnail_ref`, so the
   * previous test only ever exercised the placeholder branch — this
   * one adds `PRODUCT_WITH_THUMB` to exercise the `<img>` branch too.
   * `alt=""` images have no accessible name/role, so they're queried
   * by class via `container.querySelector` rather than
   * `screen.getByRole("img")`.
   */
  it("renders a thumbnail image for a product that has one, alongside the placeholder for one that doesn't", async () => {
    getProducts.mockResolvedValueOnce([PRODUCT_WITH_THUMB, PRODUCT_1]);

    const { container } = renderBuyerHome();

    await screen.findByText("Digital Sticker Pack");

    const thumbImages = container.querySelectorAll("img.product-card__thumb-img");
    expect(thumbImages).toHaveLength(1);
    expect(thumbImages[0]).toHaveAttribute(
      "src",
      "https://storage.example/thumbnails/prod-3.png",
    );
    expect(thumbImages[0]).toHaveAttribute("alt", "");
    expect(screen.getAllByText("No image")).toHaveLength(1);
  });

  it("shows an empty-state message when there are no products", async () => {
    getProducts.mockResolvedValueOnce([]);

    renderBuyerHome();

    expect(
      await screen.findByText("No products are listed yet — check back soon."),
    ).toBeInTheDocument();
  });

  it("shows the backend's message on an ApiError", async () => {
    getProducts.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderBuyerHome();

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    getProducts.mockRejectedValueOnce(new Error("network down"));

    renderBuyerHome();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load products. Check your connection and try again.",
    );
  });
});

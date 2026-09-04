import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { seedSellerSession, SELLER_SESSION_STORAGE_KEY } from "./authTestRouter";
import {
  renderSellerDashboardPage,
  SELLER_LOGIN_PLACEHOLDER,
} from "./sellerDashboardTestRouter";

const { createProduct, getMyProducts } = vi.hoisted(() => ({
  createProduct: vi.fn(),
  getMyProducts: vi.fn(),
}));
vi.mock("../api/products", () => ({ createProduct, getMyProducts }));

const SESSION = { token: "tok123", email: "seller@example.com" };

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

const SAMPLE_PRODUCT = {
  id: "prod-1",
  seller_id: "seller-1",
  name: "E-book: Learn Amharic",
  price: 150,
  description: "A beginner's guide.",
  drive_link: "https://drive.google.com/file/d/abc",
};

async function fillAndSubmitProduct(fields: {
  name: string;
  price: string;
  description?: string;
  driveLink: string;
}) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Name"), fields.name);
  if (fields.price) {
    await user.type(screen.getByLabelText("Price (ETB)"), fields.price);
  }
  if (fields.description) {
    await user.type(screen.getByLabelText("Description"), fields.description);
  }
  await user.type(screen.getByLabelText("Public Google Drive link"), fields.driveLink);
  await user.click(screen.getByRole("button", { name: "Add product" }));
}

describe("SellerHome", () => {
  it("shows the logged-out view and never calls getMyProducts", () => {
    renderSellerDashboardPage({ route: "/seller" });

    expect(screen.getByRole("heading", { name: "Seller area" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute(
      "href",
      "/seller/login",
    );
    expect(screen.getByRole("link", { name: "Register" })).toHaveAttribute(
      "href",
      "/seller/register",
    );
    expect(getMyProducts).not.toHaveBeenCalled();
  });

  it("loads and shows the seller's products", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([SAMPLE_PRODUCT]);

    renderSellerDashboardPage({ route: "/seller" });

    expect(screen.getByText("Loading your products…")).toBeInTheDocument();
    expect(getMyProducts).toHaveBeenCalledWith("tok123");

    const item = await screen.findByText("E-book: Learn Amharic");
    const card = item.closest("li")!;
    expect(within(card).getByText("150.00 ETB")).toBeInTheDocument();
    expect(within(card).getByText("A beginner's guide.")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Drive link" })).toHaveAttribute(
      "href",
      "https://drive.google.com/file/d/abc",
    );
  });

  it("shows an empty-state message when there are no products", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);

    renderSellerDashboardPage({ route: "/seller" });

    expect(
      await screen.findByText("You haven't added any products yet."),
    ).toBeInTheDocument();
  });

  it("shows an error message when loading products fails (non-auth error)", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockRejectedValueOnce(
      new ApiError(500, { detail: "Internal server error" }, "Internal server error"),
    );

    renderSellerDashboardPage({ route: "/seller" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("clears the session and redirects to /seller/login on a 401 loading products", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderSellerDashboardPage({ route: "/seller" });

    expect(await screen.findByText(SELLER_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(SELLER_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("logs out and returns to the logged-out view", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    const user = userEvent.setup();

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await user.click(screen.getByRole("button", { name: "Log out" }));

    expect(screen.getByRole("heading", { name: "Seller area" })).toBeInTheDocument();
    expect(localStorage.getItem(SELLER_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("does not submit the add-product form with no price entered", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "Untitled",
      price: "",
      driveLink: "https://drive.google.com/file/d/xyz",
    });

    expect(createProduct).not.toHaveBeenCalled();
  });

  it("adds a product, prepends it to the list, and clears the form", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockResolvedValueOnce(SAMPLE_PRODUCT);

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      description: "A beginner's guide.",
      driveLink: "https://drive.google.com/file/d/abc",
    });

    expect(createProduct).toHaveBeenCalledWith("tok123", {
      name: "E-book: Learn Amharic",
      price: 150,
      description: "A beginner's guide.",
      drive_link: "https://drive.google.com/file/d/abc",
    });
    await waitFor(() => expect(screen.getByText("E-book: Learn Amharic")).toBeInTheDocument());
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Public Google Drive link")).toHaveValue("");
  });

  it("clears the session and redirects to /seller/login on a 401 adding a product", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      driveLink: "https://drive.google.com/file/d/abc",
    });

    expect(await screen.findByText(SELLER_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(SELLER_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("shows the backend's message when adding a product fails (non-auth error)", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockRejectedValueOnce(
      new ApiError(422, { detail: "drive_link must be a URL" }, "drive_link must be a URL"),
    );

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      driveLink: "https://drive.google.com/file/d/abc",
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("drive_link must be a URL");
  });
});

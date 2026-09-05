import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { seedSellerSession, SELLER_SESSION_STORAGE_KEY } from "./authTestRouter";
import {
  renderSellerDashboardPage,
  SELLER_LOGIN_PLACEHOLDER,
} from "./sellerDashboardTestRouter";

const { createProduct, getMyProducts, uploadThumbnail } = vi.hoisted(() => ({
  createProduct: vi.fn(),
  getMyProducts: vi.fn(),
  uploadThumbnail: vi.fn(),
}));
vi.mock("../api/products", () => ({ createProduct, getMyProducts, uploadThumbnail }));

const SESSION = { token: "tok123", email: "seller@example.com" };

/**
 * Task 106: jsdom has no real `URL.createObjectURL`/`revokeObjectURL`
 * (calling either throws "not implemented"), but `SellerHome.tsx`'s
 * thumbnail preview effect (Task 102) calls both. Stubbed once for
 * the whole file rather than per-test — `vi.clearAllMocks()` in the
 * existing `afterEach` below clears call history between tests but
 * leaves this initial implementation in place, so every test still
 * gets a working (fake) object URL.
 */
let objectUrlCounter = 0;
const createObjectURLMock = vi.fn(() => `blob:mock-thumbnail-url-${++objectUrlCounter}`);
const revokeObjectURLMock = vi.fn();

beforeAll(() => {
  URL.createObjectURL = createObjectURLMock;
  URL.revokeObjectURL = revokeObjectURLMock;
});

/** Builds a `File` of an exact byte size, for the 500 KB limit checks. */
function makeThumbnailFile(name: string, type: string, sizeBytes: number): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

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
  thumbnail?: File;
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
  if (fields.thumbnail) {
    await user.upload(screen.getByLabelText("Thumbnail (optional)"), fields.thumbnail);
  }
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

  /**
   * Task 106: tests for Task 102's thumbnail file input + preview,
   * in isolation from form submission — none of these pick a file and
   * then submit, so `createProduct`/`uploadThumbnail` are never
   * exercised here. That combined flow is Task 103's job, tested by
   * Task 107 (which will also need to add `uploadThumbnail: vi.fn()`
   * to this file's mock factory, per the flag left in Task 103's
   * CURRENT_STATUS.md — not needed for these tests).
   */
  it("shows a live preview when a valid thumbnail is selected", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    const user = userEvent.setup();
    const file = makeThumbnailFile("cover.png", "image/png", 1024);
    await user.upload(screen.getByLabelText("Thumbnail (optional)"), file);

    expect(createObjectURLMock).toHaveBeenCalledWith(file);
    const preview = await screen.findByAltText("Selected thumbnail preview");
    expect(preview).toHaveAttribute("src", createObjectURLMock.mock.results[0].value);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects a non-image file type with an inline error and no preview", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    // `applyAccept: false`: the real <input accept="image/jpeg,image/png,
    // image/webp"> already stops a real browser's file picker from
    // offering a .pdf at all, but user-event's default `upload()`
    // faithfully emulates that same filtering — silently dropping any
    // file that doesn't match `accept` before firing `change` at all.
    // That's correct for modeling a real browser, but it means this
    // test's whole point (proving SellerHome.tsx's *own* JS validation
    // catches a bad file) can never be exercised through a realistic
    // upload. Disabling it here is deliberate: this test needs a file
    // that bypasses the OS picker's filter (e.g. dragged in, or the
    // accept attribute doesn't match every OS/browser's MIME sniffing
    // exactly) to reach the code path Task 102 actually added.
    const user = userEvent.setup({ applyAccept: false });
    const badFile = makeThumbnailFile("resume.pdf", "application/pdf", 1024);
    await user.upload(screen.getByLabelText("Thumbnail (optional)"), badFile);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Thumbnail must be a JPG, PNG, or WebP image.",
    );
    expect(screen.queryByAltText("Selected thumbnail preview")).not.toBeInTheDocument();
    expect(createObjectURLMock).not.toHaveBeenCalled();
  });

  it("rejects a thumbnail over 500 KB with an inline error and no preview", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    const user = userEvent.setup();
    const bigFile = makeThumbnailFile("big.png", "image/png", 500 * 1024 + 1);
    await user.upload(screen.getByLabelText("Thumbnail (optional)"), bigFile);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Thumbnail must be 500 KB or smaller.",
    );
    expect(screen.queryByAltText("Selected thumbnail preview")).not.toBeInTheDocument();
    expect(createObjectURLMock).not.toHaveBeenCalled();
  });

  it("clears the error and shows a preview after fixing an invalid selection", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    const user = userEvent.setup({ applyAccept: false });
    const input = screen.getByLabelText("Thumbnail (optional)");

    await user.upload(input, makeThumbnailFile("resume.pdf", "application/pdf", 1024));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Thumbnail must be a JPG, PNG, or WebP image.",
    );

    await user.upload(input, makeThumbnailFile("cover.png", "image/png", 1024));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(await screen.findByAltText("Selected thumbnail preview")).toBeInTheDocument();
  });

  it("replaces the preview and revokes the old object URL when a new thumbnail is selected", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    const user = userEvent.setup();
    const input = screen.getByLabelText("Thumbnail (optional)");

    await user.upload(input, makeThumbnailFile("a.png", "image/png", 1024));
    const firstPreview = await screen.findByAltText("Selected thumbnail preview");
    const firstSrc = firstPreview.getAttribute("src");

    await user.upload(input, makeThumbnailFile("b.webp", "image/webp", 2048));
    const secondPreview = await screen.findByAltText("Selected thumbnail preview");
    expect(secondPreview.getAttribute("src")).not.toBe(firstSrc);
    expect(revokeObjectURLMock).toHaveBeenCalledWith(firstSrc);
  });

  /**
   * Task 107: tests for Task 103's upload wiring — the combined
   * pick-a-file-then-submit flow, exercising `uploadThumbnail()`
   * itself rather than just the picker (Task 106, above).
   */
  it("does not call uploadThumbnail when no thumbnail was picked", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockResolvedValueOnce(SAMPLE_PRODUCT);

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      driveLink: "https://drive.google.com/file/d/abc",
    });

    await waitFor(() => expect(screen.getByText("E-book: Learn Amharic")).toBeInTheDocument());
    expect(uploadThumbnail).not.toHaveBeenCalled();
  });

  it("uploads the picked thumbnail after the product is created, and clears the picker", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockResolvedValueOnce(SAMPLE_PRODUCT);
    uploadThumbnail.mockResolvedValueOnce({ thumbnail_ref: "https://storage.example/thumb.png" });

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    const file = makeThumbnailFile("cover.png", "image/png", 1024);
    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      driveLink: "https://drive.google.com/file/d/abc",
      thumbnail: file,
    });

    await waitFor(() =>
      expect(uploadThumbnail).toHaveBeenCalledWith("tok123", SAMPLE_PRODUCT.id, file),
    );
    expect(screen.getByText("E-book: Learn Amharic")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // The picker is reset once the product row exists, regardless of
    // the (here, successful) upload outcome — no leftover preview.
    expect(screen.queryByAltText("Selected thumbnail preview")).not.toBeInTheDocument();
  });

  it("shows a non-fatal inline warning when the thumbnail upload fails (non-auth error)", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockResolvedValueOnce(SAMPLE_PRODUCT);
    uploadThumbnail.mockRejectedValueOnce(
      new ApiError(502, { detail: "Storage upload failed" }, "Storage upload failed"),
    );

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      driveLink: "https://drive.google.com/file/d/abc",
      thumbnail: makeThumbnailFile("cover.png", "image/png", 1024),
    });

    // The product itself was added — this must never look like the
    // whole submission failed.
    await waitFor(() => expect(screen.getByText("E-book: Learn Amharic")).toBeInTheDocument());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The product was added, but the thumbnail could not be uploaded: Storage upload failed",
    );
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });

  it("shows a generic fallback message when the thumbnail upload fails with a non-ApiError", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockResolvedValueOnce(SAMPLE_PRODUCT);
    uploadThumbnail.mockRejectedValueOnce(new Error("network down"));

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      driveLink: "https://drive.google.com/file/d/abc",
      thumbnail: makeThumbnailFile("cover.png", "image/png", 1024),
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The product was added, but the thumbnail could not be uploaded: Check your connection and try again.",
    );
  });

  it("clears the session and redirects to /seller/login on a 401 from the thumbnail upload", async () => {
    seedSellerSession(SESSION);
    getMyProducts.mockResolvedValueOnce([]);
    createProduct.mockResolvedValueOnce(SAMPLE_PRODUCT);
    uploadThumbnail.mockRejectedValueOnce(
      new ApiError(401, { detail: "Not authenticated" }, "Not authenticated"),
    );

    renderSellerDashboardPage({ route: "/seller" });
    await screen.findByText("You haven't added any products yet.");

    await fillAndSubmitProduct({
      name: "E-book: Learn Amharic",
      price: "150",
      driveLink: "https://drive.google.com/file/d/abc",
      thumbnail: makeThumbnailFile("cover.png", "image/png", 1024),
    });

    expect(await screen.findByText(SELLER_LOGIN_PLACEHOLDER)).toBeInTheDocument();
    expect(localStorage.getItem(SELLER_SESSION_STORAGE_KEY)).toBeNull();
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import {
  renderAuthPage,
  seedSellerSession,
  SELLER_HOME_PLACEHOLDER,
  SELLER_SESSION_STORAGE_KEY,
} from "./authTestRouter";

const { loginSeller } = vi.hoisted(() => ({ loginSeller: vi.fn() }));
vi.mock("../api/sellers", () => ({ loginSeller }));

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Log in" }));
}

describe("SellerLogin", () => {
  it("renders the login form", () => {
    renderAuthPage({ route: "/seller/login" });

    expect(screen.getByRole("heading", { name: "Seller login" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
  });

  it("redirects to /seller when a session already exists", () => {
    seedSellerSession({ token: "existing-token", email: "seller@example.com" });

    renderAuthPage({ route: "/seller/login" });

    expect(screen.getByText(SELLER_HOME_PLACEHOLDER)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Seller login" })).not.toBeInTheDocument();
  });

  it("shows the password-reset success banner when arriving with passwordResetDone state", () => {
    renderAuthPage({ route: "/seller/login", state: { passwordResetDone: true } });

    expect(
      screen.getByText("Your password has been reset. Log in with your new password."),
    ).toBeInTheDocument();
  });

  it("on success, saves the session and navigates to /seller", async () => {
    loginSeller.mockResolvedValueOnce({ access_token: "abc123", token_type: "bearer" });

    renderAuthPage({ route: "/seller/login" });
    await fillAndSubmit("seller@example.com", "hunter22");

    expect(loginSeller).toHaveBeenCalledWith("seller@example.com", "hunter22");
    await waitFor(() => expect(screen.getByText(SELLER_HOME_PLACEHOLDER)).toBeInTheDocument());

    const stored = JSON.parse(localStorage.getItem(SELLER_SESSION_STORAGE_KEY) ?? "null");
    expect(stored).toEqual({ token: "abc123", email: "seller@example.com" });
  });

  it("shows the backend's message on a generic (wrong credentials) ApiError", async () => {
    loginSeller.mockRejectedValueOnce(
      new ApiError(401, { detail: "Invalid email or password." }, "Invalid email or password."),
    );

    renderAuthPage({ route: "/seller/login" });
    await fillAndSubmit("seller@example.com", "wrongpass");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(localStorage.getItem(SELLER_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("branches a 403 into the unverified state with a link to verify-email", async () => {
    loginSeller.mockRejectedValueOnce(
      new ApiError(403, { detail: "Email not verified." }, "Email not verified."),
    );

    renderAuthPage({ route: "/seller/login" });
    await fillAndSubmit("unverified@example.com", "hunter22");

    expect(
      await screen.findByText("Please verify your email before logging in."),
    ).toBeInTheDocument();
    const verifyLink = screen.getByRole("link", { name: "Verify now" });
    expect(verifyLink).toHaveAttribute("href", "/seller/verify-email");
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    loginSeller.mockRejectedValueOnce(new Error("network down"));

    renderAuthPage({ route: "/seller/login" });
    await fillAndSubmit("seller@example.com", "hunter22");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not log in. Check your connection and try again.",
    );
  });
});

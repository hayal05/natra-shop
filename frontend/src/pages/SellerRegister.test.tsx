import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { renderAuthPage, seedSellerSession, SELLER_HOME_PLACEHOLDER } from "./authTestRouter";

const { registerSeller } = vi.hoisted(() => ({ registerSeller: vi.fn() }));
vi.mock("../api/sellers", () => ({ registerSeller }));

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

async function fillAndSubmit(
  email: string,
  password: string,
  confirmPassword: string,
) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.type(screen.getByLabelText("Confirm password"), confirmPassword);
  await user.click(screen.getByRole("button", { name: "Register" }));
}

describe("SellerRegister", () => {
  it("renders the registration form", () => {
    renderAuthPage({ route: "/seller/register" });

    expect(
      screen.getByRole("heading", { name: "Seller registration" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm password")).toBeInTheDocument();
  });

  it("redirects to /seller when a session already exists", () => {
    seedSellerSession({ token: "existing-token", email: "seller@example.com" });

    renderAuthPage({ route: "/seller/register" });

    expect(screen.getByText(SELLER_HOME_PLACEHOLDER)).toBeInTheDocument();
    expect(registerSeller).not.toHaveBeenCalled();
  });

  it("rejects a mismatched confirm-password without calling the API", async () => {
    renderAuthPage({ route: "/seller/register" });

    await fillAndSubmit("seller@example.com", "hunter22", "somethingelse");

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords don't match.");
    expect(registerSeller).not.toHaveBeenCalled();
  });

  it("on success, navigates to /seller/verify-email with the email in router state", async () => {
    registerSeller.mockResolvedValueOnce({ id: "abc123", email: "seller@example.com" });

    renderAuthPage({ route: "/seller/register" });
    await fillAndSubmit("seller@example.com", "hunter22", "hunter22");

    expect(registerSeller).toHaveBeenCalledWith("seller@example.com", "hunter22");
    // VerifyEmail.tsx reads location.state.email and pre-fills its own
    // email field with it — asserting on that pre-filled value is how
    // this test confirms the state actually arrived, without reaching
    // into router internals.
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Verify your email" })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Email")).toHaveValue("seller@example.com");
  });

  it("shows the backend's message on an ApiError (e.g. email already registered)", async () => {
    registerSeller.mockRejectedValueOnce(
      new ApiError(409, { detail: "Email already registered." }, "Email already registered."),
    );

    renderAuthPage({ route: "/seller/register" });
    await fillAndSubmit("seller@example.com", "hunter22", "hunter22");

    expect(await screen.findByRole("alert")).toHaveTextContent("Email already registered.");
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    registerSeller.mockRejectedValueOnce(new Error("network down"));

    renderAuthPage({ route: "/seller/register" });
    await fillAndSubmit("seller@example.com", "hunter22", "hunter22");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not register. Check your connection and try again.",
    );
  });
});

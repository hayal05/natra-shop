import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { renderAuthPage, seedSellerSession } from "./authTestRouter";

const { verifyEmail, resendVerificationEmail } = vi.hoisted(() => ({
  verifyEmail: vi.fn(),
  resendVerificationEmail: vi.fn(),
}));
vi.mock("../api/sellers", () => ({ verifyEmail, resendVerificationEmail }));

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("VerifyEmail", () => {
  it("pre-fills the email field from router state", () => {
    renderAuthPage({
      route: "/seller/verify-email",
      state: { email: "seller@example.com" },
    });

    expect(screen.getByLabelText("Email")).toHaveValue("seller@example.com");
  });

  it("leaves the email field blank when opened without router state", () => {
    renderAuthPage({ route: "/seller/verify-email" });

    expect(screen.getByLabelText("Email")).toHaveValue("");
  });

  it("does not submit a code shorter than 6 digits", async () => {
    const user = userEvent.setup();
    renderAuthPage({
      route: "/seller/verify-email",
      state: { email: "seller@example.com" },
    });

    await user.type(screen.getByLabelText("Verification code"), "123");
    await user.click(screen.getByRole("button", { name: "Verify email" }));

    expect(verifyEmail).not.toHaveBeenCalled();
  });

  it("on success, shows the verified state with a log-in link when no session exists", async () => {
    verifyEmail.mockResolvedValueOnce({ verified: true });
    const user = userEvent.setup();
    renderAuthPage({
      route: "/seller/verify-email",
      state: { email: "seller@example.com" },
    });

    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify email" }));

    expect(verifyEmail).toHaveBeenCalledWith("seller@example.com", "123456");
    expect(await screen.findByText("Your email is verified.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue to log in" })).toHaveAttribute(
      "href",
      "/seller/login",
    );
  });

  it("on success while already logged in, links to the dashboard instead", async () => {
    seedSellerSession({ token: "tok", email: "seller@example.com" });
    verifyEmail.mockResolvedValueOnce({ verified: true });
    const user = userEvent.setup();
    renderAuthPage({
      route: "/seller/verify-email",
      state: { email: "seller@example.com" },
    });

    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify email" }));

    expect(
      await screen.findByRole("link", { name: "Continue to your dashboard" }),
    ).toHaveAttribute("href", "/seller");
  });

  it("shows the backend's message when the code is wrong or expired", async () => {
    verifyEmail.mockRejectedValueOnce(
      new ApiError(400, { detail: "Invalid or expired code." }, "Invalid or expired code."),
    );
    const user = userEvent.setup();
    renderAuthPage({
      route: "/seller/verify-email",
      state: { email: "seller@example.com" },
    });

    await user.type(screen.getByLabelText("Verification code"), "000000");
    await user.click(screen.getByRole("button", { name: "Verify email" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired code.");
  });

  it("disables the resend button while the email field is empty", () => {
    renderAuthPage({ route: "/seller/verify-email" });

    expect(screen.getByRole("button", { name: "Resend code" })).toBeDisabled();
  });

  it("resends the code and shows the generic sent message", async () => {
    resendVerificationEmail.mockResolvedValueOnce({
      message: "If that email needs verification, a new code has been sent.",
    });
    const user = userEvent.setup();
    renderAuthPage({
      route: "/seller/verify-email",
      state: { email: "seller@example.com" },
    });

    await user.click(screen.getByRole("button", { name: "Resend code" }));

    expect(resendVerificationEmail).toHaveBeenCalledWith("seller@example.com");
    await waitFor(() =>
      expect(
        screen.getByText("If that email needs verification, a new code has been sent."),
      ).toBeInTheDocument(),
    );
  });

  it("shows an error message if resending fails", async () => {
    resendVerificationEmail.mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup();
    renderAuthPage({
      route: "/seller/verify-email",
      state: { email: "seller@example.com" },
    });

    await user.click(screen.getByRole("button", { name: "Resend code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not resend the code. Check your connection and try again.",
    );
  });
});

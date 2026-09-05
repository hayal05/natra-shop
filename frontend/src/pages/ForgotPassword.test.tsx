import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { renderAuthPage } from "./authTestRouter";

const { requestPasswordReset, confirmPasswordReset } = vi.hoisted(() => ({
  requestPasswordReset: vi.fn(),
  confirmPasswordReset: vi.fn(),
}));
vi.mock("../api/sellers", () => ({ requestPasswordReset, confirmPasswordReset }));

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

/** Drives step 1 (request) through to a successful step-2 transition. */
async function advanceToConfirmStep(
  user: ReturnType<typeof userEvent.setup>,
  infoMessage = "If that email is registered, a reset code has been sent.",
) {
  requestPasswordReset.mockResolvedValueOnce({ message: infoMessage });
  await user.type(screen.getByLabelText("Email"), "seller@example.com");
  await user.click(screen.getByRole("button", { name: "Send reset code" }));
  await screen.findByText(infoMessage);
}

describe("ForgotPassword", () => {
  it("renders step 1 (request) by default", () => {
    renderAuthPage({ route: "/seller/forgot-password" });

    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send reset code" })).toBeInTheDocument();
  });

  it("advances to step 2 and shows the backend's info message on success", async () => {
    const user = userEvent.setup();
    renderAuthPage({ route: "/seller/forgot-password" });

    await advanceToConfirmStep(user, "If that email is registered, a reset code has been sent.");

    expect(requestPasswordReset).toHaveBeenCalledWith("seller@example.com");
    expect(screen.getByLabelText("Reset code")).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toBeInTheDocument();
  });

  it("shows an error and stays on step 1 if the request fails", async () => {
    requestPasswordReset.mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup();
    renderAuthPage({ route: "/seller/forgot-password" });

    await user.type(screen.getByLabelText("Email"), "seller@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not request a reset code. Check your connection and try again.",
    );
    expect(screen.queryByLabelText("Reset code")).not.toBeInTheDocument();
  });

  it("rejects mismatched new passwords in step 2 without calling the API", async () => {
    const user = userEvent.setup();
    renderAuthPage({ route: "/seller/forgot-password" });
    await advanceToConfirmStep(user);

    await user.type(screen.getByLabelText("Reset code"), "123456");
    await user.type(screen.getByLabelText("New password"), "newpassword1");
    await user.type(screen.getByLabelText("Confirm new password"), "somethingelse1");
    await user.click(screen.getByRole("button", { name: "Reset password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords don't match.");
    expect(confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("on success, navigates to /seller/login with passwordResetDone state", async () => {
    confirmPasswordReset.mockResolvedValueOnce({ reset: true });
    const user = userEvent.setup();
    renderAuthPage({ route: "/seller/forgot-password" });
    await advanceToConfirmStep(user);

    await user.type(screen.getByLabelText("Reset code"), "123456");
    await user.type(screen.getByLabelText("New password"), "newpassword1");
    await user.type(screen.getByLabelText("Confirm new password"), "newpassword1");
    await user.click(screen.getByRole("button", { name: "Reset password" }));

    expect(confirmPasswordReset).toHaveBeenCalledWith(
      "seller@example.com",
      "123456",
      "newpassword1",
    );
    // SellerLogin.tsx reads location.state.passwordResetDone and shows
    // its own success banner — asserting on that banner is how this
    // test confirms both the navigation target and the state payload
    // without reaching into router internals.
    await waitFor(() =>
      expect(
        screen.getByText("Your password has been reset. Log in with your new password."),
      ).toBeInTheDocument(),
    );
  });

  it("shows the backend's message when the reset code is wrong or expired", async () => {
    confirmPasswordReset.mockRejectedValueOnce(
      new ApiError(400, { detail: "Invalid or expired code." }, "Invalid or expired code."),
    );
    const user = userEvent.setup();
    renderAuthPage({ route: "/seller/forgot-password" });
    await advanceToConfirmStep(user);

    await user.type(screen.getByLabelText("Reset code"), "123456");
    await user.type(screen.getByLabelText("New password"), "newpassword1");
    await user.type(screen.getByLabelText("Confirm new password"), "newpassword1");
    await user.click(screen.getByRole("button", { name: "Reset password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired code.");
  });

  it("'Start over' returns to step 1", async () => {
    const user = userEvent.setup();
    renderAuthPage({ route: "/seller/forgot-password" });
    await advanceToConfirmStep(user);

    await user.click(screen.getByRole("button", { name: "Start over" }));

    expect(screen.getByRole("button", { name: "Send reset code" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Reset code")).not.toBeInTheDocument();
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import AdminLogin from "./AdminLogin";

const { loginAdmin } = vi.hoisted(() => ({ loginAdmin: vi.fn() }));
vi.mock("../api/admin", () => ({ loginAdmin }));

const ADMIN_SESSION_STORAGE_KEY = "natra_admin_session";

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

/**
 * `AdminLogin` only ever navigates to `/admin-portal` (there's no
 * branching destination the way `SellerLogin` has for its 403 case),
 * so a single placeholder route is enough here — no need for
 * `authTestRouter.tsx`'s multi-route setup, which exists for pages
 * that navigate to *each other*.
 */
function renderAdminLogin(route = "/admin-portal/login") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/admin-portal" element={<div>ADMIN_PORTAL_PLACEHOLDER</div>} />
        <Route path="/admin-portal/login" element={<AdminLogin />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Log in" }));
}

describe("AdminLogin", () => {
  it("renders the login form", () => {
    renderAdminLogin();

    expect(screen.getByRole("heading", { name: "Admin login" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    // No self-registration for the one Master Admin identity.
    expect(screen.queryByText(/register/i)).not.toBeInTheDocument();
  });

  it("redirects to /admin-portal when a session already exists", () => {
    localStorage.setItem(
      ADMIN_SESSION_STORAGE_KEY,
      JSON.stringify({ token: "existing-token", email: "admin@example.com" }),
    );

    renderAdminLogin();

    expect(screen.getByText("ADMIN_PORTAL_PLACEHOLDER")).toBeInTheDocument();
    expect(loginAdmin).not.toHaveBeenCalled();
  });

  it("on success, saves the session and navigates to /admin-portal", async () => {
    loginAdmin.mockResolvedValueOnce({ access_token: "abc123", token_type: "bearer" });

    renderAdminLogin();
    await fillAndSubmit("admin@example.com", "hunter22");

    expect(loginAdmin).toHaveBeenCalledWith("admin@example.com", "hunter22");
    expect(await screen.findByText("ADMIN_PORTAL_PLACEHOLDER")).toBeInTheDocument();

    const stored = JSON.parse(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY) ?? "null");
    expect(stored).toEqual({ token: "abc123", email: "admin@example.com" });
  });

  it("shows the backend's message on a wrong-credentials ApiError", async () => {
    loginAdmin.mockRejectedValueOnce(
      new ApiError(401, { detail: "Invalid email or password." }, "Invalid email or password."),
    );

    renderAdminLogin();
    await fillAndSubmit("admin@example.com", "wrongpass");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("shows a generic fallback message for a non-ApiError failure", async () => {
    loginAdmin.mockRejectedValueOnce(new Error("network down"));

    renderAdminLogin();
    await fillAndSubmit("admin@example.com", "hunter22");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not log in. Check your connection and try again.",
    );
  });
});

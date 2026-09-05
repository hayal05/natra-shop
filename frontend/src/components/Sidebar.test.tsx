import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Sidebar from "./Sidebar";
import { saveSellerSession, clearSellerSession } from "../lib/session";
import { saveAdminSession, clearAdminSession } from "../lib/adminSession";

/**
 * Task 84: `Sidebar` only needs router *context* (`Link`/`NavLink`),
 * not real routes to navigate between — so each test wraps it in a
 * bare `MemoryRouter` (no `Routes`) with `initialEntries` set to
 * whichever path the test cares about for `NavLink`'s active-class
 * behavior, rather than pulling in `adminDashboardTestRouter.tsx`'s
 * heavier five-page route table.
 */
function renderSidebar(props: { isOpen?: boolean; onClose?: () => void; route?: string } = {}) {
  const { isOpen = false, onClose = vi.fn(), route = "/" } = props;
  render(
    <MemoryRouter initialEntries={[route]}>
      <Sidebar isOpen={isOpen} onClose={onClose} />
    </MemoryRouter>,
  );
  return { onClose };
}

describe("Sidebar", () => {
  it("renders the logo and nav links with the right hrefs", () => {
    renderSidebar();

    expect(screen.getByRole("link", { name: "NATRA" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Seller" })).toHaveAttribute("href", "/seller");
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute(
      "href",
      "/admin-portal",
    );
  });

  it("adds the is-open class to the <aside> only when isOpen is true", () => {
    const { container: closedContainer } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Sidebar isOpen={false} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    expect(closedContainer.querySelector("aside")).not.toHaveClass("is-open");

    const { container: openContainer } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Sidebar isOpen={true} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    expect(openContainer.querySelector("aside")).toHaveClass("is-open");
  });

  it("marks only the current route's link active", () => {
    renderSidebar({ route: "/seller" });

    expect(screen.getByRole("link", { name: "Seller" })).toHaveClass(
      "sidebar__link--active",
    );
    expect(screen.getByRole("link", { name: "Home" })).not.toHaveClass(
      "sidebar__link--active",
    );
    expect(screen.getByRole("link", { name: "Admin" })).not.toHaveClass(
      "sidebar__link--active",
    );
  });

  it("marks Home active (via NavLink's end prop) only at exactly /, not other routes", () => {
    renderSidebar({ route: "/admin-portal" });

    expect(screen.getByRole("link", { name: "Home" })).not.toHaveClass(
      "sidebar__link--active",
    );
    expect(screen.getByRole("link", { name: "Admin" })).toHaveClass(
      "sidebar__link--active",
    );
  });

  it("calls onClose when a nav link is clicked", async () => {
    const { onClose } = renderSidebar();
    const user = userEvent.setup();

    await user.click(screen.getByRole("link", { name: "Seller" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the logo link is clicked", async () => {
    const { onClose } = renderSidebar();
    const user = userEvent.setup();

    await user.click(screen.getByRole("link", { name: "NATRA" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the close button is clicked", async () => {
    const { onClose } = renderSidebar({ isOpen: true });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Close menu" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  /**
   * Ad hoc addition alongside Sidebar.tsx's role-scoped sub-nav: the
   * seller/admin "functions" section only shows for a logged-in
   * session AND while inside that role's own area — never for a
   * logged-out visitor, and never for one role's functions while
   * browsing the other role's (or the storefront's) pages.
   */
  describe("role-scoped function sub-nav", () => {
    afterEach(() => {
      clearSellerSession();
      clearAdminSession();
    });

    it("shows seller functions only when logged in as seller AND inside /seller", () => {
      saveSellerSession({ token: "t", email: "seller@example.com" });
      renderSidebar({ route: "/seller/payment-methods" });

      expect(
        screen.getByRole("link", { name: "Payment Methods & Earnings" }),
      ).toHaveAttribute("href", "/seller/payment-methods");
      expect(
        screen.getByRole("link", { name: "Dashboard" }),
      ).toHaveAttribute("href", "/seller");
    });

    it("hides seller functions when not logged in, even inside /seller", () => {
      renderSidebar({ route: "/seller" });

      expect(
        screen.queryByRole("link", { name: "Payment Methods & Earnings" }),
      ).not.toBeInTheDocument();
    });

    it("hides seller functions when logged in but outside /seller", () => {
      saveSellerSession({ token: "t", email: "seller@example.com" });
      renderSidebar({ route: "/" });

      expect(
        screen.queryByRole("link", { name: "Payment Methods & Earnings" }),
      ).not.toBeInTheDocument();
    });

    it("shows admin functions only when logged in as admin AND inside /admin-portal", () => {
      saveAdminSession({ token: "t", email: "admin@example.com" });
      renderSidebar({ route: "/admin-portal/settlements" });

      expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
        "href",
        "/admin-portal/settings",
      );
      expect(
        screen.getByRole("link", { name: "Reports by Seller" }),
      ).toHaveAttribute("href", "/admin-portal/reports/by-seller");
    });

    it("hides admin functions when not logged in, even inside /admin-portal", () => {
      renderSidebar({ route: "/admin-portal" });

      expect(
        screen.queryByRole("link", { name: "Settlements" }),
      ).not.toBeInTheDocument();
    });

    it("does not show admin functions while browsing the seller area", () => {
      saveAdminSession({ token: "t", email: "admin@example.com" });
      renderSidebar({ route: "/seller" });

      expect(
        screen.queryByRole("link", { name: "Settlements" }),
      ).not.toBeInTheDocument();
    });

    it("calls onClose when a function sub-link is clicked", async () => {
      saveSellerSession({ token: "t", email: "seller@example.com" });
      const { onClose } = renderSidebar({ route: "/seller" });
      const user = userEvent.setup();

      await user.click(
        screen.getByRole("link", { name: "Payment Methods & Earnings" }),
      );

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});

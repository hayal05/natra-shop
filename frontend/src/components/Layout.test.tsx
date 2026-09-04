import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Layout from "./Layout";

const PAGE_CONTENT = "PAGE_CONTENT_PLACEHOLDER";

/**
 * `Layout` renders its child route via `<Outlet />`, so it needs a
 * real nested route (not just router context like `Sidebar.test.tsx`)
 * to render anything through it.
 */
function renderLayout(route = "/") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<div>{PAGE_CONTENT}</div>} />
          <Route path="seller" element={<div>SELLER_PLACEHOLDER</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("Layout", () => {
  it("renders the matched child route via Outlet", () => {
    renderLayout();

    expect(screen.getByText(PAGE_CONTENT)).toBeInTheDocument();
  });

  it("starts with the mobile nav closed: no backdrop, menu button collapsed", () => {
    renderLayout();

    expect(
      screen.getByRole("button", { name: "Open menu" }),
    ).toHaveAttribute("aria-expanded", "false");
    // The backdrop is only rendered while the mobile nav is open.
    expect(document.querySelector(".sidebar-backdrop")).not.toBeInTheDocument();
  });

  it("opens the mobile nav (backdrop appears, menu button expands) on the topbar button", async () => {
    renderLayout();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Open menu" }));

    expect(
      screen.getByRole("button", { name: "Open menu" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelector(".sidebar-backdrop")).toBeInTheDocument();
  });

  it("closes the mobile nav when the backdrop is clicked", async () => {
    renderLayout();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Open menu" }));
    expect(document.querySelector(".sidebar-backdrop")).toBeInTheDocument();

    await user.click(document.querySelector(".sidebar-backdrop")!);

    expect(document.querySelector(".sidebar-backdrop")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Open menu" }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the mobile nav (and navigates) when a sidebar link is clicked", async () => {
    renderLayout();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.click(screen.getByRole("link", { name: "Seller" }));

    expect(await screen.findByText("SELLER_PLACEHOLDER")).toBeInTheDocument();
    expect(document.querySelector(".sidebar-backdrop")).not.toBeInTheDocument();
  });
});

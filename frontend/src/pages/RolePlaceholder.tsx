type RolePlaceholderProps = {
  role: "Seller" | "Admin";
  nextTask: number;
  /**
   * True once every real view for this role (register/login/dashboard/
   * etc.) already exists, and this stub is only catching genuinely
   * unmatched sub-paths — not "the rest of the role isn't built yet".
   * Seller sets this from Task 57 on; Admin doesn't until its own
   * views are done (Tasks 58-61).
   */
  roleOtherwiseBuilt?: boolean;
};

/**
 * Shared stub for whatever part of the seller/admin route trees
 * doesn't have a real view yet. Seller register/login (Task 55), the
 * add/list-products dashboard (Task 56), and payment methods +
 * earnings (Task 57) now exist — the seller side is done, so its
 * catch-all sets `roleOtherwiseBuilt` and shows a plain "page not
 * found" message instead of "not built yet". Admin login (Task 58),
 * products overview (Task 59), settings (Task 60), settlements (Task
 * 61), and platform/per-seller reports (Tasks 62-63) now exist too —
 * the admin side is done as of Task 63, so its catch-all sets
 * `roleOtherwiseBuilt` the same way. Kept as one component so the
 * placeholders can't drift; each route in App.tsx passes its own
 * props.
 */
function RolePlaceholder({ role, nextTask, roleOtherwiseBuilt }: RolePlaceholderProps) {
  return (
    <div className="card">
      <h1>{role} area</h1>
      {roleOtherwiseBuilt ? (
        <p>This page doesn't exist. Try the {role.toLowerCase()} dashboard instead.</p>
      ) : (
        <p>
          The {role.toLowerCase()} login and dashboard views are built starting
          at Task {nextTask}. This page is Task 50's routing placeholder.
        </p>
      )}
      {role === "Admin" && (
        <p>
          <em>
            Note: this route lives at <code>/admin-portal</code>, not{" "}
            <code>/admin</code> — see App.tsx's routing comment.
          </em>
        </p>
      )}
    </div>
  );
}

export default RolePlaceholder;

import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState, type FormEvent } from "react";
import { clearSellerSession, getSellerSession } from "../lib/session";
import {
  createProduct,
  getMyProducts,
  type SellerProduct,
} from "../api/products";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type ListState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; products: SellerProduct[] };

type FormState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string };

/**
 * `/seller` index. Logged-out: links to login/register (Task 55).
 * Logged-in: the Task 56 dashboard — add a product (`POST /products`)
 * and view the seller's own products (`GET /products/mine`).
 *
 * Both calls send the session token from lib/session.ts. A 401/403
 * response (expired token, or a role mismatch that shouldn't normally
 * happen) clears the session and sends the seller to `/seller/login`
 * rather than showing a raw error — an expired session isn't really
 * an "error" from the seller's point of view, it's just "log in
 * again".
 */
function SellerHome() {
  const navigate = useNavigate();
  const [session, setSession] = useState(getSellerSession());
  const [listState, setListState] = useState<ListState>({ status: "loading" });
  const [formState, setFormState] = useState<FormState>({ status: "idle" });
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [description, setDescription] = useState("");
  const [driveLink, setDriveLink] = useState("");

  useEffect(() => {
    if (!session) return;
    let cancelled = false;

    setListState({ status: "loading" });
    getMyProducts(session.token)
      .then((products) => {
        if (!cancelled) setListState({ status: "ready", products });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          clearSellerSession();
          navigate("/seller/login", { replace: true });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load your products. Check your connection and try again.";
        setListState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [session, navigate]);

  function handleLogout() {
    clearSellerSession();
    setSession(null);
  }

  function handleAddProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;

    const trimmedName = name.trim();
    const trimmedDriveLink = driveLink.trim();
    const parsedPrice = Number(price);

    if (
      !trimmedName ||
      !trimmedDriveLink ||
      !Number.isFinite(parsedPrice) ||
      parsedPrice <= 0
    ) {
      return;
    }

    setFormState({ status: "submitting" });
    createProduct(session.token, {
      name: trimmedName,
      price: parsedPrice,
      description: description.trim(),
      drive_link: trimmedDriveLink,
    })
      .then((product) => {
        setFormState({ status: "idle" });
        setName("");
        setPrice("");
        setDescription("");
        setDriveLink("");
        setListState((prev) =>
          prev.status === "ready"
            ? { status: "ready", products: [product, ...prev.products] }
            : prev,
        );
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          clearSellerSession();
          navigate("/seller/login", { replace: true });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not add the product. Check your connection and try again.";
        setFormState({ status: "error", message });
      });
  }

  if (!session) {
    return (
      <div className="card">
        <h1>Seller area</h1>
        <p>Log in to your seller account, or register a new one.</p>
        <p>
          <Link className="btn-primary btn-link" to="/seller/login">
            Log in
          </Link>{" "}
          <Link className="btn-link" to="/seller/register">
            Register
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="seller-dashboard">
      <div className="card">
        <h1>Seller dashboard</h1>
        <p>
          Logged in as <strong>{session.email}</strong>.
        </p>
        <p>
          <Link className="btn-link" to="/seller/payment-methods">
            Payment methods &amp; earnings
          </Link>
        </p>
        <button className="btn-primary" onClick={handleLogout}>
          Log out
        </button>
      </div>

      <h2>Add a product</h2>
      <form className="card auth-form" onSubmit={handleAddProduct}>
        <label htmlFor="product-name">Name</label>
        <input
          id="product-name"
          type="text"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="product-price">Price (ETB)</label>
        <input
          id="product-price"
          type="number"
          required
          min="0.01"
          step="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="product-description">Description</label>
        <textarea
          id="product-description"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        <label htmlFor="product-drive-link">Public Google Drive link</label>
        <input
          id="product-drive-link"
          type="url"
          required
          placeholder="https://drive.google.com/..."
          value={driveLink}
          onChange={(e) => setDriveLink(e.target.value)}
          disabled={formState.status === "submitting"}
        />

        {formState.status === "error" && (
          <p className="form-error" role="alert">
            {formState.message}
          </p>
        )}

        <button
          className="btn-primary"
          type="submit"
          disabled={formState.status === "submitting"}
        >
          {formState.status === "submitting" ? "Adding…" : "Add product"}
        </button>
      </form>

      <h2>Your products</h2>

      {listState.status === "loading" && <p>Loading your products…</p>}

      {listState.status === "error" && (
        <div className="card" role="alert">
          <p>{listState.message}</p>
        </div>
      )}

      {listState.status === "ready" && listState.products.length === 0 && (
        <p>You haven't added any products yet.</p>
      )}

      {listState.status === "ready" && listState.products.length > 0 && (
        <ul className="seller-product-list">
          {listState.products.map((product) => (
            <li key={product.id} className="card seller-product-list__item">
              <p className="seller-product-list__name">{product.name}</p>
              <p className="seller-product-list__price">
                {formatPrice(product.price)}
              </p>
              {product.description && (
                <p className="seller-product-list__description">
                  {product.description}
                </p>
              )}
              <p>
                <a href={product.drive_link} target="_blank" rel="noreferrer">
                  Drive link
                </a>
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default SellerHome;

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getProducts, type ProductGridItem } from "../api/products";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; products: ProductGridItem[] };

/**
 * Task 51: real buyer product grid, backed by GET /products.
 * Product-detail navigation (Link to /product/:id) exists here but the
 * destination page is still Task 52's placeholder — that's expected,
 * not a bug in this task.
 */
function BuyerHome() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    getProducts()
      .then((products) => {
        if (!cancelled) setState({ status: "ready", products });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load products. Check your connection and try again.";
        setState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p>Loading products…</p>;
  }

  if (state.status === "error") {
    return (
      <div className="card" role="alert">
        <p>{state.message}</p>
      </div>
    );
  }

  if (state.products.length === 0) {
    return (
      <div className="card">
        <p>No products are listed yet — check back soon.</p>
      </div>
    );
  }

  return (
    <div className="product-grid">
      {state.products.map((product) => (
        <Link
          key={product.id}
          to={`/product/${product.id}`}
          className="product-card"
        >
          {/* Object Storage image resolution doesn't exist yet (see
              ARCHITECTURE.md: "products.thumbnail_ref exists but is
              unused for now" — no upload endpoint or Object Storage
              integration has been built). Every product shows this
              placeholder until that's built; there's no thumbnail URL
              to construct from thumbnail_ref today even when it's set. */}
          <div className="product-card__thumb">No image</div>
          <div className="product-card__body">
            <p className="product-card__name">{product.name}</p>
            <p className="product-card__price">{formatPrice(product.price)}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}

export default BuyerHome;

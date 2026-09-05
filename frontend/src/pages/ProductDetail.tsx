import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getProductDetail, type ProductDetail as ProductDetailType } from "../api/products";
import { ApiError } from "../api/client";
import { formatPrice } from "../lib/format";

type LoadState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error"; message: string }
  | { status: "ready"; product: ProductDetailType };

/**
 * Task 52: real product details view, backed by GET /products/{id}.
 * The "Buy Now" button is a visible placeholder only — Task 53 wires
 * it up to the payment-info/receipt-submission flow.
 *
 * Task 105: mirrors Task 104's `BuyerHome.tsx` treatment — renders an
 * <img> from `thumbnail_ref` when it's set (a real Object Storage URL
 * since Task 95), falling back to the pre-existing "No image"
 * placeholder only when it's `null`.
 */
function ProductDetail() {
  const { productId } = useParams();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    if (!productId) return;
    let cancelled = false;

    getProductDetail(productId)
      .then((product) => {
        if (!cancelled) setState({ status: "ready", product });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ status: "not-found" });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load this product. Check your connection and try again.";
        setState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [productId]);

  if (state.status === "loading") {
    return <p>Loading product…</p>;
  }

  if (state.status === "not-found") {
    return (
      <div className="card">
        <p>This product doesn't exist or may have been removed.</p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="card" role="alert">
        <p>{state.message}</p>
      </div>
    );
  }

  const { product } = state;

  return (
    <div className="product-detail">
      {product.thumbnail_ref ? (
        <img
          className="product-detail__thumb-img"
          src={product.thumbnail_ref}
          alt=""
        />
      ) : (
        <div className="product-detail__thumb">No image</div>
      )}
      <div className="product-detail__body">
        <h1>{product.name}</h1>
        <p className="product-detail__price">{formatPrice(product.price)}</p>
        {product.description ? (
          <p className="product-detail__description">{product.description}</p>
        ) : (
          <p className="product-detail__description product-detail__description--empty">
            No description provided.
          </p>
        )}
        <Link className="btn-primary btn-link" to={`/product/${product.id}/buy`}>
          Buy Now
        </Link>
      </div>
    </div>
  );
}

export default ProductDetail;

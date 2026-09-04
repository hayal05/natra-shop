/**
 * All prices in the backend (products.price, sales.commission/payable,
 * etc.) are plain NUMBER(12,2) Ethiopian Birr amounts — no currency
 * field anywhere in the schema, so ETB is hardcoded here rather than
 * read from the API.
 */
export function formatPrice(amount: number): string {
  return `${amount.toFixed(2)} ETB`;
}

import { describe, expect, it } from "vitest";
import { formatPrice } from "./format";

describe("formatPrice", () => {
  it("formats a whole number with two decimal places and the ETB suffix", () => {
    expect(formatPrice(150)).toBe("150.00 ETB");
  });

  it("formats zero", () => {
    expect(formatPrice(0)).toBe("0.00 ETB");
  });

  it("rounds to two decimal places", () => {
    expect(formatPrice(19.999)).toBe("20.00 ETB");
    expect(formatPrice(19.995)).toBe("20.00 ETB");
  });

  it("keeps two decimal places even when the amount already has fewer/none", () => {
    expect(formatPrice(19.5)).toBe("19.50 ETB");
    expect(formatPrice(19)).toBe("19.00 ETB");
  });

  it("does not insert thousands separators for large amounts", () => {
    expect(formatPrice(1234567)).toBe("1234567.00 ETB");
  });
});

import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatInt,
  formatKrw,
  formatPct,
  formatSignedPct,
} from "./formatters";

describe("formatters", () => {
  it("formatKrw — 정수화 + 콤마 + 원", () => {
    expect(formatKrw(1234567)).toBe("1,234,567원");
    expect(formatKrw(1234.7)).toBe("1,235원"); // Math.round
    expect(formatKrw(0)).toBe("0원");
    expect(formatKrw(null)).toBe("—");
    expect(formatKrw(undefined)).toBe("—");
    expect(formatKrw(NaN)).toBe("—");
    expect(formatKrw(Infinity)).toBe("—");
  });

  it("formatInt — Math.round + 콤마", () => {
    expect(formatInt(1234.7)).toBe("1,235");
    expect(formatInt(null)).toBe("—");
  });

  it("formatPct — 소수 2자리 + %", () => {
    expect(formatPct(1.8857)).toBe("1.89%");
    expect(formatPct(0)).toBe("0.00%");
    expect(formatPct(null)).toBe("—");
  });

  it("formatSignedPct — 양수에 + 부호", () => {
    expect(formatSignedPct(1.5)).toBe("+1.50%");
    expect(formatSignedPct(-2.3)).toBe("-2.30%");
    expect(formatSignedPct(0)).toBe("+0.00%");
    expect(formatSignedPct(null)).toBe("—");
  });

  it("formatDate — ISO 그대로 반환, 빈 값은 —", () => {
    expect(formatDate("2024-01-12")).toBe("2024-01-12");
    expect(formatDate(null)).toBe("—");
    expect(formatDate("")).toBe("—");
  });
});

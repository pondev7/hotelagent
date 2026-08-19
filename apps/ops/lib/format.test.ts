import { describe, expect, it } from "vitest";

import { formatCommission, maskPhone } from "./format";

describe("formatCommission", () => {
  it("keeps the digits the API sent, without parsing them", () => {
    expect(formatCommission("15.00")).toBe("15%");
    expect(formatCommission("13.50")).toBe("13.5%");
  });

  it("does not round a rate that needs both decimals", () => {
    expect(formatCommission("12.25")).toBe("12.25%");
  });

  it("survives an integer rate", () => {
    expect(formatCommission("15")).toBe("15%");
  });
});

describe("maskPhone", () => {
  it("shows the last four so a number can be recognised but not read off", () => {
    // The country prefix survives — only digits are masked. Keeping the `+91`
    // shape visible is what lets an operator spot a number that is not Indian
    // at all, which is usually a data-entry mistake.
    expect(maskPhone("+919800000001")).toBe("+••••••••0001");
  });

  it("renders an em dash when a hotel has no reception number", () => {
    // Tier C's entire integration is this column. An empty cell would read as
    // "loading"; the dash reads as "we do not have one", which is a fact an
    // operator can act on.
    expect(maskPhone(null)).toBe("—");
  });
});

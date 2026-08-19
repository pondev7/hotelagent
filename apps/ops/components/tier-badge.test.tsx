import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TierBadge } from "./tier-badge";

describe("TierBadge", () => {
  it("names the tier and explains what it costs in operator time", () => {
    render(<TierBadge tier="manual" />);

    const badge = screen.getByText("Manual");
    expect(badge).toBeInTheDocument();
    // The hint is what makes the badge legible to someone new on the desk.
    expect(badge).toHaveAttribute("title", expect.stringContaining("telephones reception"));
  });

  it("renders every tier the API can send", () => {
    // The map is exhaustive over the generated union, so this fails loudly if a
    // fourth tier is added in Python and forgotten here.
    for (const tier of ["live", "bot", "manual"] as const) {
      const { unmount } = render(<TierBadge tier={tier} />);
      expect(screen.getByTitle(/Tier [ABC]/)).toBeInTheDocument();
      unmount();
    }
  });
});

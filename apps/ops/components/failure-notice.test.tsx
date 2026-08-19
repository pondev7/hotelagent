/**
 * *"It survives the API being down without a blank screen."*
 *
 * The client tests prove the failure is classified correctly; these prove the
 * classification reaches the screen as words an operator can act on.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FailureNotice } from "./failure-notice";
import { ApiError } from "@/lib/api";

describe("FailureNotice", () => {
  it("tells the operator the desk is offline, and how to fix it", () => {
    render(
      <FailureNotice error={new ApiError("unreachable", "boom")} what="the hotel directory" />,
    );

    expect(screen.getByText(/cannot reach the api/i)).toBeInTheDocument();
    expect(screen.getByText(/make dev/)).toBeInTheDocument();
  });

  it("reassures that the console is a view, not the record", () => {
    // An operator seeing an error mid-shift needs to know whether bookings are
    // at risk. At M1 they are not: the record is Postgres, and this is a
    // window onto it.
    render(<FailureNotice error={new ApiError("timeout", "slow")} what="the directory" />);

    expect(screen.getByText(/a view, not the record/i)).toBeInTheDocument();
  });

  it("passes the API's own message through for a domain error", () => {
    const error = new ApiError("http", "404", {
      status: 404,
      body: { code: "unknown_hotel", message: "hotel 123 is not in city 456", detail: null },
    });

    render(<FailureNotice error={error} what="this hotel" />);

    expect(screen.getByText("hotel 123 is not in city 456")).toBeInTheDocument();
    // Not an outage — so it must not offer the `make dev` remedy.
    expect(screen.queryByText(/make dev/)).not.toBeInTheDocument();
  });

  it("renders something legible even for an error it has never seen", () => {
    // A thrown string, a null, a framework error. The component is the last
    // thing between an unexpected value and a blank page, so it must not
    // assume it was handed an ApiError.
    render(<FailureNotice error={"a bare string"} what="the directory" />);

    expect(screen.getByText(/could not load the directory/i)).toBeInTheDocument();
    expect(screen.getByText(/unexpected error/i)).toBeInTheDocument();
  });
});

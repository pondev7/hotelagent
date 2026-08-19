/**
 * S08's exit criterion has two halves, and this file specifies the second:
 * *"it survives the API being down without a blank screen."*
 *
 * That is a statement about failure paths, so failure paths are what is tested.
 * The happy path is covered incidentally — it is the easy case, and it is the
 * one that gets exercised by hand every time anyone opens the console.
 *
 * `fetch` is stubbed rather than a server being started. These tests are about
 * how the client interprets what comes back, and a real server is both slower
 * and unable to produce the interesting cases on demand: you cannot ask a
 * healthy API for a timeout.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getHotel, listCities, listHotels } from "./api";

function respondWith(body: unknown, init: ResponseInit = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200, ...init })),
  );
}

function failWith(error: Error): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw error;
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the request the client actually sends", () => {
  it("scopes the directory to a city", async () => {
    respondWith({ items: [], total: 0, limit: 50, offset: 0 });

    await listHotels({ cityId: "city-1" });

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("city_id=city-1");
  });

  it("omits the tier parameter entirely when no tier is chosen", async () => {
    respondWith({ items: [], total: 0, limit: 50, offset: 0 });

    await listHotels({ cityId: "city-1", tier: null });

    // `?tier=` with an empty value is not the same request as no `tier` at all:
    // the API would reject the empty string against the enum and answer 422,
    // turning "show me everything" into an error page.
    expect(String(vi.mocked(fetch).mock.calls[0][0])).not.toContain("tier=");
  });

  it("sends the tier when one is chosen, so filtering happens in SQL", async () => {
    respondWith({ items: [], total: 0, limit: 50, offset: 0 });

    await listHotels({ cityId: "city-1", tier: "manual" });

    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain("tier=manual");
  });

  it("asks for cities without a city, because that is the endpoint that supplies one", async () => {
    respondWith([]);

    await listCities();

    expect(String(vi.mocked(fetch).mock.calls[0][0])).not.toContain("city_id");
  });

  it("escapes an id rather than pasting it into the path", async () => {
    respondWith({ hotel_id: "x" });

    await getHotel("../conversations", "city-1");

    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain("%2F");
  });
});

describe("what the operator is told when it fails", () => {
  it("reports an unreachable API as unreachable, not as a crash", async () => {
    failWith(new TypeError("fetch failed"));

    const error = await listCities().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe("unreachable");
    // The one sentence that reaches the screen. It has to say something an
    // operator can act on, not "TypeError: fetch failed".
    expect((error as ApiError).operatorMessage).toMatch(/not responding/i);
  });

  it("distinguishes a timeout from a refused connection", async () => {
    const timeout = new Error("timed out");
    timeout.name = "TimeoutError";
    failWith(timeout);

    const error = (await listCities().catch((caught: unknown) => caught)) as ApiError;

    expect(error.kind).toBe("timeout");
    expect(error.operatorMessage).toMatch(/too long/i);
  });

  it("prefers the API's own message over our generic one", async () => {
    respondWith(
      {
        error: {
          code: "unknown_hotel",
          message: "hotel 123 is not in city 456",
          detail: null,
        },
      },
      { status: 404 },
    );

    const error = (await getHotel("123", "456").catch((caught: unknown) => caught)) as ApiError;

    expect(error.kind).toBe("http");
    expect(error.status).toBe(404);
    // `code` is what the UI branches on; it is stable across a Python rename,
    // which the class name is not.
    expect(error.body?.code).toBe("unknown_hotel");
    expect(error.operatorMessage).toBe("hotel 123 is not in city 456");
  });

  it("survives an error response that is not in our envelope", async () => {
    // A 502 from a reverse proxy is HTML, not our JSON. The console still has
    // to render something — this is the case that produces a blank screen if
    // the client assumes every failure is well-formed.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>502 Bad Gateway</html>", { status: 502 })),
    );

    const error = (await listCities().catch((caught: unknown) => caught)) as ApiError;

    expect(error.kind).toBe("malformed");
    expect(error.operatorMessage).toMatch(/does not understand/i);
  });

  it("does not mistake a 200 with a broken body for success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("not json at all", { status: 200 })),
    );

    const error = (await listCities().catch((caught: unknown) => caught)) as ApiError;

    expect(error.kind).toBe("malformed");
  });

  it("does not retry — the operator is already watching", async () => {
    failWith(new TypeError("fetch failed"));

    await listCities().catch(() => undefined);

    expect(vi.mocked(fetch)).toHaveBeenCalledOnce();
  });
});

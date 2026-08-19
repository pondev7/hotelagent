/**
 * The one place the console talks to the API.
 *
 * Every function here is typed from `packages/contracts`, which is generated
 * from the API's own OpenAPI document. Nothing in this file describes a
 * response shape by hand — that is the whole point. A field renamed in Python
 * fails `make contracts`, and a field *used* incorrectly fails `tsc`, so the
 * console cannot drift from the API without something going red first.
 *
 * These run on the server. Next renders these pages on the Node side and the
 * browser never calls the API directly, which is why `OPS_API_BASE_URL` exists
 * separately from `NEXT_PUBLIC_API_BASE_URL`: inside Docker the API answers to
 * `http://api:8000` on the container network and to `http://localhost:8000`
 * from the operator's browser. One variable cannot be both.
 */

import type { City, Hotel, IntegrationTier, Page } from "@contracts";

/**
 * Why not `NEXT_PUBLIC_*` alone: a `NEXT_PUBLIC_` variable is inlined into the
 * browser bundle at build time. A server-side base URL neither needs to be nor
 * should be — it names an internal address that is useless to a browser and
 * mildly informative to an attacker.
 */
const BASE_URL =
  process.env.OPS_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

/** How long we wait before deciding the API is not going to answer. */
const TIMEOUT_MS = 8_000;

/**
 * Every failure the console can render, as one closed set.
 *
 * `unreachable` and `timeout` are deliberately distinct from `http`: the API
 * being down is an operational fact the operator can act on ("the desk is
 * offline, ring the hotel"), while a 404 is a fact about the thing they asked
 * for. Collapsing them into "something went wrong" is what produces a console
 * nobody trusts.
 */
export type FailureKind = "unreachable" | "timeout" | "http" | "malformed";

/** The error envelope every non-2xx response carries — see `errors.py`. */
export interface ApiErrorBody {
  code: string;
  message: string;
  detail: Record<string, unknown> | null;
}

export class ApiError extends Error {
  readonly kind: FailureKind;
  readonly status: number | null;
  /** Present only when the API answered in its own envelope. */
  readonly body: ApiErrorBody | null;

  constructor(
    kind: FailureKind,
    message: string,
    options: { status?: number | null; body?: ApiErrorBody | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status ?? null;
    this.body = options.body ?? null;
  }

  /**
   * What an operator should be told, in preference order.
   *
   * The API's `message` wins when there is one, because it knows what actually
   * happened ("hotel ... is not in city ..."). The fallbacks describe the
   * transport, which is all we know when the response never arrived.
   */
  get operatorMessage(): string {
    if (this.body?.message) return this.body.message;
    switch (this.kind) {
      case "unreachable":
        return "The API is not responding. It may be starting up, or not running.";
      case "timeout":
        return "The API took too long to answer.";
      case "malformed":
        return "The API answered in a shape this console does not understand.";
      case "http":
        return `The API refused the request (HTTP ${this.status ?? "?"}).`;
    }
  }
}

function isErrorBody(value: unknown): value is { error: ApiErrorBody } {
  if (typeof value !== "object" || value === null) return false;
  const envelope = (value as { error?: unknown }).error;
  if (typeof envelope !== "object" || envelope === null) return false;
  const { code, message } = envelope as { code?: unknown; message?: unknown };
  return typeof code === "string" && typeof message === "string";
}

/**
 * One fetch, one error type.
 *
 * Note what this does *not* do: retry. A GET behind an operator staring at a
 * screen is already retried by the human, and a silent retry only doubles the
 * time before they learn the desk is offline. Retries belong on the outbound
 * side, where nobody is watching (see `http_max_attempts` in `config.py`).
 */
async function request<T>(path: string, params: URLSearchParams): Promise<T> {
  const url = `${BASE_URL}${path}?${params.toString()}`;

  let response: Response;
  try {
    response = await fetch(url, {
      signal: AbortSignal.timeout(TIMEOUT_MS),
      headers: { accept: "application/json" },
      // Operator screens must not show yesterday's directory. Next caches
      // fetches in server components by default; this opts out explicitly
      // rather than relying on the default staying what it is today.
      cache: "no-store",
    });
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "TimeoutError";
    throw new ApiError(
      timedOut ? "timeout" : "unreachable",
      `${timedOut ? "timed out" : "could not reach"} ${path}`,
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("malformed", `${path} did not return JSON`, {
      status: response.status,
    });
  }

  if (!response.ok) {
    throw new ApiError("http", `${path} returned ${response.status}`, {
      status: response.status,
      body: isErrorBody(payload) ? payload.error : null,
    });
  }

  return payload as T;
}

/**
 * The cities an operator may be scoped to.
 *
 * The only call that takes no `city_id`, because it is the one that supplies
 * them.
 */
export function listCities(): Promise<City[]> {
  return request<City[]>("/api/cities", new URLSearchParams());
}

export interface HotelQuery {
  cityId: string;
  tier?: IntegrationTier | null;
  limit?: number;
  offset?: number;
}

/**
 * The directory for one city.
 *
 * `cityId` is a required argument rather than an optional one with a default,
 * mirroring the API. Invariant #1 is only worth anything if it is impossible to
 * forget at every layer, and a default here would quietly reintroduce exactly
 * what `params.py` refused to allow.
 */
export function listHotels({
  cityId,
  tier,
  limit = 50,
  offset = 0,
}: HotelQuery): Promise<Page<Hotel>> {
  const params = new URLSearchParams({
    city_id: cityId,
    limit: String(limit),
    offset: String(offset),
  });
  if (tier) params.set("tier", tier);
  return request<Page<Hotel>>("/api/hotels", params);
}

export function getHotel(hotelId: string, cityId: string): Promise<Hotel> {
  return request<Hotel>(
    `/api/hotels/${encodeURIComponent(hotelId)}`,
    new URLSearchParams({ city_id: cityId }),
  );
}

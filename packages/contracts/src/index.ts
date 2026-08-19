/**
 * The names the ops console imports.
 *
 * `generated.ts` is machine-written and gitignored — it is a faithful but
 * verbose transcription of the OpenAPI document, where a hotel is spelled
 * `components["schemas"]["HotelSummary"]`. This file is the hand-written,
 * committed layer that gives those types the names a React component wants.
 *
 * It is type-only, so it costs nothing at runtime, and it is load-bearing as a
 * drift check: rename or remove a schema on the Python side and `make contracts`
 * fails here at `tsc` rather than six months later in a component that silently
 * became `any`.
 */

import type { components } from "./generated.js";

type Schemas = components["schemas"];

/**
 * A market the console can be scoped to.
 *
 * The console's entry point: every other request carries a `city_id`, and this
 * is the only endpoint that hands one out. Unlike the rest, it is a bare array
 * rather than a `Page` — cities are a bounded set, and staying outside the page
 * envelope is what keeps it outside the "every paginated collection is
 * city-scoped" rule it could not satisfy.
 */
export type City = Schemas["CitySummary"];

/** A hotel as the directory screen shows it. */
export type Hotel = Schemas["HotelSummary"];

/**
 * How we learn whether a room is free. The directory filters on it.
 *
 * Exported as a type, not a value: `generated.ts` publishes it as a string
 * union, so a `tier` that is not one of these three fails at `tsc` rather than
 * at the API as a 422.
 */
export type IntegrationTier = Schemas["IntegrationTier"];

/** One row of the unified inbox. */
export type Conversation = Schemas["ConversationSummary"];

/** One turn of a transcript. */
export type Message = Schemas["MessageOut"];

/** A unit of work for an operator: which hotel to ring, and what to ask. */
export type CallTask = Schemas["CallTaskSummary"];

/**
 * Every non-2xx response body, without exception.
 *
 * One error type is the whole point of overriding FastAPI's own validation
 * response: a call site handles failure once, not once per status code.
 */
export type ErrorEnvelope = Schemas["ErrorEnvelope"];

/**
 * The pagination envelope.
 *
 * FastAPI publishes each instantiation of the Python `Page[T]` as its own schema
 * (`Page_HotelSummary_`), so the generic is reconstructed here. Declared
 * structurally rather than aliased to one of them, which keeps a single `<Table
 * of T>` component possible on the console side.
 */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

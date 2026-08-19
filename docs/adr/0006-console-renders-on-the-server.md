# 0006 — The ops console fetches on the server, and gets its city from the API

- **Status:** accepted
- **Date:** 2026-08-19
- **Slice:** M1 / S08

## Context

S08 puts the first real screen in front of an operator. Three questions had to
be answered before a single component was written, and all three are expensive
to change later.

**1. Where does data fetching happen?** The Next.js App Router allows either:
server components that `await` the API during render, or client components that
`useEffect` and `fetch` from the browser. The repository was ambiguous — the
skeleton shipped `NEXT_PUBLIC_API_BASE_URL`, which implies the browser calls the
API, while `cors_origins` in `config.py` implies the same.

**2. How does the console obtain a `city_id`?** Every collection in the API
requires one (`api/params.py`, invariant #1) and deliberately has no default.
There was no endpoint that returned cities, and city ids are uuid7 values minted
when the row is created — so they differ between a laptop, CI and production and
cannot be baked into a build.

**3. Where is the tier filter applied?** S08's deliverable says "filter by
tier", and `GET /api/hotels` had no such parameter.

## Decision

**Data fetching happens on the server.** Pages are server components that call
`lib/api.ts` directly. Only three components are `"use client"`: the theme
toggle, the city switcher, and the theme provider — each because it needs
browser state or an event handler, and for no other reason.

This introduces `OPS_API_BASE_URL` alongside `NEXT_PUBLIC_API_BASE_URL`. They
are genuinely different addresses: under Compose the rendering server reaches
the API at `http://api:8000` on the container network, while the operator's
browser can only reach `http://localhost:8000`.

**`GET /api/cities` was added**, returning a bare array rather than a `Page`. It
is the one endpoint that takes no `city_id`, because it is the tenancy root.
The selected city then lives in the URL (`?city=<uuid>`), not in React state.

**The tier filter is a query parameter** on `GET /api/hotels`, typed as the
`IntegrationTier` enum, applied in SQL to both the page and the count.

## Consequences

Good:

- No API URL, no CORS surface and no credentials reach the browser. CORS
  remains configured because S09's polling will need it.
- Loading states come from `loading.tsx` and Suspense rather than from a
  `useState` triple in every component. There is no `useEffect` in the console.
- Filter and city are in the URL, so a screen is linkable, bookmarkable, and
  survives a reload. A mis-scoped screen is diagnosed by reading the address bar.
- `total` is honest. Filtering in the browser would have hidden rows from the
  current page while still reporting the unfiltered count — correct at five
  hotels, wrong at fifty.
- The city list is unpaginated, so it stays outside `_list_operations()` in
  `test_openapi_contract.py`. The alternative was an allowlist exempting it from
  "every list endpoint requires a `city_id`", and an allowlist on a tenancy
  check is what rots into a leak.

Costs and risks:

- Two base-URL variables is a real trap. Someone will eventually set only the
  `NEXT_PUBLIC_` one and get a console that works in the browser's imagination
  and not on the server. The fallback chain in `lib/api.ts` softens it.
- Every interaction is a server round-trip. Fine for a directory; the inbox
  (S09) will want optimistic updates for the reply composer, which means that
  screen keeps local state even though this one does not.
- `packages/contracts` is outside the `apps/ops` Docker build context, so a
  `next build` *inside* the container cannot typecheck. Dev works (type-only
  imports are erased without resolution). Packaging this properly is S12's
  problem, not S08's.

## When to revisit

- If a screen needs sub-second interaction that a round-trip cannot serve —
  the call-task queue (S10) is the likely first case.
- If a second client of the API appears (a hotelier dashboard, M4) that needs
  browser-side calls, the CORS and `NEXT_PUBLIC_` story becomes load-bearing
  rather than vestigial.
- If cities ever number in the hundreds, `GET /api/cities` needs pagination —
  and at that point it needs a scoping story of its own, because an operator
  should not see every market.

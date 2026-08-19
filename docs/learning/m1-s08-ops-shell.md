# S08 — Ops console shell and hotel directory · learning notes

> Companion to `M1 slice 08`. Read `docs/milestone-1.md` §S08 for the contract
> this slice was built against, and `docs/adr/0006-console-renders-on-the-server.md`
> for the three decisions taken before any component was written.

## What we built

The first real operator screen: a hotel directory that lists a city's hotels
with their tier, commission and verification state, filterable by tier, with a
read-only detail view behind each name. Underneath it sits the React foundation
every later console slice reuses — an app shell with navigation, a city
switcher, dark mode, a typed API client generated from the API's own OpenAPI
document, and designed loading, empty and failure states. Three small additions
to the Python side made it possible at all: `GET /api/cities`, a `?tier=` filter
on the directory, and `make seed`.

This is also the slice where the frontend stopped being ungated: `make lint` now
typechecks the console and `make test` runs its suite, with a second CI job
behind both.

---

## The concepts

### 1. What React actually is

React is a library for describing what the screen should look like *as a
function of data*, and letting something else work out how to get the DOM into
that shape.

The traditional way to update a page is to reach into the DOM and mutate it:
find the element, set its text, add a class. That works and it does not scale,
because the number of possible transitions between states grows as the square of
the number of states. You end up writing "if we were showing an error and now we
have data, remove the error node, re-enable the button, restore the heading".

React inverts it. You write one function that says what the page looks like
*given the current data*, and you never write a transition at all:

```tsx
function TierBadge({ tier }: { tier: IntegrationTier }) {
  const { label, hint, variant } = TIERS[tier];
  return <Badge variant={variant} title={hint}>{label}</Badge>;
}
```

That is a **component**: a function taking data (**props**) and returning a
description of UI. It is not HTML and it does not touch the DOM. It returns an
object tree — "a `Badge` with these props, containing this text" — and React
compares that tree to the previous one and applies the minimum set of DOM
operations to close the gap. That comparison is the **reconciler**, and it is
the reason you can write "here is what the page is" instead of "here is how the
page changes".

### 2. JSX is not HTML

`<Badge variant={variant}>` is **JSX** — syntax sugar that compiles to a
function call. That expression becomes roughly:

```ts
jsx(Badge, { variant: variant, title: hint, children: label })
```

Three consequences follow, and each one explains something that otherwise looks
arbitrary:

- **It is an expression.** You can put it in a variable, return it from a
  conditional, or `.map()` an array into a list of them — which is exactly what
  the directory does with `page.items.map(...)`.
- **Attributes are JavaScript, not strings.** `className` rather than `class`,
  because `class` is a reserved word; `{...props}` spreads an object into
  attributes.
- **A capitalised tag is a component; a lowercase tag is a DOM element.**
  `<Badge>` compiles to a reference to the `Badge` function. `<span>` compiles
  to the string `"span"`. Forget to import a component and you get a mystifying
  "the tag is not recognised" rather than "undefined variable".

### 3. Why re-renders happen, and what that costs

React re-runs a component function when its props change, when its state
changes, or when its parent re-renders. "Re-render" means *calling the function
again and diffing the result* — not touching the DOM. The DOM work is whatever
the diff turned out to require, which is often nothing.

This is why the usual performance panic is misplaced. A component re-rendering
is cheap; a component re-rendering and producing a *different tree shape* is
what costs. It is also why `key` matters on a list:

```tsx
{page.items.map((hotel) => (
  <TableRow key={hotel.hotel_id}>
```

Without a key, React matches old children to new by position. Insert a hotel at
the top and every row is "changed". With a stable key it matches by identity,
sees one insertion, and does one DOM operation. Using the array index as a key
is the classic bug: it is positional, so it buys nothing precisely when it
matters.

In this slice almost nothing re-renders, because almost nothing is interactive —
which brings us to the decision that shapes the whole console.

### 4. Server components and client components

The App Router runs components in **two different places**, and the distinction
is the single most important thing to understand about modern Next.js.

By default a component is a **server component**. It executes on the Node
server, during the request, and its output is serialised into the HTML sent to
the browser. It can be `async`. It can read a database or call an API with a
secret. Its code is *never sent to the browser*.

A component marked `"use client"` at the top of its file is a **client
component**. Its code is compiled into the JavaScript bundle, shipped, and
executed in the browser. Only client components may use state, effects, event
handlers, or browser APIs — because only they run somewhere those things exist.

Our directory page is a server component, and that is why it can do this:

```tsx
export default async function HotelsPage({ searchParams }) {
  const cities = await listCities();
  const page = await listHotels({ cityId: city.city_id, tier });
```

An `await` in the middle of a component, with no loading state, no `useEffect`
and no `useState`. The page simply does not exist until the data has arrived,
because it is rendered on a machine that can wait.

Three components in this console are `"use client"`, each for a specific
reason:

| Component | Why |
|---|---|
| `theme-provider.tsx` | `next-themes` needs React context |
| `theme-toggle.tsx` | needs `useState`, `useEffect` and an `onClick` |
| `city-switcher.tsx` | needs an `onChange` handler and `useTransition` |

Everything else — the shell, the table, the badges, the filter, both pages —
runs on the server and ships zero JavaScript. The build output shows the result:
`118 kB` first-load JS for a full data screen, almost all of it React itself.

The boundary is one-directional in an important way: a server component may
render a client component (it becomes a placeholder that hydrates in the
browser), but a client component cannot import a server component. That is why
`theme-provider.tsx` exists as a one-line wrapper — marking `layout.tsx` itself
`"use client"` would drag every page inside it into the browser bundle.

### 5. File-based routing, and what each special filename does

The App Router maps directories to URLs. A folder becomes a path segment; a file
with a reserved name becomes a role in that segment:

```
app/
  layout.tsx              → wraps everything; <html> and <body> live here
  page.tsx                → GET /
  hotels/
    page.tsx              → GET /hotels
    loading.tsx           → the Suspense fallback while page.tsx awaits
    [hotelId]/
      page.tsx            → GET /hotels/<anything>
```

Square brackets make a **dynamic segment**, and the matched value arrives as
`params`. `loading.tsx` is the one that looks like magic and is not: Next wraps
the route in a `<Suspense>` boundary whose fallback is that file. The shell
paints instantly, the table's space shows skeletons, and the data streams in
when it lands. We wrote no Suspense boundary and no loading flag.

In Next 15, both `params` and `searchParams` are **promises**:

```tsx
const params = await searchParams;
```

That is not ceremony. Awaiting them is how a page declares "my output depends on
this request", which is what moves it from statically prerendered to
server-rendered on demand. The build output labels each route accordingly — `○`
static, `ƒ` dynamic.

### 6. Fetching and caching, and one deliberate opt-out

Next patches the global `fetch` in server components to add caching. That is
useful for a marketing page and wrong for an operator's screen, so the client
opts out explicitly:

```ts
response = await fetch(url, { cache: "no-store", ... });
```

An operator looking at a directory that is thirty seconds stale has been told a
small lie by their tools, and a console that lies occasionally is a console that
gets checked against WhatsApp every time. Note the comment in `lib/api.ts`: this
is written down not because the current default requires it, but so that a
change to the default cannot silently change our behaviour.

### 7. The URL as state

The directory has two pieces of state — which city, which tier — and neither
lives in React:

```tsx
const city = cities.find((c) => c.city_id === requested) ?? cities[0];
const tier = parseTier(params.tier);
```

Both come out of the URL. The tier filter is therefore not a component with an
`onClick` at all; it is four `<Link>`s:

```tsx
<Link href={`/hotels?${params.toString()}`}>
```

This is worth dwelling on, because the instinct from most UI frameworks is to
reach for `useState`. Putting it in the URL buys: a screen you can send to a
colleague, a filter that survives a reload, "open in new tab" to compare two
tiers, working back and forward buttons, zero JavaScript, and — the operational
one — a mis-scoped screen you can diagnose by *reading the address bar* instead
of inspecting a store.

The rule of thumb: state that describes **what you are looking at** belongs in
the URL. State that describes **how you are looking at it** (a dropdown being
open) belongs in the component.

### 8. Hydration, and the mismatch that theme toggles always cause

The server renders HTML. The browser then runs React over that HTML and attaches
event handlers to the existing DOM rather than rebuilding it. That is
**hydration**, and it requires the browser's first render to produce *the same
tree the server did*. If they differ, React warns and discards the server's
work.

A theme toggle breaks this by construction. The theme is in `localStorage`,
which the server cannot read, so the server renders "system" and the browser
renders "dark". Hence:

```tsx
const [mounted, setMounted] = useState(false);
useEffect(() => setMounted(true), []);
if (!mounted) return <div className="h-8 w-[102px] rounded-md bg-muted" aria-hidden />;
```

The first client render returns the same placeholder the server did — so they
match — and the real toggle appears immediately after mount. The placeholder is
sized to the real control so nothing shifts.

`suppressHydrationWarning` on `<html>` is the other half. `next-themes` writes
the theme class onto `<html>` before React hydrates, so that one element
legitimately differs. Suppressing it there is correct; suppressing it anywhere
else hides real bugs.

`useEffect(fn, [])` deserves a note of its own: the second argument is the
**dependency array**, and it controls when the effect re-runs. `[]` means "after
the first mount, never again". Omit it entirely and the effect runs after
*every* render — which, if the effect sets state, is an infinite loop. This is
the single most common React bug, and it is why the array is not optional in
practice.

### 9. Tailwind is not inline styles

The objection to `className="flex items-center gap-2 rounded-md px-2.5 py-1"` is
immediate: this is inline styling with extra steps. It is not, and the
difference is not stylistic.

- **It is a closed vocabulary.** `p-4` is one of a fixed scale. There is no
  `p-13`. A design system enforced by the fact that the alternative does not
  compile beats one enforced by review.
- **It composes with variants inline.** `hover:bg-muted`,
  `focus-visible:ring-2`, `sm:grid-cols-2`, `dark:*` — none of which an inline
  `style` attribute can express at all. A media query has nowhere to live in a
  `style` prop.
- **It is deleted with the markup.** The permanent problem with a stylesheet is
  that nobody dares remove a rule, because nothing tells you what still uses it.
  Utility classes have no such afterlife.
- **The output is bounded.** Tailwind scans the source and emits only what is
  used, so the CSS grows with the number of *distinct* utilities, not with the
  number of components.

The cost is real: markup is noisy, and a repeated cluster of twelve classes
wants extracting into a component. That is what `components/ui/` is.

### 10. CSS custom properties, and why dark mode is not a second stylesheet

Look at what the token layer declares:

```css
:root  { --background: 0 0% 100%; --foreground: 224 71% 4%; }
.dark  { --background: 224 71% 4%; --foreground: 210 20% 98%; }
```

and how Tailwind consumes it:

```ts
background: "hsl(var(--background))",
```

Every colour in the console is named by **role** — `background`, `muted`,
`destructive` — never by hue. Dark mode is then one block that redefines the
same names. No component contains a `dark:` prefix anywhere; they are all
written once and are correct in both themes.

The values are HSL *channels* with no `hsl()` wrapper — `224 71% 4%`, not
`hsl(224 71% 4%)`. That is not a quirk. Tailwind composes them as
`hsl(var(--background) / <alpha-value>)`, so `bg-background/50` works. Store the
complete colour function and there is nowhere to inject the alpha.

`darkMode: "class"` rather than Tailwind's default media query, because an
operator on a shared desk machine needs to be able to *choose*, and a media
query cannot be overridden by a person.

### 11. shadcn/ui is not a dependency

`components/ui/badge.tsx` is ninety lines of our source, in our repository,
under our git history. There is no `@shadcn/badge` in `package.json`.

That is the entire idea. A component library you install is a contract you do
not control: restyling means fighting its CSS specificity, and a behaviour you
need means waiting for a maintainer or forking. shadcn/ui distributes *source
you copy in*. Changing the badge means editing the badge.

The trade you accept: no upstream fixes, and the code is genuinely yours to
maintain. For a console with four screens and one design language, that is the
right side of the trade. For a date picker with timezone handling and
accessibility, it would not be.

`cva` (class-variance-authority) is how a variant table stays a table:

```ts
const badgeVariants = cva("inline-flex items-center ...", {
  variants: { variant: { success: "bg-success/10 text-success", ... } },
  defaultVariants: { variant: "default" },
});
```

The alternative is a chain of ternaries in the component body, where you cannot
see all the variants at once and therefore add a fifth without noticing the
fourth already does the job.

And `cn()`, which every component uses:

```ts
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

`clsx` flattens conditionals and falsy values. `twMerge` then resolves Tailwind
*conflicts*: `cn("px-4", "px-6")` is `px-6`, not both. Without the second half,
a caller passing `className="px-6"` to override a component's `px-4` gets a
result decided by stylesheet order — a bug that moves when you rename a file.

### 12. TypeScript in this codebase

Three things carry most of the weight here.

**Structural typing.** TypeScript compares shapes, not names. Anything with the
right fields *is* a `Hotel`. This is why the generated types work at all: the
API's JSON is checked against a shape, with no runtime class involved.

**Typing props.** A component's props are just an object type, usually inline:

```tsx
export function TierBadge({ tier }: { tier: IntegrationTier }) {
```

`IntegrationTier` is `"live" | "bot" | "manual"` — a **union of literal types**,
generated from the Python enum. So `TIERS[tier]` is checked exhaustively: add a
fourth tier in `enums.py`, regenerate, and the record literal fails to compile
because it is missing a key. That is the drift check working in the direction
that is normally impossible to police.

**Discriminated unions for failure.** `ApiError.kind` is
`"unreachable" | "timeout" | "http" | "malformed"`, and the `switch` over it in
`operatorMessage` has no `default` branch — deliberately. Every case is handled,
so TypeScript can prove the function returns a string. Add a fifth kind and the
compiler reports the switch as no longer exhaustive.

**`import type`.** Every contracts import is `import type { Hotel } from
"@contracts"`. That is not a style preference: type-only imports are *erased*
at compile time, so `packages/contracts` produces no runtime import, no bundle
weight, and no module resolution at all in the browser.

### 13. Testing a frontend, and choosing what not to test

Vitest runs the suite; React Testing Library renders components into a `jsdom`
DOM — a JavaScript implementation of the browser's DOM API, with no browser.

RTL's principle is that tests should find elements the way a person does:

```tsx
expect(screen.getByText(/cannot reach the api/i)).toBeInTheDocument();
```

not by CSS class or component internals. A test that queries `.badge-warning`
breaks when you restyle and passes when the text becomes gibberish, which is
precisely backwards.

We deliberately did **not** add Playwright. S08's exit criterion is a read-only
screen and its failure states, all unit-testable. Real browser automation earns
its cost when there is interaction worth driving — the reply composer (S09) and
the two-operator claim race (S10). Adding a browser download to CI now would be
paying four slices early.

What *is* tested is the part most likely to be wrong and least likely to be
noticed: the failure paths. Eleven tests on the API client, four on the failure
notice. The happy path gets exercised by hand every time anyone opens the
console; nobody opens the console with the API deliberately stopped.

One trap worth knowing: RTL registers its between-test cleanup **only** when
Vitest's `globals` are enabled. This project imports `describe`/`it`/`expect`
explicitly, so `vitest.setup.ts` registers `afterEach(cleanup)` by hand. Without
it, every render accumulates in one shared document and assertions start failing
with "found multiple elements" — a failure that blames the component for a leak
between tests. We hit this exact wall while writing the component tests.

### 14. Make file targets, and a generated file that is not committed

`packages/contracts/src/generated.ts` is gitignored. It is derived from the API,
and committing a machine-written 1000-line file means resolving merge conflicts
in one. But `make lint-ops` needs it to exist.

The Makefile expresses this as a **file target** rather than a phony one:

```make
GENERATED_TS := packages/contracts/src/generated.ts

$(GENERATED_TS):
	$(MAKE) contracts

lint-ops: $(OPS_MODULES) $(GENERATED_TS)
	npm --prefix apps/ops run typecheck
```

This is what make is actually for. A rule whose target is a real filename runs
only when that file is missing. On a fresh clone — and on every CI run — it is
missing, so it is generated once. Afterwards `make lint` does not pay for a
regeneration it does not need.

The trade-off is worth stating plainly: an API change does *not* invalidate this
automatically, because the rule has no prerequisites listing the Python sources.
`make contracts` remains the explicit step you run after touching a schema. CI
starts from an empty checkout every time, so CI always regenerates and always
sees drift — which is the place it matters.

---

## Reading our code

### The path a request takes

Start at `apps/ops/app/hotels/page.tsx`. The whole screen is one async function,
and the order of its four steps is the design:

1. `await searchParams` — the page declares itself request-dependent.
2. `await listCities()` — inside a `try`. If this fails there is no shell worth
   rendering, because the switcher would have nothing to switch between, so it
   returns a bare `FailureNotice`.
3. Resolve the city: `cities.find(...) ?? cities[0]`. Note the comment — falling
   back to the first city is safe *here* because the list came from the API and
   contains only cities this console may see. The same fallback in `params.py`
   would have invented a scope the caller never asked for, which is exactly what
   invariant #1 forbids.
4. `await listHotels(...)` — inside its own `try`, whose failure renders the
   shell *with* a failure notice inside it. The operator keeps their navigation.

Then `lib/api.ts`. Every function is four lines because all the thinking is in
`request()`: one fetch, one timeout, one error type, and no retry. The comment
explains the last one — a GET behind an operator staring at a screen is already
retried by the human, and a silent retry only doubles the time before they learn
the desk is offline.

### Where the tenancy invariant shows up in a frontend

Invariant #1 is a database rule, and it has now surfaced in four places in the
console, none of which is a database:

- `listHotels({ cityId })` takes the city as a **required** argument, mirroring
  the API rather than defaulting it.
- The city is in the URL, so a mis-scoped screen is visible in the address bar.
- `CitySwitcher` deletes `offset` when the city changes — page 3 of Kanyakumari
  is not page 3 of anything else.
- Every nav link carries `?city=`, so moving between sections cannot lose scope.

With one city all four are invisible. That is the point of doing them now.

### The two halves of "do not show a blank screen"

`lib/api.ts` decides *what kind* of failure happened; `FailureNotice` decides
what to say about it. The split matters because "the API is down" and "that
hotel is not in this city" are different facts for the person reading them: the
first has a remedy (`make dev`) and a reassurance (bookings are unaffected; this
console is a view, not the record), the second does not.

`EmptyState` is a third thing again, and keeping it separate is deliberate: "no
manual hotels in this city" is a true and useful answer, while "the API is down"
is not an answer at all. A console that renders both as an empty table teaches
its operators to distrust it.

---

## The gotchas

- **`"use client"` is contagious downward.** Everything a client component
  imports goes to the browser too. One misplaced directive at the top of a
  layout puts the entire app in the bundle. This is why the theme provider is
  its own one-line file.
- **Server components cannot use hooks, and the error is confusing.** Adding a
  `useState` to a server component fails at build with a message about the
  wrong thing. Ask first: does this file have `"use client"`?
- **`useEffect` with no dependency array runs after every render.** If it sets
  state, that is an infinite loop. The empty array is not boilerplate.
- **Array index as a `key` is not a key.** It is positional, so it provides no
  identity exactly when identity matters — insertion and reordering.
- **`?tier=` empty is not the same as absent.** `params.set("tier", "")` sends
  `?tier=`, which the API rejects against the enum as a 422 — turning "show me
  everything" into an error page. There is a test for this.
- **Money arrives as a string.** `commission_rate` is `Numeric(5,2)` in Postgres
  and `string` in the generated TypeScript, because JavaScript's `number` is a
  float. `formatCommission` formats digits and never parses them. The day
  anything needs to *add* two rates, the answer is a decimal library.
- **Filtering client-side lies about `total`.** Fetch a page and filter it in
  React and you have hidden rows from the current page while still reporting the
  unfiltered count. Correct at five hotels, wrong at fifty, and it ships.
- **RTL does not clean up without globals.** See §13. It presents as a component
  bug and is not.
- **Two base URLs is a real trap.** Set only `NEXT_PUBLIC_API_BASE_URL` and you
  get a console that works in the browser's imagination and not on the server.

---

## Check yourself

1. Why can `HotelsPage` be `async` and `await` an API call directly, when
   `ThemeToggle` cannot?
2. The tier filter is four `<Link>`s rather than four buttons with `onClick`.
   Name three things that buys, and one thing it costs.
3. `GET /api/cities` returns a bare array while every other collection returns a
   `Page`. What would have broken if it had returned a `Page` instead?
4. `--background` is stored as `224 71% 4%` rather than `hsl(224 71% 4%)`. What
   stops working if you store the wrapped form?
5. What is `mounted` in `ThemeToggle` defending against, and why does a
   placeholder of exactly `h-8 w-[102px]` matter?
6. `commission_rate` is typed `string` in TypeScript. Why, and what would go
   wrong if the API sent a JSON number?
7. `make lint-ops` depends on `packages/contracts/src/generated.ts`, which is
   gitignored. What happens on a fresh clone, and what does *not* happen when
   you change a Pydantic schema?
8. The directory falls back to `cities[0]` when `?city=` is missing, but
   `params.py` refuses to default `city_id`. Why is one safe and the other a
   tenancy leak?

---

## Going deeper

- **React** — [react.dev/learn](https://react.dev/learn). The "Describing the
  UI" and "Escape Hatches" sections are the two that matter; the second is
  mostly about when *not* to use `useEffect`.
- **Server components** — [the Next.js docs on Server
  Components](https://nextjs.org/docs/app/building-your-application/rendering/server-components),
  then the App Router's caching page, which is the part people get wrong.
- **Tailwind** — the [utility-first
  argument](https://tailwindcss.com/docs/utility-first) states the case better
  than a summary can.
- **shadcn/ui** — [ui.shadcn.com](https://ui.shadcn.com). Read one component's
  source before installing anything; the philosophy is visible in the code.
- **Testing Library** — [Guiding
  Principles](https://testing-library.com/docs/guiding-principles). Short, and
  it explains why the query API is shaped the way it is.
- **TypeScript** — the [handbook on narrowing and discriminated
  unions](https://www.typescriptlang.org/docs/handbook/2/narrowing.html), which
  is what makes `ApiError.kind` work.

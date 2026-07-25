# HotelAgent — Conversational Hotel Booking over WhatsApp

> A WhatsApp-first booking concierge — **human-in-the-loop today, agentic tomorrow, indistinguishable to the customer throughout.**
> Launch in **Kanyakumari**, expand town-by-town.

**Version:** 0.2 (Vision & Architecture — post-FlashRooms field research)
**Date:** 2026-07-25
**Owner:** Founding team
**Changes from v0.1:** competitive teardown of FlashRooms added (§1.5); monetisation revised from 8–12% to tiered 11–15% (§2.6); supply-side integration tiers introduced as a core concept (§2.4); architecture reframed around an availability router and an ops console rather than an assumed live-inventory source of truth (§3); operating model now explicitly hybrid (§2.3); GTM revised to remote-ops (§2.7); phases rewritten to put revenue before automation (§3.9).

---

## 1. Business Problem

### 1.1 The context

Kanyakumari is a high-footfall pilgrimage and tourism town (sunrise/sunset point, Vivekananda Rock, Thiruvalluvar statue). Demand is **seasonal, spiky, and last-minute** — pilgrims, weekend travellers from Tamil Nadu and Kerala, and bus-tour groups. Local hotel supply is dominated by **small and mid-tier independent properties** (20–80 rooms) that are poorly served by the current booking ecosystem.

### 1.2 Pain points

**For travellers (demand side)**

- OTAs (MakeMyTrip, Booking.com, Goibibo) list mostly branded and mid-large hotels; many good local guesthouses are missing or carry thin, stale inventory.
- App fatigue: installing an app, creating an account, KYC, and payment friction is disproportionate for a one-night stay.
- Language barrier: much of the audience is more comfortable in **Tamil / Malayalam / Hindi** than navigating English-only apps.
- No easy way to ask real questions — "Is parking free?", "Can I get a 6 AM check-in for sunrise?", "Sea-facing under ₹2,500?" — without ringing each hotel individually.

**For hoteliers (supply side)**

- OTA commissions of **15–25%** crush thin margins on budget rooms.
- Small properties have no channel manager or PMS; inventory lives in a **paper register or Excel**.
- Phone bookings are unmanaged: missed calls are lost revenue, double-bookings happen, and there is no record.
- No digital presence or direct-booking channel they actually control.

### 1.3 Why WhatsApp

- **~500M Indian users**; it is the default communication layer, already installed, already trusted.
- **Zero install, zero new account** for the traveller — the conversation *is* the product.
- Native support for the messy, question-heavy, multilingual way people actually book.
- Rich message types (lists, buttons, images, location, payment links) enable a full booking flow inside the chat.
- **Economically decisive:** under Meta's current per-message pricing, *user-initiated* service conversations and all free-form replies inside the 24-hour window are free. An inbound-first funnel (QR codes, click-to-WhatsApp ads, Google Business "Message") therefore has near-zero messaging cost. See §3.8.

### 1.4 Opportunity statement

> Build a **conversational commerce layer** that lets a traveller book a Kanyakumari hotel room end-to-end inside a WhatsApp chat — in their own language, in under 3 minutes — while giving small hoteliers a **zero-tech-overhead** direct channel. Kanyakumari is the wedge; the platform generalises to any tourist town.

### 1.5 Competitive intelligence — the FlashRooms teardown

**This section is the most important change in v0.2.** In July 2026 we found a competitor via a Google ad and investigated it end-to-end as a customer and then in person at the hotel.

**What FlashRooms is**

| Aspect | Finding |
|---|---|
| Acquisition | Google Ads → WhatsApp number (click-to-WhatsApp) |
| Interface | WhatsApp chat, felt like an AI agent |
| Reality | **100% human**, operated from **Trichy** — remote from the inventory |
| Availability check | An operator **telephones the hotel reception** and asks |
| Inventory integration | **None.** No PMS, no channel manager, no dashboard |
| Payment | Operator sends **FlashRooms' own QR code**; money lands with FlashRooms |
| Settlement | Hotel is paid out net of a **15% commission** |
| Verified at | Hotel Jayam, Kanyakumari (manager interview) |

**What it proves — five conclusions that reshape our strategy**

1. **The market is validated with zero technology.** Someone is sustaining paid Google Ads on the back of a phone-and-WhatsApp desk. That is the strongest possible demand signal, and it cost us nothing to obtain.

2. **The AI is not the product.** A senior AI architect could not distinguish the FlashRooms desk from an agent. Customers are buying *one number, their language, someone who answers, no app*. The LLM is a **cost and throughput lever**, not the value proposition. This reframes our product specification from "percentage automated" to a **response-time contract** (§2.2).

3. **Price is not the constraint on hotelier adoption.** Hotels already pay 15% for a service with no inventory sync, no dashboard, no instant confirmation and no digital presence. Undercutting to 8–12% surrenders a third of our revenue to solve a problem hoteliers do not have. **v0.1's monetisation thesis is withdrawn.**

4. **Owning the QR is the structural advantage.** Because FlashRooms collects the money and settles net, their commission is *automatic* rather than honour-system. There is no leakage, no reconciliation dispute, and no way for the hotel to route around them on that booking. We must replicate this from day one.

5. **Remote operations work.** Kanyakumari is run from Trichy. Our v0.1 assumption of feet-on-street, city-by-city expansion is more expensive than necessary. A single ops pod can plausibly serve several towns (§2.7).

**Where FlashRooms is beatable**

| Their constraint | Our wedge |
|---|---|
| One operator handles ~20–40 conversations/day | AI absorbs the ~80% of chats that never convert |
| Almost certainly not 24/7 | Nights and pre-dawn — critical in a **sunrise** town |
| Breaks under peak-season surge | Elastic capacity; spiky demand is when leads are worth most |
| Every booking costs a phone call, forever | Calls become a **dataset** and a **supply-onboarding funnel** |
| Call-centre mindset; no product surface | Hotelier bot, dashboard, KB, reviews, repeat-customer memory |
| No moat beyond the phone number | Availability history, payment rails, traveller relationship |

**Field research still outstanding** (do before committing spend — see §6):

- Probe FlashRooms at Tue 3pm, Sat 9pm, 11pm, and a peak weekend. Time every reply. Establish their real hours, staffing and failure modes. This becomes our SLA benchmark.
- Interview 8–10 Kanyakumari hotels, not one. Key questions: do they use FlashRooms or similar; monthly booking volume through it; is settlement reliable; what irritates them; **and — would they give someone priority access to their last 5 rooms on a Saturday at a better rate?** A "yes" means there is a supply-side product here that is more than a cheaper OTA.
- Confirm whether FlashRooms is running any city other than Kanyakumari.

---

## 2. Business Solution

### 2.1 Product in one line

A **booking concierge on WhatsApp** that understands natural-language intent in the traveller's own language, finds a real room, answers real questions, takes payment and confirms — with the work behind the curtain done by an AI agent, a human operator, or both, depending on what the situation needs.

### 2.2 The product specification is a response-time contract

Because the customer cannot tell (and does not care) whether they are talking to a person or a model, we do not specify the product as "an AI agent." We specify it as a **service-level contract**, and we are free to satisfy it however is cheapest and most reliable at any given moment.

| Commitment | Target | Notes |
|---|---|---|
| First reply | **< 30 seconds** | 24/7. This alone beats FlashRooms at night. |
| Shortlist presented | < 90 seconds | From a qualified request |
| Availability confirmed | **< 5 minutes** (Tier C) / instant (Tier A) | Traveller sees an honest progress message |
| Booking confirmed after payment | < 60 seconds | With booking ID, pin, hotel contact |
| Human reachable | 1 tap, always | Persistent quick-reply |

Automation percentage is an **internal cost metric**, not a customer-facing promise.

### 2.3 The hybrid operating model

Human-in-the-loop is not a stopgap on the way to agentic. The two coexist permanently, with the boundary moving as trust and data accumulate.

| Level | Who does what | Where it applies |
|---|---|---|
| **L0 — Manual desk** | Human does everything (the FlashRooms model) | Day 1; new city launch; any total system failure |
| **L1 — AI copilot** | Agent drafts every reply, human approves and sends | Trust-building; complex or high-value bookings |
| **L2 — Agent front, human middle** | Agent owns greeting, language, qualification, FAQ, shortlist and post-booking. Human owns the availability call and the close. | The default steady state for Tier C hotels |
| **L3 — Fully agentic** | Agent runs end-to-end; humans only on escalation | Tier A hotels; repeat customers; simple requests |

**The economic logic.** At roughly ₹2,200 ADR, a 15% take is about ₹330 gross per booking. A fully-loaded ops agent in Tamil Nadu is roughly ₹1,000/day. If they handle 30 conversations and close 6, labour alone is ~₹170 per booking — over half the take, before any ad spend. The expensive part is not the close; it is the **~80% of conversations that never convert**: price shoppers, wrong dates, out-of-scope questions, browsers.

> **Therefore the AI goes to the top of the funnel first, not the bottom.** It is a 4–6x throughput multiplier on the same headcount, and it does not require betting the business on a model handling money correctly in week one.

*(These figures are estimates. Validate them against real data during M0 — see the build plan.)*

### 2.4 Supply-side integration tiers — the core architectural idea

v0.1 asserted "inventory is the source of truth." FlashRooms shows that for most of our supply, **the receptionist's memory is the source of truth** — and that is not a defect. It is real-time, never stale, requires zero integration, and works on day one.

So hotels are never migrated en masse. They live permanently at different tiers within the same city, and the platform routes accordingly.

| Tier | Availability source | Confirm latency | Commission | Onboarding effort |
|---|---|---|---|---|
| **A — Live** | Hotelier keeps a calendar in our dashboard, or PMS/channel-manager integration | **Instant** | **11%** | Days |
| **B — Bot** | Hotelier WhatsApp bot: *"2 AC rooms tonight? [Yes] [No]"* | **1–3 min** | **13%** | Hours |
| **C — Manual** | Ops operator telephones reception | **5–15 min** | **15%** | **Minutes** |

**Every hotel launches at Tier C.** That is how we get 40–50 properties live in six weeks instead of six months. The traveller simply sees *"Checking with the hotel — about 2 minutes ⏳"*, which is exactly what FlashRooms already does and the market already accepts.

**Three things this buys us that FlashRooms has never extracted:**

1. **A digitisation flywheel.** Commission is the incentive. Every hotelier has a standing reason to move themselves up a tier, and our margin improves precisely where our costs fall. We never have to sell "digital transformation" — we just publish the rate card.
2. **A supply acquisition funnel.** After our operators have called Hotel Jayam 200 times, the pitch to move to Tier B writes itself. FlashRooms has been making those calls for a year and never converted the relationship into infrastructure.
3. **A proprietary dataset.** Every call yields a labelled datapoint: *hotel × date × room type × available/not × price quoted*. After one season we can predict availability well enough to pre-confirm optimistically on high-vacancy nights and skip the call entirely. **This is the only genuinely defensible asset in the business.**

### 2.5 The traveller journey (happy path)

1. **Entry** — QR at the bus stand, a poster, a Google Business "Message" button, or a click-to-WhatsApp ad → WhatsApp opens pre-filled with "Hi".
2. **Understand** — agent greets, detects language, fills slots: dates, guests, budget, preferences (sea-view, AC, parking, early check-in).
3. **Search** — the availability router returns a **ranked shortlist**, blending Tier A live results with Tier B/C candidates marked as "confirming".
4. **Q&A** — traveller asks follow-ups; agent answers from the hotel knowledge base, grounded, never invented.
5. **Confirm availability** — Tier A instant; Tier B/C triggers a bot ping or an operator call, with an honest wait message.
6. **Select & hold** — traveller picks; system soft-holds for 10 minutes.
7. **Guest details** — name and headcount captured conversationally; ID collection deferred to check-in.
8. **Pay** — **our** UPI QR / payment link. Money lands with us. "Pay at hotel" only for verified or repeat users.
9. **Confirm** — booking ID, hotel contact, location pin, cancellation policy, calendar add.
10. **Post-booking** — directions, check-in nudge, review request, and a stored profile that makes the next booking a two-message affair.

### 2.6 Monetisation (revised)

- **Commission per booking, tiered 11–15%** — primary. We *match* the incumbent at Tier C and compete on throughput, hours and reliability, not on price. The discount is earned by digitising, not by negotiating.
- **We collect, then settle net.** This is non-negotiable. It makes revenue automatic, gives us the payment record that makes disputes resolvable, funds a working-capital float, and is the hardest thing for a phone-desk competitor to copy.
- **SaaS subscription** for hoteliers (dashboard, calendar, analytics) — secondary, recurring, and a further pull toward Tier A.
- **Featured placement** during peak season.
- **Adjacent services** (cabs, tours, temple darshan slots) — later, and natural in a pilgrimage town.

**Settlement mechanics to design carefully:** payout cadence (we favour weekly, or on-checkout), refund liability, no-show handling, and a clear written agreement with each hotel. Holding customer money creates obligations — treat it seriously from booking one.

### 2.7 Go-to-market (Kanyakumari wedge)

- **Supply first, and cheap.** Because Tier C onboarding is a phone number, a rate card and a signature, target 40–50 hotels — roughly 70% of usable budget inventory — in weeks, not months.
- **Demand:** click-to-WhatsApp Google Ads (opens a 72-hour free messaging window), QR codes at the bus stand, railway station and tourist points, Google Business Profile "Message", tour-operator partnerships, local WhatsApp community seeding.
- **Own the hours FlashRooms cannot.** Nights, pre-dawn (this is a sunrise town), and peak-season surges. Advertise it.
- **Trust:** verified hotels, transparent pricing with no surprise taxes, instant written confirmation, a published human fallback number.

### 2.8 Expansion thesis (revised)

FlashRooms runs Kanyakumari from Trichy. Remote ops is proven, which makes expansion far cheaper than v0.1 assumed. A single ops pod — plausibly in Nagercoil or Madurai — could run **Kanyakumari, Rameswaram and Tirupati concurrently**, with the agent absorbing the language and volume differences. A new city is: onboard Tier C supply, load a language pack, flip a config flag. Target the same profile of tier-2/3 pilgrimage and tourist towns (Rameswaram, Madurai, Tirupati, Munnar, Varkala).

### 2.9 Success metrics

- **North Star:** confirmed bookings per week.
- **Cost of service per booking** (ops labour + LLM + ads) — the metric the automation ladder exists to move.
- Conversation → booking conversion; time-to-book; **time-to-first-reply** (our SLA).
- Containment rate (share of bookings completed with no human touch), by tier.
- Tier mix over time — the digitisation flywheel made visible.
- Hotelier retention and settlement disputes per 100 bookings.
- Repeat-traveller rate; take rate vs OTA; contribution margin per booking.

---

## 3. Technical Architecture

### 3.1 Design principles (revised)

- **The ops console is a first-class product, not an admin afterthought.** On day one it *is* the product. Everything else is built around it.
- **Availability is a routed capability, not a table.** One interface, three implementations (live / bot / manual). Callers never know which.
- **Agentic where it pays, human where it matters.** Automation level is per-conversation and per-hotel, decided at runtime.
- **Multi-tenant and city-agnostic from day one.** City and hotel are data, not code.
- **We hold the money.** Payment collection is core, not a plugin.
- **Never overbook.** Soft holds, atomic confirmation, idempotency on every money or inventory mutation.
- **Human fallback always reachable.**
- **Stateless services, stateful conversations.**
- **Every LLM call and every availability answer is logged as training and eval data.** The dataset is the moat; start accruing it before the model needs it.

### 3.2 High-level component diagram

```
                        ┌────────────────────────────────────────────────┐
   Traveller (WhatsApp) │              HotelAgent Platform                │
        │               │                                                │
        ▼               │  ┌────────────────┐   ┌───────────────┐         │
 ┌─────────────┐ webhook│  │  Channel /      │   │  Orchestrator │         │
 │ WhatsApp    │───────►│  │  Messaging      │──►│  (Agent Core) │         │
 │ Cloud API   │◄───────│  │  Gateway        │◄──│  LLM + Tools  │         │
 └─────────────┘  send  │  └────────┬───────┘   └──────┬────────┘         │
                        │           │                   │                  │
                        │           ▼                   ▼                  │
                        │  ┌────────────────┐   ┌──────────────────┐      │
                        │  │  Session /      │   │  Tool / Function │      │
                        │  │  Context Store  │   │  Layer           │      │
                        │  └────────────────┘   └───┬───┬───┬───┬──┘      │
                        │                           │   │   │   │          │
                        │  ┌──────────────────┐     ▼   ▼   ▼   ▼          │
                        │  │  AUTOMATION      │  ┌─────────────────────┐   │
                        │  │  GOVERNOR        │  │ Availability Router │   │
                        │  │  (L0/L1/L2/L3    │  ├─────────────────────┤   │
                        │  │   per conv.)     │  │ Tier A │ Tier B │ C │   │
                        │  └────────┬─────────┘  │ live   │ bot    │ 📞│   │
                        │           │            └────┬───┴───┬────┴─┬─┘   │
                        │           ▼                 │       │      │      │
                        │  ┌────────────────────┐     │       │      │      │
                        │  │  OPS CONSOLE       │◄────┼───────┼──────┘      │
                        │  │  · unified inbox   │     │       │             │
                        │  │  · AI draft/send   │     │       │             │
                        │  │  · call & log task │     │       │             │
                        │  │  · payment recon   │     │       │             │
                        │  └────────────────────┘     │       │             │
                        │                             ▼       ▼             │
                        │   ┌─────────┐ ┌─────────┐ ┌────────┐ ┌────┐      │
                        │   │Inventory│ │ Booking │ │Payments│ │ KB │      │
                        │   │& Search │ │& Holds  │ │+ Ledger│ │RAG │      │
                        │   └────┬────┘ └────┬────┘ └───┬────┘ └─┬──┘      │
                        │        │           │          │        │          │
                        │   ┌────▼───────────▼──────────▼────────▼─────┐   │
                        │   │  PostgreSQL (+pgvector) · Redis · Object  │   │
                        │   │  store · append-only event log            │   │
                        │   └───────────────────────────────────────────┘   │
                        └────────────────────────────────┬───────────────────┘
                                                         │
                    ┌────────────────────────────────────┴──────────┐
                    │  Hotelier WhatsApp bot  ·  Hotelier dashboard  │
                    └───────────────────────────────────────────────┘
```

Two components are new in v0.2 and both are load-bearing: the **Automation Governor** and the **Availability Router**.

### 3.3 The Automation Governor

Decides, per conversation turn, whether the agent replies directly, drafts for human approval, or hands off entirely. Inputs:

- Hotel tier and per-hotel trust score
- Conversation stage (pre-qualification is safe; money and confirmation are not)
- Model confidence and whether the reply asserts a price, policy or availability
- Booking value; new vs repeat traveller
- Current ops staffing and queue depth (degrade to L3 under load, upgrade to L1 when quiet)
- A global kill-switch and a per-stage config

This is the single knob that lets the business grow into automation rather than leaping to it. **Build it at M2, even if it only has two settings.** Retrofitting it later means restructuring the agent loop.

### 3.4 The Availability Router

```
check_availability(hotel_id, dates, guests, room_type?)
  → { status: available | unavailable | pending,
      price, hold_token?, eta_seconds, source_tier }
```

- **Tier A** → read the calendar, return synchronously.
- **Tier B** → send a structured WhatsApp prompt to the hotelier bot, return `pending` with an ETA, resolve on reply.
- **Tier C** → create a **call task** in the ops console queue, return `pending`, resolve when the operator logs the outcome.

The agent's conversation flow is identical in all three cases; only the wait message differs. Every resolution — whatever the tier — is written to an `availability_observation` table. That table is the dataset from §2.4.

### 3.5 Core components

1. **Channel / Messaging Gateway** — WhatsApp Cloud API (direct with Meta, or via a BSP). Handles inbound webhooks, outbound sends, interactive message types, delivery receipts, and the 24-hour session-window and template rules. Normalises payloads into an internal **channel-agnostic message schema** so Instagram / SMS / web chat is a driver, not a rewrite.

2. **Orchestrator (Agent Core)** — an LLM agent loop with tool use. Owns intent understanding, slot filling, language detection and switching, tool selection, reply composition, and escalation. Deterministic business rules (pricing, availability, hold expiry, commission) live in services, **never in the prompt**. Prompts are versioned artefacts in the repo.

3. **Session / Context Store** — per-user state (intent, slots, active hold, language, automation level) in Redis with TTL; full transcript and structured events persisted to Postgres.

4. **Tool / Function Layer** — `search_hotels`, `check_availability`, `get_hotel_details`, `answer_hotel_question` (RAG), `hold_room`, `create_booking`, `initiate_payment`, `check_payment_status`, `cancel_or_modify_booking`, `escalate_to_human`.

5. **Ops Console** — unified conversation inbox with AI-drafted replies; the **call-task queue** (which hotel to ring, what to ask, log the answer in two clicks); payment reconciliation; hotel onboarding and verification; refunds and overrides. Optimise it ruthlessly for operator seconds-per-booking — that number *is* our gross margin at Tier C.

6. **Inventory & Search Service** — hotels, room types, rates, amenities, policies, photos, per-hotel tier and commission. Ranking blends relevance, price, rating, historical availability probability and conversion propensity. Ingest via dashboard, hotelier bot, CSV, and later PMS integrations.

7. **Booking & Holds Service** — soft holds with TTL; atomic confirmation with optimistic locking; lifecycle held → confirmed → checked-in → completed / cancelled / no-show, modelled as an **append-only event log**, not just a status column.

8. **Payments & Ledger Service** — UPI collection (dynamic QR and payment links) via Razorpay / Cashfree; webhook handling; **a real double-entry-style ledger** covering customer payment, commission, hotel payable, payout and refund. Idempotent. No card data stored.

9. **Knowledge Base / RAG** — per-hotel structured facts plus free text (policies, FAQs, nearby attractions, sunrise-viewing quirks) embedded in pgvector. Grounds `answer_hotel_question`.

10. **Hotelier interfaces** — WhatsApp bot for daily ops (availability prompts, booking alerts, "block 3 rooms tonight"); web dashboard for calendar, rates, bookings, payouts, photos, KB editing.

11. **Notifications / Jobs** — async workers for hold expiry, reminders, payment retries, review requests, and template messages within WhatsApp policy windows.

12. **Analytics & Observability** — funnel analytics, LLM cost and token tracking, latency, containment by tier, operator throughput, and **prompt/response logging with an eval harness** from the very first LLM call.

### 3.6 Data model (core entities, revised)

- **City** (id, name, config, active_languages, ops_pod_id)
- **Hotel** (id, city_id, name, geo, verification_status, **integration_tier**, **commission_rate**, **reception_phone**, policies, trust_score)
- **RoomType** (id, hotel_id, name, base_price, capacity, amenities[])
- **AvailabilityCalendar** (room_type_id, date, total, booked, price_override) — *Tier A only*
- **AvailabilityObservation** (hotel_id, room_type_id, date, observed_at, source_tier, available, quoted_price, operator_id) — *the dataset*
- **CallTask** (id, hotel_id, conversation_id, question, status, assigned_to, opened_at, resolved_at, outcome)
- **Hold** (id, room_type_id, dates, user_id, expires_at)
- **Booking** (id, hotel_id, room_type_id, user_id, dates, amount, commission_rate, commission_amount, status, payment_ref)
- **BookingEvent** (booking_id, type, payload, occurred_at) — append-only
- **User** (wa_id, name, language_pref, prior_bookings, trust_flags)
- **Conversation** (user_id, city_id, transcript, state, current_intent, **automation_level**)
- **AgentTrace** (conversation_id, turn, prompt_version, model, tokens, latency_ms, tool_calls, was_edited_by_human, outcome)
- **HotelKnowledge** (hotel_id, chunks[], embeddings)
- **LedgerEntry** (booking_id, account, direction, amount, gateway_ref, status, occurred_at)

### 3.7 Multi-city and multi-tenancy

Every query scoped by `city_id`; hotels partitioned by city. Language packs and city-specific config (attractions, sunrise check-in quirks, peak calendars) are data. Onboarding a city loads hotels, tiers and KB — no code change. **Put `city_id` on every row from row one, even with one city.**

### 3.8 Messaging economics

Under Meta's current model, per-message pricing applies to business-initiated template traffic, while **customer-initiated service conversations and free-form replies inside the 24-hour window are free**, and click-to-WhatsApp ad entries open a longer free window. Indian utility templates are in the region of ₹0.13–0.15 per message.

Design consequences:

- **Structure everything to be inbound-first.** QR codes and click-to-WhatsApp ads, not outbound blasts.
- **Keep the conversation inside the 24-hour window.** Reply promptly; that is free and it is also our SLA.
- **Classify templates correctly.** Booking confirmations and reminders are *utility*, not marketing — an order of magnitude cheaper.
- Net effect: messaging is a rounding error. Our real variable costs are **ops labour, ads and LLM tokens**, in that order.

*(Verify current rates with Meta or the chosen BSP before finalising any model.)*

### 3.9 Phased delivery (revised — revenue before automation)

| Phase | Scope | Outcome |
|---|---|---|
| **0 — Manual desk, instrumented** | WhatsApp Business App, 5–10 Tier C hotels, our UPI QR, every conversation logged | **First revenue in ~2 weeks.** Domain learned before it is coded. |
| **1 — Ops console + Cloud API** | Migrate to Cloud API; message store, hotel/booking schema, ops inbox, call-task queue, payment reconciliation. Still 100% human replies. | The system of record exists. Operator throughput measurable. |
| **2 — AI copilot (L1)** | Agent drafts every reply; human sends. Automation Governor v1. Eval harness on M0/M1 transcripts. | Trust earned with zero customer risk. % sent-unedited is the KPI. |
| **3 — Agent front-of-funnel (L2)** | Agent autonomously handles greeting, language, qualification, FAQ, shortlist. Hotelier bot ships (Tier B). 30–50 hotels. | Cost-per-booking falls sharply. 24/7 becomes real. |
| **4 — Payments & auto-confirm (L3)** | Payment links, soft holds, atomic booking, automated confirmation. Tier A hotels fully autonomous. | End-to-end agentic for a growing slice of supply. |
| **5 — Scale & harden** | Hotelier dashboard, RAG KB, reminders, reviews, analytics, availability prediction | Repeatable, measured, defensible. |
| **6 — Second city** | City config abstraction proven; Rameswaram or Tirupati from the same ops pod | Expansion validated at near-zero marginal cost. |

*(Detailed engineering milestones, hosting and repo strategy: see the companion Technical Milestones document.)*

---

## 4. UI / UX

### 4.1 UX principles

- **Conversation is the interface.** Minimise typing; buttons and lists for choices, free text for questions.
- **Language-native.** Detect and respond in Tamil / Malayalam / Hindi / English; allow switching anytime; understand mixed-language "Tanglish".
- **Fast to value.** Shortlist within 2–3 exchanges; book in under 3 minutes.
- **Honest about waiting.** When we are ringing the hotel, say so and give an ETA. Never fake instant availability we do not have.
- **Seam-free.** The handover between agent and operator must be invisible: same persona, same voice, same name. Agree a single character and hold it — this is a product decision, not a prompt detail.
- **Transparent.** Always show the price breakdown, cancellation policy, and a confirmation with a real booking ID and hotel contact.
- **Human within reach.** One tap, always.

### 4.2 WhatsApp message-type mapping

| Step | WhatsApp feature |
|---|---|
| Greeting / language | Text + quick-reply buttons (English / தமிழ் / മലയാളം / हिंदी) |
| Dates & guests | Conversational text; optional date buttons |
| Shortlist | List message or card carousel (image, name, price, "View") |
| Hotel details | Image messages + text; buttons "Book" / "Ask a question" / "Back" |
| Filters | Quick-reply buttons (Sea view / AC / Parking / Under ₹2,500) |
| **Availability wait** | Text with ETA + typing indicator; follow-up on resolution |
| Confirm selection | Button "Confirm & Hold" |
| Payment | CTA URL button → payment link, or dynamic UPI QR image |
| Confirmation | Text summary + location pin + "Add to calendar" + booking ID |
| Support | Persistent "Talk to a human" quick reply |

### 4.3 Sample conversation (Tier C — the honest-wait pattern)

```
Traveller:  Hi, need a room in Kanyakumari this weekend

Agent:      Vanakkam! 🙏 I can help you book a hotel in Kanyakumari.
            Which language do you prefer?
            [ English ]  [ தமிழ் ]  [ हिंदी ]  [ മലയാളം ]

Traveller:  English is fine. 2 adults, Sat–Sun, sea view under 3000

Agent:      Got it — 2 guests, 25–26 Jul, sea-view, budget ₹3,000.
            Here are 3 good options:  📋
            ┌───────────────────────────────┐
            │ 🏨 Sea Breeze Residency        │
            │ Sea-facing · AC · Free parking │
            │ ₹2,600/night · ⭐ 4.3          │  [ View ]
            ├───────────────────────────────┤
            │ 🏨 Sunrise Comforts            │
            │ Partial sea view · AC          │
            │ ₹2,300/night · ⭐ 4.1          │  [ View ]
            └───────────────────────────────┘

Traveller:  Does Sea Breeze allow early check-in? I want the sunrise

Agent:      Yes 🌅 Sea Breeze offers early check-in from 6 AM
            (subject to availability, no extra charge). Their rooftop
            faces east — great for sunrise. Shall I check if a
            sea-facing room is free for Saturday?
            [ Yes, check ]   [ See photos ]   [ Other hotels ]

Traveller:  Yes check

Agent:      Confirming with the hotel now — about 2 minutes ⏳
                        ← ops console raises a CallTask;
                          operator rings reception, logs "2 available @ ₹2,600";
                          observation written to the dataset

Agent:      ✅ Confirmed available — sea-facing, ₹2,600/night.
            I've held it for 10 minutes.
            Total ₹2,600 (no extra taxes).
            Free cancellation until 24h before check-in.
            [ Pay ₹2,600 via UPI ]      [ Not now ]

Traveller:  (pays via our QR)

Agent:      ✅ Booked! ID: KK-4821
            Sea Breeze Residency · 25–26 Jul · 2 guests
            📍 [location pin]   ☎ +91-98xxxxxxx
            See you at sunrise! I'll send directions on the day. 🌅
```

### 4.4 Hotelier UX

- **WhatsApp bot** for daily ops: structured availability prompts ("2 AC rooms tonight? [Yes] [No]"), instant booking alerts with accept/decline, "block 3 rooms", nightly settlement summary.
- **Web dashboard** for richer control: availability calendar, rate management, booking list, payouts and settlements, reviews, KB/FAQ editing, photo uploads.
- **Onboarding**: Tier C sign-up in under 15 minutes — name, rooms, rates, reception number, payout account, rate card signed. Everything else is progressive.

### 4.5 Accessibility and inclusivity

- Full multilingual support including mixed-language understanding.
- Voice-note input (transcribed) for low-literacy users — high value in this market, worth prioritising earlier than v0.1 assumed.
- Clear, low-jargon copy; emoji as visual anchors, not decoration.

---

## 5. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Overbooking / double-book | Soft holds + atomic transactions + idempotency; Tier C confirms *before* holding |
| LLM invents a price or policy | Governor blocks autonomous replies that assert price/policy/availability; answers grounded in tool or RAG output only |
| **Holding customer money** — refunds, disputes, no-shows | Written hotel agreements, clear refund policy, real ledger from day one, reputable gateway, weekly settlement discipline |
| **Hotel disintermediation** (traveller books direct next time) | We hold the thread, the booking record and the payment history; loyalty and multi-city memory; commission is on *our* channel bookings only |
| **FlashRooms copies our automation** | Speed. Their constraint is a call-centre operating model. Our dataset and tier flywheel compound; their phone list does not |
| Operator quality / voice inconsistency between AI and human | Single named persona, canned-phrase library, ops console templates, QA sampling |
| Thin supply at launch | Tier C onboarding is minutes, not months — that is the whole point |
| WhatsApp template rejection or policy change | Inbound-first design keeps us inside free service windows; BSP as fallback; human number published |
| Hotelier low tech adoption | Tier C requires *no* technology; the bot and dashboard are opt-in upgrades with a financial reward |
| Payment failures / disputes | Retries, "pay at hotel" fallback for verified users, clear refund policy, reconciliation screen in ops console |
| Seasonality / demand troughs | Multi-city from one ops pod smooths the labour cost; dynamic pricing; promoted listings |
| LLM cost at scale | Cheap model for routing and classification, capable model for conversation; prompt caching; concise context; measured per conversation from call one |
| Key-person dependency on ops staff | Everything in the console, nothing in anyone's head; call scripts standardised |

---

## 6. Open Questions

**Closed by field research**

- ~~Commission level?~~ → **Match at 15%, discount to 11–13% for digitisation.** Price is not the adoption constraint.
- ~~Who collects payment?~~ → **We do.** FlashRooms proves the model works and that it is the structural advantage.
- ~~Is there demand?~~ → **Yes**, proven by a competitor sustaining paid ads with zero technology.
- ~~Feet-on-street per city?~~ → **No.** Remote ops proven (Trichy → Kanyakumari).

**Still open**

- BSP vs direct Meta Cloud API for launch — direct is cheaper and Claude Code can build it; a BSP is faster on template approval and support. Decide at M1.
- Ops staffing model: founder-operated for M0–M2, then how many, on what shift pattern, and where?
- "Pay at hotel" — universal, or verified/repeat users only? No-show risk vs conversion lift.
- ID/KYC — defer to check-in, or capture upfront where local rules require?
- Settlement cadence — weekly, or on-checkout? Trade-off between hotelier trust and our float.
- Does FlashRooms operate other cities, and are there similar desks in Rameswaram / Tirupati we should study or acquire?
- Legal structure for holding customer funds and remitting to hotels — get advice before volume, not after.

---

## 7. Summary

Small hoteliers in Kanyakumari are underserved by OTAs; travellers want a fast, multilingual, no-app way to book. A competitor called **FlashRooms already proves both** — from Trichy, with a telephone, a WhatsApp number and a QR code, at 15% commission.

That discovery changes the plan rather than discouraging it. We are not building a cheaper OTA and we are not betting on the AI being the product. **We are building the version of FlashRooms that scales**: the same trusted conversational surface and the same money flow, but with a supply model that spans manual, bot and live inventory simultaneously; an automation ladder that moves cost out of the business as trust accrues; a 24/7 SLA the incumbent structurally cannot meet; and an availability dataset that compounds into a moat they cannot build.

Start manual, earn revenue in weeks, and let the technology run one step ahead of the business — never two.

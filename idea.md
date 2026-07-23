# HotelAgent — Conversational Hotel Booking over WhatsApp

> A WhatsApp-first, agentic booking assistant. Launch in **Kanyakumari**, expand city-by-city.

**Version:** 0.1 (Vision & Architecture) · **Date:** 2026-07-23 · **Owner:** Founding team

---

## 1. Business Problem

### 1.1 The context
Kanyakumari is a high-footfall pilgrimage and tourism town (sunrise/sunset point, Vivekananda Rock, Thiruvalluvar statue). Demand is **seasonal, spiky, and last-minute** — pilgrims, weekend travellers from Tamil Nadu/Kerala, and bus-tour groups. Yet the local hotel supply is dominated by **small and mid-tier independent properties** (20–80 rooms) that are poorly served by the current booking ecosystem.

### 1.2 Pain points

**For travellers (demand side)**
- OTAs (MakeMyTrip, Booking.com, Goibibo) list mostly branded/mid-large hotels; many good local guesthouses are missing or have thin/stale inventory.
- App fatigue: installing an app, creating an account, KYC, and payment friction for a one-night stay is disproportionate.
- Language barrier: much of the audience is more comfortable in **Tamil / Malayalam / Hindi** than navigating English-only apps.
- No easy way to ask real questions — "Is parking free?", "Can I get an early 6 AM check-in for sunrise?", "Sea-facing under ₹2500?" — without calling each hotel.

**For hoteliers (supply side)**
- OTA commissions of **15–25%** crush thin margins on budget rooms.
- Small properties lack a channel manager / PMS; inventory lives in a **paper register or Excel**.
- Phone-based bookings are unmanaged: missed calls = lost revenue, double-bookings, no record.
- No digital presence or direct-booking channel they actually control.

### 1.3 Why WhatsApp
- **~500M+ Indian users**; it is the default communication layer, already installed, already trusted.
- **Zero install / zero new account** for the traveller — the conversation *is* the product.
- Native support for the messy, question-heavy, multilingual way people actually book.
- Rich message types (lists, buttons, images, location, payments) enable a full booking flow inside the chat.

### 1.4 Opportunity statement
> Build a **conversational commerce layer** that lets a traveller book a Kanyakumari hotel room end-to-end inside a WhatsApp chat — in their own language, in under 3 minutes — while giving small hoteliers a **low-commission, zero-tech-overhead** direct channel. Kanyakumari is the wedge; the platform generalises to any tourist city.

---

## 2. Business Solution

### 2.1 Product in one line
An **AI concierge on WhatsApp** that understands natural-language intent, searches live local inventory, answers questions, and completes a booking with payment and confirmation — no app, no forms.

### 2.2 Two-sided model

| Side | What they get | How they interact |
|------|---------------|-------------------|
| **Traveller** | Search, ask, compare, book, pay, get confirmation & directions | WhatsApp chat (the agent) |
| **Hotelier** | Direct bookings, low commission, inventory & calendar management, digital presence | WhatsApp bot + lightweight web dashboard |

### 2.3 The traveller journey (happy path)
1. **Entry** — scans a QR at the bus stand / poster / Google listing, or clicks `wa.me` link → opens WhatsApp pre-filled with "Hi".
2. **Understand** — agent greets, detects language, asks/infers: dates, guests, budget, preferences (sea-view, AC, parking, early check-in).
3. **Search** — agent queries live inventory, returns a **ranked shortlist** (WhatsApp list/cards with photo, price, key amenities).
4. **Q&A** — traveller asks follow-ups in natural language; agent answers from hotel knowledge base.
5. **Select & hold** — traveller picks a room; agent soft-holds inventory (e.g. 10 min).
6. **Guest details** — name + count captured conversationally; ID collection deferred to check-in or captured if required.
7. **Pay** — WhatsApp Pay / UPI deep link / payment link; or "Pay at hotel" where allowed.
8. **Confirm** — instant confirmation message with booking ID, hotel contact, location pin, cancellation policy, and calendar-add.
9. **Post-booking** — reminders, directions, check-in nudges, and a review request after checkout.

### 2.4 Monetisation
- **Commission per booking** (target **8–12%**, undercutting OTAs) — primary.
- **SaaS subscription** for hoteliers (dashboard, channel management) — secondary, recurring.
- **Featured placement / promoted listings** during peak season.
- **Payment float / value-added services** (travel add-ons, cabs, tour packages) — later.

### 2.5 Go-to-market (Kanyakumari wedge)
- **Supply first:** onboard 30–50 hotels manually before launch (feet-on-street; ~70% of usable budget inventory).
- **Demand:** QR codes at bus stand, railway station, tourist points; partnerships with tour operators; Google Business Profile "Message" button; local WhatsApp community seeding.
- **Trust:** verified hotels, transparent pricing, instant confirmation, human fallback number.

### 2.6 Expansion thesis
The Kanyakumari build is deliberately **city-agnostic**: a city is just a configuration + inventory set + language pack. New city = onboard supply + flip a config flag. Target the same profile — **tier-2/3 tourist & pilgrimage towns** (Rameswaram, Madurai, Tirupati, Munnar, Varkala) underserved by OTAs.

### 2.7 Success metrics (North Star + supporting)
- **North Star:** confirmed bookings / week.
- Conversation → booking conversion rate.
- Time-to-book (target < 3 min).
- Repeat-traveller rate; hotelier retention.
- Take rate vs. OTA; contribution margin per booking.
- CSAT / containment (bookings completed without human handoff).

---

## 3. Technical Architecture

### 3.1 Design principles
- **Agentic, not scripted.** An LLM agent with tools — not a rigid decision-tree bot. Handles open-ended questions gracefully.
- **Multi-tenant & city-agnostic from day one.** City/hotel are data, not code.
- **Inventory is the source of truth.** No overbooking — soft holds + atomic confirmation.
- **Human-in-the-loop fallback.** Always an escape hatch to a human agent or the hotel.
- **Stateless services, stateful conversations.** Conversation state persisted per user, services horizontally scalable.

### 3.2 High-level component diagram

```
                        ┌──────────────────────────────────────────┐
   Traveller (WhatsApp) │                                          │
        │               │            HotelAgent Platform            │
        ▼               │                                          │
 ┌─────────────┐  webhook│  ┌────────────────┐   ┌───────────────┐  │
 │ WhatsApp    │────────►│  │  Channel /      │   │  Orchestrator │  │
 │ Cloud API   │◄────────│  │  Messaging      │──►│  (Agent Core) │  │
 │ (Meta / BSP)│  send   │  │  Gateway        │◄──│  LLM + Tools  │  │
 └─────────────┘         │  └────────────────┘   └──────┬────────┘  │
                         │        ▲                       │           │
                         │  ┌─────┴──────┐         ┌──────▼───────┐   │
                         │  │ Session /  │         │  Tool /       │  │
                         │  │ Context    │         │  Function     │  │
                         │  │ Store      │         │  Layer        │  │
                         │  │ (Redis)    │         └──┬───┬───┬───┘   │
                         │  └────────────┘            │   │   │       │
                         │                            ▼   ▼   ▼       │
                         │   ┌─────────┐ ┌─────────┐ ┌────────┐ ┌────┐│
                         │   │Inventory│ │ Booking │ │Payments│ │ KB ││
                         │   │& Search │ │& Holds  │ │(UPI/WA)│ │RAG ││
                         │   │ Service │ │ Service │ │ Service│ │    ││
                         │   └────┬────┘ └────┬────┘ └───┬────┘ └─┬──┘│
                         │        │           │          │        │   │
                         │   ┌────▼───────────▼──────────▼────────▼─┐ │
                         │   │  Data Layer: PostgreSQL · Redis ·     │ │
                         │   │  Vector DB · Object store (images)    │ │
                         │   └───────────────────────────────────────┘ │
                         │                            ▲                 │
                         └────────────────────────────┼─────────────────┘
                                                      │
                     ┌────────────────────────────────┴───────┐
                     │  Hotelier Dashboard (web) + Hotelier    │
                     │  WhatsApp bot  ·  Ops/Admin console     │
                     └─────────────────────────────────────────┘
```

### 3.3 Core components

**1. Channel / Messaging Gateway**
- Integrates with **WhatsApp Business Platform (Cloud API)** via Meta directly or a BSP (Gupshup, Twilio, AiSensy, Interakt) — BSP recommended for faster template approval and billing simplicity.
- Handles inbound webhooks, outbound sends, interactive message types (list, buttons, CTA, location, media), delivery receipts, and 24-hour session-window / template-message rules.
- Normalises WhatsApp payloads into an internal channel-agnostic message schema (future-proofing for Instagram/Web/SMS).

**2. Orchestrator (Agent Core)** — the brain
- An **LLM agent loop** (Claude — `claude-sonnet-5` for the conversational path; escalate to `claude-opus-4-8` for complex reasoning/edge cases) with **tool use / function calling**.
- Responsibilities: intent understanding, slot-filling (dates, guests, budget, prefs), language detection/switching, deciding which tools to call, composing natural replies, and knowing when to hand off to a human.
- **System prompt + guardrails** define persona, policies (never overbook, never invent prices, always confirm before charging), and safety.
- Built with the **Claude Agent SDK** or a managed agent loop; deterministic business rules (pricing, availability, hold expiry) live in services, **not** in the prompt.

**3. Session / Context Store**
- Per-user conversation state (current intent, filled slots, active hold, language) in **Redis** with TTL.
- Full transcript + structured events persisted to Postgres for analytics and audit.

**4. Tool / Function Layer** — the agent's hands. Key tools:
- `search_availability(city, dates, guests, filters)` → ranked rooms
- `get_hotel_details(hotel_id)` / `answer_hotel_question(hotel_id, q)` (RAG)
- `hold_room(room_id, dates)` → soft lock with TTL
- `create_booking(hold_id, guest)` → atomic confirm
- `initiate_payment(booking_id, method)` / `check_payment_status`
- `cancel_or_modify_booking(booking_id, ...)`
- `escalate_to_human(reason)`

**5. Inventory & Search Service**
- Source of truth for rooms, rates, availability calendar, amenities per hotel.
- Supports filters (price, view, AC, parking, check-in time) and **ranking** (relevance, price, rating, conversion propensity).
- Ingests inventory from: hotelier dashboard, hotelier WhatsApp bot, CSV import, and (later) channel-manager/PMS integrations.

**6. Booking & Holds Service**
- **Soft holds** (Redis, e.g. 10-min TTL) to prevent double-booking during checkout.
- **Atomic confirmation** with DB transaction + optimistic locking on the availability row.
- Manages booking lifecycle: held → confirmed → checked-in → completed / cancelled / no-show.
- Emits events (confirmation, reminders) to the notification pipeline.

**7. Payments Service**
- **UPI** deep links, **WhatsApp Pay**, and payment links via **Razorpay / Cashfree / PhonePe**.
- Supports "Pay now" and "Pay at hotel"; handles webhooks, reconciliation, refunds for cancellations.
- Idempotent; PCI concerns offloaded to the gateway (no card data stored).

**8. Knowledge Base / RAG**
- Per-hotel structured facts + free-text (policies, FAQs, nearby attractions) embedded into a **vector DB** (pgvector / Pinecone / Qdrant).
- Powers `answer_hotel_question` so the agent answers grounded, not hallucinated. Citations back to hotel data.

**9. Hotelier interfaces**
- **Lightweight web dashboard**: manage rooms, rates, availability, view/confirm bookings, payouts, reviews.
- **Hotelier WhatsApp bot**: update availability ("Block 5 rooms tonight"), get booking alerts, accept/decline — meets low-tech hoteliers where they are.

**10. Ops / Admin console**
- Human-agent handoff inbox, conversation monitoring, hotel onboarding/verification, content moderation, pricing overrides, refunds.

**11. Notifications / Jobs**
- Async workers (queue-based) for reminders, hold-expiry, payment retries, review requests, and template messages within WhatsApp policy windows.

**12. Analytics & Observability**
- Funnel analytics (conversation → booking), LLM cost/token tracking, latency, containment rate.
- **Prompt/response logging + evals** to continuously improve the agent (guardrail regressions, hallucination checks).

### 3.4 Suggested tech stack

| Layer | Choice (recommended) | Notes |
|-------|----------------------|-------|
| Messaging | WhatsApp Cloud API via BSP (Gupshup/Twilio) | Faster onboarding, template mgmt |
| Agent / LLM | **Claude (Sonnet 5 default, Opus 4.8 for hard cases)** via Claude Agent SDK | Tool use, strong multilingual (Tamil/Malayalam/Hindi) |
| Backend | Python (FastAPI) or Node (NestJS) | Python pairs well with LLM/RAG tooling |
| Async / jobs | Celery/RQ or BullMQ + Redis | Reminders, holds, webhooks |
| Primary DB | PostgreSQL | Inventory, bookings, ledger |
| Cache / state | Redis | Session, holds |
| Vector DB | pgvector (start) → Qdrant/Pinecone | Hotel KB / RAG |
| Object store | S3 / GCS | Hotel images |
| Payments | Razorpay / Cashfree + UPI + WhatsApp Pay | Indian rails |
| Hosting | AWS / GCP (containers on ECS/Cloud Run) + Kubernetes later | Start simple, scale out |
| Dashboard | React (Next.js) | Hotelier + admin |
| Observability | OpenTelemetry, Grafana, LLM tracing (Langfuse/Helicone) | Cost + quality |

### 3.5 Data model (core entities, simplified)
- **City** (id, name, config, active_languages)
- **Hotel** (id, city_id, name, geo, verification_status, commission_rate, policies)
- **RoomType** (id, hotel_id, name, base_price, capacity, amenities[])
- **AvailabilityCalendar** (room_type_id, date, total, booked, price_override)
- **Hold** (id, room_type_id, dates, user_id, expires_at)
- **Booking** (id, hotel_id, room_type_id, user, dates, amount, commission, status, payment_ref)
- **User** (wa_id, name, language_pref, prior_bookings)
- **Conversation** (user_id, transcript, state, current_intent)
- **HotelKnowledge** (hotel_id, chunks[], embeddings)
- **Payment/Ledger** (booking_id, gateway_ref, amount, status, payouts)

### 3.6 Multi-city & multi-tenancy
- Every query scoped by `city_id`; hotels partitioned by city and tenant.
- **Language packs** and city-specific config (attractions, timing quirks like sunrise check-in) are data.
- Onboarding a city = load hotels + inventory + KB; no code change.

### 3.7 Reliability, safety, compliance
- **No overbooking:** holds + atomic transactions + idempotency keys everywhere money/inventory moves.
- **Guardrails:** agent never quotes a price or confirms a booking outside tool results; refuses to invent policies; always confirms amount before payment.
- **Human fallback:** `escalate_to_human` + a published support number.
- **Data privacy:** DPDP Act (India) compliance — consent, data minimisation (defer ID collection), retention limits, no card storage.
- **WhatsApp policy:** respect 24-hour session window, use approved templates for proactive messages, opt-in for marketing.
- **Resilience:** graceful degradation if LLM/tool is down (fallback to human or "we'll get back to you"); retries with backoff on webhooks/payments.

### 3.8 Phased delivery

| Phase | Scope | Outcome |
|-------|-------|---------|
| **0 — Foundations** | WhatsApp integration, agent loop, 1 pilot hotel, manual inventory | Book a room end-to-end in chat |
| **1 — Kanyakumari MVP** | 30–50 hotels, search+Q&A+pay+confirm, English+Tamil, hotelier WhatsApp bot | Live bookings, take rate proven |
| **2 — Scale KK** | Malayalam/Hindi, dashboard, reminders, reviews, analytics, holds hardening | Repeatable, measured funnel |
| **3 — Multi-city** | City config abstraction, 2nd city (e.g. Rameswaram) | Expansion validated |
| **4 — Platform** | PMS/channel-manager integrations, add-ons (cabs/tours), promoted listings | Marketplace + higher ARPU |

---

## 4. UI / UX

### 4.1 UX principles
- **Conversation is the interface.** Minimise typing; use buttons/lists for choices, free text for questions.
- **Language-native.** Detect and respond in the traveller's language (Tamil/Malayalam/Hindi/English); allow switching anytime.
- **Fast to value.** Shortlist within the first 2–3 exchanges; book in under 3 minutes.
- **Transparent & trustworthy.** Always show price breakdown, cancellation policy, and a confirmation with a real booking ID and hotel contact.
- **Forgiving.** Handle typos, mixed languages, and changed-my-mind gracefully; easy to go back / modify.
- **Human within reach.** One tap to a human whenever the traveller is stuck.

### 4.2 WhatsApp message-type mapping
| Step | WhatsApp feature |
|------|------------------|
| Greeting / language | Text + quick-reply buttons (English / தமிழ் / മലയാളം / हिंदी) |
| Collect dates/guests | Conversational text; optional date buttons |
| Show shortlist | **List message** or **carousel of cards** (image + name + price + "View") |
| Hotel details / photos | Image messages + text; buttons: "Book", "Ask a question", "Back" |
| Amenities filter | Quick-reply buttons (Sea view / AC / Parking / Under ₹2500) |
| Confirm selection | Button: "Confirm & Hold" |
| Payment | CTA URL button → payment link / WhatsApp Pay |
| Confirmation | Text summary + **location pin** + "Add to calendar" + booking ID |
| Support | Persistent "Talk to a human" quick reply |

### 4.3 Sample conversation (illustrative)

```
Traveller:  Hi, need a room in Kanyakumari this weekend

Agent:      Vanakkam! 🙏 I can help you book a hotel in Kanyakumari.
            Which language do you prefer?
            [ English ]  [ தமிழ் ]  [ हिंदी ]  [ മലയാളം ]

Traveller:  English is fine. 2 adults, Sat–Sun, sea view under 3000

Agent:      Got it — 2 guests, 25–26 Jul, sea-view, budget ₹3000.
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
            faces east — great for sunrise. Shall I hold a room?
            [ Confirm & Hold ]   [ See photos ]   [ Other hotels ]

Traveller:  Confirm

Agent:      Held for 10 min ⏳  Total ₹2,600 + ₹0 taxes = ₹2,600.
            Free cancellation until 24h before check-in.
            Pay now to confirm:
            [ Pay ₹2,600 via UPI ]      [ Pay at hotel ]

Traveller:  (pays)

Agent:      ✅ Booked! ID: KK-4821
            Sea Breeze Residency · 25–26 Jul · 2 guests
            📍 [location pin]   ☎ +91-98xxxxxxx
            See you at sunrise! I'll send directions on the day. 🌅
```

### 4.4 Hotelier UX
- **WhatsApp bot** for daily ops: "How many rooms free tonight?", "Block 3 rooms", instant booking alerts with accept/decline.
- **Web dashboard** for richer control: calendar view of availability, rate management, booking list, payouts/settlements, reviews, KB/FAQ editing, photo uploads.
- **Onboarding wizard**: add hotel, rooms, rates, photos, policies in < 30 min with field-team assistance.

### 4.5 Accessibility & inclusivity
- Full multilingual support incl. mixed-language ("Tanglish") understanding.
- Voice-note input support (transcribe) for low-literacy users — roadmap.
- Clear, low-jargon copy; emoji as visual anchors, not decoration.

---

## 5. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Overbooking / double-book | Soft holds + atomic txns + idempotency |
| LLM hallucinates price/policy | Guardrails: answers only from tool/RAG data; confirm before charge |
| Thin supply at launch | Feet-on-street onboarding of ~70% budget inventory before go-live |
| WhatsApp template rejections / policy changes | Use a BSP; keep flows session-window-friendly; human fallback |
| Hotelier low tech adoption | WhatsApp bot as primary interface; field support |
| Payment failures / disputes | Reputable gateway, retries, "pay at hotel" fallback, clear refund policy |
| Seasonality / demand troughs | Dynamic pricing, promoted listings, expand cities to smooth demand |
| LLM cost at scale | Sonnet default + Opus only for hard cases; caching; concise prompts |

---

## 6. Open Questions
- BSP vs. direct Meta Cloud API for launch?
- "Pay at hotel" — allow universally or only for verified/repeat users (no-show risk)?
- ID/KYC — defer to check-in, or capture upfront where local rules require?
- Commission level to balance hotelier adoption vs. unit economics?
- Human-ops staffing model for handoffs in the first months?

---

## 7. Summary
Small hoteliers in Kanyakumari are underserved by OTAs; travellers want a fast, multilingual, no-app way to book. **HotelAgent** meets both inside WhatsApp with an **agentic AI concierge** backed by real inventory, payments, and instant confirmation — at a fraction of OTA commission. The architecture is **multi-tenant and city-agnostic by design**, so Kanyakumari is a wedge, not a ceiling: prove the funnel here, then scale town by town.

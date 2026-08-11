# 0003 — Use the Anthropic SDK directly, with no agent framework

**Status:** Accepted
**Date:** 2026-08-11
**Deciders:** Founding team

## Context

M2 introduces an LLM agent loop. The default reflex is to reach for a framework
— LangGraph, LangChain, CrewAI, or one of their successors — and the founding
team already knows LangGraph from prior work, so this is not unfamiliarity
talking.

Two features of *this* system shape the decision.

**The loop is small.** HotelAgent's agent does: call the model → maybe call a
tool → maybe ask a human → repeat. That is roughly 200 lines. It is not a graph
of many nodes with complex branching, which is the situation frameworks are
genuinely good at.

**The Automation Governor sits inside the loop.** Invariant #4 requires that
*every* outbound message pass through a component deciding whether the agent
replies directly, drafts for human approval, or hands off entirely — based on
hotel tier, conversation stage, model confidence, booking value, and current ops
queue depth. That is an interception point on every single turn, and it is the
mechanism by which the entire business moves from L1 to L2 to L3.

## Options considered

**A framework.** Faster to a first demo. Provides state machines, retries,
memory abstractions and tracing integrations. Costs: an opinionated control flow
you must bend to intercept, an extra abstraction between you and the API, opaque
stack traces, and version churn in a fast-moving library.

**The SDK directly.** You write the loop. More initial code, complete control of
every turn, stack traces that point at your own functions, and an upgrade path
tied only to the Anthropic API itself.

## Decision

**Write the loop against the Anthropic SDK directly. No agent framework.**

The SDK is imported only inside `adapters/llm/`, per invariant #9, so the loop
depends on our own interface rather than on a vendor's client.

Supporting invariants: prompts are versioned files in the repo, not framework
prompt objects (#10), and every call is traced with prompt version, model,
tokens, latency, tool calls, whether a human edited the draft, and outcome (#7).
Both are things frameworks tend to want to own, and both are things we need to
own.

## Consequences

**Easier:**
- The Governor is a plain function call in a loop we wrote, not a fight with
  someone else's control flow.
- Debugging is reading our own code. When a booking goes wrong at 2am, the stack
  trace points at `modules/agent/`, not into a dependency.
- The team learns how tool-use loops actually work — an explicit goal
  (`docs/milestones.md` §8), and knowledge that transfers to any provider.
- No dependency on a fast-moving library's release cadence.

**Harder:**
- We write and test retries, tool dispatch, message-history management and
  token accounting ourselves. This is real work, budgeted in M2.
- Multi-agent orchestration, if we ever want it, would be built from scratch.
  Nothing in `docs/vision.md` calls for it.
- No free integrations. Langfuse tracing is wired by hand — acceptable, since
  invariant #7 specifies exactly what we need traced and it is more than a
  generic integration would capture.

## When to revisit

**When the loop exceeds roughly 500 lines**, or when we genuinely need a graph
of many nodes with complex conditional branching rather than a single
conversational loop.

If that happens, the adapter boundary means the change is contained: the
framework would live behind `adapters/llm/` and `modules/agent/`, not spread
through the codebase.

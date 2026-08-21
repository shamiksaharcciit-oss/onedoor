# Roadmap

**The goal:** a governed-actuation engine that plugs into any solution — AI
gateways, agent frameworks, enterprise systems — as either an embedded library
or a self-hosted decision service, with the enterprise features expected of
infrastructure: authentication and authorization, auditability, observability,
and a scalable persistence layer. Self-hosted, open source, Apache-2.0.

**The strategy:** the moat is semantics, not surface area. The decision core
(tiers, default-deny, reversibility-as-precondition, ordered checks) changes
rarely and carefully; enforcement surfaces and integrations grow demand-driven
— ideally contributed by the people who need them. onedoor composes with
gateways and content-safety tools; it does not compete with them.

## Where the plan actually lives

This file used to carry a release-by-release feature list. It went stale, because
the live plan moved into two working documents that are updated with every change:

| Document | Answers |
|---|---|
| **[BACKLOG.md](BACKLOG.md)** | What is being built: every ticket, its size, its sequencing, the migration-number register, and the release mapping. |
| **[CONFORMANCE.md](CONFORMANCE.md)** | What conforms to [AADP](https://datatracker.ietf.org/doc/draft-saha-aadp/) today: requirement by requirement, with the test that holds each one in place, and every gap named. |

Nothing is marked done in either without a passing test. Read those for anything
version-specific; this page deliberately carries only what does not go stale.

onedoor is the reference implementation of the AADP Internet-Draft, so
`CONFORMANCE.md` is the honest answer to "what does it actually do yet" — including
the parts that do not work. Start there.

## Non-goals

- **Not a gateway.** onedoor decides; gateways route. Compose, don't compete.
- **Not a content-safety filter.** Prompt-injection and toxicity screening
  belong to the tools built for them; onedoor governs *actions*.
- **Not an agent framework.** Bring your own agent; onedoor is the door.
- **Never clever storage.** SQLite stays the default; Postgres is an option,
  not a replacement.

## Research track (RFC, unscheduled): session-aware trust

An authorizer that remembers what an agent has done *this session* and degrades
autonomy accordingly — three denials in ten minutes should mean something; a burst
of novel action types should mean more. Open questions: which signals, what decay,
and how to keep it deterministic and auditable rather than a reputation vibe.
Design discussion happens in the issue tracker before any code. Strong disagreement
welcome; that is what RFCs are for.

## v1.0 criterion

v1.0 is declared when the decision semantics have survived contact with three
real deployments **unchanged** — not when a feature list completes. Stability
is earned, then versioned.

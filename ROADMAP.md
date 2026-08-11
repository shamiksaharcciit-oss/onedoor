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

---

## v0.3 — consultable by anything (in progress)

- **HTTP decision service.** A FastAPI app exposing the PDP over the network:
  `POST /v1/decide`, `POST /v1/report`, approvals (list / approve / deny),
  kill switch, health. Any enforcement point in any language can now consult
  the engine.
- **Authentication & first authorization split.** API-key auth on every
  endpoint, with two roles from day one: *decide* keys (submit and report)
  and *admin* keys (approve, deny, kill switch, policy reload). Separation of
  duties is a governance property, so it arrives before multi-tenancy, not
  after. OIDC/JWT follows in v0.4.
- **Observability.** OpenTelemetry traces per decision (span attributes:
  action type, outcome, reason code, tier) and metrics (decisions by outcome,
  denials by reason, cap utilization, approval latency). Optional dependency;
  the engine never requires a collector.
- **Approval notifications.** A pluggable notifier interface; webhook as the
  reference implementation (Slack-compatible payload). "Who sees the
  approval?" gets a real answer.
- **Packaging.** `pip install onedoor` (PyPI), with `[service]` and `[otel]`
  extras; a Dockerfile for the service.

## v0.4 — many principals, durable at scale

- **Identity & tenancy.** Actor and tenant on every `ActionRequest`;
  per-principal policies and caps; a permission hierarchy (key × team × org,
  most-restrictive-wins — the shape LiteLLM got right). OIDC/JWT
  authentication for the service.
- **Scalable persistence.** A storage interface with two implementations:
  SQLite (default, forever — single-node deployments deserve boring
  technology) and Postgres (multi-instance, `SELECT ... FOR UPDATE`
  reservations preserving the race-free-caps invariant). Alembic migrations.
- **Audit hardening.** Hash-chained audit rows (tamper-evidence), JSONL/SIEM
  export, retention policies. The log is already append-only; this makes it
  provably so.
- **RBAC for governance operations.** Named approver roles, proposer ≠
  approver enforcement, per-tenant admin scopes.

## v0.5 — more doorways, full documentation

- **MCP streamable-HTTP transport** for the proxy (stdio remains).
- **LiteLLM adapter graduates** from `examples/` to a supported integration,
  with intent carried to post-call hooks so the audit records true outcomes.
- **LangChain/LangGraph tool wrapper**; Envoy `ext_authz` filter if demand
  shows up.
- **Documentation site**: concepts (the ordered pipeline and why the order),
  policy reference, an integration guide per surface (library, service, MCP,
  LiteLLM), deployment and operations guide, threat model.

## Research track (RFC, unscheduled): session-aware trust

An authorizer that remembers what an agent has done *this session* and
degrades autonomy accordingly — three denials in ten minutes should mean
something; a burst of novel action types should mean more. Open questions:
which signals, what decay, and how to keep it deterministic and auditable
rather than a reputation vibe. Design discussion happens in the issue
tracker before any code. Strong disagreement welcome; that is what RFCs
are for.

## Non-goals

- **Not a gateway.** onedoor decides; gateways route. Compose, don't compete.
- **Not a content-safety filter.** Prompt-injection and toxicity screening
  belong to the tools built for them; onedoor governs *actions*.
- **Not an agent framework.** Bring your own agent; onedoor is the door.
- **Never clever storage.** SQLite stays the default; Postgres is an option,
  not a replacement.

## v1.0 criterion

v1.0 is declared when the decision semantics have survived contact with three
real deployments **unchanged** — not when a feature list completes. Stability
is earned, then versioned.

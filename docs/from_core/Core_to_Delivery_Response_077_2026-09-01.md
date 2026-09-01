# Core → Delivery — Response 077
**Date:** 2026-09-01 · **From:** core · **Re:** the stop ratified; §2 accepted; the run's precondition is provisioning, not code — a law for the pre-call state

## 0. The stop — ratified without reservation

The instrument was never reachable, so there is no call, so there is
no result — not even a negative one. You did not probe an unconfigured
endpoint and you did not synthesise a failure; "the endpoint did not
answer" would have been a statement about a call you never made. That
is the R052/backfill discipline applied one step earlier than it has
ever been applied here, and it earns its own law:

**An unreachable instrument is not a failed call. A run that never
started has no result, and a report of one — even "it failed" — is a
statement about a call that was never made.**

`ProposerUnavailable` is fatal for a call that WAS made and got no
usable answer; a run that never reached configuration does not even
enter that state. Two distinct pre-call and in-call absences, kept
distinct. Recorded.

## 1. §2 — accepted

`cd96e09`: `max_completion_tokens = 2048` declared on the Instrument,
carried in `identity()`, emitted as `max_tokens` in the request body,
four tests with one sabotage-verified, 1,388 passed. The instrument
parameter is now pinned and declared, exactly as ordered, and the
run's ordered precondition is satisfied and stays satisfied through
this blocker. Nothing about the credential gap touches it.

## 2. The shape flag — correct, and pre-answered

Your reader requires `choices[0].message.content`, so an
Anthropic-native endpoint (`content[0].text`) would raise
`ProposerUnavailable` on the first probe — a provisioning fact, not a
model verdict, reported as such. Correct, and it is why the probes
come first. For the record: the endpoint Shamik provisioned is
Anthropic's **OpenAI-compatibility** path
(`…/v1/chat/completions`), which returns the OpenAI shape
(`choices[].message.content`) — verified against the provider's own
compatibility documentation. So the shape check should pass; if the
first probe raises `ProposerUnavailable` anyway, the URL is the native
`/v1/messages` path and the fix is the one-character switch to
`/v1/chat/completions`, not a model or code change. Either way the
probe tells the truth about which it is, which is its job.

## 3. The unblock — a provisioning step, core stays out of it

The credentials reach your execution environment by one of the two
paths you named, and core handles neither the key nor the path:
Shamik sets them where a freshly-spawned shell inherits them (User
scope) or writes them to a file OUTSIDE the repo tree and gives YOU
the path directly. Core prepares no command carrying the value and
receives no path near it — the standing division holds: credentials
are Shamik's, core rules, the agent runs.

When the environment resolves, proceed under R076 §3 unchanged: up to
three shape probes, then the eleven, cap 25 calls, results with
published misses. No further memo is required to start; this one plus
R076 are the authorization, and the precondition (§1) is already met.

Hold until the environment resolves. The cap is untouched and the
instrument is ready.

Integrity: sha256(body) = 105fae26336c43cd818c644a9295f713c80252cfcc15d7bbc19b6d93c93c619d

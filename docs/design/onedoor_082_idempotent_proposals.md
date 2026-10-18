# Design note: idempotent proposals on (thread_id, tool_call_id)

Covers ruling item 2 (OD2+OD3) for 0.8.2. No code in this note or alongside it; it stops here
for review.

## The bug this closes

LangGraph resume re-executes the interrupted node from the top, including the code that
proposes the action. `onedoor/integrations/langchain_middleware.py`'s `wrap_tool_call` /
`_decide()` builds a brand-new `ActionRequest` (fresh `request_id = uuid4()`) on every call,
and `onedoor/guardrail/approvals.create()` has no check before its `INSERT` — so every resume
leaves behind a second, never-granted `pending` row. This is already named as a known
limitation in `CHANGELOG.md`'s most recent "Known limitations" entry: harmless (it is never
the row presented or consumed) but visible via `GET /v1/approvals`. The fix: a re-executed
node's proposal attempt finds its original approval row instead of creating a new one.

## Schema change

Add two nullable columns to `approvals` (`onedoor/store/migrations/0001_init.sql:75-86`):

- `thread_id TEXT`
- `tool_call_id TEXT`

Plus one unique index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_resume_key ON approvals (thread_id, tool_call_id);
```

SQLite's unique index treats every `NULL` as distinct from every other `NULL`, so this index
constrains nothing for a row where either column is `NULL` — which is every row written before
this migration, and every row from any caller that never passes the pair (the HTTP service,
the MCP integration, direct engine calls). It only binds a row where **both** columns are set,
which today is only the LangChain middleware's resumable path.

`onedoor/guardrail/approvals.create()` becomes find-or-create: when both `thread_id` and
`tool_call_id` are given, it looks the pair up first (`SELECT id FROM approvals WHERE
thread_id = ? AND tool_call_id = ?`) and returns that row's id — in whatever state it is now
in — instead of inserting. Only when no row exists, or either key is absent, does it insert as
today. `decide_and_reserve()` (`onedoor/guardrail/decision.py:137-145`) gains two optional
pass-through parameters with the same names, and the only caller that would supply them is
`wrap_tool_call`, which already holds `tool_call_id` (`langchain_middleware.py:177`) and can
read `thread_id` from the incoming `RunnableConfig`'s `configurable` mapping when LangGraph
supplies one.

**Open question, for review:** a resumed node that finds its original row returns that row
regardless of whether the re-built `ActionRequest` is byte-identical to the one that produced
it (LangGraph's contract is that re-execution is deterministic, but onedoor has no way to
verify that from inside `create()`). The alternative — comparing the new request against the
stored `request_json` and refusing on a mismatch — is a real option but is not assumed here;
it changes what a caller sees on a resume that genuinely diverged, and that is a judgment call
better made before code, not during review of it.

## Migration number

**0029 is already taken** — `onedoor/store/migrations/0029_decide_principal.sql` shipped in
0.8.1 (`ALTER TABLE actions_audit ADD COLUMN decide_principal TEXT`). The ruling's own text
names 0029 as "the enforcer's next"; that was accurate when 29vb was written and is stale now.
**The next free number is 0030.** `approvals` is defined in `0001_init.sql`, not a Studio
table (Studio's own tables — `ratifications`, `backtest_receipts`, `kill_switch_episodes`, and
others — are added starting at `0016`/`0017`/`0018`), so `0030_approval_resume_key.sql`
touching `approvals` does not run into the "no numbered migration may touch a Studio table"
limit.

## Upgrade path from 0.8.1

Run the new migration; it only adds columns and an index, no backfill. Every caller that does
not pass `thread_id`/`tool_call_id` — which, before the middleware is updated to pass them, is
every caller — is byte-for-byte unaffected: `create()`'s new lookup is skipped whenever either
key is absent, so the insert path is exactly what it is today. The only behavior change visible
to an operator is that a resumed LangGraph proposal, after the middleware is updated in the
code step that follows this note, stops producing a second `GET /v1/approvals` row — the
CHANGELOG's existing "Known limitations" entry for this is removed once the fix lands and
verified by a holding test, in the usual "Behaviour changes" shape with no action required from
a deployer beyond running the migration.

## Rows written before this migration

`thread_id` and `tool_call_id` are `NULL` on every such row, forever — nothing rewrites them.
Because `NULL` never collides with anything under the unique index, these rows are completely
inert with respect to the new constraint: they cannot be found by the new lookup (which only
runs when both keys are supplied) and cannot block a new row from being created. A pre-migration
row's behavior under every existing code path is unchanged.

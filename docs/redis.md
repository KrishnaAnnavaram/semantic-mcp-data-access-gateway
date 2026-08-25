# Redis 8.8 shared intelligence

Redis is a shared, derived-memory layer for the Domain Expert and MCP Agent. It
does not replace any system of record:

- PostgreSQL remains the authority for Treasury and portfolio data.
- Qdrant remains the authority for embedded knowledge chunks.
- MCP remains the only production path from an agent to data and calculations.
- A2A remains the only path between runtime agents.

The layer is optional. With `REDIS_ENABLED=false` the injected implementation is
a true no-op. With Redis enabled but temporarily unreachable, reads become
misses and writes/telemetry are skipped unless `REDIS_REQUIRED=true` explicitly
makes startup connectivity mandatory.

## Runtime layout

```text
Domain Expert ─┐                         ┌─ RedisJSON exact cache
               ├─ RedisIntelligence ─────├─ RediSearch semantic cache
MCP Agent ─────┘                         ├─ Streams / TimeSeries / counters
                                         ├─ owned single-flight locks
                                         └─ Redis 8.8 INCREX rate limits

PostgreSQL ── market data (authoritative)
Qdrant ────── knowledge + local BGE embeddings (authoritative)
MCP/A2A ───── unchanged execution and agent boundaries
```

There is no fourth runtime agent. `RedisIntelligence`, like `KnowledgeBase` and
`DataProvider`, is an adapter/service shared by the existing three-agent
network.

## What is cached

| Agent | Operation | Exact | Semantic | Default TTL |
|---|---|---:|---:|---:|
| Domain Expert | executable/reference retrieval | yes | no | 15 minutes |
| Domain Expert | derive requirement | yes | yes, safety-gated | 24 hours |
| Domain Expert | revise requirement | yes | no | 12 hours |
| Domain Expert | validate result | yes | no | 1 hour |
| MCP Agent | catalogue | yes | no | 5 minutes |
| MCP Agent | capability assessment | yes | no | 6 hours |
| MCP Agent | user choices | yes | no | 5 minutes |
| MCP Agent | execute data plan | **no** | **no** | n/a |

Execution is deliberately uncached. Current/latest results are freshness
sensitive. Historical results could become safely cacheable only after every
`DataProvider` exposes an immutable source snapshot identifier; a date alone is
not proof that the underlying corrected dataset is unchanged.

Failures, invalid structured outputs, empty retrieval outages, credentials, and
objects containing credential-like data are not cached.

## Exact identity and invalidation

Exact keys are SHA-256 fingerprints of canonical inputs plus every material
dependency:

- complete operation input, including prior plan and requested fields/rows;
- deterministic knowledge corpus digest;
- live catalogue/backend fingerprint;
- prompt, schema, capability-logic, semantic-policy, and envelope versions;
- configured LLM provider and model for LLM-derived entries.

A content or contract change therefore produces a new key. TTL remains a memory
and freshness bound, not the primary correctness mechanism. Cached JSON is
validated again on read; malformed or version-incompatible objects are removed
and counted as invalidations.

To invalidate intentionally, bump the relevant constant in
`agents/cache/versions.py`, change `REDIS_NAMESPACE_VERSION`, or use the bounded
admin command:

```bash
python -m agents.cache.admin clear --scope domain
python -m agents.cache.admin clear --scope mcp
python -m agents.cache.admin clear --scope semantic
python -m agents.cache.admin clear --scope all
```

`clear` scans only the configured namespace's cache/semantic prefixes and uses
`UNLINK`. It does not flush Redis and does not delete Streams, TimeSeries,
counters, rate limits, or unrelated application data.

## Semantic safety

The L2 semantic cache applies only to `derive`. It reuses the same local
`BAAI/bge-small-en-v1.5` FastEmbed instance already owned by the executable
Qdrant store; it introduces no paid embedding call or second embedding model.

A vector result is only a candidate. Reuse requires all of the following:

1. cosine similarity meets `REDIS_SEMANTIC_SIMILARITY_THRESHOLD`;
2. knowledge/prompt/schema versions are identical;
3. metric, confidence level, horizon, lookback, curve family, tenors, temporal
   mode and dates, requested fields/rows, and portfolio identity are identical;
4. a non-empty metric signature was recognized.

For example, 99% and 95% VaR, one-day and ten-day VaR, nominal and real yields,
and 2008 versus latest data are refused even if their embeddings are nearly
identical. Similar-looking refusals are counted as semantic-safety rejections.

## Coordination and overload controls

An exact miss takes an ownership-token lock with `SET NX PX`. Only the owner
computes; contenders use bounded exponential backoff and read the completed
exact object. Release is a Lua compare-and-delete, so an expired lock can never
be deleted by its former owner. Waiting is bounded and remains below the A2A
turn deadline.

Optional model caps use Redis 8.8's atomic `INCREX` for a global fixed window and
per-specialist fixed windows. Zero means disabled. A Redis outage fails open;
an actual exhausted cap returns a visible structured-call failure rather than
silently issuing another model request.

## Operational evidence

Every cached/missed specialist operation records redacted, bounded evidence:

- `smcp:v1:stream:agent-events`: approximate-maxlen Redis Stream;
- `smcp:v1:ts:*`: latency, Redis latency, tokens, cache outcomes, LLM calls,
  saved calls, saved tokens, and negotiation metrics with retention;
- `smcp:v1:stats:counters`: exact/semantic hits, misses, avoided calls, actual
  tokens, estimated savings, invalidations, expirations, and safety refusals;
- `smcp:v1:stats:question-frequency:*`: sorted-set repeated-question counts;
- `smcp:v1:run:*`: TTL-bound RedisJSON turn summaries, searchable by a
  RediSearch JSON index.

Token savings are copied from the cached call's actual provider usage. If a
custom provider exposes no usage, the value stays absent/zero; no token estimate
is fabricated. Latency savings use the historically measured uncached duration.
Each cache entry records provider, model, creation/access times, hit count, and
historical usage.

`GET /health` reports Redis connectivity, server version, JSON/Search/TimeSeries
availability, redacted configuration, counters, top questions, stream length,
and selected p50/p95/p99 latencies. The command-line equivalent is:

```bash
python -m agents.cache.admin health --analytics
```

## LangSmith

This Redis telemetry (Streams/TimeSeries/counters) and LangSmith are separate
systems, but a cache hit is not invisible in a trace: `@traced` marks the
*agent* method (`domain_expert.derive`, `mcp_agent.catalogue`, ...), and on a
hit that method's body — the model call, the `qdrant.search` child span —
never runs. Without a marker, that run would show up in LangSmith as a bare
`llm`/`retriever` span with no model attribution and near-zero duration,
indistinguishable from a silent failure. `RedisIntelligence` attaches
`cache_status` (`exact_hit` / `semantic_hit` / `wait_hit` / `miss`), plus
`cache_type`, `redis_latency_ms` and — on a semantic hit —
`semantic_similarity`, as run metadata on whichever span is active, and a
`cache:<status>` tag for filtering a project's run list to hits versus misses.
A `structured_call` rejected by the native rate limiter is tagged
`rate_limited` the same way. Both are fail-open, like every other call into
`agents/observability.py`: a broken tracer never affects the cache.

## Local operation

Copy `.env.example` to `.env`, then run:

```bash
docker compose up -d redis redis-insight
docker compose ps redis redis-insight
```

Redis is pinned to the official `redis:8.8.2` image. AOF (`everysec`) and RDB
snapshots are both enabled on the `redis-data` volume. `volatile-lfu` evicts only
TTL-bearing cache/run objects while retained operational structures stay
bounded by max length or retention. Redis Insight uses the official image at
<http://localhost:5540> and persists its configuration in a separate volume.

If port 6379 is occupied, set `REDIS_PORT=6380` and point host-side clients at
`redis://localhost:6380/0`. Container-to-container traffic still uses port 6379.

## Verification

Pure policy tests always run. Docker-backed tests opt in explicitly so the
ordinary suite remains usable without infrastructure:

```bash
# PowerShell
$env:REDIS_INTEGRATION_URL='redis://127.0.0.1:6379/0'
python -m pytest -q tests/test_redis_intelligence.py
```

The integration suite verifies RedisJSON exact reuse, contract-version
invalidation, owned single-flight behavior, strict semantic refusal/reuse,
Streams/counters, native rate limiting, and Redis 8.8 module health.

## Deferred extensions

- Historical execution caching: blocked on immutable provider snapshot IDs.
- Pub/Sub invalidation: unnecessary while content/version fingerprints provide
  deterministic invalidation.
- t-digest latency aggregation: current bounded TimeSeries values calculate
  exact percentiles at health-query time; introduce a digest only after volume
  justifies the additional state.

Primary operational references: [Redis 8.8 release](https://redis.io/blog/redis-8-8-is-ga/),
[official Redis Docker image](https://hub.docker.com/_/redis),
[persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/),
and [Redis Insight Docker setup](https://redis.io/docs/latest/operate/redisinsight/install/install-on-docker/).

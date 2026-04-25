# V4 Phase 0f Audit — sovereign-swarm post-migration state
**Date:** 2026-04-25
**After:** Phase 0c + 0d + 0e migrations complete

## Summary

Sovereign-swarm went from 33 modules to 24 modules. Of the 24 remaining, **6 are clear hotel infrastructure** (used by tenants or heavily by other infrastructure), and **18 are isolated dead code** (zero external use, zero internal use).

## Hotel infrastructure (KEEP)

| Module | External tenants using | Internal modules using | Files | Verdict |
|--------|----------------------|----------------------|-------|---------|
| `protocol/` | 6 (ATX/GBB/gli) | 24 | 6 | **HOTEL** — SwarmAgent base contract, narrator infra |
| `runtime/` | 0 | 4 | 7 | **HOTEL** — DAG executor, narrator infra |
| `integration/` | 0 | 7 | 6 | **HOTEL** — generic plumbing |
| `web_agent/` | 1 (ATX) | 2 | 3 | **HOTEL** — generic UI-TARS VLM client |
| `mcp_servers/` | 0 | 1 | 2 | **HOTEL** — MCP serving infrastructure |
| `audit/` | 0 | 1 | 4 | **HOTEL** — audit utilities |

## Dead code candidates (zero usage anywhere)

These 18 modules are not imported by any tenant, by any other sovereign-swarm module, or by any test. They are stale exploration code from earlier development that never got wired into the live system.

| Module | Files | LOC |
|--------|-------|-----|
| `calendar/` | 7 | ~732 |
| `competitive_intel/` | 8 | ~1,006 |
| `content/` | 8 | ~1,309 |
| `curation/` | 7 | ~737 |
| `digital_twin/` | 6 | ~955 |
| `document_intel/` | 8 | ~759 |
| `financial_ops/` | 4 | ~612 |
| `learning/` | 8 | ~1,567 |
| `legal/` | 6 | ~882 |
| `medical/` | 7 | ~1,054 |
| `model_lab/` | 6 | ~801 |
| `monitoring/` | 6 | ~973 |
| `personal_finance/` | 6 | ~914 |
| `recruitment/` | 6 | ~1,017 |
| `scientist/` | 10 | ~1,436 |
| `synesthesia/` | 7 | ~1,464 |
| `voice/` | 6 | ~893 |
| `workflow/` | 6 | ~897 |
| **Total** | **122** | **~16,000 LOC** |

## Recommendation for Phase 0g

Three options for the dead-code modules:

1. **Delete all 18.** Aggressive. Per V4, room-level concerns shouldn't live in the hotel even if unused. Frees ~16,000 LOC of cognitive overhead.
2. **Migrate to a "future" tenant repo or a separate sovereign-modules repo.** Preserves the work for when a tenant needs it, removes it from sovereign-swarm.
3. **Leave in place with a deprecation note.** Conservative. Doesn't hurt anything but keeps the noise.

**Tim's call.** The migration runbook authorized deletion of "modules that don't belong in the hotel" but the audit reveals a much larger pool than the original Phase 0c scope.

## Tests still in sovereign-swarm

After Phase 0c-0e cleanup:
- `tests/test_coordinator_dispatch.py`
- `tests/test_coordinator_factory.py`
- `tests/test_mcp_servers.py` (pre-existing breakage from missing `mcp` pip dep)
- `tests/test_web_agent.py`

20 pass, 4 skipped. Pre-existing mcp test still pre-broken.

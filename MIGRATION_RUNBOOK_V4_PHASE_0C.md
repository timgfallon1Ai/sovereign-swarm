# Migration Runbook · V4 Phase 0c
## inbound/ + sales_ops/ + support/ → ATX-Mats-Ai

**Status:** DRAFT — awaiting Tim's review before execution
**Author:** Claude (paired with Tim)
**Date:** 2026-04-24
**Architecture decision ref:** V4 hotel/room metaphor (full per-tenant duplication, no shared business-logic library)

---

## 1. Pre-flight findings

The dependency audit changed the migration shape from what I initially scoped:

### What's actually coupled

`inbound/`, `sales_ops/`, and `support/` are a tightly-coupled cluster:

```
inbound/router.py      ──→ sales_ops/{models, store}    (Contact, Enrollment, SalesOpsStore)
inbound/router.py      ──→ support/{models, service, store}   (Case, CaseService, SupportStore)
inbound/matcher.py     ──→ sales_ops/{models, store}    (Contact lookup)
inbound/publish_gate.py ──→ inbound/{matcher, sendgrid_parser}    (intra-cluster only)
```

Migrating `inbound/` alone is impossible — it pulls `sales_ops/` and `support/` with it. They move as a unit.

### Who actually uses these modules

| Consumer | Imports inbound | Imports sales_ops | Imports support | Strategy |
|----------|----------------|-------------------|----------------|----------|
| **ATX-Mats-Ai** | via tenant_api | ✅ direct (`SalesOpsStore`) | ✅ direct (`SupportStore`) | **Full migration target** |
| **GBB-Ai-Agent-System** | ❌ has own `core/orchestrator.py` | ❌ | ❌ | **No-op** (GBB built its own) |
| **gli-ai** | ❌ | ❌ | ❌ | **No-op** |
| sovereign-swarm/tenant_api | ✅ heavy | ✅ heavy | ✅ heavy | **Refactor or dissolve** |
| sovereign-swarm/tests | ✅ | ✅ | ✅ | **Move to ATX tests** |

**Key finding:** This migration only affects **ATX**. GBB and GLI never used these modules. Scope is smaller than feared.

### tenant_api complication

`sovereign_swarm/tenant_api/app.py` is a generic FastAPI factory that imports **all three modules**. ATX uses it. Per V4, this is hotel infrastructure mixing room concerns.

**Recommendation: dissolve `tenant_api/` entirely.** ATX writes its own FastAPI assembly using its own modules. Cleaner sovereignty.

If Tim wants to keep `tenant_api/`, it must be refactored to a tenant-agnostic factory taking injected stores via DI. But that's more work for less benefit.

---

## 2. Migration scope (final)

**In scope:**
- Migrate `sovereign_swarm/inbound/` (4 files, 638 LOC) → `atx_mats_ai/inbound/`
- Migrate `sovereign_swarm/sales_ops/` (11 files, 2,570 LOC) → `atx_mats_ai/sales_ops/`
- Migrate `sovereign_swarm/support/` (4 files, 501 LOC) → `atx_mats_ai/support/`
- Migrate tests `test_inbound.py`, `test_publish_gate.py`, `test_sales_ops.py`, `test_support.py` → ATX tests
- Rewrite ATX `main.py` to use its own modules + bootstrap own FastAPI directly
- Dissolve `sovereign_swarm/tenant_api/` (delete or freeze as legacy)

**Out of scope (this phase):**
- GBB / gli (they don't use these modules)
- Other sovereign-swarm modules (marketing, learning, etc.) — separate phases
- ATX behavioral changes (the gate logic stays as-is — pure code relocation)

**Total LOC moved:** ~3,710 + ~1,000 LOC of tests = **~4,700 LOC**
**Estimated time:** 4-6 hours focused work

---

## 3. Target state

### After migration — ATX-Mats-Ai layout

```
ATX-Mats-Ai/
├── atx_mats_ai/
│   ├── inbound/                  ← NEW (migrated from sovereign-swarm)
│   │   ├── __init__.py
│   │   ├── matcher.py            (imports from atx_mats_ai.sales_ops)
│   │   ├── publish_gate.py       (ATX-specific allowlists/patterns over time)
│   │   ├── router.py             (imports from atx_mats_ai.sales_ops + atx_mats_ai.support)
│   │   └── sendgrid_parser.py    (no internal imports)
│   ├── sales_ops/                ← NEW (migrated from sovereign-swarm)
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── apollo.py
│   │   ├── approval_queue.py
│   │   ├── cli.py
│   │   ├── models.py
│   │   ├── sequencer.py
│   │   ├── sequences/
│   │   └── store.py
│   ├── support/                  ← NEW (migrated from sovereign-swarm)
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── service.py
│   │   └── store.py
│   ├── api/                      ← NEW (replaces sovereign_swarm.tenant_api use)
│   │   ├── __init__.py
│   │   ├── inbound_webhook.py    (FastAPI router for SendGrid webhook)
│   │   ├── crm_router.py         (FastAPI routes for /api/crm/*)
│   │   ├── outbox_router.py      (FastAPI routes for /api/outbox/*)
│   │   └── state.py              (DI state for the API)
│   ├── main.py                   ← REWRITTEN (own FastAPI bootstrap, no tenant_api dependency)
│   ├── config.py                 (existing, may need ATX_INBOUND_* env vars added)
│   └── ... (existing modules untouched)
└── tests/
    ├── test_inbound.py            ← migrated
    ├── test_publish_gate.py       ← migrated
    ├── test_sales_ops.py          ← migrated
    └── test_support.py            ← migrated
```

### After migration — sovereign-swarm layout

```
sovereign-swarm/
├── sovereign_swarm/
│   ├── inbound/                  ← DELETED
│   ├── sales_ops/                ← DELETED
│   ├── support/                  ← DELETED
│   ├── tenant_api/               ← DELETED (or frozen as `_legacy_tenant_api/`)
│   └── ... (other modules untouched in this phase)
└── tests/
    ├── test_inbound.py            ← DELETED
    ├── test_publish_gate.py       ← DELETED
    ├── test_sales_ops.py          ← DELETED
    └── test_support.py            ← DELETED
```

---

## 4. Step-by-step migration sequence

### Step 1: Create ATX target directories
```bash
cd ~/Documents/GitHub/ATX-Mats-Ai
mkdir -p atx_mats_ai/{inbound,sales_ops,support,api}
mkdir -p atx_mats_ai/sales_ops/sequences
```

### Step 2: Copy + rewrite imports — sales_ops first (deepest dependency)
For each file in `sovereign_swarm/sales_ops/`:
1. Copy to `atx_mats_ai/sales_ops/<same_name>`
2. Replace `from sovereign_swarm.sales_ops.X` → `from atx_mats_ai.sales_ops.X`
3. Replace `from sovereign_swarm.support.X` → `from atx_mats_ai.support.X` (if any)

**Verification:** `python -c "from atx_mats_ai.sales_ops import store; print('ok')"` runs without ImportError.

### Step 3: Copy + rewrite imports — support
Same pattern as Step 2. Rewrite `sovereign_swarm.support.X` → `atx_mats_ai.support.X`.

### Step 4: Copy + rewrite imports — inbound
Same pattern. Rewrite all `sovereign_swarm.{inbound,sales_ops,support}.X` → `atx_mats_ai.{inbound,sales_ops,support}.X`.

### Step 5: Build ATX's own API layer (replaces tenant_api)
Read `sovereign_swarm/tenant_api/app.py` and split its concerns into:
- `atx_mats_ai/api/inbound_webhook.py` — SendGrid webhook handler
- `atx_mats_ai/api/crm_router.py` — `/api/crm/*` routes
- `atx_mats_ai/api/outbox_router.py` — `/api/outbox/*` routes
- `atx_mats_ai/api/state.py` — DI container

Adapt to:
- Tenant is hardcoded `"atx_mats"` (no multi-tenant logic — this IS the ATX room)
- All imports point to `atx_mats_ai.*`
- Hardcoded ATX-specific config (env var names like `ATX_SENDGRID_*`)

### Step 6: Rewrite ATX main.py
Remove:
```python
from sovereign_swarm.sales_ops.store import SalesOpsStore
from sovereign_swarm.support.store import SupportStore
from sovereign_swarm.tenant_api import (
    TenantAPIState,
    create_inbound_webhook_router,
    create_tenant_api_router,
)
```

Replace with:
```python
from atx_mats_ai.sales_ops.store import SalesOpsStore
from atx_mats_ai.support.store import SupportStore
from atx_mats_ai.api.state import APIState
from atx_mats_ai.api.inbound_webhook import create_inbound_webhook_router
from atx_mats_ai.api.crm_router import create_crm_router
from atx_mats_ai.api.outbox_router import create_outbox_router
```

### Step 7: Migrate tests
Move `tests/test_{inbound,publish_gate,sales_ops,support}.py` from sovereign-swarm to ATX. Rewrite imports.

### Step 8: Verify ATX standalone
```bash
cd ~/Documents/GitHub/ATX-Mats-Ai
pytest tests/ -x
python -m atx_mats_ai.main &  # smoke-test the FastAPI starts
```

All tests pass. App starts. Health endpoint responds.

### Step 9: Verify ATX deploy
Push to ATX's git. Railway picks up the change. Tail logs to confirm startup.

### Step 10: Delete from sovereign-swarm
Only after Step 9 confirms ATX is healthy on Railway:
```bash
cd ~/Documents/GitHub/sovereign-swarm
git rm -r sovereign_swarm/{inbound,sales_ops,support,tenant_api}
git rm tests/test_{inbound,publish_gate,sales_ops,support}.py
```

### Step 11: Verify sovereign-swarm still builds
```bash
cd ~/Documents/GitHub/sovereign-swarm
pytest tests/ -x
```

If any tests still reference deleted modules, those tests are orphaned and should be deleted in this commit.

### Step 12: Commit + tag
```bash
# In ATX
git add . && git commit -m "Migrate inbound/sales_ops/support from sovereign-swarm to ATX (V4 Phase 0c)"

# In sovereign-swarm
git add . && git commit -m "Remove inbound/sales_ops/support/tenant_api — migrated to ATX (V4 Phase 0c)"
git tag v4-phase-0c-complete
```

---

## 5. Risk + rollback

### Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Import path bug after rewrite | High | Medium | Test suite covers most. Smoke-test main.py boot. |
| ATX Railway deploy breaks | Medium | High | Deploy to staging first if possible. Otherwise rollback ready. |
| Hidden circular import after migration | Low | High | Run all tests at each module step (2/3/4) not just at end. |
| Missing test coverage exposes runtime bug | Medium | Medium | Manual smoke test of inbound webhook with a test SendGrid payload. |
| sovereign-swarm leftover imports break GBB or gli | Low | High | GBB and gli don't import these modules — verified in audit. Still run their test suites after Step 10. |

### Rollback procedure

If ANY step fails after Step 10 (deletion):

```bash
cd ~/Documents/GitHub/sovereign-swarm
git revert HEAD  # restore deleted modules
git push
# Then revert ATX migration commits
cd ~/Documents/GitHub/ATX-Mats-Ai
git revert <migration commits>
git push  # Railway redeploys old version
```

If failure happens BEFORE Step 10, just abandon ATX changes — sovereign-swarm hasn't been touched, no rollback needed.

**Critical rule:** Step 10 (deletion from sovereign-swarm) is the point of no easy return. Do not proceed past Step 9 verification without ATX confirmed healthy on Railway for at least 30 minutes.

---

## 6. Decision points for Tim

Before I execute this runbook, confirm:

1. **Dissolve `sovereign_swarm/tenant_api/` entirely** (vs. keep as DI factory)? My pick: dissolve. Cleanest hotel/room separation.

2. **ATX builds its own `api/` layer from scratch** (vs. copying tenant_api/ verbatim and renaming)? My pick: build from scratch but copy logic. Avoids inheriting hotel-style abstractions.

3. **Migrate tests to ATX or leave them in sovereign-swarm momentarily?** My pick: migrate now, single commit. Keeping orphaned tests is debt.

4. **Is this safe to run while Railway production is live?** ATX is on Railway (saw `railway.toml` in repo). If yes, what's the maintenance window — or do we accept ~5 min of webhook downtime during the redeploy at Step 9?

5. **Order: should I do this in ONE focused session (4-6 hrs continuous) or split across days (Steps 1-7 day 1, Steps 8-12 day 2 with overnight observation)?** My pick: split. Less fatigue → fewer mistakes. Step 7 ends with ATX still using sovereign-swarm code (we haven't broken it yet); Step 10 onward is the cutover.

---

## 7. Out of band — what comes after

Once Phase 0c is complete and stable for ~3 days:

- **Phase 0d:** Migrate `marketing/` — bigger (3,148 LOC), but pattern is the same. Each tenant gets its own copy.
- **Phase 0e:** Migrate `learning/`, `analytics/` (per-tenant), `competitive_intel/`, `strategic_intel/`.
- **Phase 0f:** Audit remaining sovereign-swarm modules. Most should migrate; only narrator-related stays.
- **Phase 0g:** Slim sovereign-swarm to its narrator role + tenant lifecycle + cross-tenant aggregation only.

---

## End of runbook

"""SalesOpsAgent — SwarmAgent wrapper for sales_ops capabilities.

Routes task strings to the appropriate sub-component:
- prospect  → Apollo search + upsert
- enroll    → Sequencer.enroll
- tick      → Sequencer.tick (stage next due messages)
- queue     → ApprovalQueue.pending
- approve   → ApprovalQueue.approve / approve_all_safe
- pipeline  → summary of enrollments and activity
- reply     → Sequencer.pause_on_reply
"""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)
from sovereign_swarm.sales_ops.apollo import ApolloClient
from sovereign_swarm.sales_ops.approval_queue import ApprovalQueue
from sovereign_swarm.sales_ops.models import EnrollmentStatus
from sovereign_swarm.sales_ops.sequencer import Sequencer
from sovereign_swarm.sales_ops.store import SalesOpsStore

logger = structlog.get_logger()


class SalesOpsAgent(SwarmAgent):
    """Agent that owns CRM, sequencing, and approval queue for sales outreach."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._store: SalesOpsStore | None = None
        self._sequencer: Sequencer | None = None
        self._queue: ApprovalQueue | None = None
        self._apollo: ApolloClient | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="sales_ops",
            description=(
                "Sales operations agent — Apollo prospecting, sequence enrollment, "
                "message staging for approval, pipeline reporting. Tenant-aware. "
                "Stage-for-approval default; zero auto-send without human in loop."
            ),
            version="0.1.0",
            domains=["sales", "crm", "outbound", "prospecting", "pipeline"],
            supported_intents=[
                "prospect",
                "enroll",
                "tick",
                "queue",
                "approve",
                "approve_all_safe",
                "skip",
                "pipeline",
                "record_reply",
            ],
            capabilities=[
                "apollo_prospecting",
                "sequence_enrollment",
                "message_drafting",
                "approval_queue",
                "pipeline_reporting",
                "reply_handling",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        task = (request.task or "").lower()
        params = request.parameters or request.context or {}

        try:
            if "prospect" in task:
                result = await self._prospect(params)
            elif "enroll" in task:
                result = await self._enroll(params)
            elif "tick" in task or "advance" in task:
                result = await self._tick(params)
            elif "queue" in task or "pending" in task:
                result = await self._queue(params)
            elif "approve" in task and "safe" in task:
                result = await self._approve_all_safe(params)
            elif "approve" in task:
                result = await self._approve(params)
            elif "skip" in task:
                result = await self._skip(params)
            elif "pipeline" in task or "status" in task:
                result = await self._pipeline(params)
            elif "reply" in task:
                result = await self._record_reply(params)
            else:
                result = await self._pipeline(params)

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.85),
            )
        except Exception as exc:
            logger.error("sales_ops.execute_failed", error=str(exc))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Intents
    # ------------------------------------------------------------------

    async def _prospect(self, params: dict[str, Any]) -> dict[str, Any]:
        tenant = params.get("tenant", "atx_mats")
        titles = params.get("titles") or ["facility manager", "operations manager"]
        keywords = params.get("keywords", "")
        industries = params.get("industries")
        locations = params.get("locations")
        limit = int(params.get("limit", 10))

        apollo = self._get_apollo()
        if not apollo.is_configured:
            return {
                "markdown": "APOLLO_API_KEY not configured. Set env var to enable prospecting.",
                "error": "apollo_not_configured",
                "confidence": 0.0,
            }

        pairs = await apollo.search_people(
            tenant=tenant,
            titles=titles,
            keywords=keywords,
            industries=industries,
            locations=locations,
            limit=limit,
        )

        store = await self._get_store()
        upserted = 0
        rows = []
        for contact, company in pairs:
            company_id = None
            if company.name:
                company_id = await store.upsert_company(company)
            contact.company_id = company_id
            contact_id = await store.upsert_contact(contact)
            rows.append({
                "contact_id": contact_id,
                "name": contact.display,
                "email": contact.email,
                "company": company.name,
            })
            upserted += 1

        md = f"### Prospected {upserted} contacts for `{tenant}`\n\n"
        for r in rows[:20]:
            md += f"- [{r['contact_id']}] **{r['name']}** — {r['email']} @ {r['company']}\n"
        return {
            "markdown": md,
            "count": upserted,
            "contacts": rows,
            "confidence": 0.9 if upserted else 0.3,
        }

    async def _enroll(self, params: dict[str, Any]) -> dict[str, Any]:
        tenant = params.get("tenant", "atx_mats")
        contact_ids = params.get("contact_ids") or ([params["contact_id"]] if "contact_id" in params else [])
        sequence = params.get("sequence", "atx_distributor")
        sequencer = await self._get_sequencer()

        results = []
        for cid in contact_ids:
            enrollment = await sequencer.enroll(tenant, int(cid), sequence)
            results.append({
                "contact_id": cid,
                "enrollment_id": enrollment.id if enrollment else None,
                "ok": enrollment is not None,
            })

        ok_count = sum(1 for r in results if r["ok"])
        md = f"### Enrolled {ok_count}/{len(results)} in `{sequence}`\n"
        return {"markdown": md, "results": results, "count": ok_count, "confidence": 0.9}

    async def _tick(self, params: dict[str, Any]) -> dict[str, Any]:
        tenant = params.get("tenant")
        sequencer = await self._get_sequencer()
        msgs = await sequencer.tick(tenant=tenant)
        md = f"### Tick complete — {len(msgs)} messages drafted\n"
        for m in msgs[:20]:
            md += f"- [{m.id}] step {m.step_index} ({m.channel.value}) → contact {m.contact_id}\n"
        return {"markdown": md, "drafted": len(msgs), "confidence": 1.0}

    async def _queue(self, params: dict[str, Any]) -> dict[str, Any]:
        tenant = params.get("tenant")
        queue = await self._get_queue()
        pending = await queue.pending(tenant=tenant)
        md = f"### Pending approval ({len(pending)} messages)\n\n"
        for m in pending[:30]:
            preview = (m.body or m.subject or "")[:80].replace("\n", " ")
            md += (
                f"- **[{m.id}]** step {m.step_index} ({m.channel.value}) "
                f"→ contact {m.contact_id}: `{preview}...`\n"
            )
        return {"markdown": md, "pending": len(pending), "confidence": 1.0}

    async def _approve(self, params: dict[str, Any]) -> dict[str, Any]:
        message_id = int(params.get("message_id") or 0)
        if message_id == 0:
            return {"markdown": "Missing message_id.", "confidence": 0.0}
        queue = await self._get_queue()
        ok = await queue.approve(message_id)
        md = f"### Approve {message_id}: {'✓ sent' if ok else '✗ failed'}\n"
        return {"markdown": md, "ok": ok, "confidence": 1.0 if ok else 0.3}

    async def _approve_all_safe(self, params: dict[str, Any]) -> dict[str, Any]:
        tenant = params.get("tenant")
        queue = await self._get_queue()
        stats = await queue.approve_all_safe(tenant=tenant)
        md = (
            f"### Auto-approve safe steps\n"
            f"- Sent: {stats['sent']}\n"
            f"- Skipped (unsafe, needs explicit approval): {stats['skipped_unsafe']}\n"
            f"- Failed: {stats['failed']}\n"
        )
        return {"markdown": md, **stats, "confidence": 1.0}

    async def _skip(self, params: dict[str, Any]) -> dict[str, Any]:
        message_id = int(params.get("message_id") or 0)
        reason = params.get("reason", "")
        queue = await self._get_queue()
        ok = await queue.skip(message_id, reason)
        return {
            "markdown": f"### Skip {message_id}: {'✓' if ok else '✗'}\n",
            "ok": ok,
            "confidence": 1.0,
        }

    async def _pipeline(self, params: dict[str, Any]) -> dict[str, Any]:
        tenant = params.get("tenant", "atx_mats")
        store = await self._get_store()
        active = await store.list_enrollments(tenant, status=EnrollmentStatus.ACTIVE)
        paused = await store.list_enrollments(tenant, status=EnrollmentStatus.PAUSED)
        completed = await store.list_enrollments(tenant, status=EnrollmentStatus.COMPLETED)
        contacts = await store.list_contacts(tenant, limit=5000)

        md = (
            f"### Pipeline — {tenant}\n\n"
            f"- Contacts: {len(contacts)}\n"
            f"- Active enrollments: {len(active)}\n"
            f"- Paused (replied, awaiting review): {len(paused)}\n"
            f"- Completed: {len(completed)}\n"
        )
        return {
            "markdown": md,
            "contacts": len(contacts),
            "active": len(active),
            "paused": len(paused),
            "completed": len(completed),
            "confidence": 1.0,
        }

    async def _record_reply(self, params: dict[str, Any]) -> dict[str, Any]:
        contact_id = int(params.get("contact_id") or 0)
        reason = params.get("reason", "reply_received")
        sequencer = await self._get_sequencer()
        count = await sequencer.pause_on_reply(contact_id, reason=reason)
        return {
            "markdown": f"### Paused {count} enrollment(s) for contact {contact_id}\n",
            "paused_count": count,
            "confidence": 1.0,
        }

    # ------------------------------------------------------------------
    # Lazy initializers
    # ------------------------------------------------------------------

    async def _get_store(self) -> SalesOpsStore:
        if self._store is None:
            self._store = SalesOpsStore()
            await self._store.initialize()
        return self._store

    async def _get_sequencer(self) -> Sequencer:
        if self._sequencer is None:
            store = await self._get_store()
            self._sequencer = Sequencer(store)
        return self._sequencer

    async def _get_queue(self) -> ApprovalQueue:
        if self._queue is None:
            store = await self._get_store()
            self._queue = ApprovalQueue(store)
        return self._queue

    def _get_apollo(self) -> ApolloClient:
        if self._apollo is None:
            self._apollo = ApolloClient()
        return self._apollo

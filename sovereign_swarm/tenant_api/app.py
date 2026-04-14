"""Sovereign Tenant API — FastAPI app factory.

Each tenant backend (gli-ai, gbb-ai-agent-system, atx-mats-ai) imports
this module and mounts it on their app:

    from sovereign_swarm.tenant_api import create_tenant_api
    app.include_router(create_tenant_api(tenant_key="atx_mats"), prefix="/api/crm")

This provides the shared endpoints for approvals, cases, analytics,
contacts, activities, etc. Tenant-specific endpoints stay in the tenant's
own code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from sovereign_swarm.analytics import (
    channel_metrics,
    funnel_metrics,
    sequence_metrics,
)
from sovereign_swarm.tenant_api.auth import (
    TokenClaims,
    TokenPair,
    hash_password,
    issue_token_pair,
    issue_token,
    issue_refresh_token,
    decode_token,
    require_tenant_claim,
    verify_password,
)
from sovereign_swarm.inbound.router import InboundRouter
from sovereign_swarm.inbound.sendgrid_parser import parse_sendgrid_webhook
from sovereign_swarm.sales_ops.approval_queue import ApprovalQueue
from sovereign_swarm.sales_ops.models import (
    EnrollmentStatus,
    MessageStatus,
)
from sovereign_swarm.sales_ops.sequencer import Sequencer
from sovereign_swarm.sales_ops.store import SalesOpsStore
from sovereign_swarm.support.models import (
    CaseMessageDirection,
    CasePriority,
    CaseStatus,
)
from sovereign_swarm.support.service import CaseService
from sovereign_swarm.support.store import SupportStore

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Dependency injection state
# ---------------------------------------------------------------------------


class TenantAPIState:
    """Holds per-tenant store singletons.

    Tenant backend instantiates this at startup and passes to create_tenant_api.

    `users` is an in-memory dict of {email: hashed_password} for the pilot
    auth system. Production deployments should replace this with a DB-backed
    user store (move into SalesOpsStore or a dedicated auth store).
    """

    def __init__(
        self,
        tenant_key: str,
        sales_store: SalesOpsStore,
        support_store: SupportStore,
        users: dict[str, str] | None = None,
    ) -> None:
        self.tenant_key = tenant_key
        self.sales_store = sales_store
        self.support_store = support_store

        self.sequencer = Sequencer(sales_store)
        self.approval_queue = ApprovalQueue(sales_store)
        self.case_service = CaseService(support_store)
        self.inbound_router = InboundRouter(sales_store, support_store)

        # Seed with default admin if no users provided
        self.users: dict[str, str] = users or {}
        if not self.users:
            # Sourced from env — default to tim@{tenant}.com for dev
            import os
            default_email = os.getenv(
                "DEFAULT_ADMIN_EMAIL", f"tim@{tenant_key}.com"
            )
            default_pw = os.getenv("DEFAULT_ADMIN_PASSWORD", "sovereign-dev-2026")
            self.users[default_email] = hash_password(default_pw)


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class ReplyCaseBody(BaseModel):
    body: str
    subject: str | None = None


class ResolveCaseBody(BaseModel):
    note: str = ""


class AssignCaseBody(BaseModel):
    assignee: str


class EnrollBody(BaseModel):
    contact_ids: list[int]
    sequence_name: str


class SkipMessageBody(BaseModel):
    reason: str = ""


class EditMessageBody(BaseModel):
    subject: str | None = None
    body: str | None = None


class LoginBody(BaseModel):
    email: str
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_tenant_api_router(
    state: TenantAPIState,
    require_auth: bool = True,
) -> APIRouter:
    """Return a FastAPI APIRouter exposing the Sovereign Tenant API contract.

    When `require_auth=True` (default), every endpoint under this router
    (EXCEPT /auth/login and /auth/refresh) requires a valid JWT with
    `tenant` claim matching `state.tenant_key`.

    Two routers are created: `auth_router` (no auth) and `crm_router`
    (auth required). Both are merged into the returned router so the
    call site only sees one include_router call.
    """
    tenant = state.tenant_key
    auth_dep = require_tenant_claim(tenant)

    # --- Auth sub-router (no auth required for login/refresh) -----------

    auth_router = APIRouter()

    @auth_router.post("/auth/login", response_model=TokenPair)
    async def login(body: LoginBody):
        hashed = state.users.get(body.email)
        if not hashed or not verify_password(body.password, hashed):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return issue_token_pair(subject=body.email, tenant=tenant)

    @auth_router.post("/auth/refresh", response_model=TokenPair)
    async def refresh(body: RefreshBody):
        claims = decode_token(body.refresh_token)
        if claims.tenant != tenant:
            raise HTTPException(status_code=403, detail="Token tenant mismatch")
        return issue_token_pair(subject=claims.sub, tenant=tenant)

    # --- Protected sub-router -------------------------------------------

    protected_deps = [Depends(auth_dep)] if require_auth else []
    router = APIRouter(dependencies=protected_deps)

    @router.get("/auth/me")
    async def me(claims: TokenClaims = Depends(auth_dep)):
        return {
            "authenticated": True,
            "email": claims.sub,
            "tenant": claims.tenant,
            "scopes": claims.scopes,
            "expires_at": claims.exp,
        }

    # ------------------------------------------------------------------
    # Approvals
    # ------------------------------------------------------------------

    @router.get("/approvals")
    async def list_approvals():
        messages = await state.approval_queue.pending(tenant=tenant)
        # Hydrate contact info for each
        out = []
        for m in messages:
            contact = await state.sales_store.get_contact(m.contact_id)
            company = None
            if contact and contact.company_id:
                company = await state.sales_store.get_company(contact.company_id)
            out.append({
                **m.model_dump(),
                "contact": (
                    {
                        "id": contact.id,
                        "first_name": contact.first_name,
                        "last_name": contact.last_name,
                        "email": contact.email,
                        "role": contact.role,
                        "company_name": company.name if company else "",
                    }
                    if contact
                    else None
                ),
            })
        return {"messages": out, "count": len(out)}

    @router.post("/approvals/{message_id}/approve")
    async def approve_message(message_id: int):
        ok = await state.approval_queue.approve(message_id)
        if not ok:
            raise HTTPException(status_code=400, detail="Could not approve message")
        return {"ok": True, "message_id": message_id}

    @router.post("/approvals/{message_id}/skip")
    async def skip_message(message_id: int, body: SkipMessageBody):
        ok = await state.approval_queue.skip(message_id, reason=body.reason)
        if not ok:
            raise HTTPException(status_code=404, detail="Message not found")
        return {"ok": True, "message_id": message_id}

    @router.put("/approvals/{message_id}")
    async def edit_message(message_id: int, body: EditMessageBody):
        msg = await state.sales_store.get_message(message_id)
        if not msg or msg.tenant != tenant:
            raise HTTPException(status_code=404, detail="Message not found")
        if msg.status != MessageStatus.DRAFTED:
            raise HTTPException(status_code=400, detail="Only drafted messages can be edited")
        if body.subject is not None:
            msg.subject = body.subject
        if body.body is not None:
            msg.body = body.body
        await state.sales_store.update_message(msg)
        return {"ok": True, "message_id": message_id}

    @router.post("/approvals/approve-all-safe")
    async def approve_all_safe():
        stats = await state.approval_queue.approve_all_safe(tenant=tenant)
        return stats

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    @router.get("/contacts")
    async def list_contacts(
        limit: int = Query(100, le=500),
        company_id: int | None = None,
    ):
        contacts = await state.sales_store.list_contacts(
            tenant=tenant, limit=limit, company_id=company_id
        )
        return {"contacts": [c.model_dump() for c in contacts], "count": len(contacts)}

    @router.get("/contacts/{contact_id}")
    async def get_contact(contact_id: int):
        contact = await state.sales_store.get_contact(contact_id)
        if not contact or contact.tenant != tenant:
            raise HTTPException(status_code=404, detail="Contact not found")
        return contact.model_dump()

    # ------------------------------------------------------------------
    # Companies
    # ------------------------------------------------------------------

    @router.get("/companies")
    async def list_companies(limit: int = Query(100, le=500)):
        companies = await state.sales_store.list_companies(tenant=tenant, limit=limit)
        return {"companies": [c.model_dump() for c in companies]}

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------

    @router.get("/activities")
    async def list_activities(
        contact_id: int = Query(...),
        limit: int = Query(100, le=500),
    ):
        activities = await state.sales_store.activities_for_contact(contact_id, limit=limit)
        return {"activities": [a.model_dump() for a in activities]}

    # ------------------------------------------------------------------
    # Sequences
    # ------------------------------------------------------------------

    @router.post("/sequences/enroll")
    async def enroll_contacts(body: EnrollBody):
        results = []
        for cid in body.contact_ids:
            enrollment = await state.sequencer.enroll(
                tenant, cid, body.sequence_name
            )
            results.append({
                "contact_id": cid,
                "enrollment_id": enrollment.id if enrollment else None,
                "ok": enrollment is not None,
            })
        return {"results": results}

    @router.post("/sequences/tick")
    async def tick_sequences():
        msgs = await state.sequencer.tick(tenant=tenant)
        return {"drafted": len(msgs)}

    # ------------------------------------------------------------------
    # Cases
    # ------------------------------------------------------------------

    @router.get("/cases")
    async def list_cases(
        status: str | None = Query(None),
        limit: int = Query(200, le=500),
    ):
        status_enum = CaseStatus(status) if status else None
        cases = await state.support_store.list_cases(
            tenant=tenant, status=status_enum, limit=limit
        )
        out = []
        for c in cases:
            contact = None
            if c.contact_id:
                ct = await state.sales_store.get_contact(c.contact_id)
                if ct:
                    company = (
                        await state.sales_store.get_company(ct.company_id)
                        if ct.company_id else None
                    )
                    contact = {
                        "id": ct.id,
                        "first_name": ct.first_name,
                        "last_name": ct.last_name,
                        "email": ct.email,
                        "company_name": company.name if company else "",
                    }
            out.append({**c.model_dump(), "contact": contact})
        return {"cases": out, "count": len(out)}

    @router.get("/cases/counts")
    async def case_counts():
        counts = await state.case_service.pipeline_summary(tenant)
        return {"counts": counts}

    @router.get("/cases/{case_id}")
    async def get_case(case_id: int):
        case = await state.support_store.get_case(case_id)
        if not case or case.tenant != tenant:
            raise HTTPException(status_code=404, detail="Case not found")
        messages = await state.support_store.messages_for_case(case_id)
        contact = None
        if case.contact_id:
            ct = await state.sales_store.get_contact(case.contact_id)
            if ct:
                company = (
                    await state.sales_store.get_company(ct.company_id)
                    if ct.company_id else None
                )
                contact = {
                    "id": ct.id,
                    "first_name": ct.first_name,
                    "last_name": ct.last_name,
                    "email": ct.email,
                    "company_name": company.name if company else "",
                }
        return {
            "case": {**case.model_dump(), "contact": contact},
            "messages": [m.model_dump() for m in messages],
        }

    @router.post("/cases/{case_id}/reply")
    async def reply_case(case_id: int, body: ReplyCaseBody):
        msg = await state.case_service.reply(
            case_id=case_id,
            tenant=tenant,
            direction=CaseMessageDirection.OUTBOUND,
            body=body.body,
            subject=body.subject or "",
        )
        return {"ok": True, "message_id": msg.id}

    @router.post("/cases/{case_id}/resolve")
    async def resolve_case(case_id: int, body: ResolveCaseBody):
        case = await state.case_service.resolve(case_id, tenant, note=body.note)
        return {"ok": True, "case": case.model_dump()}

    @router.post("/cases/{case_id}/assign")
    async def assign_case(case_id: int, body: AssignCaseBody):
        case = await state.case_service.assign(case_id, tenant, body.assignee)
        return {"ok": True, "case": case.model_dump()}

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    @router.get("/analytics/funnel")
    async def analytics_funnel(
        _from: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
    ):
        from_dt = datetime.fromisoformat(_from) if _from else None
        to_dt = datetime.fromisoformat(to) if to else None
        return await funnel_metrics(
            state.sales_store, tenant=tenant, date_from=from_dt, date_to=to_dt
        )

    @router.get("/analytics/channels")
    async def analytics_channels(
        _from: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
    ):
        from_dt = datetime.fromisoformat(_from) if _from else None
        to_dt = datetime.fromisoformat(to) if to else None
        return await channel_metrics(
            state.sales_store, tenant=tenant, date_from=from_dt, date_to=to_dt
        )

    @router.get("/analytics/sequences")
    async def analytics_sequences(
        _from: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
    ):
        from_dt = datetime.fromisoformat(_from) if _from else None
        to_dt = datetime.fromisoformat(to) if to else None
        return await sequence_metrics(
            state.sales_store, tenant=tenant, date_from=from_dt, date_to=to_dt
        )

    # Merge auth routes (unprotected) + protected routes into single router
    final_router = APIRouter()
    final_router.include_router(auth_router)
    final_router.include_router(router)
    return final_router


def create_inbound_webhook_router(state: TenantAPIState) -> APIRouter:
    """Separate router for inbound webhooks (not under /api/crm/*)."""
    router = APIRouter()

    @router.post("/sendgrid-inbound")
    async def sendgrid_inbound(payload: dict[str, Any]):
        inbound = parse_sendgrid_webhook(payload)
        result = await state.inbound_router.handle(inbound, tenant=state.tenant_key)
        return result

    return router

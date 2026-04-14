"""Sovereign Tenant API — the shared REST contract every tenant backend implements.

Usage in tenant backend (e.g. atx-mats-ai):

    from fastapi import FastAPI
    from sovereign_swarm.sales_ops.store import SalesOpsStore
    from sovereign_swarm.support.store import SupportStore
    from sovereign_swarm.tenant_api import (
        TenantAPIState,
        create_tenant_api_router,
        create_inbound_webhook_router,
    )

    app = FastAPI()

    sales_store = SalesOpsStore(db_path="data/sales_ops.db")
    support_store = SupportStore(db_path="data/support.db")
    state = TenantAPIState(
        tenant_key="atx_mats",
        sales_store=sales_store,
        support_store=support_store,
    )

    app.include_router(create_tenant_api_router(state), prefix="/api/crm")
    app.include_router(create_inbound_webhook_router(state), prefix="/webhook")

    @app.on_event("startup")
    async def startup():
        await sales_store.initialize()
        await support_store.initialize()
"""

from sovereign_swarm.tenant_api.app import (
    TenantAPIState,
    create_inbound_webhook_router,
    create_tenant_api_router,
)

__all__ = [
    "TenantAPIState",
    "create_inbound_webhook_router",
    "create_tenant_api_router",
]

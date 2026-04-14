"""Funnel analytics — stage transition counts + conversion rates.

Reads from sales_ops contacts + opportunities + activities to compute:
- Contacts by stage (OpportunityStage enum)
- Stage-to-stage conversion rates
- Time-in-stage distribution
- Drop-off analysis

All metrics tenant-scoped.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.sales_ops.models import OpportunityStage
from sovereign_swarm.sales_ops.store import SalesOpsStore

logger = structlog.get_logger()

# Ordered stages for funnel display
FUNNEL_STAGES = [
    OpportunityStage.COLD,
    OpportunityStage.AWARE,
    OpportunityStage.ENGAGED,
    OpportunityStage.MQL,
    OpportunityStage.SQL,
    OpportunityStage.OPPORTUNITY,
    OpportunityStage.CLOSE,
    OpportunityStage.WON,
]


async def funnel_metrics(
    store: SalesOpsStore,
    tenant: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Compute funnel metrics for a tenant.

    Returns:
        {
            "stages": [{"stage": "cold", "count": 42, "conversion_from_prior_pct": null}, ...],
            "total_contacts": int,
            "total_won": int,
            "overall_conversion_pct": float,
            "date_from": iso,
            "date_to": iso,
        }
    """
    if date_to is None:
        date_to = datetime.utcnow()
    if date_from is None:
        date_from = date_to - timedelta(days=90)

    db = await store._conn()

    # Count contacts per stage (via opportunities latest stage)
    # If no opportunity exists for a contact, count them as "cold"
    sql = """
    SELECT
      COALESCE(latest_opp.stage, 'cold') AS stage,
      COUNT(DISTINCT c.id) AS contact_count
    FROM contacts c
    LEFT JOIN (
      SELECT contact_id, stage,
             ROW_NUMBER() OVER (PARTITION BY contact_id ORDER BY updated_at DESC) AS rn
      FROM opportunities
      WHERE tenant = ?
    ) latest_opp ON latest_opp.contact_id = c.id AND latest_opp.rn = 1
    WHERE c.tenant = ?
      AND c.unsubscribed = 0
      AND c.created_at >= ?
      AND c.created_at <= ?
    GROUP BY stage
    """

    params = [tenant, tenant, date_from.isoformat(), date_to.isoformat()]
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()

    counts_by_stage = {row[0]: row[1] for row in rows}

    # Build ordered stages with conversion rates
    stages_output: list[dict[str, Any]] = []
    prior_count: int | None = None
    total_contacts = 0

    for stage in FUNNEL_STAGES:
        count = counts_by_stage.get(stage.value, 0)
        total_contacts += count
        conversion = None
        if prior_count is not None and prior_count > 0:
            conversion = round((count / prior_count) * 100, 1)
        stages_output.append({
            "stage": stage.value,
            "count": count,
            "conversion_from_prior_pct": conversion,
        })
        prior_count = count if count > 0 else prior_count  # keep the denominator active

    total_won = counts_by_stage.get(OpportunityStage.WON.value, 0)
    top_count = stages_output[0]["count"] if stages_output else 0
    overall_conversion = (
        round((total_won / top_count) * 100, 1) if top_count else 0.0
    )

    return {
        "stages": stages_output,
        "total_contacts": total_contacts,
        "total_won": total_won,
        "overall_conversion_pct": overall_conversion,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }

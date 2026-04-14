"""Sequence analytics — per-template performance metrics."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.sales_ops.store import SalesOpsStore

logger = structlog.get_logger()


async def sequence_metrics(
    store: SalesOpsStore,
    tenant: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Compute per-sequence-template metrics.

    Returns:
        {
            "sequences": [
                {
                    "sequence_name": "atx_distributor",
                    "enrolled": 10,
                    "active": 5,
                    "paused": 3,
                    "completed": 1,
                    "exited": 1,
                    "reply_rate_pct": 30.0,
                },
                ...
            ]
        }
    """
    if date_to is None:
        date_to = datetime.utcnow()
    if date_from is None:
        date_from = date_to - timedelta(days=90)

    db = await store._conn()

    sql = """
    SELECT sequence_name, status, COUNT(*) as cnt
    FROM sequence_enrollments
    WHERE tenant = ?
      AND enrolled_at >= ?
      AND enrolled_at <= ?
    GROUP BY sequence_name, status
    """
    params = [tenant, date_from.isoformat(), date_to.isoformat()]

    # Aggregate
    by_seq: dict[str, dict[str, int]] = {}
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
        for row in rows:
            seq_name, status, cnt = row
            if seq_name not in by_seq:
                by_seq[seq_name] = {
                    "enrolled": 0,
                    "active": 0,
                    "paused": 0,
                    "completed": 0,
                    "exited": 0,
                }
            by_seq[seq_name]["enrolled"] += cnt
            if status in by_seq[seq_name]:
                by_seq[seq_name][status] += cnt

    # Reply rate: paused enrollments are often those that got a reply
    sequences_out: list[dict[str, Any]] = []
    for seq_name, counts in by_seq.items():
        enrolled = counts["enrolled"]
        paused = counts["paused"]
        reply_rate = round((paused / enrolled) * 100, 1) if enrolled else 0.0
        sequences_out.append({
            "sequence_name": seq_name,
            **counts,
            "reply_rate_pct": reply_rate,
        })

    sequences_out.sort(key=lambda x: x["enrolled"], reverse=True)

    return {
        "sequences": sequences_out,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }

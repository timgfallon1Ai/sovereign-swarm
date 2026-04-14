"""Channel analytics — performance by outbound channel."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.sales_ops.store import SalesOpsStore

logger = structlog.get_logger()


async def channel_metrics(
    store: SalesOpsStore,
    tenant: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Compute per-channel performance metrics.

    Returns:
        {
            "channels": [
                {
                    "channel": "email",
                    "sent": 150,
                    "opened": 42,
                    "clicked": 8,
                    "replied": 3,
                    "open_rate_pct": 28.0,
                    "reply_rate_pct": 2.0
                },
                ...
            ]
        }
    """
    if date_to is None:
        date_to = datetime.utcnow()
    if date_from is None:
        date_from = date_to - timedelta(days=30)

    db = await store._conn()

    sql = """
    SELECT channel,
           SUM(CASE WHEN type='email_sent' OR type='sms_sent' OR type='linkedin_message' OR type='call_attempted' THEN 1 ELSE 0 END) AS sent,
           SUM(CASE WHEN type='email_opened' THEN 1 ELSE 0 END) AS opened,
           SUM(CASE WHEN type='email_clicked' THEN 1 ELSE 0 END) AS clicked,
           SUM(CASE WHEN type='email_replied' OR type='sms_replied' THEN 1 ELSE 0 END) AS replied
    FROM activities
    WHERE tenant = ?
      AND occurred_at >= ?
      AND occurred_at <= ?
    GROUP BY channel
    """
    params = [tenant, date_from.isoformat(), date_to.isoformat()]

    channels_out: list[dict[str, Any]] = []
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
        for row in rows:
            channel, sent, opened, clicked, replied = row
            sent = sent or 0
            opened = opened or 0
            clicked = clicked or 0
            replied = replied or 0
            open_rate = round((opened / sent) * 100, 1) if sent else 0.0
            click_rate = round((clicked / sent) * 100, 1) if sent else 0.0
            reply_rate = round((replied / sent) * 100, 1) if sent else 0.0
            channels_out.append({
                "channel": channel or "unknown",
                "sent": sent,
                "opened": opened,
                "clicked": clicked,
                "replied": replied,
                "open_rate_pct": open_rate,
                "click_rate_pct": click_rate,
                "reply_rate_pct": reply_rate,
            })

    return {
        "channels": channels_out,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }

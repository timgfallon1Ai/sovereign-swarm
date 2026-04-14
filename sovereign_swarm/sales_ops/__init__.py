"""Sales Ops — CRM, sequencing, and approval queue for outbound sales.

Tenant-aware. Stage-for-approval default. Zero auto-send without human
in loop. Reuses communication/email.py for SendGrid delivery.
"""

from sovereign_swarm.sales_ops.agent import SalesOpsAgent

__all__ = ["SalesOpsAgent"]

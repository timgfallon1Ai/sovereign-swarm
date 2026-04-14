"""Sequence templates registry.

Import any sequence module to auto-register it. Tenant-specific sequences
live here; shared logic lives in `base.py`.
"""

from sovereign_swarm.sales_ops.sequences.base import (
    SequenceStep,
    SequenceTemplate,
    get_sequence,
    list_sequences,
    register_sequence,
    render_template,
)

# Import sequences to trigger registration side-effects
from sovereign_swarm.sales_ops.sequences import atx_distributor  # noqa: F401

__all__ = [
    "SequenceStep",
    "SequenceTemplate",
    "get_sequence",
    "list_sequences",
    "register_sequence",
    "render_template",
]

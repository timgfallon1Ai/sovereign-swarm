"""SequenceTemplate base class + registry.

A sequence is an ordered list of SequenceSteps. Each step has a channel,
a day_offset (relative to enrollment start), a subject/body template,
and optional content_generator for LLM-enhanced personalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sovereign_swarm.sales_ops.models import (
    Contact,
    MessageChannel,
)


@dataclass
class SequenceStep:
    """A single step in a sequence."""

    index: int
    day_offset: int  # days from enrollment start
    channel: MessageChannel
    subject_template: str = ""
    body_template: str = ""
    # Optional LLM-based content enhancement — takes (contact, brand, step) → (subject, body)
    content_generator: Callable[..., Any] | None = None
    # Steps 4+ typically require explicit approval (ROI/pricing asks)
    requires_explicit_approval: bool = False
    # Manual-only steps don't produce an auto-send message (e.g., "reminder: call them")
    manual_only: bool = False
    description: str = ""


@dataclass
class SequenceTemplate:
    """Abstract base: a sequence is an ordered list of steps."""

    name: str
    tenant: str  # which tenant this sequence applies to (or "*" for any)
    description: str
    steps: list[SequenceStep] = field(default_factory=list)

    def get_step(self, index: int) -> SequenceStep | None:
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None

    @property
    def length(self) -> int:
        return len(self.steps)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, SequenceTemplate] = {}


def register_sequence(template: SequenceTemplate) -> None:
    """Register a sequence template in the global registry."""
    _REGISTRY[template.name] = template


def get_sequence(name: str) -> SequenceTemplate | None:
    """Look up a sequence template by name."""
    return _REGISTRY.get(name)


def list_sequences(tenant: str | None = None) -> list[SequenceTemplate]:
    """List registered sequences, optionally filtered by tenant."""
    if tenant is None:
        return list(_REGISTRY.values())
    return [t for t in _REGISTRY.values() if t.tenant == tenant or t.tenant == "*"]


# ---------------------------------------------------------------------------
# Template rendering helpers
# ---------------------------------------------------------------------------


def render_template(template: str, contact: Contact, brand: Any | None = None) -> str:
    """Replace {first_name}, {last_name}, {company}, {role}, {tagline}, {one_liner}."""
    if not template:
        return ""

    company_name = ""
    # company_id lookup would require the store — caller can pre-hydrate this
    if hasattr(contact, "_company_name"):
        company_name = contact._company_name  # type: ignore

    replacements = {
        "{first_name}": contact.first_name or "there",
        "{last_name}": contact.last_name or "",
        "{full_name}": contact.full_name or "there",
        "{email}": contact.email or "",
        "{role}": contact.role or "your role",
        "{company}": company_name or "your company",
    }

    if brand is not None:
        replacements["{tagline}"] = getattr(brand, "tagline", "")
        replacements["{one_liner}"] = getattr(brand, "one_liner", "")
        replacements["{brand_name}"] = getattr(brand, "display_name", "")
        replacements["{brand_domain}"] = getattr(brand, "domain", "")

    out = template
    for token, value in replacements.items():
        out = out.replace(token, str(value))
    return out

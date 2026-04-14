"""Human-in-the-middle publish gate for inbound auto-replies.

Sits between the LLM's proposed reply and the outbound send channel.
Classifies each (inbound, proposed_reply, match) tuple into one of four
actions:

- SEND   — trusted sender or low-risk reply; send immediately
- DRAFT  — cold / unknown sender or reply contains commitment language;
           hold for Tim's review
- DROP   — detected spam / phishing; never send, optionally alert Tim
- MANUAL — high-stakes reply content (commits to meeting, seminar, deal);
           do NOT send without explicit human edit + approval

Built in response to the 2026-04-14 incident where GBB's AI auto-replied
as info@graciebarrabuda.com to:
- Ben from JitsOpenMats offering seminar promotion (AI said "we'd be
  interested in promoting")
- Austin Aguilar cold outreach x3
- Lisa Craft janitorial cold outreach x4
- PushPress gym software (AI invited them to bring their child to BJJ)
- Anderson/gymadmin.app (AI asked how old their child is)
- Hassan/Lion Leather cold outreach (boxing gloves MOQ)
- "MetaMask wallet suspended" phishing (confirmed live inbox to scammers)

v1 is heuristic-only — no LLM classifier. Fast, deterministic, auditable.
Upgrade path: add a Haiku classifier for borderline cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import structlog

from sovereign_swarm.inbound.matcher import InboundMatch
from sovereign_swarm.inbound.sendgrid_parser import InboundEmail

logger = structlog.get_logger()


class GateAction(str, Enum):
    SEND = "send"           # auto-send OK
    DRAFT = "draft"         # save for human review
    DROP = "drop"           # don't send, don't draft
    MANUAL = "manual"       # human MUST edit + approve — no auto-send ever


class GateTier(str, Enum):
    TRUSTED = "trusted"             # known customer, active relationship
    COLD_UNKNOWN = "cold_unknown"   # no prior contact
    COLD_MARKETING = "cold_marketing"  # cold outreach w/ marketing keywords
    SPAM = "spam"                   # automated mass marketing
    PHISHING = "phishing"           # likely phishing / scam
    HIGH_STAKES = "high_stakes"     # reply commits to something concrete


@dataclass
class PublishDecision:
    action: GateAction
    tier: GateTier
    reasons: list[str] = field(default_factory=list)
    notify_human: bool = False
    auto_skip_after_hours: int | None = None  # None = never auto-skip

    @property
    def should_send(self) -> bool:
        return self.action == GateAction.SEND

    def as_dict(self) -> dict:
        return {
            "action": self.action.value,
            "tier": self.tier.value,
            "reasons": self.reasons,
            "notify_human": self.notify_human,
            "auto_skip_after_hours": self.auto_skip_after_hours,
        }


# ---------------------------------------------------------------------------
# Detection heuristics
# ---------------------------------------------------------------------------

# Phishing indicators — subject or body. Tuned to the MetaMask incident
# and the common classes of scam (wallet seizure, invoice attached, reset).
_PHISHING_SUBJECT_PATTERNS = [
    re.compile(r"\b(wallet|account)\s+(will be\s+)?(suspend|freeze|lock|terminat|clos)", re.I),
    re.compile(r"unusual (sign.?in|activity|login)", re.I),
    re.compile(r"verify your (wallet|account|identity) (immediately|now|within)", re.I),
    re.compile(r"(reset|confirm) your password", re.I),
    re.compile(r"invoice (attached|overdue|due)", re.I),
    re.compile(r"(crypto|bitcoin|btc|eth|metamask|coinbase|trezor|ledger)", re.I),
    re.compile(r"\b(urgent|immediate) (action|attention) (required|needed)", re.I),
    re.compile(r"suspicious (activity|transaction|login)", re.I),
]

_PHISHING_DOMAIN_BLOCKLIST = {
    # Not real, but common impersonation patterns — extend over time
    "dukcapil.makassarkota.go.id",  # the MetaMask phish from the incident
}

# Marketing / spam signals — used when sender has no prior relationship
_MARKETING_BODY_PATTERNS = [
    re.compile(r"\bunsubscribe\b", re.I),
    re.compile(r"\bopt.?out\b", re.I),
    re.compile(r"\bview in browser\b", re.I),
    re.compile(r"helped .{3,60}\s+(and|&)\s+more", re.I),  # "Helped Freebirds, RAVE... & more" pattern
    re.compile(r"quick question about your", re.I),  # classic cold-outreach opener
    re.compile(r"no.?cost (estimate|quote|proposal)", re.I),
    re.compile(r"custom .{3,30} (MOQ|minimum order)", re.I),  # "Custom gloves MOQ 50"
    re.compile(r"(checkout|see) what's new", re.I),
    re.compile(r"\bless admin,? more\b", re.I),  # gymadmin.app pattern
]

_MARKETING_FROM_PATTERNS = [
    re.compile(r"(marketing|newsletter|campaigns?|team|no-?reply|hello|hi)@", re.I),
]

# Commitment language in the proposed reply — if the LLM is about to commit
# GBB to something, humans MUST approve. These are the exact phrases from
# the incident replies.
_COMMITMENT_PATTERNS = [
    # Match both "we'd love to X" and "we'd definitely be interested in X"
    re.compile(r"we['\u2019]?d\s+(love|definitely|be interested|like|be happy)", re.I),
    re.compile(r"we would\s+(love|definitely|be interested|like|be happy)", re.I),
    re.compile(r"happy to (meet|schedule|chat|discuss|hop on|jump on|partner|promote)", re.I),
    re.compile(r"i['\u2019]?d (love|like) to (meet|schedule|chat|discuss|hop on|jump on)", re.I),
    re.compile(r"looking forward to (meeting|seeing|connecting)", re.I),
    re.compile(r"let['\u2019]?s (schedule|set up|book|arrange|get on)", re.I),
    re.compile(r"you can (stop by|swing by|come by|visit)", re.I),
    # AI asking spam marketer's child's age (the Anderson/gymadmin.app case)
    re.compile(r"(how old|what age) is your", re.I),
    re.compile(r"free trial (class|lesson|session)", re.I),
    re.compile(r"book (a|the|your) (call|appointment|meeting|demo)", re.I),
    re.compile(r"attach(ed|ing) (is|the|our)", re.I),
    # Promoting / partnering language
    re.compile(r"interested in (promoting|partnering|working)", re.I),
]


def _looks_like_phishing(inbound: InboundEmail) -> tuple[bool, list[str]]:
    reasons = []
    subject = inbound.subject or ""
    for pat in _PHISHING_SUBJECT_PATTERNS:
        if pat.search(subject):
            reasons.append(f"phishing_pattern_subject:{pat.pattern}")
    domain = (inbound.from_email or "").split("@")[-1].lower()
    if domain and domain in _PHISHING_DOMAIN_BLOCKLIST:
        reasons.append(f"blocklisted_domain:{domain}")
    return bool(reasons), reasons


def _looks_like_marketing(inbound: InboundEmail) -> tuple[bool, list[str]]:
    reasons = []
    body = inbound.text_body or ""
    subject = inbound.subject or ""
    for pat in _MARKETING_BODY_PATTERNS:
        if pat.search(body) or pat.search(subject):
            reasons.append(f"marketing_pattern:{pat.pattern}")
    from_addr = inbound.from_email or ""
    for pat in _MARKETING_FROM_PATTERNS:
        if pat.search(from_addr):
            reasons.append(f"marketing_from:{pat.pattern}")
    return bool(reasons), reasons


def _reply_makes_commitment(proposed_reply: str) -> tuple[bool, list[str]]:
    reasons = []
    for pat in _COMMITMENT_PATTERNS:
        if pat.search(proposed_reply or ""):
            reasons.append(f"commitment_pattern:{pat.pattern}")
    return bool(reasons), reasons


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def decide(
    inbound: InboundEmail,
    proposed_reply: str,
    match: InboundMatch | None = None,
    *,
    allow_auto_reply_to_trusted: bool = True,
) -> PublishDecision:
    """Classify an inbound + proposed reply and return a gate decision.

    Priority (first match wins):
    1. Phishing → DROP, notify Tim
    2. Reply makes a concrete commitment → MANUAL (never auto-send)
    3. Sender matches known contact → SEND (if allowed) or DRAFT
    4. Marketing / cold outreach patterns → DRAFT, no notify, auto-skip 72h
    5. Unknown sender (no match, no marketing signal) → DRAFT, notify
    6. (fallback) DRAFT, notify
    """
    reasons_bucket: list[str] = []

    # 1. Phishing check — highest priority
    is_phish, phish_reasons = _looks_like_phishing(inbound)
    if is_phish:
        reasons_bucket.extend(phish_reasons)
        return PublishDecision(
            action=GateAction.DROP,
            tier=GateTier.PHISHING,
            reasons=reasons_bucket,
            notify_human=True,
            auto_skip_after_hours=None,
        )

    # 2. Commitment language check — the LLM is about to commit us to
    #    something concrete. No auto-send, ever.
    commits, commit_reasons = _reply_makes_commitment(proposed_reply)
    if commits:
        reasons_bucket.extend(commit_reasons)
        return PublishDecision(
            action=GateAction.MANUAL,
            tier=GateTier.HIGH_STAKES,
            reasons=reasons_bucket,
            notify_human=True,
            auto_skip_after_hours=None,
        )

    # 3. Trusted sender — known contact in the CRM
    is_trusted = match is not None and match.has_match
    if is_trusted and allow_auto_reply_to_trusted:
        reasons_bucket.append(f"trusted_contact:{match.matched_via}")
        return PublishDecision(
            action=GateAction.SEND,
            tier=GateTier.TRUSTED,
            reasons=reasons_bucket,
            notify_human=False,
            auto_skip_after_hours=None,
        )

    # 4. Marketing / cold outreach signals
    is_marketing, mkt_reasons = _looks_like_marketing(inbound)
    if is_marketing:
        reasons_bucket.extend(mkt_reasons)
        return PublishDecision(
            action=GateAction.DRAFT,
            tier=GateTier.COLD_MARKETING,
            reasons=reasons_bucket,
            notify_human=False,              # don't spam Tim with these
            auto_skip_after_hours=72,
        )

    # 5. Unknown sender, no clear signal — draft + notify
    if not is_trusted:
        reasons_bucket.append("unknown_sender")
        return PublishDecision(
            action=GateAction.DRAFT,
            tier=GateTier.COLD_UNKNOWN,
            reasons=reasons_bucket,
            notify_human=True,
            auto_skip_after_hours=168,  # 7 days
        )

    # 6. Fallback — trusted contact but auto_reply disabled at tenant level
    reasons_bucket.append("policy_review_required")
    return PublishDecision(
        action=GateAction.DRAFT,
        tier=GateTier.TRUSTED,
        reasons=reasons_bucket,
        notify_human=True,
        auto_skip_after_hours=None,
    )

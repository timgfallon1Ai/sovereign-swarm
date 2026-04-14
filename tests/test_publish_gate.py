"""Tests for the inbound publish gate.

Each incident from 2026-04-14 is a test case. If any of these regress,
we'll know before the AI auto-replies to another spam marketer.
"""

from __future__ import annotations

from sovereign_swarm.inbound.matcher import InboundMatch
from sovereign_swarm.inbound.publish_gate import (
    GateAction,
    GateTier,
    PublishDecision,
    decide,
)
from sovereign_swarm.inbound.sendgrid_parser import InboundEmail
from sovereign_swarm.sales_ops.models import Contact


def _email(
    from_email: str = "stranger@example.com",
    from_name: str = "Stranger",
    subject: str = "Inquiry",
    text_body: str = "Hi, just a normal email.",
) -> InboundEmail:
    return InboundEmail(
        from_email=from_email,
        from_name=from_name,
        to_emails=["info@graciebarrabuda.com"],
        subject=subject,
        text_body=text_body,
    )


def _contact(email: str = "known@customer.com") -> Contact:
    return Contact(
        tenant="gbb",
        id=1,
        first_name="Known",
        last_name="Customer",
        email=email,
        phone="",
        role="",
        company_name="",
    )


# ---------------------------------------------------------------------------
# PHISHING — 2026-04-03 MetaMask "wallet will be suspended"
# ---------------------------------------------------------------------------


def test_metamask_phish_is_dropped_and_notifies():
    inbound = _email(
        from_email="support@dukcapil.makassarkota.go.id",
        from_name="MetaMask",
        subject="Your MetaMask wallet will be suspended.",
        text_body="Verify your wallet immediately.",
    )
    reply = "Hi there, thanks for reaching out! How can I help you today?"
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.DROP
    assert decision.tier == GateTier.PHISHING
    assert decision.notify_human is True


def test_blocklisted_domain_triggers_phishing():
    inbound = _email(from_email="any@dukcapil.makassarkota.go.id", subject="hi")
    decision = decide(inbound, "Thanks for reaching out!", match=None)
    assert decision.action == GateAction.DROP
    assert decision.tier == GateTier.PHISHING


def test_generic_crypto_phish_is_dropped():
    inbound = _email(
        from_email="noreply@scam.biz",
        subject="Bitcoin wallet will be frozen — verify now",
    )
    decision = decide(inbound, "Hi! How can I help?", match=None)
    assert decision.action == GateAction.DROP
    assert decision.tier == GateTier.PHISHING


# ---------------------------------------------------------------------------
# COMMITMENT LANGUAGE — 2026-04-14 Ben/JitsOpenMats incident
# ---------------------------------------------------------------------------


def test_commitment_reply_to_cold_sender_goes_manual():
    inbound = _email(
        from_email="jitsopenmats@gmail.com",
        from_name="Ben from JitsOpenMats",
        subject="Quick question about your gym",
        text_body="We help BJJ gyms promote their seminars. Want to partner?",
    )
    reply = (
        "Hi Ben,\n\nThanks for reaching out about JitsOpenMats! We'd "
        "definitely be interested in promoting our upcoming seminars..."
    )
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.MANUAL
    assert decision.tier == GateTier.HIGH_STAKES
    assert decision.notify_human is True
    assert any("commitment_pattern" in r for r in decision.reasons)


def test_asking_spammer_about_their_child_goes_manual():
    # The AI replied to Anderson/gymadmin.app asking how old their child is
    inbound = _email(
        from_email="anderson@gymadmin.app",
        subject="Less admin, more rolling 🥋",
        text_body="Our Gym Admin app helps BJJ academies...",
    )
    reply = "Hi Anderson! How old is your child? Our kids classes are..."
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.MANUAL


def test_schedule_commitment_goes_manual():
    inbound = _email(from_email="new@person.com", subject="Question")
    reply = "Happy to schedule a call this week — let me know what works!"
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.MANUAL


# ---------------------------------------------------------------------------
# MARKETING / COLD OUTREACH — Lisa Craft janitorial pattern, Austin Aguilar
# ---------------------------------------------------------------------------


def test_no_cost_estimate_drafts_no_notify():
    inbound = _email(
        from_email="lisacraft006@gmail.com",
        from_name="Lisa Craft",
        subject="No-Cost Janitorial Estimate - Gracie Barra",
        text_body="We offer no-cost estimates for commercial cleaning...",
    )
    reply = "Hi Lisa, we're satisfied with our current arrangements. Thanks!"
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.DRAFT
    assert decision.tier == GateTier.COLD_MARKETING
    assert decision.notify_human is False  # don't spam Tim with these
    assert decision.auto_skip_after_hours == 72


def test_helped_brands_pattern_drafts():
    # austin@email.austinaguilar.biz — "Helped Freebirds, RAVE... wanted to say hi"
    inbound = _email(
        from_email="austin@email.austinaguilar.biz",
        subject="Helped Freebirds, RAVE Restaurant Group & more — wanted to say hi",
    )
    reply = "Thanks for reaching out!"
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.DRAFT
    assert decision.tier == GateTier.COLD_MARKETING


def test_quick_question_cold_opener_drafts():
    # Ben's opener was "Quick question about your gym"
    inbound = _email(
        from_email="random@somewhere.com",
        subject="Quick question about your gym",
        text_body="I was wondering...",
    )
    reply = "Hi! Thanks for reaching out. We offer..."
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.DRAFT
    assert decision.tier == GateTier.COLD_MARKETING


def test_unsubscribe_link_drafts():
    inbound = _email(
        from_email="marketing@pushpress.com",
        subject="What's new in PushPress - March '26",
        text_body="Newsletter content here... Unsubscribe: http://...",
    )
    reply = "Thanks for the update!"
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.DRAFT
    assert decision.tier == GateTier.COLD_MARKETING


# ---------------------------------------------------------------------------
# TRUSTED — known customer replying to an ongoing thread
# ---------------------------------------------------------------------------


def test_known_customer_factual_reply_is_sent():
    inbound = _email(
        from_email="known@customer.com",
        subject="Re: Class schedule",
        text_body="Thanks, that helps. Is the 6pm full on Monday?",
    )
    reply = "No — Monday 6pm has room. See you there."  # no commitment phrases
    match = InboundMatch(contact=_contact(), matched_via="email")
    decision = decide(inbound, reply, match=match)
    assert decision.action == GateAction.SEND
    assert decision.tier == GateTier.TRUSTED


def test_known_customer_but_reply_commits_still_goes_manual():
    """Even for trusted senders, commitment language requires review."""
    inbound = _email(from_email="known@customer.com", subject="Re: quick q")
    reply = "Happy to schedule a call with you tomorrow!"
    match = InboundMatch(contact=_contact(), matched_via="email")
    decision = decide(inbound, reply, match=match)
    assert decision.action == GateAction.MANUAL


# ---------------------------------------------------------------------------
# UNKNOWN SENDER, no clear marketing signal
# ---------------------------------------------------------------------------


def test_unknown_sender_low_risk_reply_drafts_and_notifies():
    inbound = _email(
        from_email="newperson@gmail.com",
        subject="Question about trial",
        text_body="Hey, what's the cost for a trial class?",
    )
    reply = "Trial classes are complimentary. Details are on our site."
    decision = decide(inbound, reply, match=None)
    assert decision.action == GateAction.DRAFT
    assert decision.tier == GateTier.COLD_UNKNOWN
    assert decision.notify_human is True
    assert decision.auto_skip_after_hours == 168


# ---------------------------------------------------------------------------
# should_send convenience
# ---------------------------------------------------------------------------


def test_should_send_only_true_for_SEND():
    assert PublishDecision(action=GateAction.SEND, tier=GateTier.TRUSTED).should_send is True
    assert PublishDecision(action=GateAction.DRAFT, tier=GateTier.COLD_UNKNOWN).should_send is False
    assert PublishDecision(action=GateAction.DROP, tier=GateTier.PHISHING).should_send is False
    assert PublishDecision(action=GateAction.MANUAL, tier=GateTier.HIGH_STAKES).should_send is False

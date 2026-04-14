"""ATX Mats distributor outreach — 28-touchpoint B2B sequence.

Maps the CMO funnel architecture to concrete touchpoints for ATX Mats
targeting facility managers, commercial builders, OEM buyers, and
distributor principals in the commercial/industrial flooring space.

Steps 1-3: Low-risk intro (LinkedIn connect, intro email, quick reply)
           — can be auto-approved in bulk by Tim with --all-safe flag.
Steps 4+ : Require explicit per-message approval (ROI, pricing, SMS).
"""

from __future__ import annotations

from sovereign_swarm.sales_ops.models import MessageChannel
from sovereign_swarm.sales_ops.sequences.base import (
    SequenceStep,
    SequenceTemplate,
    register_sequence,
)


def _build() -> SequenceTemplate:
    steps: list[SequenceStep] = []

    # --- STAGE 1: AWARE → ENGAGED (touchpoints 1-6) ---

    steps.append(SequenceStep(
        index=0, day_offset=0,
        channel=MessageChannel.LINKEDIN,
        subject_template="",
        body_template=(
            "Hi {first_name} — saw your work at {company}. I run ATX Mats "
            "(commercial flooring, Austin + Shanghai OEM). Not pitching — "
            "would love to connect and trade notes on facility ops."
        ),
        description="T1: LinkedIn connection request",
    ))

    steps.append(SequenceStep(
        index=1, day_offset=2,
        channel=MessageChannel.EMAIL,
        subject_template="Quick question on {company}'s flooring spec",
        body_template=(
            "Hi {first_name},\n\n"
            "Tim Fallon here from ATX Mats. No pitch — just a quick question.\n\n"
            "Most {role}s we talk to at facilities like {company} are forced "
            "to choose between cheap mats that fail in 6 months or premium "
            "specs they can't afford to redo every 18 months.\n\n"
            "Is that pattern familiar at your site, or have you already "
            "solved it?\n\n"
            "Tim\n"
            "{brand_domain}"
        ),
        description="T2: Cold email #1 — pain-point hook",
    ))

    steps.append(SequenceStep(
        index=2, day_offset=4,
        channel=MessageChannel.LINKEDIN,
        subject_template="",
        body_template=(
            "Thanks for connecting, {first_name}. I dropped a note on your "
            "email — no pressure to reply there, but curious if the "
            "durability-vs-budget tension is a real issue at {company}."
        ),
        description="T3: LinkedIn message #1 — reference the email",
    ))

    steps.append(SequenceStep(
        index=3, day_offset=6,
        channel=MessageChannel.EMAIL,
        subject_template="How Davis Flooring cut mat replacement cost 40%",
        body_template=(
            "Hi {first_name},\n\n"
            "Short case: Davis Flooring had $180K/yr in mat replacements "
            "across 12 sites. We spec'd our heavy-duty rubber mat to their "
            "exact load ratings — they're 2 years in, zero replacements, "
            "$110K saved annualized.\n\n"
            "Spec sheet + the SGS compliance test results attached. If you "
            "want a sample panel for {company}, I can ship one this week.\n\n"
            "Tim\n"
            "{brand_domain}"
        ),
        requires_explicit_approval=True,
        description="T4: Cold email #2 — social proof + offer sample",
    ))

    steps.append(SequenceStep(
        index=4, day_offset=8,
        channel=MessageChannel.CALL,
        subject_template="Call attempt #1",
        body_template=(
            "Call {first_name} at {company}. Reference: Davis case study, "
            "anti-fatigue / industrial flooring. Goal: 15-min discovery."
        ),
        manual_only=True,
        description="T5: Phone call attempt #1 (manual)",
    ))

    steps.append(SequenceStep(
        index=5, day_offset=10,
        channel=MessageChannel.EMAIL,
        subject_template="Cost-per-slip math for {company}",
        body_template=(
            "Hi {first_name},\n\n"
            "Ran the numbers on a site your size:\n\n"
            "• Avg slip/fall claim: $48K per incident (NSC 2024 data)\n"
            "• Anti-fatigue mat upgrade cost: ~$18K for a 20K sqft footprint\n"
            "• Break-even: one prevented incident\n\n"
            "Happy to run the specifics for {company} if you share square "
            "footage and current mat spec.\n\n"
            "Tim"
        ),
        requires_explicit_approval=True,
        description="T6: Cold email #3 — ROI angle",
    ))

    # --- STAGE 2: ENGAGED → MQL (touchpoints 7-12) ---

    steps.append(SequenceStep(
        index=6, day_offset=12,
        channel=MessageChannel.LINKEDIN,
        subject_template="",
        body_template=(
            "Hi {first_name} — shared a post on OSHA slip-fall trends this "
            "morning that's getting traction with other {role}s. Worth a "
            "look: https://atxmats.com/insights"
        ),
        description="T7: LinkedIn message #2 — share relevant content",
    ))

    steps.append(SequenceStep(
        index=7, day_offset=14,
        channel=MessageChannel.CALL,
        subject_template="Call attempt #2 + voicemail",
        body_template=(
            "Second attempt. If VM: leave 20-sec message referencing the "
            "cost-per-slip math email. End with: 'tim@atxmats.com or "
            "512-XXX-XXXX — easier to text.'"
        ),
        manual_only=True,
        description="T8: Phone call #2 + voicemail",
    ))

    steps.append(SequenceStep(
        index=8, day_offset=17,
        channel=MessageChannel.EMAIL,
        subject_template="Last note from me (unless you want to keep talking)",
        body_template=(
            "Hi {first_name},\n\n"
            "I've reached out a few times — don't want to be a pest.\n\n"
            "If flooring isn't top of mind, no worries. If it's on your Q3 "
            "list, reply with 'Q3' and I'll circle back then.\n\n"
            "Otherwise, I'll close out the file.\n\n"
            "Tim"
        ),
        requires_explicit_approval=True,
        description="T9: Email #4 — breakup / last-try",
    ))

    steps.append(SequenceStep(
        index=9, day_offset=21,
        channel=MessageChannel.SMS,
        subject_template="",
        body_template=(
            "{first_name}, Tim @ ATX Mats. Sent you the ROI math on flooring "
            "for {company}. One-line reply (even 'no') closes the loop for me. "
            "Reply STOP to opt out."
        ),
        requires_explicit_approval=True,
        description="T10: SMS re-engagement (consented only)",
    ))

    steps.append(SequenceStep(
        index=10, day_offset=24,
        channel=MessageChannel.EMAIL,
        subject_template="One more: {company} hiring / growth signal",
        body_template=(
            "Hi {first_name} — saw {company} is [TRIGGER EVENT: hiring / "
            "expanding / new location]. Usually means facility planning "
            "conversations are happening. If flooring is in scope, I can "
            "run a 10-min spec review this week.\n\n"
            "Tim"
        ),
        requires_explicit_approval=True,
        description="T11: Email #5 — trigger-based re-engage",
    ))

    steps.append(SequenceStep(
        index=11, day_offset=28,
        channel=MessageChannel.EMAIL,
        subject_template="Final follow-up",
        body_template=(
            "Hi {first_name} — last note. I'm closing the file on this thread "
            "but wanted to leave the door open. If you're ever spec'ing "
            "industrial flooring at {company} or anywhere else, I'm "
            "tim@atxmats.com.\n\nAll best,\nTim"
        ),
        description="T12: Final close",
    ))

    # --- STAGE 3: MQL → SQL (steps 13-18) — only fire if engaged ---
    # These run if a prior step got a reply. Reply detection triggers a
    # pause + human review before advancing. These are here as scaffold.

    steps.append(SequenceStep(
        index=12, day_offset=35,
        channel=MessageChannel.EMAIL,
        subject_template="Sample panel for {company}?",
        body_template=(
            "Hi {first_name} — thanks for the reply. Standard next step: "
            "ship you a 2x3' sample panel of our heavy-duty rubber (the "
            "spec Davis uses). Free, no obligation. Street address?"
        ),
        requires_explicit_approval=True,
        description="T13: Sample panel offer (post-engagement)",
    ))

    steps.append(SequenceStep(
        index=13, day_offset=42,
        channel=MessageChannel.EMAIL,
        subject_template="Sample landed — how's it holding up?",
        body_template=(
            "Hi {first_name} — sample should've arrived. How's it feel? "
            "Common feedback: '{brand_name} is heavier than expected' — "
            "that's the 8mm backing doing its job.\n\n"
            "Want to run a 30-day test on one high-traffic area at {company}?"
        ),
        requires_explicit_approval=True,
        description="T14: Post-sample follow-up",
    ))

    steps.append(SequenceStep(
        index=14, day_offset=49,
        channel=MessageChannel.CALL,
        subject_template="Discovery call",
        body_template=(
            "Schedule 15-min discovery call with {first_name}. Cover: "
            "current vendor, pain points, sqft, timeline, budget authority."
        ),
        manual_only=True,
        description="T15: Discovery call (scheduled)",
    ))

    steps.append(SequenceStep(
        index=15, day_offset=56,
        channel=MessageChannel.EMAIL,
        subject_template="Quote attached — {company} flooring spec",
        body_template=(
            "Hi {first_name},\n\nQuote attached per our call.\n\n"
            "Summary:\n"
            "• [SQFT] sqft of [SPEC]\n"
            "• Total: $[PRICE]\n"
            "• Lead time: 4-6 weeks from PO\n"
            "• Warranty: 10 years\n\n"
            "Questions? Happy to hop on a call.\n\nTim"
        ),
        requires_explicit_approval=True,
        description="T16: Formal quote sent",
    ))

    steps.append(SequenceStep(
        index=15, day_offset=63,
        channel=MessageChannel.EMAIL,
        subject_template="Quote follow-up",
        body_template=(
            "Hi {first_name} — checking in on the quote. Any questions or "
            "changes needed? I can hold the pricing for 30 days if you need "
            "more time for internal approvals."
        ),
        requires_explicit_approval=True,
        description="T17: Quote follow-up",
    ))

    steps.append(SequenceStep(
        index=16, day_offset=70,
        channel=MessageChannel.MANUAL,
        subject_template="Executive sponsor outreach",
        body_template=(
            "Identify VP Operations or CFO at {company}. Tim sends a brief "
            "executive-to-executive note referencing the pending quote with "
            "{first_name}."
        ),
        manual_only=True,
        requires_explicit_approval=True,
        description="T18: Executive sponsor",
    ))

    # --- STAGE 4: CLOSE → ONBOARD → EXPAND (steps 19-28) ---

    steps.append(SequenceStep(
        index=17, day_offset=77,
        channel=MessageChannel.EMAIL,
        subject_template="Contract + next steps",
        body_template=(
            "Hi {first_name} — attached is the PO / contract per our terms. "
            "Once signed, we'll kick off production. I'll be your point of "
            "contact through installation.\n\nTim"
        ),
        requires_explicit_approval=True,
        description="T19: Contract sent",
    ))

    steps.append(SequenceStep(
        index=18, day_offset=84,
        channel=MessageChannel.EMAIL,
        subject_template="Welcome to ATX Mats",
        body_template=(
            "Hi {first_name},\n\n"
            "Order confirmed. Production kickoff Monday. You'll get a "
            "tracking link once shipped.\n\n"
            "Installation checklist + spec sheet attached.\n\nTim"
        ),
        description="T20: Onboarding welcome",
    ))

    steps.append(SequenceStep(
        index=19, day_offset=91,
        channel=MessageChannel.EMAIL,
        subject_template="Installation check-in",
        body_template=(
            "Hi {first_name} — mats should be installed by now. How's "
            "everything looking? Any issues to flag?"
        ),
        description="T21: Day-7 install check-in",
    ))

    steps.append(SequenceStep(
        index=20, day_offset=120,
        channel=MessageChannel.EMAIL,
        subject_template="Quick favor",
        body_template=(
            "Hi {first_name} — mats have been in for ~30 days. If you're "
            "happy, a quick Google review would mean the world. Link: "
            "https://atxmats.com/review\n\nTim"
        ),
        description="T22: 30-day review request",
    ))

    steps.append(SequenceStep(
        index=21, day_offset=180,
        channel=MessageChannel.EMAIL,
        subject_template="6-month check-in: how's the flooring holding up?",
        body_template=(
            "Hi {first_name} — six months in. Most customers see zero "
            "degradation by now. Want to confirm you're seeing the same?\n\n"
            "Also — if you have any other sites or upcoming projects, "
            "happy to spec them out.\n\nTim"
        ),
        description="T23: 6-month health check",
    ))

    steps.append(SequenceStep(
        index=22, day_offset=210,
        channel=MessageChannel.EMAIL,
        subject_template="New anti-fatigue line for {role}s",
        body_template=(
            "Hi {first_name} — launching a new ergonomic line specifically "
            "for [ROLE-RELEVANT USE CASE]. Thought of you. 10% early-access "
            "pricing for existing customers. Specs attached.\n\nTim"
        ),
        requires_explicit_approval=True,
        description="T24: Expansion / upsell",
    ))

    steps.append(SequenceStep(
        index=23, day_offset=240,
        channel=MessageChannel.EMAIL,
        subject_template="Referral ask",
        body_template=(
            "Hi {first_name} — who else in your network is dealing with the "
            "same flooring challenges? Happy to pay a $500 referral bonus "
            "or donate equivalent to a charity of your choice for any intro "
            "that turns into a customer."
        ),
        requires_explicit_approval=True,
        description="T25: Referral ask",
    ))

    steps.append(SequenceStep(
        index=24, day_offset=270,
        channel=MessageChannel.MANUAL,
        subject_template="Account QBR",
        body_template=(
            "Schedule quarterly business review with {first_name}. Cover: "
            "satisfaction, upcoming projects, roadmap preview, expansion "
            "opportunities."
        ),
        manual_only=True,
        description="T26: Quarterly business review",
    ))

    steps.append(SequenceStep(
        index=25, day_offset=300,
        channel=MessageChannel.EMAIL,
        subject_template="ATX Mats distributor program",
        body_template=(
            "Hi {first_name} — given your position in the market, wanted to "
            "ask if you'd be interested in our distributor program. Exclusive "
            "territory, 30% margin, co-marketing funds. Worth 15 min?"
        ),
        requires_explicit_approval=True,
        description="T27: Distributor upgrade offer",
    ))

    steps.append(SequenceStep(
        index=26, day_offset=365,
        channel=MessageChannel.EMAIL,
        subject_template="1-year anniversary",
        body_template=(
            "Hi {first_name} — been a year since we first worked together. "
            "Mats should still look new. If they do, I'd love to feature "
            "{company} in a case study (with your approval). If anything's "
            "off, tell me now so we can fix it.\n\nTim"
        ),
        description="T28: Anniversary / case study ask",
    ))

    # Renumber indices sequentially in case there are duplicates above
    for i, s in enumerate(steps):
        s.index = i

    return SequenceTemplate(
        name="atx_distributor",
        tenant="atx_mats",
        description="28-touchpoint B2B outreach for commercial flooring distributors",
        steps=steps,
    )


SEQUENCE = _build()
register_sequence(SEQUENCE)

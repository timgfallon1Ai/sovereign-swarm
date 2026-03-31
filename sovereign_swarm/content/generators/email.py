"""Email sequence generator for multi-step campaigns."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class SequenceType(str, Enum):
    WELCOME = "welcome"
    RE_ENGAGEMENT = "re_engagement"
    WIN_BACK = "win_back"
    ONBOARDING = "onboarding"
    NURTURE = "nurture"
    PROMOTIONAL = "promotional"


@dataclass
class EmailStep:
    """A single email in a sequence."""

    step_number: int
    subject_line: str
    body: str
    cta_text: str
    cta_url: str = ""
    send_delay_days: int = 0  # days after previous email
    notes: str = ""


@dataclass
class EmailSequence:
    """A multi-step email campaign."""

    name: str
    sequence_type: SequenceType
    emails: list[EmailStep] = field(default_factory=list)
    target_audience: str = ""
    goal: str = ""


# ------------------------------------------------------------------
# Templates for each sequence type
# ------------------------------------------------------------------

_WELCOME_TEMPLATES: list[dict[str, Any]] = [
    {
        "subject": "Welcome to {brand} -- here's what to expect",
        "body": (
            "Hi {name},\n\n"
            "Welcome aboard! We're thrilled to have you.\n\n"
            "Here's what you can expect over the next few days:\n"
            "- A quick-start guide to get you up and running\n"
            "- Tips from our most successful users\n"
            "- A special offer just for new members\n\n"
            "If you have any questions, just reply to this email.\n\n"
            "Best,\n{brand} Team"
        ),
        "cta": "Get Started",
        "delay": 0,
    },
    {
        "subject": "Quick tip: Get the most out of {brand}",
        "body": (
            "Hi {name},\n\n"
            "Now that you've had a chance to look around, here's a pro tip "
            "that our best users swear by:\n\n"
            "[Top feature or workflow tip]\n\n"
            "Try it out today and see the difference.\n\n"
            "Cheers,\n{brand} Team"
        ),
        "cta": "Try It Now",
        "delay": 2,
    },
    {
        "subject": "Your exclusive welcome offer inside",
        "body": (
            "Hi {name},\n\n"
            "As a thank you for joining {brand}, we'd like to offer you "
            "something special:\n\n"
            "[Special offer details]\n\n"
            "This offer expires in 48 hours, so don't wait!\n\n"
            "Best,\n{brand} Team"
        ),
        "cta": "Claim Your Offer",
        "delay": 5,
    },
]

_RE_ENGAGEMENT_TEMPLATES: list[dict[str, Any]] = [
    {
        "subject": "We miss you, {name}!",
        "body": (
            "Hi {name},\n\n"
            "It's been a while since we've seen you. We wanted to check in "
            "and let you know about some exciting updates:\n\n"
            "[Recent improvements or new features]\n\n"
            "Come back and see what's new!\n\n"
            "Best,\n{brand} Team"
        ),
        "cta": "See What's New",
        "delay": 0,
    },
    {
        "subject": "A special something just for you",
        "body": (
            "Hi {name},\n\n"
            "We know life gets busy. To make it easy to come back, "
            "we've prepared something special for you:\n\n"
            "[Re-engagement offer or incentive]\n\n"
            "We'd love to have you back.\n\n"
            "Cheers,\n{brand} Team"
        ),
        "cta": "Come Back",
        "delay": 3,
    },
]

_WIN_BACK_TEMPLATES: list[dict[str, Any]] = [
    {
        "subject": "It's not goodbye, is it?",
        "body": (
            "Hi {name},\n\n"
            "We noticed you haven't been around lately and we'd hate to "
            "see you go.\n\n"
            "Is there anything we can do better? We're always improving "
            "based on feedback from people like you.\n\n"
            "Reply to this email and let us know.\n\n"
            "Best,\n{brand} Team"
        ),
        "cta": "Share Feedback",
        "delay": 0,
    },
    {
        "subject": "Last chance: {brand} special offer",
        "body": (
            "Hi {name},\n\n"
            "Before we part ways, we wanted to extend one final offer:\n\n"
            "[Win-back offer -- discount, free month, etc.]\n\n"
            "This is our way of saying we value your business.\n\n"
            "Best,\n{brand} Team"
        ),
        "cta": "Accept Offer",
        "delay": 5,
    },
]


class EmailSequenceGenerator:
    """Creates multi-step email sequences.

    Supports welcome series, re-engagement, win-back, and custom sequences.
    Each email includes subject line, body, CTA, and send timing.
    """

    def __init__(self, anthropic_client: Any | None = None) -> None:
        self._client = anthropic_client

    async def generate(
        self,
        sequence_type: SequenceType | str,
        brand: str = "Our Company",
        audience: str = "customers",
        goal: str = "",
        num_emails: int | None = None,
    ) -> EmailSequence:
        """Generate an email sequence of the given type."""
        if isinstance(sequence_type, str):
            sequence_type = SequenceType(sequence_type)

        templates = self._get_templates(sequence_type)
        if num_emails:
            templates = templates[:num_emails]

        emails: list[EmailStep] = []
        for i, tpl in enumerate(templates, 1):
            emails.append(
                EmailStep(
                    step_number=i,
                    subject_line=tpl["subject"].format(brand=brand, name="{name}"),
                    body=tpl["body"].format(brand=brand, name="{name}"),
                    cta_text=tpl["cta"],
                    send_delay_days=tpl["delay"],
                )
            )

        return EmailSequence(
            name=f"{sequence_type.value.replace('_', ' ').title()} Series",
            sequence_type=sequence_type,
            emails=emails,
            target_audience=audience,
            goal=goal or f"Drive engagement via {sequence_type.value} emails",
        )

    def _get_templates(self, seq_type: SequenceType) -> list[dict[str, Any]]:
        """Return template list for a given sequence type."""
        mapping = {
            SequenceType.WELCOME: _WELCOME_TEMPLATES,
            SequenceType.RE_ENGAGEMENT: _RE_ENGAGEMENT_TEMPLATES,
            SequenceType.WIN_BACK: _WIN_BACK_TEMPLATES,
        }
        # Fallback to welcome for types without dedicated templates
        return mapping.get(seq_type, _WELCOME_TEMPLATES)

    def format_sequence_markdown(self, sequence: EmailSequence) -> str:
        """Format an email sequence as readable markdown."""
        lines = [
            f"## {sequence.name}",
            f"**Type:** {sequence.sequence_type.value}",
            f"**Audience:** {sequence.target_audience}",
            f"**Goal:** {sequence.goal}",
            f"**Emails:** {len(sequence.emails)}",
            "",
        ]
        for email in sequence.emails:
            delay_note = (
                f"Send {email.send_delay_days} day(s) after previous"
                if email.send_delay_days > 0
                else "Send immediately"
            )
            lines.extend([
                f"### Email #{email.step_number} -- {delay_note}",
                f"**Subject:** {email.subject_line}",
                "",
                email.body,
                "",
                f"**CTA:** [{email.cta_text}]",
                "---",
                "",
            ])
        return "\n".join(lines)

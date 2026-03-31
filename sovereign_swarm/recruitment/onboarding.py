"""Onboarding checklist management by role."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.recruitment.models import (
    OnboardingChecklist,
    OnboardingItem,
    OnboardingItemStatus,
)

logger = structlog.get_logger()


# ------------------------------------------------------------------
# Standard onboarding items (common to all roles)
# ------------------------------------------------------------------

_STANDARD_ITEMS: list[dict[str, str]] = [
    {"name": "Complete employment paperwork (W-4, I-9, direct deposit)", "category": "paperwork"},
    {"name": "Sign employee handbook acknowledgment", "category": "paperwork"},
    {"name": "Sign NDA / non-compete (if applicable)", "category": "paperwork"},
    {"name": "Set up company email account", "category": "access"},
    {"name": "Set up Slack / communication tools access", "category": "access"},
    {"name": "Provide building / facility key or access card", "category": "access"},
    {"name": "Set up scheduling system access", "category": "access"},
    {"name": "Orientation with manager (company overview, values, expectations)", "category": "training"},
    {"name": "Tour of facility and introductions", "category": "training"},
    {"name": "Review safety procedures and emergency protocols", "category": "training"},
    {"name": "Assign onboarding buddy or mentor", "category": "mentor"},
    {"name": "Schedule 30-day check-in with manager", "category": "training"},
    {"name": "Schedule 90-day performance review", "category": "training"},
]

# ------------------------------------------------------------------
# Role-specific items
# ------------------------------------------------------------------

_ROLE_ITEMS: dict[str, list[dict[str, str]]] = {
    "bjj_instructor": [
        {"name": "Verify belt rank and lineage documentation", "category": "paperwork"},
        {"name": "CPR/First Aid certification verification", "category": "paperwork"},
        {"name": "Review class curriculum and lesson plan templates", "category": "training"},
        {"name": "Shadow existing instructor for 3 classes", "category": "training"},
        {"name": "Complete teaching style assessment", "category": "training"},
        {"name": "Set up class schedule in booking system", "category": "access"},
    ],
    "front_desk": [
        {"name": "Train on POS / payment system", "category": "training"},
        {"name": "Train on membership management software", "category": "training"},
        {"name": "Review phone scripts and greeting protocols", "category": "training"},
        {"name": "Learn membership plans and pricing", "category": "training"},
        {"name": "Shadow current front desk for 2 shifts", "category": "training"},
    ],
    "marketing_coordinator": [
        {"name": "Set up access to social media accounts", "category": "access"},
        {"name": "Set up access to analytics tools (GA, social insights)", "category": "access"},
        {"name": "Review brand guidelines and tone of voice document", "category": "training"},
        {"name": "Review current marketing calendar and campaigns", "category": "training"},
        {"name": "Set up design tools access (Canva, Adobe)", "category": "access"},
        {"name": "Review content approval workflow", "category": "training"},
    ],
    "personal_trainer": [
        {"name": "Verify personal training certification", "category": "paperwork"},
        {"name": "Liability insurance verification", "category": "paperwork"},
        {"name": "Review client intake and assessment forms", "category": "training"},
        {"name": "Tour equipment and learn facility layout", "category": "training"},
        {"name": "Set up client scheduling system", "category": "access"},
        {"name": "Review client programming templates", "category": "training"},
    ],
}


class OnboardingManager:
    """Generates and tracks onboarding checklists by role.

    Creates role-specific onboarding checklists combining standard items
    with role-specific tasks. Tracks completion percentage.
    """

    def generate_checklist(
        self,
        employee_name: str,
        role: str,
        start_date: datetime | None = None,
    ) -> OnboardingChecklist:
        """Generate an onboarding checklist for a new hire."""
        start = start_date or datetime.now()
        items: list[OnboardingItem] = []

        # Standard items (first week due dates)
        for i, item_def in enumerate(_STANDARD_ITEMS):
            due = start + timedelta(days=min(i, 7))
            items.append(
                OnboardingItem(
                    name=item_def["name"],
                    description=f"Category: {item_def['category']}",
                    due_date=due,
                )
            )

        # Role-specific items
        role_key = role.lower().replace(" ", "_")
        role_items = _ROLE_ITEMS.get(role_key, [])
        for i, item_def in enumerate(role_items):
            due = start + timedelta(days=7 + i)
            items.append(
                OnboardingItem(
                    name=item_def["name"],
                    description=f"Category: {item_def['category']}",
                    due_date=due,
                )
            )

        return OnboardingChecklist(
            employee_name=employee_name,
            role=role,
            start_date=start,
            items=items,
            completion_pct=0.0,
        )

    def update_item_status(
        self,
        checklist: OnboardingChecklist,
        item_name: str,
        status: OnboardingItemStatus,
    ) -> OnboardingChecklist:
        """Update the status of a specific onboarding item."""
        for item in checklist.items:
            if item.name == item_name:
                item.status = status
                break

        # Recalculate completion
        completed = sum(
            1 for item in checklist.items
            if item.status == OnboardingItemStatus.COMPLETED
        )
        total = max(len(checklist.items), 1)
        checklist.completion_pct = round((completed / total) * 100, 1)

        return checklist

    def format_checklist_markdown(self, checklist: OnboardingChecklist) -> str:
        """Format an onboarding checklist as markdown."""
        lines = [
            f"## Onboarding Checklist: {checklist.employee_name}",
            f"**Role:** {checklist.role}",
        ]
        if checklist.start_date:
            lines.append(f"**Start Date:** {checklist.start_date.strftime('%Y-%m-%d')}")
        lines.append(f"**Completion:** {checklist.completion_pct}%\n")

        # Group by status
        status_icons = {
            OnboardingItemStatus.NOT_STARTED: "[ ]",
            OnboardingItemStatus.IN_PROGRESS: "[~]",
            OnboardingItemStatus.COMPLETED: "[x]",
            OnboardingItemStatus.BLOCKED: "[!]",
        }

        for item in checklist.items:
            icon = status_icons.get(item.status, "[ ]")
            due = f" (due {item.due_date.strftime('%m/%d')})" if item.due_date else ""
            lines.append(f"- {icon} {item.name}{due}")

        lines.append(
            f"\n*{len(checklist.items)} total items | "
            f"{checklist.completion_pct}% complete*"
        )
        return "\n".join(lines)

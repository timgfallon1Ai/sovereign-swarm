"""Job posting builder with role templates and compliance."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from sovereign_swarm.recruitment.models import JobPosting, JobStatus

logger = structlog.get_logger()


# ------------------------------------------------------------------
# GBB role templates
# ------------------------------------------------------------------

_ROLE_TEMPLATES: dict[str, dict[str, Any]] = {
    "bjj_instructor": {
        "title": "Brazilian Jiu-Jitsu Instructor",
        "description": (
            "Join our world-class coaching team at Ground Based Bodywork (GBB). "
            "We are seeking an experienced BJJ instructor to lead classes, "
            "develop curriculum, and mentor students of all skill levels."
        ),
        "requirements": [
            "Purple belt or higher in Brazilian Jiu-Jitsu",
            "Minimum 2 years teaching experience",
            "Strong communication and interpersonal skills",
            "CPR/First Aid certification (or willingness to obtain)",
            "Ability to demonstrate techniques safely",
        ],
        "nice_to_haves": [
            "Competition experience at regional or national level",
            "Experience with kids/youth programs",
            "Background in strength and conditioning",
        ],
        "benefits": [
            "Competitive compensation",
            "Free training at all GBB locations",
            "Continuing education support",
            "Flexible scheduling",
        ],
    },
    "front_desk": {
        "title": "Front Desk Coordinator",
        "description": (
            "Be the welcoming face of Ground Based Bodywork. "
            "Manage member check-ins, handle inquiries, process memberships, "
            "and ensure a smooth daily operation of the facility."
        ),
        "requirements": [
            "Excellent customer service skills",
            "Proficiency with scheduling and POS systems",
            "Strong organizational abilities",
            "Ability to multitask in a fast-paced environment",
            "High school diploma or equivalent",
        ],
        "nice_to_haves": [
            "Experience in fitness or martial arts industry",
            "Familiarity with CRM software",
            "Bilingual (English/Spanish)",
        ],
        "benefits": [
            "Free membership at GBB",
            "Health and wellness perks",
            "Growth opportunities within the organization",
        ],
    },
    "marketing_coordinator": {
        "title": "Marketing Coordinator",
        "description": (
            "Drive brand awareness and member acquisition for GBB. "
            "Manage social media accounts, create content, plan events, "
            "and execute marketing campaigns across digital and local channels."
        ),
        "requirements": [
            "Bachelor's degree in Marketing, Communications, or related field",
            "1-3 years of marketing experience",
            "Proficiency with social media platforms and scheduling tools",
            "Basic graphic design skills (Canva, Adobe Creative Suite)",
            "Strong copywriting abilities",
        ],
        "nice_to_haves": [
            "Experience in fitness or wellness industry",
            "Video production and editing skills",
            "Knowledge of SEO and paid advertising",
            "Photography skills",
        ],
        "benefits": [
            "Free GBB membership",
            "Remote work flexibility",
            "Professional development budget",
            "Creative autonomy",
        ],
    },
    "personal_trainer": {
        "title": "Personal Trainer / Strength Coach",
        "description": (
            "Help our members achieve their fitness goals through personalized "
            "training programs. Design and deliver one-on-one and small group "
            "sessions focused on strength, conditioning, and injury prevention."
        ),
        "requirements": [
            "Certified Personal Trainer (NASM, ACE, NSCA, or equivalent)",
            "Minimum 1 year of training experience",
            "Knowledge of exercise physiology and biomechanics",
            "Strong motivational and communication skills",
            "Ability to work flexible hours including evenings/weekends",
        ],
        "nice_to_haves": [
            "Experience with martial arts athletes",
            "Nutrition certification",
            "Group fitness instruction experience",
            "Corrective exercise specialization",
        ],
        "benefits": [
            "Competitive per-session rate plus bonuses",
            "Free GBB membership and training",
            "Client referral program",
            "Continuing education support",
        ],
    },
}

# EEO compliance statement
_EEO_STATEMENT = (
    "We are an equal opportunity employer. All qualified applicants will "
    "receive consideration for employment without regard to race, color, "
    "religion, sex, sexual orientation, gender identity, national origin, "
    "disability, or veteran status."
)

# ADA compliance note
_ADA_STATEMENT = (
    "Reasonable accommodations may be made to enable individuals with "
    "disabilities to perform the essential functions of this role."
)


class JobBuilder:
    """Generates job postings from role requirements.

    Includes templates for common GBB roles and compliance checklists
    for EEO and ADA requirements.
    """

    def build_from_template(
        self,
        template_key: str,
        location: str = "",
        salary_range: str = "",
        department: str = "",
    ) -> JobPosting:
        """Build a job posting from a predefined template."""
        template = _ROLE_TEMPLATES.get(template_key)
        if not template:
            available = ", ".join(_ROLE_TEMPLATES.keys())
            raise ValueError(
                f"Unknown template '{template_key}'. Available: {available}"
            )

        return JobPosting(
            id=f"job_{uuid.uuid4().hex[:8]}",
            title=template["title"],
            description=template["description"],
            requirements=template["requirements"],
            nice_to_haves=template.get("nice_to_haves", []),
            benefits=template.get("benefits", []),
            location=location,
            salary_range=salary_range,
            department=department,
            status=JobStatus.DRAFT,
        )

    def build_custom(
        self,
        title: str,
        description: str,
        requirements: list[str],
        **kwargs: Any,
    ) -> JobPosting:
        """Build a custom job posting."""
        return JobPosting(
            id=f"job_{uuid.uuid4().hex[:8]}",
            title=title,
            description=description,
            requirements=requirements,
            nice_to_haves=kwargs.get("nice_to_haves", []),
            benefits=kwargs.get("benefits", []),
            location=kwargs.get("location", ""),
            salary_range=kwargs.get("salary_range", ""),
            department=kwargs.get("department", ""),
            employment_type=kwargs.get("employment_type", "full_time"),
            status=JobStatus.DRAFT,
        )

    def get_available_templates(self) -> list[str]:
        """Return list of available role templates."""
        return list(_ROLE_TEMPLATES.keys())

    def format_posting_markdown(self, posting: JobPosting) -> str:
        """Format a job posting as markdown with compliance statements."""
        lines = [
            f"## {posting.title}",
            "",
            f"**Status:** {posting.status.value.replace('_', ' ').title()}",
        ]
        if posting.location:
            lines.append(f"**Location:** {posting.location}")
        if posting.salary_range:
            lines.append(f"**Salary Range:** {posting.salary_range}")
        if posting.department:
            lines.append(f"**Department:** {posting.department}")
        lines.append(f"**Type:** {posting.employment_type.replace('_', ' ').title()}")
        lines.append("")

        lines.append("### Description\n")
        lines.append(posting.description)
        lines.append("")

        if posting.requirements:
            lines.append("### Requirements\n")
            for req in posting.requirements:
                lines.append(f"- {req}")
            lines.append("")

        if posting.nice_to_haves:
            lines.append("### Nice to Have\n")
            for nth in posting.nice_to_haves:
                lines.append(f"- {nth}")
            lines.append("")

        if posting.benefits:
            lines.append("### Benefits\n")
            for benefit in posting.benefits:
                lines.append(f"- {benefit}")
            lines.append("")

        # Compliance section
        lines.append("---")
        lines.append(f"\n*{_EEO_STATEMENT}*\n")
        lines.append(f"*{_ADA_STATEMENT}*\n")

        return "\n".join(lines)

    def compliance_checklist(self) -> list[dict[str, str]]:
        """Return a compliance checklist for job postings."""
        return [
            {"item": "EEO statement included", "status": "required"},
            {"item": "ADA accommodations note included", "status": "required"},
            {"item": "No discriminatory language", "status": "required"},
            {"item": "Salary range disclosed (if required by state)", "status": "recommended"},
            {"item": "Essential vs. preferred qualifications separated", "status": "recommended"},
            {"item": "Physical requirements stated if applicable", "status": "recommended"},
        ]

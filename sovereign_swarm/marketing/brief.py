"""CampaignBrief — structured input for the marketing ensemble.

A ``CampaignBrief`` replaces the ad-hoc dict that the Phase 1 ensemble
accepted. It encodes everything a marketing team would write on a
one-pager before kicking off a campaign:

  - Product / subject
  - Audience
  - Campaign objective (awareness / consideration / conversion / retention)
  - Key message
  - Call-to-action
  - Constraints (things to avoid, legal/brand guardrails)
  - Desired length, aspect ratio, platforms
  - Deadline
  - Optional references (existing assets or URLs for inspiration)

The brief is JSON-serializable, hashable, and drivable from a
single ``SwarmAgentRequest.parameters`` dict. The script-generation
stage (``script_gen.py``) consumes it and returns narration_text +
video_prompt, closing the loop on Phase 1's "caller supplies text"
contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class CampaignObjective(str, Enum):
    AWARENESS = "awareness"
    CONSIDERATION = "consideration"
    CONVERSION = "conversion"
    RETENTION = "retention"
    LAUNCH = "launch"


class Platform(str, Enum):
    YOUTUBE_SHORT = "youtube_short"
    YOUTUBE_LONG = "youtube_long"
    INSTAGRAM_REEL = "instagram_reel"
    INSTAGRAM_FEED = "instagram_feed"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    WEBSITE_HERO = "website_hero"
    EMAIL = "email"
    B2B_SALES = "b2b_sales"
    OEM_PITCH = "oem_pitch"


@dataclass(frozen=True)
class CampaignBrief:
    """Structured marketing brief consumed by the Sovereign ensemble."""

    # --- Required ---
    tenant: str  # "atx_mats" | "gbb" | "gli"
    campaign_id: str  # stable identifier used in output paths
    subject: str  # the product / event / announcement being marketed
    audience: str  # the target audience override (defaults to tenant brand)
    objective: CampaignObjective
    key_message: str  # the single most important thing the audience should take away
    call_to_action: str  # what the audience should DO after watching

    # --- Optional ---
    constraints: tuple[str, ...] = ()  # "no medical claims", "no pricing", etc.
    platforms: tuple[Platform, ...] = ()
    duration_seconds: Optional[int] = None
    aspect_ratio: Optional[str] = None  # "16:9", "9:16", "1:1"
    resolution: Optional[tuple[int, int]] = None
    references: tuple[str, ...] = ()  # URLs or file paths to existing inspiration
    deadline: Optional[str] = None  # ISO date string (advisory only — not enforced)
    owner: str = ""  # human responsible for this campaign
    notes: str = ""  # freeform notes for the scriptwriter

    # --- Generation knobs (optional overrides for the downstream stages) ---
    num_stills: int = 0  # 0 = skip FLUX still-image stage
    enable_remotion: bool = False
    enable_thumbnail_qa: bool = True
    require_publish_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict (enums converted to strings)."""
        d = asdict(self)
        d["objective"] = self.objective.value
        d["platforms"] = [p.value for p in self.platforms]
        return d

    def brand_prompt_block(self) -> str:
        """Render the brief as a structured block for inclusion in an LLM prompt."""
        lines = [
            f"Tenant: {self.tenant}",
            f"Campaign: {self.campaign_id}",
            f"Subject: {self.subject}",
            f"Audience: {self.audience}",
            f"Objective: {self.objective.value}",
            f"Key message: {self.key_message}",
            f"Call to action: {self.call_to_action}",
        ]
        if self.constraints:
            lines.append("Constraints:")
            for c in self.constraints:
                lines.append(f"  - {c}")
        if self.platforms:
            lines.append(
                "Platforms: " + ", ".join(p.value for p in self.platforms)
            )
        if self.duration_seconds:
            lines.append(f"Duration: ~{self.duration_seconds} seconds")
        if self.aspect_ratio:
            lines.append(f"Aspect ratio: {self.aspect_ratio}")
        if self.references:
            lines.append("References:")
            for r in self.references:
                lines.append(f"  - {r}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CampaignBrief":
        """Build a brief from a raw dict (e.g. swarm parameters)."""
        objective = data.get("objective") or "awareness"
        if isinstance(objective, str):
            objective = CampaignObjective(objective)
        platforms = data.get("platforms") or ()
        if platforms:
            platforms = tuple(
                p if isinstance(p, Platform) else Platform(p) for p in platforms
            )
        resolution = data.get("resolution")
        if resolution is not None and not isinstance(resolution, tuple):
            resolution = tuple(resolution)
        return cls(
            tenant=data["tenant"],
            campaign_id=data["campaign_id"],
            subject=data["subject"],
            audience=data["audience"],
            objective=objective,
            key_message=data["key_message"],
            call_to_action=data["call_to_action"],
            constraints=tuple(data.get("constraints", ())),
            platforms=platforms,
            duration_seconds=data.get("duration_seconds"),
            aspect_ratio=data.get("aspect_ratio"),
            resolution=resolution,
            references=tuple(data.get("references", ())),
            deadline=data.get("deadline"),
            owner=data.get("owner", ""),
            notes=data.get("notes", ""),
            num_stills=int(data.get("num_stills", 0)),
            enable_remotion=bool(data.get("enable_remotion", False)),
            enable_thumbnail_qa=bool(data.get("enable_thumbnail_qa", True)),
            require_publish_approval=bool(
                data.get("require_publish_approval", True)
            ),
        )

"""Canva design generation stage for the marketing ensemble.

Wraps Canva MCP tools (already connected to Claude Desktop) to produce
on-brand social media posts, thumbnails, and marketing collateral as
part of the automated campaign pipeline.

This stage is designed to be called from the SovereignMarketingEnsemble
after script generation, providing a design asset alongside the video
and narration outputs.

Design notes
------------
- Does NOT call the Canva MCP directly — that's a Claude Desktop concern.
  Instead, this stage produces a structured CanvaDesignRequest that the
  ensemble can serialize and hand off to a Claude Desktop session, CLI
  script, or scheduled task that has the Canva MCP wired.
- The request includes all brand-derived parameters (palette, tone,
  audience) so the consumer can call generate-design or autofill-design
  with zero additional lookups.
- Output is a CanvaDesignResult with the design_id and URLs if the
  consumer executed it, or a "pending" status with the serialized
  request if not.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from sovereign_swarm.marketing.brand import TenantBrand

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanvaDesignRequest:
    """Everything needed to generate a Canva design via MCP tools."""

    tenant: str
    campaign_id: str
    design_type: str  # "instagram_post", "youtube_thumbnail", "poster", etc.
    query: str  # Natural language prompt for generate-design
    brand_kit_id: Optional[str] = None  # If tenant has a Canva brand kit
    title: Optional[str] = None
    # Brand context for the consumer
    palette: tuple[str, ...] = ()
    tone_keywords: tuple[str, ...] = ()
    target_audience: str = ""
    negative_prompt: str = ""
    # Optional asset IDs to include (uploaded images)
    asset_ids: list[str] = field(default_factory=list)


@dataclass
class CanvaDesignResult:
    """Result from a Canva design generation attempt."""

    status: str  # "created", "pending", "error"
    design_id: Optional[str] = None
    edit_url: Optional[str] = None
    view_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    request: Optional[CanvaDesignRequest] = None  # Stored for deferred execution
    error: Optional[str] = None
    duration_s: float = 0.0


# ---------------------------------------------------------------------------
# Design type mapping — maps campaign brief platforms to Canva design types
# ---------------------------------------------------------------------------

PLATFORM_TO_DESIGN_TYPE = {
    "instagram": "instagram_post",
    "instagram_story": "your_story",
    "facebook": "facebook_post",
    "facebook_cover": "facebook_cover",
    "youtube_thumbnail": "youtube_thumbnail",
    "youtube_banner": "youtube_banner",
    "twitter": "twitter_post",
    "pinterest": "pinterest_pin",
    "linkedin": "poster",  # LinkedIn doesn't have a dedicated type
    "email": "email",
    "flyer": "flyer",
    "poster": "poster",
    "presentation": "presentation",
}


class CanvaDesignStage:
    """Produces CanvaDesignRequests from campaign briefs + brand profiles.

    Two modes:
    1. ``prepare()`` — generates the request object without executing it.
       The caller serializes it for deferred execution by a Canva-connected
       consumer (Claude Desktop session, CLI script, scheduled task).
    2. ``run()`` — calls prepare() then attempts execution if an executor
       callback is provided. Falls back to "pending" status otherwise.
    """

    def __init__(
        self,
        executor: Optional[Any] = None,  # Callable that takes CanvaDesignRequest -> CanvaDesignResult
        brand_kit_map: Optional[dict[str, str]] = None,  # tenant -> brand_kit_id
    ):
        self._executor = executor
        self._brand_kit_map = brand_kit_map or {}

    def prepare(
        self,
        brand: TenantBrand,
        campaign_id: str,
        headline: str,
        body_text: str,
        platform: str = "instagram",
        extra_context: str = "",
    ) -> CanvaDesignRequest:
        """Build a CanvaDesignRequest from brand + campaign parameters."""
        design_type = PLATFORM_TO_DESIGN_TYPE.get(platform, "poster")

        # Compose the generation query with brand context
        palette_str = ", ".join(brand.palette[:3])
        tone_str = ", ".join(brand.tone_keywords[:3])

        query = (
            f"Create a {design_type} for {brand.display_name}. "
            f"Headline: {headline}. "
            f"Body: {body_text}. "
            f"Brand colors: {palette_str}. "
            f"Tone: {tone_str}. "
            f"Target audience: {brand.target_audience[:200]}."
        )
        if extra_context:
            query += f" Additional context: {extra_context}"

        return CanvaDesignRequest(
            tenant=brand.key,
            campaign_id=campaign_id,
            design_type=design_type,
            query=query,
            brand_kit_id=self._brand_kit_map.get(brand.key),
            title=f"{brand.display_name} - {headline[:60]}",
            palette=brand.palette,
            tone_keywords=brand.tone_keywords,
            target_audience=brand.target_audience,
            negative_prompt=brand.negative_prompt,
        )

    def run(
        self,
        brand: TenantBrand,
        campaign_id: str,
        headline: str,
        body_text: str,
        platform: str = "instagram",
        output_dir: Optional[Path] = None,
        extra_context: str = "",
    ) -> CanvaDesignResult:
        """Prepare and optionally execute a Canva design generation."""
        t0 = time.time()
        request = self.prepare(
            brand=brand,
            campaign_id=campaign_id,
            headline=headline,
            body_text=body_text,
            platform=platform,
            extra_context=extra_context,
        )

        # Serialize the request for deferred execution
        if output_dir:
            req_path = Path(output_dir) / "canva_request.json"
            req_path.write_text(json.dumps(asdict(request), indent=2, default=str))

        # Attempt execution if an executor is wired
        if self._executor:
            try:
                result = self._executor(request)
                result.duration_s = round(time.time() - t0, 2)
                return result
            except Exception as exc:
                logger.warning("canva_stage.executor_failed", error=str(exc))
                return CanvaDesignResult(
                    status="error",
                    request=request,
                    error=f"{type(exc).__name__}: {exc}",
                    duration_s=round(time.time() - t0, 2),
                )

        # No executor — return pending with the serialized request
        return CanvaDesignResult(
            status="pending",
            request=request,
            duration_s=round(time.time() - t0, 2),
        )

    @staticmethod
    def load_request(path: str | Path) -> CanvaDesignRequest:
        """Load a serialized CanvaDesignRequest from disk."""
        data = json.loads(Path(path).read_text())
        # Convert lists back to tuples for frozen dataclass
        data["palette"] = tuple(data.get("palette", ()))
        data["tone_keywords"] = tuple(data.get("tone_keywords", ()))
        return CanvaDesignRequest(**data)

"""MarketingAgent — swarm wrapper around SovereignMarketingEnsemble.

Exposes the cross-tenant marketing production pipeline as a
``SwarmAgent`` so the coordinator can dispatch campaign requests via
the standard protocol. Supports three intents:

  - ``produce_campaign``  — run a full campaign (narration + video + mux)
  - ``list_tenants``      — return the known tenant brand profiles
  - ``get_brand``         — return one tenant brand profile

Request parameter schema (``SwarmAgentRequest.parameters``)::

    intent           : "produce_campaign" | "list_tenants" | "get_brand"
    tenant           : str (required for produce/get_brand)
    campaign_id      : str (required for produce)
    narration_text   : str (required for produce)
    video_prompt     : str (required for produce)
    resolution       : [w, h] (optional)
    num_frames       : int (optional)
    steps            : int (optional)
    seed             : int (optional, default 7)
    notes            : str (optional)
"""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.marketing.brand import TENANTS, get_brand
from sovereign_swarm.marketing.ensemble import (
    MarketingCampaignRequest,
    SovereignMarketingEnsemble,
)
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class MarketingAgent(SwarmAgent):
    """Cross-tenant marketing production agent (ATX Mats / GBB / GLI)."""

    def __init__(
        self,
        ensemble: SovereignMarketingEnsemble | None = None,
        config: Any | None = None,
    ) -> None:
        self.config = config
        self.ensemble = ensemble or SovereignMarketingEnsemble()

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="marketing",
            description=(
                "Cross-tenant marketing production agent -- generates "
                "on-brand narration + motion video + final mux for "
                "ATX Mats, GBB, and GLI. Uses VibeVoice for TTS, "
                "Wan 2.2 MLX for text-to-video, and ffmpeg for "
                "composition. Fully local; zero API cost."
            ),
            domains=["marketing", "content", "video", "ads", "campaigns"],
            supported_intents=[
                "produce_campaign",
                "generate_ad",
                "generate_video_ad",
                "list_tenants",
                "get_brand",
                "get_tenant_brand",
            ],
            capabilities=[
                "video_campaign_production",
                "tenant_brand_lookup",
                "local_only_generation",
                "multi_tenant",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        params = request.parameters or {}
        intent = (params.get("intent") or self._infer_intent(request.task)).lower()

        if intent in {"list_tenants"}:
            return SwarmAgentResponse(
                agent_name="marketing",
                status="success",
                output=f"{len(TENANTS)} tenants registered",
                data={"tenants": {k: b.display_name for k, b in TENANTS.items()}},
                confidence=1.0,
            )

        if intent in {"get_brand", "get_tenant_brand"}:
            tenant = params.get("tenant")
            if not tenant:
                return SwarmAgentResponse(
                    agent_name="marketing",
                    status="error",
                    error="intent=get_brand requires 'tenant' parameter",
                )
            try:
                brand = get_brand(tenant)
            except KeyError as exc:
                return SwarmAgentResponse(
                    agent_name="marketing", status="error", error=str(exc)
                )
            return SwarmAgentResponse(
                agent_name="marketing",
                status="success",
                output=f"{brand.display_name}: {brand.tagline}",
                data={
                    "tenant": brand.key,
                    "display_name": brand.display_name,
                    "tagline": brand.tagline,
                    "tone_keywords": list(brand.tone_keywords),
                    "palette": list(brand.palette),
                    "voice_name": brand.voice_name,
                    "domain": brand.domain,
                },
                confidence=1.0,
            )

        if intent in {"produce_campaign", "generate_ad", "generate_video_ad"}:
            tenant = params.get("tenant")
            campaign_id = params.get("campaign_id")
            narration_text = params.get("narration_text")
            video_prompt = params.get("video_prompt")
            missing = [
                name
                for name, val in (
                    ("tenant", tenant),
                    ("campaign_id", campaign_id),
                    ("narration_text", narration_text),
                    ("video_prompt", video_prompt),
                )
                if not val
            ]
            if missing:
                return SwarmAgentResponse(
                    agent_name="marketing",
                    status="error",
                    error=f"produce_campaign missing required params: {missing}",
                )

            try:
                req = MarketingCampaignRequest(
                    tenant=tenant,
                    campaign_id=campaign_id,
                    narration_text=narration_text,
                    video_prompt=video_prompt,
                    resolution=tuple(params.get("resolution"))
                    if params.get("resolution")
                    else None,
                    num_frames=params.get("num_frames"),
                    steps=params.get("steps"),
                    seed=int(params.get("seed", 7)),
                    extra_negative_prompt=params.get("extra_negative_prompt", ""),
                    notes=params.get("notes", ""),
                )
                result = self.ensemble.run(req)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "marketing.produce_campaign_failed",
                    tenant=tenant,
                    campaign_id=campaign_id,
                )
                return SwarmAgentResponse(
                    agent_name="marketing",
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )

            status = result.status  # "success" | "partial" | "error"
            return SwarmAgentResponse(
                agent_name="marketing",
                status=status if status != "partial" else "success",
                output=(
                    f"{result.tenant} campaign {result.campaign_id}: "
                    f"{status} in {result.total_duration_s:.1f}s"
                ),
                data={
                    "tenant": result.tenant,
                    "campaign_id": result.campaign_id,
                    "output_dir": result.output_dir,
                    "artifacts": result.artifacts,
                    "stages": [
                        {
                            "stage": s.stage,
                            "status": s.status,
                            "duration_s": s.duration_s,
                            "data": s.data,
                            "error": s.error,
                        }
                        for s in result.stages
                    ],
                    "total_duration_s": result.total_duration_s,
                    "total_cost_usd": result.total_cost_usd,
                },
                confidence=0.9 if status == "success" else 0.5,
            )

        return SwarmAgentResponse(
            agent_name="marketing",
            status="error",
            error=f"Unknown intent: {intent}",
        )

    @staticmethod
    def _infer_intent(task: str) -> str:
        t = (task or "").lower()
        if any(kw in t for kw in ("list tenant", "what tenant", "which tenant")):
            return "list_tenants"
        if any(kw in t for kw in ("brand", "voice", "palette")) and "produce" not in t:
            return "get_brand"
        return "produce_campaign"

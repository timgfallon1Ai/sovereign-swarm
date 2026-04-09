"""Sovereign marketing ensemble — shared production stack for ATX Mats, GBB, and GLI.

The ensemble is a thin orchestration layer over:
  - Claude (script + research) via the existing ContentAgent / LLM
  - VibeVoice local TTS for narration (via OpenMontage registry)
  - Wan2.2 MLX local text-to-video for motion clips (via OpenMontage)
  - UI-TARS-1.5-7B for thumbnail grounding + QA
  - FLUX via inference.sh for still imagery (existing skill)
  - Remotion / ffmpeg for final composition

Tenants supported out of the box:

  - ``atx_mats`` — Austin Mats flooring manufacturer, commercial + OEM
  - ``gbb``      — Green Bear Brand (Tim Fallon's parent company)
  - ``gli``      — Green Light Innovations, e-commerce monorepo

Each tenant contributes its own ``TenantBrand`` (voice, palette,
target audience, negative prompts). Campaigns reference a tenant by
key; the ensemble loads the brand at request time.
"""

from sovereign_swarm.marketing.agent import MarketingAgent
from sovereign_swarm.marketing.brand import TenantBrand, TENANTS, get_brand
from sovereign_swarm.marketing.brief import (
    CampaignBrief,
    CampaignObjective,
    Platform,
)
from sovereign_swarm.marketing.ensemble import (
    MarketingCampaignRequest,
    MarketingCampaignResult,
    SovereignMarketingEnsemble,
)
from sovereign_swarm.marketing.publish_gate import (
    PublishApprovalState,
    PublishGate,
    PublishRequest,
)
from sovereign_swarm.marketing.remotion_compose import (
    RemotionComposerStage,
    RemotionResult,
)
from sovereign_swarm.marketing.script_gen import (
    MarketingScriptGenerator,
    ScriptResult,
)
from sovereign_swarm.marketing.stills import (
    FluxStillsStage,
    StillResult,
    StillsResult,
)
from sovereign_swarm.marketing.thumbnail_qa import (
    ThumbnailQAResult,
    ThumbnailQAStage,
)

__all__ = [
    # Agent
    "MarketingAgent",
    # Core pipeline
    "SovereignMarketingEnsemble",
    "MarketingCampaignRequest",
    "MarketingCampaignResult",
    # Brand + brief
    "TenantBrand",
    "TENANTS",
    "get_brand",
    "CampaignBrief",
    "CampaignObjective",
    "Platform",
    # Phase 2 stages
    "MarketingScriptGenerator",
    "ScriptResult",
    "FluxStillsStage",
    "StillResult",
    "StillsResult",
    "ThumbnailQAStage",
    "ThumbnailQAResult",
    "RemotionComposerStage",
    "RemotionResult",
    "PublishGate",
    "PublishRequest",
    "PublishApprovalState",
]

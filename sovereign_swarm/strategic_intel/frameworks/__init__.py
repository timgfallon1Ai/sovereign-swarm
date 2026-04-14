"""Strategic analysis framework modules.

Each framework defines search queries, synthesis prompts, and output schemas.
Tier 1 frameworks run weekly on autopilot.
Tier 2 frameworks run on demand or when triggered by Tier 1 signals.
"""

from sovereign_swarm.strategic_intel.frameworks.market_breakdown import MarketBreakdownFramework
from sovereign_swarm.strategic_intel.frameworks.problem_priority import ProblemPriorityFramework
from sovereign_swarm.strategic_intel.frameworks.content_engine import ContentEngineFramework
from sovereign_swarm.strategic_intel.frameworks.distribution_plan import DistributionPlanFramework
from sovereign_swarm.strategic_intel.frameworks.competitor_map import CompetitorMapFramework
from sovereign_swarm.strategic_intel.frameworks.offer_creation import OfferCreationFramework
from sovereign_swarm.strategic_intel.frameworks.scale_system import ScaleSystemFramework

TIER_1_FRAMEWORKS = [
    MarketBreakdownFramework,
    ProblemPriorityFramework,
    ContentEngineFramework,
    DistributionPlanFramework,
]

TIER_2_FRAMEWORKS = [
    CompetitorMapFramework,
    OfferCreationFramework,
    ScaleSystemFramework,
]

ALL_FRAMEWORKS = TIER_1_FRAMEWORKS + TIER_2_FRAMEWORKS

__all__ = [
    "TIER_1_FRAMEWORKS",
    "TIER_2_FRAMEWORKS",
    "ALL_FRAMEWORKS",
    "MarketBreakdownFramework",
    "ProblemPriorityFramework",
    "ContentEngineFramework",
    "DistributionPlanFramework",
    "CompetitorMapFramework",
    "OfferCreationFramework",
    "ScaleSystemFramework",
]

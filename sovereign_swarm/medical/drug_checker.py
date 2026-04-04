"""DrugInteractionChecker -- checks known drug interactions via sovereign-ingest."""

from __future__ import annotations

import structlog

from sovereign_swarm.medical.knowledge import MedicalKnowledgeEngine
from sovereign_swarm.medical.models import MEDICAL_DISCLAIMER, DrugInteraction

logger = structlog.get_logger()

# Keywords used to classify interaction severity from description text
_SEVERITY_KEYWORDS: dict[str, list[str]] = {
    "contraindicated": [
        "contraindicated",
        "do not use",
        "fatal",
        "life-threatening",
        "never combine",
        "absolute contraindication",
    ],
    "severe": [
        "severe",
        "serious",
        "dangerous",
        "significant risk",
        "major",
        "black box",
        "serotonin syndrome",
        "qtc prolongation",
        "bleeding risk",
    ],
    "moderate": [
        "moderate",
        "caution",
        "monitor",
        "may increase",
        "may decrease",
        "adjust dose",
        "clinical significance",
    ],
    "mild": [
        "mild",
        "minor",
        "unlikely",
        "low risk",
        "theoretical",
    ],
}


class DrugInteractionChecker:
    """Check known drug-drug interactions using sovereign-ingest DrugBank data."""

    def __init__(self, knowledge: MedicalKnowledgeEngine) -> None:
        self._knowledge = knowledge

    async def check_interactions(
        self, drug_list: list[str]
    ) -> list[DrugInteraction]:
        """Check all pairwise interactions for a list of drugs.

        Returns a list of DrugInteraction models. Always includes the
        medical disclaimer in log output.
        """
        if len(drug_list) < 2:
            logger.info("drug_checker.need_at_least_two_drugs")
            return []

        raw = await self._knowledge.get_drug_interactions(drug_list)
        interactions: list[DrugInteraction] = []

        for item in raw:
            drug_a = item["drug_a"]
            drug_b = item["drug_b"]
            raw_data = item.get("raw", {})

            description = raw_data.get(
                "content",
                raw_data.get("text", raw_data.get("description", "")),
            )
            mechanism = raw_data.get("mechanism", "")
            severity = self._classify_severity(description)

            interactions.append(
                DrugInteraction(
                    drug_a=drug_a,
                    drug_b=drug_b,
                    severity=severity,
                    description=description,
                    mechanism=mechanism,
                )
            )

        logger.info(
            "drug_checker.completed",
            drugs=drug_list,
            interactions_found=len(interactions),
            disclaimer=MEDICAL_DISCLAIMER,
        )
        return interactions

    @staticmethod
    def _classify_severity(description: str) -> str:
        """Classify interaction severity based on keywords in description."""
        text_lower = description.lower()

        # Check from most severe to least severe
        for severity in ["contraindicated", "severe", "moderate", "mild"]:
            for keyword in _SEVERITY_KEYWORDS[severity]:
                if keyword in text_lower:
                    return severity

        # Default to moderate if we have a description but no keyword match
        if description.strip():
            return "moderate"
        return "mild"

    def format_report(self, interactions: list[DrugInteraction]) -> str:
        """Format interactions into a readable markdown report."""
        if not interactions:
            return (
                "No known interactions found for the provided medications.\n\n"
                f"**Disclaimer:** {MEDICAL_DISCLAIMER}"
            )

        lines = ["## Drug Interaction Report\n"]
        for ix in interactions:
            severity_icon = {
                "contraindicated": "!!!",
                "severe": "!!",
                "moderate": "!",
                "mild": "~",
            }.get(ix.severity, "?")

            lines.append(
                f"### [{severity_icon}] {ix.drug_a} + {ix.drug_b} "
                f"({ix.severity.upper()})"
            )
            if ix.description:
                lines.append(f"**Description:** {ix.description}")
            if ix.mechanism:
                lines.append(f"**Mechanism:** {ix.mechanism}")
            lines.append("")

        lines.append(f"\n**Disclaimer:** {MEDICAL_DISCLAIMER}")
        return "\n".join(lines)

"""MedicalAgent -- medical research, imaging, drug interactions, clinical trials."""

from __future__ import annotations

import re
from typing import Any

import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge
from sovereign_swarm.medical.models import (
    MEDICAL_DISCLAIMER,
    MedicalDomain,
    MedicalReport,
)
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()

# Keyword routing patterns
_DRUG_KEYWORDS = re.compile(
    r"drug interaction|medication check|drug check|interactions between",
    re.IGNORECASE,
)
_IMAGING_KEYWORDS = re.compile(
    r"xray|x-ray|mri|ct scan|imaging|ultrasound|histopath|radiology",
    re.IGNORECASE,
)
_TRIAL_KEYWORDS = re.compile(
    r"clinical trial|trial search|nct\d+",
    re.IGNORECASE,
)
_RESEARCH_KEYWORDS = re.compile(
    r"research|literature|pubmed|systematic review|meta-analysis|evidence",
    re.IGNORECASE,
)


class MedicalAgent(SwarmAgent):
    """Medical research and analysis agent for the swarm.

    Capabilities: medical literature search, drug interaction checking,
    medical imaging analysis (Phase A heuristic / Phase B MedGemma),
    clinical trial search, and general medical knowledge queries.

    ALL responses include a mandatory medical disclaimer.
    """

    def __init__(
        self,
        ingest_bridge: SovereignIngestBridge | None = None,
        config: Any | None = None,
    ) -> None:
        self._ingest = ingest_bridge
        self._config = config

        # Lazy-initialized components
        self._knowledge: Any | None = None
        self._imaging: Any | None = None
        self._drug_checker: Any | None = None
        self._researcher: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="medical",
            description=(
                "Medical research and analysis agent -- drug interactions, "
                "imaging analysis, clinical trial search, PubMed literature, "
                "and general medical knowledge queries"
            ),
            domains=[
                "medical",
                "health",
                "clinical",
                "pharmaceutical",
                "radiology",
                "oncology",
                "dentistry",
            ],
            supported_intents=[
                "medical",
                "health",
                "drug_check",
                "imaging",
                "clinical_research",
            ],
            capabilities=[
                "medical_research",
                "imaging_analysis",
                "drug_interaction_check",
                "clinical_trial_search",
                "treatment_research",
                "anatomy_reference",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route medical requests to the appropriate sub-component."""
        if not self._ingest or not self._ingest.available:
            return SwarmAgentResponse(
                agent_name="medical",
                status="error",
                error="Knowledge base (sovereign-ingest) not available",
            )

        task = request.task
        try:
            # Route by keyword
            if _DRUG_KEYWORDS.search(task):
                return await self._handle_drug_check(request)
            elif _IMAGING_KEYWORDS.search(task):
                return await self._handle_imaging(request)
            elif _TRIAL_KEYWORDS.search(task):
                return await self._handle_clinical_trials(request)
            elif _RESEARCH_KEYWORDS.search(task):
                return await self._handle_research(request)
            else:
                return await self._handle_general(request)

        except Exception as e:
            logger.error("medical.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="medical",
                status="error",
                error=f"{str(e)}\n\n{MEDICAL_DISCLAIMER}",
            )

    # ------------------------------------------------------------------
    # Sub-handlers
    # ------------------------------------------------------------------

    async def _handle_drug_check(
        self, request: SwarmAgentRequest
    ) -> SwarmAgentResponse:
        """Handle drug interaction check requests."""
        checker = self._get_drug_checker()
        drugs = request.parameters.get("drugs", [])

        if not drugs:
            # Try to parse drug names from the task text
            drugs = self._extract_drug_names(request.task)

        if len(drugs) < 2:
            return SwarmAgentResponse(
                agent_name="medical",
                status="error",
                error=(
                    "Please provide at least two drug names to check interactions. "
                    f"\n\n{MEDICAL_DISCLAIMER}"
                ),
            )

        interactions = await checker.check_interactions(drugs)
        report = checker.format_report(interactions)

        return SwarmAgentResponse(
            agent_name="medical",
            status="success",
            output=report,
            data={
                "interaction_count": len(interactions),
                "drugs_checked": drugs,
                "severities": [ix.severity for ix in interactions],
            },
            confidence=0.7 if interactions else 0.3,
        )

    async def _handle_imaging(
        self, request: SwarmAgentRequest
    ) -> SwarmAgentResponse:
        """Handle medical imaging analysis requests."""
        analyzer = self._get_imaging()
        image_path = request.parameters.get(
            "image_path", request.context.get("image_path", "")
        )
        modality = request.parameters.get("modality", "xray")
        clinical_context = request.parameters.get("clinical_context", "")

        if not image_path:
            return SwarmAgentResponse(
                agent_name="medical",
                status="error",
                error=(
                    "No image path provided for imaging analysis. "
                    f"\n\n{MEDICAL_DISCLAIMER}"
                ),
            )

        analysis = await analyzer.analyze_image(
            image_path=image_path,
            modality=modality,
            clinical_context=clinical_context,
        )

        output_lines = [
            f"## Imaging Analysis ({analysis.modality.upper()})\n",
            "### Findings",
        ]
        for f in analysis.findings:
            output_lines.append(f"- {f}")
        output_lines.append(f"\n### Impression\n{analysis.impression}")
        output_lines.append(f"\n**Confidence:** {analysis.confidence:.0%}")
        if analysis.regions_of_interest:
            output_lines.append(
                f"\n**Regions of Interest:** {', '.join(analysis.regions_of_interest)}"
            )
        output_lines.append(f"\n**Disclaimer:** {MEDICAL_DISCLAIMER}")

        return SwarmAgentResponse(
            agent_name="medical",
            status="success",
            output="\n".join(output_lines),
            data={
                "modality": analysis.modality,
                "findings_count": len(analysis.findings),
                "confidence": analysis.confidence,
            },
            confidence=analysis.confidence,
        )

    async def _handle_clinical_trials(
        self, request: SwarmAgentRequest
    ) -> SwarmAgentResponse:
        """Handle clinical trial search requests."""
        researcher = self._get_researcher()
        limit = request.parameters.get("limit", 20)
        results = await researcher.search_trials(
            condition=request.task, limit=limit
        )

        if not results:
            return SwarmAgentResponse(
                agent_name="medical",
                status="success",
                output=(
                    f"No clinical trials found for: {request.task}\n\n"
                    f"**Disclaimer:** {MEDICAL_DISCLAIMER}"
                ),
                data={"results_count": 0},
                confidence=0.3,
            )

        lines = [f"## Clinical Trial Search Results\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"**{i}. {r.title}**")
            if r.pmid_or_nctid:
                lines.append(f"  NCT ID: {r.pmid_or_nctid}")
            if r.url:
                lines.append(f"  URL: {r.url}")
            if r.summary:
                lines.append(f"  {r.summary[:200]}...")
            lines.append("")

        lines.append(f"\n**Disclaimer:** {MEDICAL_DISCLAIMER}")

        return SwarmAgentResponse(
            agent_name="medical",
            status="success",
            output="\n".join(lines),
            data={"results_count": len(results)},
            confidence=0.7,
        )

    async def _handle_research(
        self, request: SwarmAgentRequest
    ) -> SwarmAgentResponse:
        """Handle literature research requests."""
        researcher = self._get_researcher()
        domain = self._detect_domain(request.task)
        limit = request.parameters.get("limit", 20)

        report = await researcher.compose_report(
            query=request.task, domain=domain, limit=limit
        )

        return SwarmAgentResponse(
            agent_name="medical",
            status="success",
            output=report,
            data={"domain": domain.value},
            confidence=0.6,
        )

    async def _handle_general(
        self, request: SwarmAgentRequest
    ) -> SwarmAgentResponse:
        """Handle general medical knowledge queries."""
        knowledge = self._get_knowledge()
        results = await knowledge.search_medical_literature(
            query=request.task, limit=10
        )

        if not results:
            return SwarmAgentResponse(
                agent_name="medical",
                status="success",
                output=(
                    f"No medical knowledge found for: {request.task}\n\n"
                    f"**Disclaimer:** {MEDICAL_DISCLAIMER}"
                ),
                data={"results_count": 0},
                confidence=0.2,
            )

        domain = self._detect_domain(request.task)
        report = MedicalReport(
            domain=domain,
            query=request.task,
            findings="\n".join(
                f"- {r.get('title', 'Untitled')}: "
                f"{r.get('content', r.get('text', ''))[:150]}"
                for r in results[:5]
            ),
            recommendations="Consult the referenced literature for detailed information.",
            references=[
                r.get("title", "Untitled") for r in results[:5]
            ],
        )

        output_lines = [
            f"## Medical Knowledge: {request.task}\n",
            f"**Domain:** {report.domain.value}\n",
            "### Findings\n",
            report.findings,
            f"\n### Recommendations\n{report.recommendations}",
            "\n### References",
        ]
        for ref in report.references:
            output_lines.append(f"- {ref}")
        output_lines.append(f"\n**Disclaimer:** {report.disclaimer}")

        return SwarmAgentResponse(
            agent_name="medical",
            status="success",
            output="\n".join(output_lines),
            data={
                "domain": report.domain.value,
                "results_count": len(results),
            },
            confidence=0.5,
        )

    # ------------------------------------------------------------------
    # Lazy initializers
    # ------------------------------------------------------------------

    def _get_knowledge(self) -> Any:
        if self._knowledge is None:
            from sovereign_swarm.medical.knowledge import MedicalKnowledgeEngine

            self._knowledge = MedicalKnowledgeEngine(self._ingest)
        return self._knowledge

    def _get_imaging(self) -> Any:
        if self._imaging is None:
            from sovereign_swarm.medical.imaging import MedicalImagingAnalyzer

            self._imaging = MedicalImagingAnalyzer()
        return self._imaging

    def _get_drug_checker(self) -> Any:
        if self._drug_checker is None:
            from sovereign_swarm.medical.drug_checker import DrugInteractionChecker

            self._drug_checker = DrugInteractionChecker(self._get_knowledge())
        return self._drug_checker

    def _get_researcher(self) -> Any:
        if self._researcher is None:
            from sovereign_swarm.medical.research import ClinicalResearcher

            self._researcher = ClinicalResearcher(self._get_knowledge())
        return self._researcher

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_domain(text: str) -> MedicalDomain:
        """Detect the medical domain from query text."""
        text_lower = text.lower()
        domain_keywords = {
            MedicalDomain.RADIOLOGY: ["radiology", "xray", "x-ray", "mri", "ct scan", "imaging"],
            MedicalDomain.ONCOLOGY: ["oncology", "cancer", "tumor", "tumour", "chemotherapy", "carcinoma"],
            MedicalDomain.DENTISTRY: ["dental", "dentistry", "tooth", "teeth", "oral", "periodontal"],
            MedicalDomain.ORTHOPEDICS: ["orthopedic", "bone", "joint", "fracture", "musculoskeletal"],
            MedicalDomain.PHARMACOLOGY: ["drug", "medication", "pharmacology", "pharmaceutical", "dosage"],
            MedicalDomain.REGENERATIVE_MEDICINE: ["regenerative", "stem cell", "tissue engineering"],
            MedicalDomain.NEUROSCIENCE: ["neuro", "brain", "cognitive", "neurological", "cns"],
            MedicalDomain.CELLULAR_BIOLOGY: ["cellular", "cell biology", "molecular", "genomic"],
        }
        for domain, keywords in domain_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    return domain
        return MedicalDomain.GENERAL

    @staticmethod
    def _extract_drug_names(text: str) -> list[str]:
        """Best-effort extraction of drug names from free text.

        Looks for patterns like "between X and Y", "X, Y, and Z", etc.
        """
        # Try "between X and Y"
        between = re.search(
            r"between\s+(\w+)\s+and\s+(\w+)", text, re.IGNORECASE
        )
        if between:
            return [between.group(1), between.group(2)]

        # Try comma-separated list with "and"
        # e.g., "aspirin, ibuprofen, and warfarin"
        list_match = re.search(
            r"(?:check|interactions?|medications?)[:\s]+(.+)",
            text,
            re.IGNORECASE,
        )
        if list_match:
            raw = list_match.group(1)
            raw = re.sub(r"\band\b", ",", raw, flags=re.IGNORECASE)
            drugs = [d.strip().rstrip(".") for d in raw.split(",") if d.strip()]
            if len(drugs) >= 2:
                return drugs

        return []

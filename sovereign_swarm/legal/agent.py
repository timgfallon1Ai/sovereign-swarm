"""LegalAgent -- legal and compliance for the Sovereign AI swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class LegalAgent(SwarmAgent):
    """Generates contracts, checks compliance, monitors regulatory changes."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._contract_gen: Any | None = None
        self._compliance: Any | None = None
        self._regulatory: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="legal",
            description=(
                "Legal and compliance agent -- generates contracts, checks "
                "trading/data/financial/employment compliance, monitors regulatory changes"
            ),
            domains=["legal", "compliance", "regulatory", "contracts", "tax"],
            supported_intents=[
                "generate_contract",
                "compliance_check",
                "regulatory_alerts",
                "tax_deadlines",
                "review_document",
            ],
            capabilities=[
                "generate_contract",
                "compliance_check",
                "regulatory_alerts",
                "tax_deadlines",
                "review_document",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route legal requests to the appropriate handler."""
        task = request.task.lower()

        try:
            if "contract" in task or "draft" in task or "generate" in task:
                result = await self._handle_contract(request)
            elif "compliance" in task or "check" in task:
                result = await self._handle_compliance(request)
            elif "regulat" in task or "alert" in task:
                result = await self._handle_regulatory(request)
            elif "tax" in task or "deadline" in task:
                result = await self._handle_tax(request)
            elif "review" in task:
                result = await self._handle_review(request)
            else:
                result = await self._handle_compliance(request)

            return SwarmAgentResponse(
                agent_name="legal",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=0.75,
            )
        except Exception as e:
            logger.error("legal.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="legal",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_contract(self, request: SwarmAgentRequest) -> dict:
        from sovereign_swarm.legal.models import ContractType

        contract_type_str = request.parameters.get("type", "service_agreement")
        try:
            contract_type = ContractType(contract_type_str)
        except ValueError:
            return {
                "markdown": f"Unknown contract type: {contract_type_str}. "
                f"Available: {', '.join(ct.value for ct in ContractType)}"
            }

        variables = request.parameters.get("variables", {})
        generator = self._get_contract_gen()
        draft = generator.generate(contract_type, variables)

        lines = [
            f"## Contract Draft: {contract_type.value}",
            f"**Parties**: {', '.join(draft.parties) if draft.parties else 'Not specified'}",
            f"**Review required**: {draft.review_required}",
            f"\n---\n",
            draft.full_text[:3000],
        ]
        if len(draft.full_text) > 3000:
            lines.append("\n... [truncated -- full text in data.contract.full_text]")

        return {
            "markdown": "\n".join(lines),
            "contract": draft.model_dump(),
        }

    async def _handle_compliance(self, request: SwarmAgentRequest) -> dict:
        context = request.parameters.get("context", request.context)
        checker = self._get_compliance()
        checks = checker.check_all(context)

        lines = ["## Compliance Report\n"]
        for check in checks:
            icon = {"pass": "PASS", "warning": "WARN", "fail": "FAIL"}.get(check.status, "?")
            lines.append(f"### [{icon}] {check.area}")
            if check.issues:
                for issue in check.issues:
                    lines.append(f"  - ISSUE: {issue}")
            if check.recommendations:
                for rec in check.recommendations:
                    lines.append(f"  - REC: {rec}")
            if not check.issues and not check.recommendations:
                lines.append("  No issues found.")
            lines.append("")

        return {
            "markdown": "\n".join(lines),
            "checks": [c.model_dump() for c in checks],
        }

    async def _handle_regulatory(self, request: SwarmAgentRequest) -> dict:
        monitor = self._get_regulatory()
        alerts = await monitor.check_for_updates()

        lines = [f"## Regulatory Alerts: {len(alerts)}\n"]
        for alert in alerts:
            lines.append(
                f"### [{alert.impact.upper()}] {alert.regulation}\n"
                f"{alert.change_description}\n"
                f"**Action**: {alert.action_required}\n"
            )

        if not alerts:
            lines.append("No new regulatory alerts.")

        return {
            "markdown": "\n".join(lines),
            "alerts": [a.model_dump() for a in alerts],
            "sources": monitor.get_sources(),
        }

    async def _handle_tax(self, request: SwarmAgentRequest) -> dict:
        from datetime import datetime

        from sovereign_swarm.legal.models import TaxDocument

        # Phase A: static tax deadline reminders
        now = datetime.utcnow()
        year = now.year

        deadlines = [
            TaxDocument(
                type="quarterly_estimate",
                period=f"{year}-Q1",
                due_date=datetime(year, 4, 15),
                status="pending" if now < datetime(year, 4, 15) else "overdue",
            ),
            TaxDocument(
                type="quarterly_estimate",
                period=f"{year}-Q2",
                due_date=datetime(year, 6, 15),
                status="pending" if now < datetime(year, 6, 15) else "overdue",
            ),
            TaxDocument(
                type="quarterly_estimate",
                period=f"{year}-Q3",
                due_date=datetime(year, 9, 15),
                status="pending" if now < datetime(year, 9, 15) else "overdue",
            ),
            TaxDocument(
                type="quarterly_estimate",
                period=f"{year}-Q4",
                due_date=datetime(year + 1, 1, 15),
                status="pending",
            ),
            TaxDocument(
                type="annual_return",
                period=str(year - 1),
                due_date=datetime(year, 4, 15),
                status="pending" if now < datetime(year, 4, 15) else "overdue",
            ),
        ]

        lines = ["## Tax Deadlines\n"]
        for td in deadlines:
            due_str = td.due_date.strftime("%B %d, %Y") if td.due_date else "TBD"
            status_icon = {"pending": "UPCOMING", "filed": "FILED", "overdue": "OVERDUE"}.get(td.status, "?")
            lines.append(f"- [{status_icon}] **{td.type}** ({td.period}): due {due_str}")

        return {
            "markdown": "\n".join(lines),
            "deadlines": [td.model_dump() for td in deadlines],
        }

    async def _handle_review(self, request: SwarmAgentRequest) -> dict:
        """Review a document for legal/compliance concerns (Phase A: stub)."""
        text = request.parameters.get("text", "")
        if not text:
            return {"markdown": "No document text provided for review."}

        # Phase A: basic keyword scanning
        concerns: list[str] = []
        text_lower = text.lower()

        red_flags = {
            "indemnif": "Indemnification clause detected -- review liability exposure",
            "unlimited liability": "Unlimited liability clause -- negotiate cap",
            "non-compete": "Non-compete clause -- review scope and duration",
            "auto-renew": "Auto-renewal clause -- set calendar reminder",
            "governing law": "Check governing law jurisdiction is acceptable",
            "arbitration": "Mandatory arbitration clause -- review enforceability",
            "intellectual property": "IP assignment clause -- verify ownership terms",
        }

        for keyword, concern in red_flags.items():
            if keyword in text_lower:
                concerns.append(concern)

        lines = [f"## Document Review: {len(concerns)} concerns found\n"]
        for c in concerns:
            lines.append(f"- {c}")
        if not concerns:
            lines.append("No obvious concerns detected (attorney review still recommended).")

        return {
            "markdown": "\n".join(lines),
            "concerns": concerns,
            "disclaimer": "This is automated screening only. Professional legal review is required.",
        }

    # ------------------------------------------------------------------
    # Lazy accessors
    # ------------------------------------------------------------------

    def _get_contract_gen(self):
        if self._contract_gen is None:
            from sovereign_swarm.legal.contract_generator import ContractGenerator

            self._contract_gen = ContractGenerator()
        return self._contract_gen

    def _get_compliance(self):
        if self._compliance is None:
            from sovereign_swarm.legal.compliance_checker import ComplianceChecker

            self._compliance = ComplianceChecker()
        return self._compliance

    def _get_regulatory(self):
        if self._regulatory is None:
            from sovereign_swarm.legal.regulatory_monitor import RegulatoryMonitor

            self._regulatory = RegulatoryMonitor()
        return self._regulatory

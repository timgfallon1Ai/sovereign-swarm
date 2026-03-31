"""Compliance checking across trading, data, financial, and employment domains."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.legal.models import ComplianceCheck

logger = structlog.get_logger()


class ComplianceChecker:
    """Checks system operations against regulatory requirements."""

    def check_all(self, context: dict[str, Any] | None = None) -> list[ComplianceCheck]:
        """Run all compliance checks and return results."""
        context = context or {}
        results: list[ComplianceCheck] = []

        results.append(self.check_trading(context.get("trading", {})))
        results.append(self.check_data_privacy(context.get("data", {})))
        results.append(self.check_financial(context.get("financial", {})))
        results.append(self.check_employment(context.get("employment", {})))

        return results

    def check_trading(self, context: dict[str, Any]) -> ComplianceCheck:
        """Check trading compliance: CFTC (Kalshi), SEC (equities)."""
        issues: list[str] = []
        recommendations: list[str] = []

        # Kalshi / CFTC checks
        kalshi_positions = context.get("kalshi_positions", [])
        for pos in kalshi_positions:
            contracts = pos.get("contracts", 0)
            # Kalshi position limits vary by market -- flag large positions
            if contracts > 25000:
                issues.append(
                    f"Kalshi position in {pos.get('market', '?')} "
                    f"({contracts} contracts) may exceed limits"
                )

        # SEC equities checks
        equities_trades = context.get("equities_trades_today", 0)
        if equities_trades > 100:
            recommendations.append(
                "High trade volume today -- ensure pattern day trader rules are met"
            )

        # Check for wash sales
        wash_sale_risk = context.get("wash_sale_candidates", [])
        if wash_sale_risk:
            issues.append(
                f"{len(wash_sale_risk)} potential wash sale(s) detected"
            )
            recommendations.append("Review wash sale candidates before year-end")

        status = "fail" if issues else "pass"
        if not issues and recommendations:
            status = "warning"

        return ComplianceCheck(
            area="trading",
            status=status,
            issues=issues,
            recommendations=recommendations,
        )

    def check_data_privacy(self, context: dict[str, Any]) -> ComplianceCheck:
        """Check data privacy compliance: GDPR, CCPA."""
        issues: list[str] = []
        recommendations: list[str] = []

        # GDPR: data subject rights
        pending_requests = context.get("pending_dsar_requests", 0)
        if pending_requests > 0:
            oldest_days = context.get("oldest_dsar_days", 0)
            if oldest_days > 25:
                issues.append(
                    f"DSAR request {oldest_days} days old -- GDPR requires response within 30 days"
                )
            else:
                recommendations.append(
                    f"{pending_requests} pending DSAR request(s) -- track deadlines"
                )

        # Data retention
        retention_violations = context.get("retention_violations", 0)
        if retention_violations > 0:
            issues.append(
                f"{retention_violations} data retention policy violation(s)"
            )

        # CCPA opt-out
        if not context.get("ccpa_opt_out_enabled", True):
            issues.append("CCPA opt-out mechanism not enabled")

        # Consent tracking
        if not context.get("consent_records_current", True):
            recommendations.append("Update consent records for all data subjects")

        status = "fail" if issues else "pass"
        if not issues and recommendations:
            status = "warning"

        return ComplianceCheck(
            area="data_privacy",
            status=status,
            issues=issues,
            recommendations=recommendations,
        )

    def check_financial(self, context: dict[str, Any]) -> ComplianceCheck:
        """Check financial compliance: AML/KYC basics, transaction reporting."""
        issues: list[str] = []
        recommendations: list[str] = []

        # Transaction reporting thresholds
        large_transactions = context.get("transactions_over_10k", 0)
        if large_transactions > 0:
            recommendations.append(
                f"{large_transactions} transaction(s) over $10,000 -- "
                "ensure CTR (Currency Transaction Report) filing"
            )

        # Suspicious activity
        suspicious_patterns = context.get("suspicious_activity_flags", 0)
        if suspicious_patterns > 0:
            issues.append(
                f"{suspicious_patterns} suspicious activity flag(s) -- "
                "SAR filing may be required"
            )

        # Tax estimated payments
        next_tax_payment = context.get("next_estimated_tax_due", "")
        if next_tax_payment:
            recommendations.append(
                f"Next estimated tax payment due: {next_tax_payment}"
            )

        status = "fail" if issues else "pass"
        if not issues and recommendations:
            status = "warning"

        return ComplianceCheck(
            area="financial",
            status=status,
            issues=issues,
            recommendations=recommendations,
        )

    def check_employment(self, context: dict[str, Any]) -> ComplianceCheck:
        """Check employment compliance: EEO, wage/hour (for GBB staff)."""
        issues: list[str] = []
        recommendations: list[str] = []

        # Wage/hour
        employees = context.get("employees", [])
        for emp in employees:
            hours = emp.get("weekly_hours", 0)
            overtime_eligible = emp.get("overtime_eligible", True)
            if hours > 40 and overtime_eligible:
                overtime_hours = hours - 40
                if not emp.get("overtime_paid", False):
                    issues.append(
                        f"Employee {emp.get('name', '?')} worked {overtime_hours} "
                        f"overtime hours without overtime pay"
                    )

        # I-9 verification
        pending_i9 = context.get("pending_i9_verifications", 0)
        if pending_i9 > 0:
            recommendations.append(
                f"{pending_i9} pending I-9 verification(s) -- complete within 3 business days of hire"
            )

        status = "fail" if issues else "pass"
        if not issues and recommendations:
            status = "warning"

        return ComplianceCheck(
            area="employment",
            status=status,
            issues=issues,
            recommendations=recommendations,
        )

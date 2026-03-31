"""FinancialOpsAgent -- cross-entity financial operations for the swarm."""

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


class FinancialOpsAgent(SwarmAgent):
    """Financial operations agent.

    Aggregates data from ATS (trading), GBB (jiu-jitsu business), GLI
    (consulting), and personal accounts to produce net-worth snapshots,
    P&L reports, cash-flow forecasts, and tax estimates.
    """

    def __init__(
        self,
        ingest_bridge: Any | None = None,
        config: Any | None = None,
    ):
        self.ingest = ingest_bridge
        self.config = config
        self._aggregator = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="financial_ops",
            description=(
                "Financial operations agent -- net worth, P&L, cash-flow "
                "forecasts, and tax estimates across ATS, GBB, GLI, and "
                "personal accounts"
            ),
            domains=[
                "finance",
                "accounting",
                "tax",
                "pnl",
                "cash_flow",
                "budget",
            ],
            supported_intents=[
                "net_worth",
                "pnl_report",
                "cash_flow_forecast",
                "tax_estimate",
                "account_summary",
                "transaction_search",
            ],
            capabilities=[
                "net_worth",
                "pnl_report",
                "cash_flow_forecast",
                "tax_estimate",
                "account_summary",
                "transaction_search",
            ],
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route a financial task to the appropriate handler."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if "net worth" in task:
                result = await self._net_worth()
            elif "p&l" in task or "profit" in task or "loss" in task or "pnl" in task:
                result = await self._pnl_report(params)
            elif "cash flow" in task or "forecast" in task:
                result = await self._cash_flow_forecast(params)
            elif "tax" in task:
                result = await self._tax_estimate(params)
            elif "account" in task or "balance" in task:
                result = await self._account_summary()
            else:
                # Default to account summary
                result = await self._account_summary()

            return SwarmAgentResponse(
                agent_name="financial_ops",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.8),
            )
        except Exception as e:
            logger.error("financial_ops.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="financial_ops",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _net_worth(self) -> dict:
        aggregator = self._get_aggregator()
        nw = await aggregator.get_net_worth()

        md = "## Net Worth Summary\n\n"
        md += f"**Total**: ${nw['total']:,.2f}\n\n"

        if nw["by_type"]:
            md += "| Account Type | Balance |\n"
            md += "|--------------|----------|\n"
            for acct_type, balance in sorted(
                nw["by_type"].items(), key=lambda x: -x[1]
            ):
                md += f"| {acct_type.replace('_', ' ').title()} | ${balance:,.2f} |\n"

        md += f"\n*{nw['account_count']} account(s) aggregated*\n"
        return {"markdown": md, "net_worth": nw, "confidence": 0.8}

    async def _pnl_report(self, params: dict) -> dict:
        aggregator = self._get_aggregator()
        period = params.get("period", "monthly")
        pnl = await aggregator.get_pnl(period)

        md = f"## P&L Report ({pnl.period.title()})\n\n"
        md += f"**Period**: {pnl.start_date.strftime('%Y-%m-%d')} to {pnl.end_date.strftime('%Y-%m-%d')}\n\n"
        md += f"| Metric | Amount |\n"
        md += f"|--------|--------|\n"
        md += f"| Revenue | ${pnl.revenue:,.2f} |\n"
        md += f"| Expenses | ${pnl.expenses:,.2f} |\n"
        md += f"| **Net Income** | **${pnl.net_income:,.2f}** |\n"

        if pnl.by_entity:
            md += "\n### By Entity\n\n"
            md += "| Entity | Net |\n"
            md += "|--------|-----|\n"
            for entity, net in sorted(
                pnl.by_entity.items(), key=lambda x: -x[1]
            ):
                md += f"| {entity} | ${net:,.2f} |\n"

        return {"markdown": md, "pnl": pnl.model_dump(), "confidence": 0.75}

    async def _cash_flow_forecast(self, params: dict) -> dict:
        aggregator = self._get_aggregator()
        months = params.get("months", params.get("months_ahead", 3))
        forecasts = await aggregator.forecast_cash_flow(months_ahead=months)

        md = f"## Cash Flow Forecast ({months} months)\n\n"
        md += "| Month | Projected Balance | Inflows | Outflows |\n"
        md += "|-------|-------------------|---------|----------|\n"
        for f in forecasts:
            md += (
                f"| {f.forecast_date.strftime('%B %Y')} "
                f"| ${f.projected_balance:,.2f} "
                f"| ${f.inflows:,.2f} "
                f"| ${f.outflows:,.2f} |\n"
            )

        if forecasts and forecasts[0].assumptions:
            md += "\n### Assumptions\n"
            for a in forecasts[0].assumptions:
                md += f"- {a}\n"

        return {
            "markdown": md,
            "forecasts": [f.model_dump() for f in forecasts],
            "confidence": 0.6,
        }

    async def _tax_estimate(self, params: dict) -> dict:
        aggregator = self._get_aggregator()
        period = params.get("period", "quarterly")
        tax = await aggregator.estimate_taxes(period)

        md = f"## Tax Estimate ({tax.period.title()})\n\n"
        md += "| Metric | Amount |\n"
        md += "|--------|--------|\n"
        md += f"| Estimated Income (YTD) | ${tax.estimated_income:,.2f} |\n"
        md += f"| Estimated Tax | ${tax.estimated_tax:,.2f} |\n"
        md += f"| Effective Rate | {tax.effective_rate:.1%} |\n"
        md += f"| **Quarterly Payment** | **${tax.quarterly_payment:,.2f}** |\n"

        if tax.notes:
            md += "\n### Notes\n"
            for n in tax.notes:
                md += f"- {n}\n"

        return {"markdown": md, "tax": tax.model_dump(), "confidence": 0.65}

    async def _account_summary(self) -> dict:
        aggregator = self._get_aggregator()
        accounts = await aggregator.get_all_accounts()

        if not accounts:
            md = (
                "## Account Summary\n\n"
                "No accounts connected. ATS, GBB, and Plaid services may be offline."
            )
            return {"markdown": md, "accounts": [], "confidence": 0.7}

        total = sum(a.balance for a in accounts)
        md = "## Account Summary\n\n"
        md += "| Account | Institution | Type | Balance |\n"
        md += "|---------|-------------|------|---------|\n"
        for a in sorted(accounts, key=lambda x: -x.balance):
            synced = (
                a.last_synced.strftime("%H:%M") if a.last_synced else "never"
            )
            md += (
                f"| {a.name} | {a.institution} "
                f"| {a.account_type.value.replace('_', ' ').title()} "
                f"| ${a.balance:,.2f} |\n"
            )

        md += f"\n**Total across all accounts**: ${total:,.2f}\n"
        return {
            "markdown": md,
            "accounts": [a.model_dump() for a in accounts],
            "total": total,
            "confidence": 0.8,
        }

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_aggregator(self):
        if self._aggregator is None:
            from sovereign_swarm.financial_ops.aggregator import (
                FinancialAggregator,
            )

            self._aggregator = FinancialAggregator(
                config=self.config,
                ingest_bridge=self.ingest,
            )
        return self._aggregator

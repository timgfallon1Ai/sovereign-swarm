"""Aggregates financial data across all entities (ATS, GBB, GLI, personal)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.financial_ops.models import (
    AccountType,
    CashFlowForecast,
    FinancialAccount,
    ProfitLoss,
    TaxEstimate,
)

logger = structlog.get_logger()


class FinancialAggregator:
    """Aggregates financial data across ATS, GBB, GLI, and personal accounts."""

    def __init__(
        self,
        config: Any | None = None,
        ingest_bridge: Any | None = None,
    ):
        self.config = config
        self.ingest = ingest_bridge
        self._accounts: list[FinancialAccount] = []

    # ------------------------------------------------------------------
    # Account aggregation
    # ------------------------------------------------------------------

    async def get_all_accounts(self) -> list[FinancialAccount]:
        """Aggregate accounts from all sources."""
        accounts: list[FinancialAccount] = []

        # ATS Trading accounts
        accounts.extend(await self._get_ats_accounts())

        # GBB accounts
        accounts.extend(await self._get_gbb_accounts())

        # Plaid-connected accounts (Phase B)
        accounts.extend(await self._get_plaid_accounts())

        self._accounts = accounts
        return accounts

    async def get_net_worth(self) -> dict:
        """Calculate total net worth across all accounts."""
        accounts = await self.get_all_accounts()
        total = sum(a.balance for a in accounts)
        by_type: dict[str, float] = {}
        for a in accounts:
            by_type.setdefault(a.account_type.value, 0)
            by_type[a.account_type.value] += a.balance
        return {
            "total": total,
            "by_type": by_type,
            "account_count": len(accounts),
        }

    # ------------------------------------------------------------------
    # P&L
    # ------------------------------------------------------------------

    async def get_pnl(self, period: str = "monthly") -> ProfitLoss:
        """Calculate P&L across all entities."""
        now = datetime.now()

        if period == "daily":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "weekly":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "ytd":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # monthly
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        by_entity: dict[str, float] = {}

        # ATS trading P&L
        ats_pnl = await self._get_ats_pnl(start, now)
        if ats_pnl:
            by_entity["ATS Trading"] = ats_pnl

        # GBB business P&L
        gbb_pnl = await self._get_gbb_pnl(start, now)
        if gbb_pnl:
            by_entity["Gracie Barra Buda"] = gbb_pnl

        revenue = sum(v for v in by_entity.values() if v > 0)
        expenses = abs(sum(v for v in by_entity.values() if v < 0))
        net_income = revenue - expenses

        return ProfitLoss(
            period=period,
            start_date=start,
            end_date=now,
            revenue=revenue,
            expenses=expenses,
            net_income=net_income,
            by_entity=by_entity,
        )

    # ------------------------------------------------------------------
    # Cash flow forecast
    # ------------------------------------------------------------------

    async def forecast_cash_flow(
        self, months_ahead: int = 3
    ) -> list[CashFlowForecast]:
        """Project cash flow based on historical patterns."""
        accounts = await self.get_all_accounts()
        current_balance = sum(a.balance for a in accounts)

        forecasts: list[CashFlowForecast] = []
        now = datetime.now()

        for month_offset in range(1, months_ahead + 1):
            forecast_date = now + timedelta(days=30 * month_offset)
            # Phase A: simple projection placeholder
            inflows = 0.0
            outflows = 0.0
            projected = current_balance + inflows - outflows

            forecasts.append(
                CashFlowForecast(
                    forecast_date=forecast_date,
                    projected_balance=projected,
                    inflows=inflows,
                    outflows=outflows,
                    assumptions=[
                        "Phase A stub -- no historical data ingested yet",
                        "Connect Plaid + ATS for real projections",
                    ],
                )
            )

        return forecasts

    # ------------------------------------------------------------------
    # Tax estimation
    # ------------------------------------------------------------------

    async def estimate_taxes(self, period: str = "quarterly") -> TaxEstimate:
        """Estimate tax obligations based on income."""
        pnl = await self.get_pnl("ytd")
        estimated_income = pnl.net_income

        # Simplified US tax estimate (self-employment + income)
        se_tax_rate = 0.153  # 15.3% SE tax
        income_tax_rate = 0.22  # estimated marginal bracket
        effective_rate = se_tax_rate + income_tax_rate * (1 - se_tax_rate / 2)

        estimated_tax = estimated_income * effective_rate
        quarterly_payment = estimated_tax / 4

        return TaxEstimate(
            period=period,
            estimated_income=estimated_income,
            estimated_tax=estimated_tax,
            effective_rate=effective_rate,
            quarterly_payment=max(quarterly_payment, 0),
            notes=[
                "Simplified estimate -- consult CPA for actual filing",
                f"Assumes {income_tax_rate:.0%} marginal income tax rate",
                "Includes self-employment tax at 15.3%",
            ],
        )

    # ------------------------------------------------------------------
    # Data source connectors
    # ------------------------------------------------------------------

    async def _get_ats_accounts(self) -> list[FinancialAccount]:
        """Get trading account balances from ATS."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("http://localhost:8081/portfolio")
                if resp.status_code == 200:
                    data = resp.json()
                    accounts: list[FinancialAccount] = []
                    for acct in data.get("accounts", [data]):
                        accounts.append(
                            FinancialAccount(
                                id=f"ats_{acct.get('id', 'main')}",
                                name="ATS Trading",
                                institution="Interactive Brokers / Kalshi",
                                account_type=AccountType.TRADING,
                                balance=acct.get(
                                    "total_value", acct.get("balance", 0)
                                ),
                                last_synced=datetime.now(),
                            )
                        )
                    return accounts
        except Exception as exc:
            logger.debug("aggregator.ats_unavailable", error=str(exc))
        return []

    async def _get_gbb_accounts(self) -> list[FinancialAccount]:
        """Get GBB business account data."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "http://localhost:8002/api/accounting/summary"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [
                        FinancialAccount(
                            id="gbb_main",
                            name="Gracie Barra Buda",
                            institution=data.get("institution", "Bank"),
                            account_type=AccountType.CHECKING,
                            balance=data.get("balance", 0),
                            last_synced=datetime.now(),
                        )
                    ]
        except Exception as exc:
            logger.debug("aggregator.gbb_unavailable", error=str(exc))
        return []

    async def _get_plaid_accounts(self) -> list[FinancialAccount]:
        """Get Plaid-connected bank accounts."""
        # Phase B: implement Plaid API integration
        return []

    async def _get_ats_pnl(
        self, start: datetime, end: datetime
    ) -> float:
        """Fetch ATS trading P&L for a period."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "http://localhost:8081/pnl",
                    params={
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("net_pnl", 0.0)
        except Exception:
            pass
        return 0.0

    async def _get_gbb_pnl(
        self, start: datetime, end: datetime
    ) -> float:
        """Fetch GBB business P&L for a period."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "http://localhost:8002/api/accounting/pnl",
                    params={
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("net_income", 0.0)
        except Exception:
            pass
        return 0.0

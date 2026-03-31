"""Wealth tracking and net worth aggregation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.personal_finance.models import (
    AccountKind,
    NetWorthSnapshot,
    PersonalAccount,
)

logger = structlog.get_logger()


class WealthTracker:
    """Aggregates personal accounts and calculates net worth over time.

    Tracks bank, brokerage, 401k, real estate equity, and crypto accounts.
    Produces net worth snapshots and month-over-month change analysis.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, PersonalAccount] = {}
        self._snapshots: list[NetWorthSnapshot] = []

    def add_account(self, account: PersonalAccount) -> None:
        """Register or update a personal account."""
        self._accounts[account.id or account.name] = account
        logger.info("wealth_tracker.account_added", name=account.name)

    def remove_account(self, account_id: str) -> bool:
        """Remove an account from tracking."""
        return self._accounts.pop(account_id, None) is not None

    def get_accounts(self) -> list[PersonalAccount]:
        """Return all tracked accounts."""
        return list(self._accounts.values())

    def calculate_net_worth(self) -> NetWorthSnapshot:
        """Calculate current net worth from all accounts."""
        assets = 0.0
        liabilities = 0.0
        by_type: dict[str, float] = {}

        for account in self._accounts.values():
            type_key = account.account_type.value
            if account.is_liability:
                liabilities += abs(account.balance)
                by_type[type_key] = by_type.get(type_key, 0) - abs(account.balance)
            else:
                assets += account.balance
                by_type[type_key] = by_type.get(type_key, 0) + account.balance

        snapshot = NetWorthSnapshot(
            assets=assets,
            liabilities=liabilities,
            total=assets - liabilities,
            by_type=by_type,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def month_over_month(self) -> dict[str, Any]:
        """Calculate month-over-month net worth changes."""
        if len(self._snapshots) < 2:
            current = self.calculate_net_worth() if not self._snapshots else self._snapshots[-1]
            return {
                "current": current.total,
                "previous": None,
                "change": 0.0,
                "change_pct": 0.0,
                "note": "Not enough history for comparison",
            }

        current = self._snapshots[-1]
        previous = self._snapshots[-2]
        change = current.total - previous.total
        change_pct = (change / abs(previous.total) * 100) if previous.total != 0 else 0

        return {
            "current": current.total,
            "previous": previous.total,
            "change": change,
            "change_pct": round(change_pct, 2),
        }

    def format_net_worth_markdown(self, snapshot: NetWorthSnapshot) -> str:
        """Format net worth snapshot as markdown."""
        lines = [
            "## Net Worth Summary\n",
            f"**Total Net Worth:** ${snapshot.total:,.2f}",
            f"**Assets:** ${snapshot.assets:,.2f}",
            f"**Liabilities:** ${snapshot.liabilities:,.2f}\n",
        ]

        if snapshot.by_type:
            lines.append("### By Account Type\n")
            lines.append("| Type | Balance |")
            lines.append("|------|---------|")
            for acct_type, balance in sorted(
                snapshot.by_type.items(), key=lambda x: -x[1]
            ):
                label = acct_type.replace("_", " ").title()
                lines.append(f"| {label} | ${balance:,.2f} |")
            lines.append("")

        mom = self.month_over_month()
        if mom["previous"] is not None:
            direction = "up" if mom["change"] >= 0 else "down"
            lines.append(
                f"**Month-over-month:** ${mom['change']:+,.2f} "
                f"({mom['change_pct']:+.1f}%) -- {direction}"
            )

        lines.append(f"\n*Snapshot taken: {snapshot.date.strftime('%Y-%m-%d %H:%M')}*")
        return "\n".join(lines)

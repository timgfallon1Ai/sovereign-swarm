"""Budget management with category tracking and alerts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.personal_finance.models import (
    Budget,
    BudgetCategory,
    BudgetStatus,
)

logger = structlog.get_logger()

# Default budget categories with suggested limits
_DEFAULT_CATEGORIES = [
    {"name": "Housing", "limit": 2000},
    {"name": "Food & Groceries", "limit": 600},
    {"name": "Transportation", "limit": 400},
    {"name": "Entertainment", "limit": 200},
    {"name": "Subscriptions", "limit": 150},
    {"name": "Health & Fitness", "limit": 200},
    {"name": "Savings", "limit": 500},
    {"name": "Investment", "limit": 500},
    {"name": "Utilities", "limit": 300},
    {"name": "Insurance", "limit": 400},
    {"name": "Personal Care", "limit": 100},
    {"name": "Miscellaneous", "limit": 200},
]


class BudgetManager:
    """Category-based budgeting with spend tracking and alerts.

    Tracks spending against category limits, alerts when approaching
    budget thresholds, and provides spending analysis.
    """

    def __init__(self) -> None:
        self._budgets: dict[str, Budget] = {}  # month -> budget

    def create_budget(
        self,
        month: str | None = None,
        categories: list[dict[str, Any]] | None = None,
    ) -> Budget:
        """Create a budget for a given month."""
        month = month or datetime.now().strftime("%Y-%m")
        cats = categories or _DEFAULT_CATEGORIES

        budget_categories = [
            BudgetCategory(
                name=c["name"],
                monthly_limit=c.get("limit", 0),
            )
            for c in cats
        ]

        budget = Budget(
            month=month,
            categories=budget_categories,
            total_limit=sum(c.monthly_limit for c in budget_categories),
        )
        self._budgets[month] = budget
        return budget

    def record_expense(
        self, category_name: str, amount: float, month: str | None = None
    ) -> BudgetCategory | None:
        """Record an expense against a budget category."""
        month = month or datetime.now().strftime("%Y-%m")
        budget = self._budgets.get(month)
        if not budget:
            return None

        for cat in budget.categories:
            if cat.name.lower() == category_name.lower():
                cat.actual_spend += amount
                cat.status = self._compute_status(cat)
                budget.total_spent = sum(c.actual_spend for c in budget.categories)
                return cat

        return None

    def get_budget(self, month: str | None = None) -> Budget | None:
        """Get budget for a specific month."""
        month = month or datetime.now().strftime("%Y-%m")
        return self._budgets.get(month)

    def get_alerts(self, month: str | None = None) -> list[dict[str, Any]]:
        """Get budget alerts for categories approaching or over limit."""
        month = month or datetime.now().strftime("%Y-%m")
        budget = self._budgets.get(month)
        if not budget:
            return []

        alerts: list[dict[str, Any]] = []
        for cat in budget.categories:
            if cat.monthly_limit <= 0:
                continue
            utilization = cat.utilization_pct
            if utilization >= 100:
                alerts.append({
                    "category": cat.name,
                    "level": "over",
                    "message": f"{cat.name}: OVER BUDGET by ${cat.actual_spend - cat.monthly_limit:,.2f}",
                    "utilization": utilization,
                })
            elif utilization >= 80:
                alerts.append({
                    "category": cat.name,
                    "level": "warning",
                    "message": f"{cat.name}: {utilization:.0f}% spent (${cat.remaining:,.2f} remaining)",
                    "utilization": utilization,
                })

        return alerts

    def spending_analysis(self, month: str | None = None) -> dict[str, Any]:
        """Analyze spending patterns for a month."""
        month = month or datetime.now().strftime("%Y-%m")
        budget = self._budgets.get(month)
        if not budget:
            return {"error": f"No budget found for {month}"}

        total_spent = sum(c.actual_spend for c in budget.categories)
        total_limit = sum(c.monthly_limit for c in budget.categories)

        top_categories = sorted(
            budget.categories, key=lambda c: c.actual_spend, reverse=True
        )[:5]

        over_budget = [c for c in budget.categories if c.status == BudgetStatus.OVER]

        return {
            "month": month,
            "total_spent": total_spent,
            "total_limit": total_limit,
            "overall_utilization": round((total_spent / max(total_limit, 1)) * 100, 1),
            "top_spending": [
                {"name": c.name, "spent": c.actual_spend, "limit": c.monthly_limit}
                for c in top_categories
            ],
            "over_budget_count": len(over_budget),
            "categories_over": [c.name for c in over_budget],
        }

    def format_budget_markdown(self, budget: Budget) -> str:
        """Format budget status as markdown."""
        lines = [
            f"## Budget: {budget.month}\n",
            f"**Total Budget:** ${budget.total_limit:,.2f}",
            f"**Total Spent:** ${budget.total_spent:,.2f}",
            f"**Remaining:** ${budget.total_limit - budget.total_spent:,.2f}\n",
            "| Category | Limit | Spent | Remaining | Status |",
            "|----------|-------|-------|-----------|--------|",
        ]

        for cat in budget.categories:
            status_icon = {
                BudgetStatus.UNDER: "OK",
                BudgetStatus.ON_TRACK: "OK",
                BudgetStatus.OVER: "OVER",
            }.get(cat.status, "OK")
            lines.append(
                f"| {cat.name} "
                f"| ${cat.monthly_limit:,.2f} "
                f"| ${cat.actual_spend:,.2f} "
                f"| ${cat.remaining:,.2f} "
                f"| {status_icon} |"
            )

        # Alerts
        alerts = self.get_alerts(budget.month)
        if alerts:
            lines.append("\n### Alerts\n")
            for alert in alerts:
                lines.append(f"- **{alert['level'].upper()}:** {alert['message']}")

        return "\n".join(lines)

    @staticmethod
    def _compute_status(cat: BudgetCategory) -> BudgetStatus:
        """Compute budget status for a category."""
        if cat.monthly_limit <= 0:
            return BudgetStatus.ON_TRACK
        utilization = cat.utilization_pct
        if utilization >= 100:
            return BudgetStatus.OVER
        elif utilization <= 50:
            return BudgetStatus.UNDER
        return BudgetStatus.ON_TRACK

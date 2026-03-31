"""PersonalFinanceAgent -- personal wealth and budget management for the swarm."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.personal_finance.models import (
    AccountKind,
    BillReminder,
    PersonalAccount,
)
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class PersonalFinanceAgent(SwarmAgent):
    """Personal finance agent.

    Tracks net worth, manages budgets, monitors financial goals,
    handles bill reminders, and produces spending analyses.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._wealth_tracker = None
        self._budget_manager = None
        self._goal_tracker = None
        self._bills: list[BillReminder] = []

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="PersonalFinanceAgent",
            description=(
                "Personal finance agent -- net worth tracking, budget management, "
                "financial goal progress, bill reminders, and spending analysis."
            ),
            version="0.1.0",
            domains=["personal_finance", "budget", "net_worth", "goals", "bills"],
            supported_intents=[
                "net_worth",
                "budget_status",
                "goal_progress",
                "bill_reminders",
                "spending_analysis",
            ],
            capabilities=[
                "net_worth",
                "budget_status",
                "goal_progress",
                "bill_reminders",
                "spending_analysis",
            ],
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route a personal finance task to the appropriate handler."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if any(kw in task for kw in ("net worth", "wealth", "total")):
                result = await self._handle_net_worth(params)
            elif any(kw in task for kw in ("budget", "spending", "expense")):
                if "analysis" in task or "analyze" in task:
                    result = await self._handle_spending_analysis(params)
                else:
                    result = await self._handle_budget(params)
            elif any(kw in task for kw in ("goal", "target", "saving")):
                result = await self._handle_goals(params)
            elif any(kw in task for kw in ("bill", "payment", "due", "remind")):
                result = await self._handle_bills(params)
            elif "account" in task or "add" in task:
                result = await self._handle_add_account(params)
            else:
                result = await self._handle_net_worth(params)

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.75),
            )
        except Exception as e:
            logger.error("personal_finance.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_add_account(self, params: dict) -> dict:
        """Add a personal account for tracking."""
        tracker = self._get_wealth_tracker()
        account = PersonalAccount(
            id=params.get("id", params.get("name", "account")),
            name=params.get("name", ""),
            account_type=AccountKind(params.get("type", "checking")),
            institution=params.get("institution", ""),
            balance=params.get("balance", 0.0),
            interest_rate=params.get("interest_rate", 0.0),
            is_liability=params.get("is_liability", False),
        )
        tracker.add_account(account)

        md = (
            f"## Account Added: {account.name}\n\n"
            f"**Type:** {account.account_type.value}\n"
            f"**Institution:** {account.institution}\n"
            f"**Balance:** ${account.balance:,.2f}\n"
        )
        return {"markdown": md, "confidence": 0.9}

    async def _handle_net_worth(self, params: dict) -> dict:
        """Calculate and display net worth."""
        tracker = self._get_wealth_tracker()

        # If accounts provided in params, add them
        accounts_data = params.get("accounts", [])
        for ad in accounts_data:
            account = PersonalAccount(
                id=ad.get("id", ad.get("name", "")),
                name=ad.get("name", ""),
                account_type=AccountKind(ad.get("type", "checking")),
                institution=ad.get("institution", ""),
                balance=ad.get("balance", 0.0),
                is_liability=ad.get("is_liability", False),
            )
            tracker.add_account(account)

        snapshot = tracker.calculate_net_worth()
        md = tracker.format_net_worth_markdown(snapshot)

        return {
            "markdown": md,
            "net_worth": snapshot.total,
            "assets": snapshot.assets,
            "liabilities": snapshot.liabilities,
            "confidence": 0.8,
        }

    async def _handle_budget(self, params: dict) -> dict:
        """Show or create budget status."""
        manager = self._get_budget_manager()
        month = params.get("month")

        budget = manager.get_budget(month)
        if not budget:
            categories = params.get("categories")
            budget = manager.create_budget(month, categories)

        # Record expenses if provided
        expenses = params.get("expenses", [])
        for exp in expenses:
            manager.record_expense(
                exp.get("category", ""),
                exp.get("amount", 0),
                month,
            )

        md = manager.format_budget_markdown(budget)
        return {"markdown": md, "total_spent": budget.total_spent, "confidence": 0.75}

    async def _handle_spending_analysis(self, params: dict) -> dict:
        """Analyze spending patterns."""
        manager = self._get_budget_manager()
        month = params.get("month")
        analysis = manager.spending_analysis(month)

        if "error" in analysis:
            md = f"## Spending Analysis\n\n{analysis['error']}"
            return {"markdown": md, "confidence": 0.5}

        md = f"## Spending Analysis: {analysis['month']}\n\n"
        md += f"**Total Spent:** ${analysis['total_spent']:,.2f} / ${analysis['total_limit']:,.2f}\n"
        md += f"**Overall Utilization:** {analysis['overall_utilization']}%\n\n"

        md += "### Top Spending Categories\n\n"
        md += "| Category | Spent | Limit |\n"
        md += "|----------|-------|-------|\n"
        for cat in analysis["top_spending"]:
            md += f"| {cat['name']} | ${cat['spent']:,.2f} | ${cat['limit']:,.2f} |\n"

        if analysis["categories_over"]:
            md += f"\n**Over budget:** {', '.join(analysis['categories_over'])}\n"

        return {"markdown": md, "analysis": analysis, "confidence": 0.75}

    async def _handle_goals(self, params: dict) -> dict:
        """Show goal progress or add a new goal."""
        tracker = self._get_goal_tracker()

        # Add goal if params provided
        if "name" in params and "target" in params:
            deadline_str = params.get("deadline")
            deadline = datetime.fromisoformat(deadline_str) if deadline_str else None
            tracker.add_goal(
                name=params["name"],
                target_amount=params["target"],
                current_amount=params.get("current", 0.0),
                deadline=deadline,
                monthly_contribution=params.get("monthly", 0.0),
            )

        md = tracker.format_goals_markdown()
        goals = tracker.get_all_goals()

        return {
            "markdown": md,
            "goal_count": len(goals),
            "confidence": 0.8,
        }

    async def _handle_bills(self, params: dict) -> dict:
        """Show bill reminders or add a new bill."""
        # Add bill if params provided
        if "name" in params and "amount" in params:
            bill = BillReminder(
                id=f"bill_{len(self._bills) + 1}",
                name=params["name"],
                amount=params["amount"],
                due_date=params.get("due_date", 1),
                autopay=params.get("autopay", False),
                account=params.get("account", ""),
                category=params.get("category", ""),
            )
            self._bills.append(bill)

        if not self._bills:
            md = "## Bill Reminders\n\nNo bills tracked. Add a bill to get started."
            return {"markdown": md, "confidence": 0.7}

        # Sort by due date
        sorted_bills = sorted(self._bills, key=lambda b: b.due_date)
        total_monthly = sum(b.amount for b in self._bills)

        md = f"## Bill Reminders ({len(self._bills)} bills)\n\n"
        md += f"**Total Monthly Bills:** ${total_monthly:,.2f}\n\n"
        md += "| Bill | Amount | Due Date | Autopay | Account |\n"
        md += "|------|--------|----------|---------|----------|\n"
        for bill in sorted_bills:
            autopay_str = "Yes" if bill.autopay else "No"
            md += (
                f"| {bill.name} "
                f"| ${bill.amount:,.2f} "
                f"| {bill.due_date}th "
                f"| {autopay_str} "
                f"| {bill.account or 'N/A'} |\n"
            )

        return {
            "markdown": md,
            "bill_count": len(self._bills),
            "total_monthly": total_monthly,
            "confidence": 0.8,
        }

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_wealth_tracker(self):
        if self._wealth_tracker is None:
            from sovereign_swarm.personal_finance.tracker import WealthTracker

            self._wealth_tracker = WealthTracker()
        return self._wealth_tracker

    def _get_budget_manager(self):
        if self._budget_manager is None:
            from sovereign_swarm.personal_finance.budget import BudgetManager

            self._budget_manager = BudgetManager()
        return self._budget_manager

    def _get_goal_tracker(self):
        if self._goal_tracker is None:
            from sovereign_swarm.personal_finance.goals import GoalTracker

            self._goal_tracker = GoalTracker()
        return self._goal_tracker

"""Financial goal tracking with projection calculations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.personal_finance.models import FinancialGoal, GoalStatus

logger = structlog.get_logger()


class GoalTracker:
    """Tracks financial goals and calculates progress.

    Supports goals like emergency fund, house down payment, retirement,
    and specific purchases. Calculates monthly contribution needed and
    projects completion date.
    """

    def __init__(self) -> None:
        self._goals: dict[str, FinancialGoal] = {}

    def add_goal(
        self,
        name: str,
        target_amount: float,
        current_amount: float = 0.0,
        deadline: datetime | None = None,
        monthly_contribution: float = 0.0,
    ) -> FinancialGoal:
        """Add a new financial goal."""
        goal = FinancialGoal(
            id=f"goal_{uuid.uuid4().hex[:8]}",
            name=name,
            target_amount=target_amount,
            current_amount=current_amount,
            deadline=deadline,
            monthly_contribution=monthly_contribution,
        )
        goal.status = self._compute_status(goal)
        self._goals[goal.id] = goal
        return goal

    def update_progress(
        self, goal_id: str, new_amount: float
    ) -> FinancialGoal | None:
        """Update current amount for a goal."""
        goal = self._goals.get(goal_id)
        if not goal:
            return None
        goal.current_amount = new_amount
        goal.status = self._compute_status(goal)
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.COMPLETED
        return goal

    def contribute(self, goal_id: str, amount: float) -> FinancialGoal | None:
        """Add a contribution to a goal."""
        goal = self._goals.get(goal_id)
        if not goal:
            return None
        goal.current_amount += amount
        goal.status = self._compute_status(goal)
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.COMPLETED
        return goal

    def get_all_goals(self) -> list[FinancialGoal]:
        """Return all tracked goals."""
        return list(self._goals.values())

    def calculate_monthly_needed(self, goal: FinancialGoal) -> float:
        """Calculate monthly contribution needed to reach goal by deadline."""
        if goal.status == GoalStatus.COMPLETED:
            return 0.0
        remaining = goal.remaining
        if not goal.deadline:
            return 0.0

        now = datetime.now()
        months_left = (goal.deadline.year - now.year) * 12 + (goal.deadline.month - now.month)
        if months_left <= 0:
            return remaining  # All at once -- past deadline

        return round(remaining / months_left, 2)

    def project_completion_date(self, goal: FinancialGoal) -> datetime | None:
        """Project when goal will be completed at current contribution rate."""
        if goal.status == GoalStatus.COMPLETED:
            return datetime.now()
        if goal.monthly_contribution <= 0:
            return None

        remaining = goal.remaining
        months_needed = remaining / goal.monthly_contribution

        now = datetime.now()
        projected_month = now.month + int(months_needed)
        projected_year = now.year + (projected_month - 1) // 12
        projected_month = ((projected_month - 1) % 12) + 1

        return datetime(projected_year, projected_month, 1)

    def format_goals_markdown(self) -> str:
        """Format all goals as markdown."""
        goals = self.get_all_goals()
        if not goals:
            return "## Financial Goals\n\nNo goals set. Add a goal to start tracking."

        lines = [
            f"## Financial Goals ({len(goals)})\n",
            "| Goal | Target | Current | Progress | Status |",
            "|------|--------|---------|----------|--------|",
        ]

        for g in goals:
            status_label = g.status.value.replace("_", " ").title()
            lines.append(
                f"| {g.name} "
                f"| ${g.target_amount:,.2f} "
                f"| ${g.current_amount:,.2f} "
                f"| {g.progress_pct:.1f}% "
                f"| {status_label} |"
            )

        lines.append("")

        # Details per goal
        for g in goals:
            if g.status == GoalStatus.COMPLETED:
                continue

            lines.append(f"### {g.name}")
            lines.append(f"- **Remaining:** ${g.remaining:,.2f}")

            if g.monthly_contribution > 0:
                lines.append(f"- **Monthly contribution:** ${g.monthly_contribution:,.2f}")
                projected = self.project_completion_date(g)
                if projected:
                    lines.append(f"- **Projected completion:** {projected.strftime('%B %Y')}")

            if g.deadline:
                needed = self.calculate_monthly_needed(g)
                lines.append(f"- **Deadline:** {g.deadline.strftime('%Y-%m-%d')}")
                lines.append(f"- **Monthly needed to hit deadline:** ${needed:,.2f}")

            lines.append("")

        return "\n".join(lines)

    def _compute_status(self, goal: FinancialGoal) -> GoalStatus:
        """Compute goal status based on progress vs. timeline."""
        if goal.current_amount >= goal.target_amount:
            return GoalStatus.COMPLETED
        if not goal.deadline:
            return GoalStatus.ON_TRACK

        now = datetime.now()
        total_duration = (goal.deadline - goal.deadline.replace(year=goal.deadline.year - 1)).days
        elapsed_ratio = max(0, (now - goal.deadline.replace(year=goal.deadline.year - 1)).days) / max(total_duration, 1)
        progress_ratio = goal.progress_pct / 100

        if progress_ratio >= elapsed_ratio + 0.1:
            return GoalStatus.AHEAD
        elif progress_ratio < elapsed_ratio - 0.1:
            return GoalStatus.BEHIND
        return GoalStatus.ON_TRACK

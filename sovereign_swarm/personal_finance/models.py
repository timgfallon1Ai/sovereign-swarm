"""Data models for the Personal Finance agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AccountKind(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    BROKERAGE = "brokerage"
    RETIREMENT_401K = "401k"
    IRA = "ira"
    ROTH_IRA = "roth_ira"
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"
    MORTGAGE = "mortgage"
    OTHER = "other"


class BudgetStatus(str, Enum):
    UNDER = "under"
    ON_TRACK = "on_track"
    OVER = "over"


class GoalStatus(str, Enum):
    ON_TRACK = "on_track"
    BEHIND = "behind"
    AHEAD = "ahead"
    COMPLETED = "completed"


class PersonalAccount(BaseModel):
    """A personal financial account."""

    id: str = ""
    name: str
    account_type: AccountKind
    institution: str = ""
    balance: float = 0.0
    interest_rate: float = 0.0  # APY or APR
    is_liability: bool = False  # True for credit cards, loans, mortgage
    last_updated: datetime = Field(default_factory=lambda: datetime.now())
    notes: str = ""


class BudgetCategory(BaseModel):
    """A single budget category with limit and actual spend."""

    name: str
    monthly_limit: float = 0.0
    actual_spend: float = 0.0
    status: BudgetStatus = BudgetStatus.ON_TRACK

    @property
    def remaining(self) -> float:
        return self.monthly_limit - self.actual_spend

    @property
    def utilization_pct(self) -> float:
        if self.monthly_limit <= 0:
            return 0.0
        return round((self.actual_spend / self.monthly_limit) * 100, 1)


class Budget(BaseModel):
    """Monthly budget with categories."""

    month: str = ""  # e.g., "2026-03"
    categories: list[BudgetCategory] = Field(default_factory=list)
    total_limit: float = 0.0
    total_spent: float = 0.0


class FinancialGoal(BaseModel):
    """A financial goal being tracked."""

    id: str = ""
    name: str
    target_amount: float
    current_amount: float = 0.0
    deadline: datetime | None = None
    monthly_contribution: float = 0.0
    status: GoalStatus = GoalStatus.ON_TRACK
    notes: str = ""

    @property
    def progress_pct(self) -> float:
        if self.target_amount <= 0:
            return 0.0
        return round((self.current_amount / self.target_amount) * 100, 1)

    @property
    def remaining(self) -> float:
        return max(0, self.target_amount - self.current_amount)


class NetWorthSnapshot(BaseModel):
    """A point-in-time net worth snapshot."""

    date: datetime = Field(default_factory=lambda: datetime.now())
    assets: float = 0.0
    liabilities: float = 0.0
    total: float = 0.0
    by_type: dict[str, float] = Field(default_factory=dict)  # account_type -> balance


class BillReminder(BaseModel):
    """A recurring bill or payment reminder."""

    id: str = ""
    name: str
    amount: float
    due_date: int = 1  # day of month
    autopay: bool = False
    account: str = ""  # which account pays it
    category: str = ""
    notes: str = ""

"""Data models for the Financial Operations agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    BROKERAGE = "brokerage"
    CREDIT_CARD = "credit_card"
    TRADING = "trading"  # ATS accounts


class FinancialAccount(BaseModel):
    """A financial account from any source."""

    id: str
    name: str
    institution: str
    account_type: AccountType
    balance: float
    currency: str = "USD"
    last_synced: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class Transaction(BaseModel):
    """A financial transaction."""

    id: str
    account_id: str
    date: datetime
    description: str
    amount: float  # negative = debit
    category: str = ""
    merchant: str = ""
    pending: bool = False


class ProfitLoss(BaseModel):
    """Profit & loss statement."""

    period: str  # "daily", "weekly", "monthly", "ytd"
    start_date: datetime
    end_date: datetime
    revenue: float = 0
    expenses: float = 0
    net_income: float = 0
    by_entity: dict[str, float] = Field(default_factory=dict)  # entity_name -> net
    by_category: dict[str, float] = Field(default_factory=dict)


class CashFlowForecast(BaseModel):
    """Projected cash flow for a future period."""

    forecast_date: datetime
    projected_balance: float
    inflows: float
    outflows: float
    assumptions: list[str] = Field(default_factory=list)


class TaxEstimate(BaseModel):
    """Estimated tax obligations."""

    period: str
    estimated_income: float
    estimated_tax: float
    effective_rate: float
    quarterly_payment: float
    notes: list[str] = Field(default_factory=list)

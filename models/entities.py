from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(120))
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#5B7C72", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    transfer_id: Mapped[str | None] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deduplication_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("category_id", "year", "month", name="uq_budget_period_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("savings_goals.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    contributed_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(180))


class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_generated_on: Mapped[date | None] = mapped_column(Date)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    valued_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Liability(Base):
    __tablename__ = "liabilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    liability_type: Mapped[str] = mapped_column(String(30), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    captured_on: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    net_worth: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Investment(Base):
    __tablename__ = "investments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(20))
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC),
                                                  onupdate=lambda: datetime.now(UTC), nullable=False)


class InvestmentTrade(Base):
    __tablename__ = "investment_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    investment_id: Mapped[int] = mapped_column(ForeignKey("investments.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    units: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    traded_on: Mapped[date] = mapped_column(Date, nullable=False)

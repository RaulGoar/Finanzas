from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.entities import Account, Category, Transaction
from services.finance import (
    FinanceError,
    account_balances,
    as_money,
    budget_status,
    create_account,
    create_asset,
    create_budget,
    create_category,
    create_goal,
    create_investment,
    create_liability,
    create_transaction,
    create_recurring_rule,
    investment_holdings,
    net_worth,
    process_recurring_rules,
    record_trade,
    seed_categories,
    transfer,
    update_asset,
    update_investment_price,
    update_liability,
)


def test_seed_categories_and_reject_duplicate_transaction(session):
    seed_categories(session)
    seed_categories(session)
    account = create_account(session, "Cuenta diaria", "Corriente", "1000")
    category = session.scalar(select(Category).where(Category.name == "Alimentación"))
    create_transaction(session, account_id=account.id, category_id=category.id, kind="expense",
                       description="Compra semanal", amount="25.50", occurred_on=date(2026, 11, 1))

    with pytest.raises(FinanceError, match="idéntico"):
        create_transaction(session, account_id=account.id, category_id=category.id, kind="expense",
                           description="Compra semanal", amount="25.50", occurred_on=date(2026, 11, 1))

    assert account_balances(session)[account.id] == Decimal("974.50")
    assert session.query(Category).count() == 10


def test_transfer_is_atomic_and_updates_both_balances(session):
    source = create_account(session, "Origen", "Corriente", "200")
    destination = create_account(session, "Destino", "Ahorro", "10")

    transfer(session, source.id, destination.id, "75", date(2026, 11, 2))

    balances = account_balances(session)
    assert balances == {source.id: Decimal("125.00"), destination.id: Decimal("85.00")}
    assert session.scalar(select(func.count(Transaction.id)).where(Transaction.transfer_id.is_not(None))) == 2
    assert session.query(Transaction).count() == 2
    with pytest.raises(FinanceError, match="insuficiente"):
        transfer(session, source.id, destination.id, "500", date(2026, 11, 2))
    assert session.query(Transaction).count() == 2


def test_budget_and_savings_progress(session):
    seed_categories(session)
    account = create_account(session, "Cuenta", "Corriente", "500")
    category = session.scalar(select(Category).where(Category.name == "Vivienda"))
    create_transaction(session, account_id=account.id, category_id=category.id, kind="expense",
                       description="Alquiler", amount="400", occurred_on=date(2026, 11, 3))
    budget = create_budget(session, category.id, 2026, 11, "500")
    assert budget_status(session, budget) == (Decimal("400.00"), Decimal("80.0"))
    goal = create_goal(session, "Emergencias", "1000", date(2027, 11, 1))
    from services.finance import contribute_to_goal, goal_progress

    contribute_to_goal(session, goal.id, account.id, "125.50", date(2026, 11, 3))
    assert goal_progress(session, goal) == Decimal("125.50")


def test_recurring_rule_generates_once_when_due(session):
    seed_categories(session)
    account = create_account(session, "Cuenta", "Corriente", "100")
    category = session.scalar(select(Category).where(Category.name == "Vivienda"))
    create_recurring_rule(session, account_id=account.id, category_id=category.id,
                          kind="expense", description="Alquiler", amount="40",
                          day_of_month=5, starts_on=date(2026, 11, 1))

    assert process_recurring_rules(session, date(2026, 11, 4)) == 0
    assert process_recurring_rules(session, date(2026, 11, 5)) == 1
    assert process_recurring_rules(session, date(2026, 11, 20)) == 0
    assert account_balances(session)[account.id] == Decimal("60.00")


def test_fifo_realized_and_unrealized_returns_include_fees(session):
    account = create_account(session, "Broker", "Corriente", "10000")
    investment = create_investment(session, "Fondo Global", "ETF", "WORLD")
    record_trade(session, investment.id, account.id, "buy", "10", "10", "2", date(2026, 1, 1))
    record_trade(session, investment.id, account.id, "buy", "5", "12", "1", date(2026, 2, 1))
    record_trade(session, investment.id, account.id, "sell", "12", "15", "3", date(2026, 3, 1))

    units, cost_basis, realized = investment_holdings(session, investment.id)
    assert units == Decimal("3.00000000")
    assert cost_basis == Decimal("36.60000000")
    assert realized == Decimal("50.60000000")
    assert net_worth(session) == Decimal("10059.00000000")
    with pytest.raises(FinanceError, match="más unidades"):
        record_trade(session, investment.id, account.id, "sell", "4", "15", "0", date(2026, 4, 1))


def test_investments_must_use_the_base_currency(session):
    from config.settings import settings

    other_currency = next(code for code in ("EUR", "USD", "GBP") if code != settings.currency)
    with pytest.raises(FinanceError, match="moneda"):
        create_investment(session, "Activo extranjero", "ETF", currency=other_currency)


def test_assets_and_liabilities_can_be_revalued(session):
    asset = create_asset(session, "Casa", "Inmueble", "100000", date(2026, 1, 1))
    liability = create_liability(session, "Hipoteca", "Hipoteca", "80000")
    update_asset(session, asset.id, "Casa", "Inmueble", "120000", date(2026, 11, 1))
    update_liability(session, liability.id, "Hipoteca", "Hipoteca", "75000")

    assert net_worth(session) == Decimal("45000.00")


def test_manual_investment_price_updates_unrealized_value(session):
    account = create_account(session, "Broker", "Corriente", "1000")
    investment = create_investment(session, "ETF", "ETF")
    record_trade(session, investment.id, account.id, "buy", "2", "10", "0", date(2026, 1, 1))
    update_investment_price(session, investment.id, "12.50")

    units, cost, realized = investment_holdings(session, investment.id)
    assert net_worth(session) == Decimal("1005.00")
    assert (units, cost, realized) == (Decimal("2.00000000"), Decimal("20.00000000"), Decimal("0.00"))


def test_money_validation():
    assert as_money("12.345") == Decimal("12.35")
    with pytest.raises(FinanceError):
        as_money("-1")
    with pytest.raises(FinanceError):
        as_money("NaN")

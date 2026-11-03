from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.settings import settings
from models.entities import (
    Account,
    Asset,
    Budget,
    Category,
    GoalContribution,
    Investment,
    InvestmentTrade,
    Liability,
    NetWorthSnapshot,
    RecurringRule,
    SavingsGoal,
    Transaction,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
ACCOUNT_TYPES = {"Corriente", "Efectivo", "Ahorro"}
ASSET_TYPES = {"Inmueble", "Vehículo", "Otro"}
LIABILITY_TYPES = {"Préstamo", "Hipoteca", "Otra"}
INVESTMENT_TYPES = {"Acción", "ETF", "Fondo", "Criptomoneda", "Otro"}


class FinanceError(ValueError):
    """Error de validación que puede mostrarse directamente en la interfaz."""


def as_money(value: Decimal | int | float | str, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as error:
        raise FinanceError("Introduce un importe válido.") from error
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        raise FinanceError("El importe debe ser mayor que cero.")
    if amount > Decimal("999999999999.99"):
        raise FinanceError("El importe supera el máximo permitido.")
    return amount


def _transaction_key(account_id: int, category_id: int | None, kind: str,
                     description: str, amount: Decimal, occurred_on: date) -> str:
    payload = json.dumps([account_id, category_id, kind, description.casefold(), str(amount), occurred_on.isoformat()])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seed_categories(session: Session) -> None:
    if session.scalar(select(func.count()).select_from(Category)):
        return
    defaults = [
        ("Vivienda", "expense", "#C26D4A"), ("Alimentación", "expense", "#6C8F6A"),
        ("Transporte", "expense", "#6687A3"), ("Salud", "expense", "#B86F78"),
        ("Ocio", "expense", "#9A7BA8"), ("Servicios", "expense", "#C39A4B"),
        ("Educación", "expense", "#548F91"), ("Otros gastos", "expense", "#7B827D"),
        ("Salario", "income", "#4E8B69"), ("Otros ingresos", "income", "#537F9E"),
    ]
    session.add_all(Category(name=name, kind=kind, color=color, is_default=True) for name, kind, color in defaults)
    session.commit()


def create_category(session: Session, name: str, kind: str, color: str = "#5B7C72") -> Category:
    name = name.strip()
    if not name or kind not in {"income", "expense"}:
        raise FinanceError("Indica un nombre y un tipo de categoría válidos.")
    if session.scalar(select(Category.id).where(func.lower(Category.name) == name.lower())):
        raise FinanceError("Ya existe una categoría con ese nombre.")
    category = Category(name=name, kind=kind, color=color, is_default=False)
    session.add(category)
    session.commit()
    return category


def create_account(session: Session, name: str, account_type: str, opening_balance: Decimal | str, institution: str = "") -> Account:
    name = name.strip()
    if not name or account_type not in ACCOUNT_TYPES:
        raise FinanceError("Indica un nombre y un tipo de cuenta válidos.")
    account = Account(name=name, account_type=account_type, institution=institution.strip() or None,
                      opening_balance=as_money(opening_balance, allow_zero=True))
    session.add(account)
    session.commit()
    return account


def account_balances(session: Session) -> dict[int, Decimal]:
    balances = {account.id: Decimal(account.opening_balance) for account in session.scalars(select(Account).where(Account.active.is_(True)))}
    for transaction in session.scalars(select(Transaction)):
        if transaction.account_id not in balances:
            continue
        amount = Decimal(transaction.amount)
        balances[transaction.account_id] += amount if transaction.kind in {"income", "transfer_in"} else -amount
    return balances


def create_transaction(session: Session, *, account_id: int, category_id: int | None, kind: str,
                       description: str, amount: Decimal | str, occurred_on: date,
                       recurring: bool = False, notes: str = "") -> Transaction:
    description = description.strip()
    value = as_money(amount)
    if kind not in {"income", "expense"} or not description or not isinstance(occurred_on, date):
        raise FinanceError("Revisa el tipo, la descripción y la fecha del movimiento.")
    account = session.get(Account, account_id)
    category = session.get(Category, category_id) if category_id else None
    if account is None or not account.active:
        raise FinanceError("Selecciona una cuenta activa.")
    if category_id and (category is None or category.kind != kind):
        raise FinanceError("La categoría no corresponde al tipo de movimiento.")
    duplicate = session.scalar(select(Transaction.id).where(
        Transaction.account_id == account_id, Transaction.category_id == category_id,
        Transaction.kind == kind, Transaction.description == description,
        Transaction.amount == value, Transaction.occurred_on == occurred_on,
    ).limit(1))
    if duplicate:
        raise FinanceError("Ya existe un movimiento idéntico. Comprueba los datos antes de repetirlo.")
    transaction = Transaction(account_id=account_id, category_id=category_id, kind=kind,
                              description=description, amount=value, occurred_on=occurred_on,
                              recurring=recurring, notes=notes.strip() or None,
                              deduplication_key=_transaction_key(account_id, category_id, kind, description, value, occurred_on))
    session.add(transaction)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise FinanceError("Ya existe un movimiento idéntico.") from error
    return transaction


def update_transaction(session: Session, transaction_id: int, **changes) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.kind not in {"income", "expense"}:
        raise FinanceError("No se encontró el movimiento editable.")
    account_id = changes.get("account_id", transaction.account_id)
    category_id = changes.get("category_id", transaction.category_id)
    kind = changes.get("kind", transaction.kind)
    description = changes.get("description", transaction.description).strip()
    amount = as_money(changes.get("amount", transaction.amount))
    occurred_on = changes.get("occurred_on", transaction.occurred_on)
    if kind not in {"income", "expense"} or not description or not isinstance(occurred_on, date):
        raise FinanceError("Revisa los datos del movimiento.")
    account = session.get(Account, account_id)
    category = session.get(Category, category_id) if category_id else None
    if account is None or not account.active or (category_id and (category is None or category.kind != kind)):
        raise FinanceError("La cuenta o categoría seleccionada no es válida.")
    duplicate = session.scalar(select(Transaction.id).where(
        Transaction.id != transaction_id, Transaction.account_id == account_id,
        Transaction.category_id == category_id, Transaction.kind == kind,
        Transaction.description == description, Transaction.amount == amount,
        Transaction.occurred_on == occurred_on,
    ).limit(1))
    if duplicate:
        raise FinanceError("Ya existe un movimiento idéntico.")
    transaction.account_id = account_id
    transaction.category_id = category_id
    transaction.kind = kind
    transaction.description = description
    transaction.amount = amount
    transaction.occurred_on = occurred_on
    transaction.recurring = changes.get("recurring", transaction.recurring)
    transaction.notes = changes.get("notes", transaction.notes)
    transaction.deduplication_key = _transaction_key(account_id, category_id, kind, description, amount, occurred_on)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise FinanceError("Ya existe un movimiento idéntico.") from error
    return transaction


def delete_transaction(session: Session, transaction_id: int) -> None:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.kind not in {"income", "expense"}:
        raise FinanceError("No se encontró el movimiento editable.")
    session.delete(transaction)
    session.commit()


def transfer(session: Session, source_id: int, destination_id: int, amount: Decimal | str,
             occurred_on: date, description: str = "Transferencia") -> str:
    value = as_money(amount)
    if source_id == destination_id:
        raise FinanceError("Elige dos cuentas distintas.")
    accounts = {account.id: account for account in session.scalars(
        select(Account).where(Account.id.in_([source_id, destination_id])).with_for_update())}
    if len(accounts) != 2 or any(not account.active for account in accounts.values()):
        raise FinanceError("Las cuentas seleccionadas no están disponibles.")
    if account_balances(session)[source_id] < value:
        raise FinanceError("El saldo de origen es insuficiente.")
    transfer_id = str(uuid4())
    label = description.strip() or "Transferencia"
    try:
        session.add_all([
            Transaction(account_id=source_id, kind="transfer_out", description=label, amount=value,
                        occurred_on=occurred_on, transfer_id=transfer_id),
            Transaction(account_id=destination_id, kind="transfer_in", description=label, amount=value,
                        occurred_on=occurred_on, transfer_id=transfer_id),
        ])
        session.commit()
    except Exception:
        session.rollback()
        raise
    return transfer_id


def create_budget(session: Session, category_id: int, year: int, month: int, limit_amount: Decimal | str) -> Budget:
    amount = as_money(limit_amount)
    if month not in range(1, 13):
        raise FinanceError("El mes debe estar entre enero y diciembre.")
    category = session.get(Category, category_id)
    if category is None or category.kind != "expense":
        raise FinanceError("El presupuesto requiere una categoría de gasto.")
    budget = session.scalar(select(Budget).where(Budget.category_id == category_id,
                                                  Budget.year == year, Budget.month == month))
    if budget is None:
        budget = Budget(category_id=category_id, year=year, month=month, limit_amount=amount)
        session.add(budget)
    else:
        budget.limit_amount = amount
    session.commit()
    return budget


def budget_status(session: Session, budget: Budget) -> tuple[Decimal, Decimal]:
    start = date(budget.year, budget.month, 1)
    end = date(budget.year + (budget.month == 12), budget.month % 12 + 1, 1)
    spent = session.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.category_id == budget.category_id, Transaction.kind == "expense",
        Transaction.occurred_on >= start, Transaction.occurred_on < end)) or ZERO
    spent = Decimal(spent)
    return spent, spent / Decimal(budget.limit_amount) * 100


def create_goal(session: Session, name: str, target_amount: Decimal | str, deadline: date | None) -> SavingsGoal:
    name = name.strip()
    if not name:
        raise FinanceError("El objetivo necesita un nombre.")
    goal = SavingsGoal(name=name, target_amount=as_money(target_amount), deadline=deadline)
    session.add(goal)
    session.commit()
    return goal


def create_recurring_rule(session: Session, *, account_id: int, category_id: int | None,
                          kind: str, description: str, amount: Decimal | str,
                          day_of_month: int, starts_on: date) -> RecurringRule:
    description = description.strip()
    category = session.get(Category, category_id) if category_id else None
    account = session.get(Account, account_id)
    if kind not in {"income", "expense"} or not description or day_of_month not in range(1, 32):
        raise FinanceError("Revisa el tipo, la descripción y el día del mes.")
    if account is None or not account.active or (category_id and (category is None or category.kind != kind)):
        raise FinanceError("La cuenta o categoría seleccionada no es válida.")
    rule = RecurringRule(account_id=account_id, category_id=category_id, kind=kind,
                         description=description, amount=as_money(amount),
                         day_of_month=day_of_month, starts_on=starts_on)
    session.add(rule)
    session.commit()
    return rule


def process_recurring_rules(session: Session, today: date) -> int:
    generated = 0
    generated_keys: set[str] = set()
    for rule in session.scalars(select(RecurringRule).where(RecurringRule.active.is_(True))):
        due_on = date(today.year, today.month,
                      min(rule.day_of_month, calendar.monthrange(today.year, today.month)[1]))
        if due_on > today or due_on < rule.starts_on or rule.last_generated_on == due_on:
            continue
        key = _transaction_key(rule.account_id, rule.category_id, rule.kind,
                               rule.description, Decimal(rule.amount), due_on)
        exists = key in generated_keys or session.scalar(
            select(Transaction.id).where(Transaction.deduplication_key == key))
        if not exists:
            session.add(Transaction(account_id=rule.account_id, category_id=rule.category_id,
                                    kind=rule.kind, description=rule.description,
                                    amount=rule.amount, occurred_on=due_on, recurring=True,
                                    deduplication_key=key))
            generated += 1
            generated_keys.add(key)
        rule.last_generated_on = due_on
    session.commit()
    return generated


def set_recurring_rule_active(session: Session, rule_id: int, active: bool) -> None:
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise FinanceError("No se encontró la regla recurrente.")
    rule.active = active
    session.commit()


def contribute_to_goal(session: Session, goal_id: int, account_id: int, amount: Decimal | str,
                       contributed_on: date, note: str = "") -> GoalContribution:
    value = as_money(amount)
    if session.get(SavingsGoal, goal_id) is None or session.get(Account, account_id) is None:
        raise FinanceError("Selecciona un objetivo y una cuenta válidos.")
    contribution = GoalContribution(goal_id=goal_id, account_id=account_id, amount=value,
                                    contributed_on=contributed_on, note=note.strip() or None)
    session.add(contribution)
    session.commit()
    return contribution


def goal_progress(session: Session, goal: SavingsGoal) -> Decimal:
    total = session.scalar(select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(
        GoalContribution.goal_id == goal.id)) or ZERO
    return Decimal(total)


def create_asset(session: Session, name: str, asset_type: str, value: Decimal | str,
                 valued_on: date, notes: str = "") -> Asset:
    if not name.strip() or asset_type not in ASSET_TYPES:
        raise FinanceError("Indica un nombre y tipo de activo válidos.")
    asset = Asset(name=name.strip(), asset_type=asset_type, value=as_money(value, allow_zero=True),
                  valued_on=valued_on, notes=notes.strip() or None)
    session.add(asset)
    session.commit()
    return asset


def update_asset(session: Session, asset_id: int, name: str, asset_type: str,
                 value: Decimal | str, valued_on: date, notes: str = "") -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise FinanceError("No se encontró el activo.")
    if not name.strip() or asset_type not in ASSET_TYPES:
        raise FinanceError("Indica un nombre y tipo de activo válidos.")
    asset.name = name.strip()
    asset.asset_type = asset_type
    asset.value = as_money(value, allow_zero=True)
    asset.valued_on = valued_on
    asset.notes = notes.strip() or None
    session.commit()
    return asset


def delete_asset(session: Session, asset_id: int) -> None:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise FinanceError("No se encontró el activo.")
    session.delete(asset)
    session.commit()


def create_liability(session: Session, name: str, liability_type: str, balance: Decimal | str,
                     due_on: date | None = None, notes: str = "") -> Liability:
    if not name.strip() or liability_type not in LIABILITY_TYPES:
        raise FinanceError("Indica un nombre y tipo de deuda válidos.")
    liability = Liability(name=name.strip(), liability_type=liability_type,
                          balance=as_money(balance, allow_zero=True), due_on=due_on,
                          notes=notes.strip() or None)
    session.add(liability)
    session.commit()
    return liability


def update_liability(session: Session, liability_id: int, name: str, liability_type: str,
                     balance: Decimal | str, due_on: date | None = None,
                     notes: str = "") -> Liability:
    liability = session.get(Liability, liability_id)
    if liability is None:
        raise FinanceError("No se encontró la deuda.")
    if not name.strip() or liability_type not in LIABILITY_TYPES:
        raise FinanceError("Indica un nombre y tipo de deuda válidos.")
    liability.name = name.strip()
    liability.liability_type = liability_type
    liability.balance = as_money(balance, allow_zero=True)
    liability.due_on = due_on
    liability.notes = notes.strip() or None
    session.commit()
    return liability


def delete_liability(session: Session, liability_id: int) -> None:
    liability = session.get(Liability, liability_id)
    if liability is None:
        raise FinanceError("No se encontró la deuda.")
    session.delete(liability)
    session.commit()


def create_investment(session: Session, name: str, asset_type: str, ticker: str = "",
                      currency: str | None = None) -> Investment:
    currency = (currency or settings.currency).upper()
    if not name.strip() or asset_type not in INVESTMENT_TYPES or currency != settings.currency:
        raise FinanceError("Indica un activo, tipo y moneda válidos.")
    investment = Investment(name=name.strip(), ticker=ticker.strip().upper() or None,
                            asset_type=asset_type, currency=currency.upper())
    session.add(investment)
    session.commit()
    return investment


def update_investment_price(session: Session, investment_id: int, current_price: Decimal | str) -> Investment:
    investment = session.get(Investment, investment_id)
    if investment is None:
        raise FinanceError("No se encontró la inversión.")
    try:
        price = Decimal(str(current_price))
    except (InvalidOperation, ValueError) as error:
        raise FinanceError("Introduce un precio válido.") from error
    if not price.is_finite() or price <= 0:
        raise FinanceError("El precio debe ser mayor que cero.")
    investment.current_price = price
    session.commit()
    return investment


def investment_holdings(session: Session, investment_id: int, *,
                        through_date: date | None = None) -> tuple[Decimal, Decimal, Decimal]:
    query = select(InvestmentTrade).where(InvestmentTrade.investment_id == investment_id)
    if through_date is not None:
        query = query.where(InvestmentTrade.traded_on <= through_date)
    trades = session.scalars(query.order_by(InvestmentTrade.traded_on, InvestmentTrade.id))
    lots: list[list[Decimal]] = []
    realized = ZERO
    for trade in trades:
        units, price, fee = Decimal(trade.units), Decimal(trade.unit_price), Decimal(trade.commission)
        if trade.side == "buy":
            lots.append([units, price + fee / units])
            continue
        remaining = units
        proceeds_per_unit = price - fee / units
        while remaining > 0 and lots:
            lot_units, cost_per_unit = lots[0]
            matched = min(remaining, lot_units)
            realized += matched * (proceeds_per_unit - cost_per_unit)
            remaining -= matched
            lots[0][0] -= matched
            if lots[0][0] == 0:
                lots.pop(0)
    units_held = sum((lot[0] for lot in lots), ZERO)
    cost_basis = sum((lot[0] * lot[1] for lot in lots), ZERO)
    return units_held, cost_basis, realized


def record_trade(session: Session, investment_id: int, account_id: int, side: str,
                 units: Decimal | str, unit_price: Decimal | str, commission: Decimal | str,
                 traded_on: date) -> InvestmentTrade:
    try:
        quantity = Decimal(str(units))
        price = Decimal(str(unit_price))
        fee = as_money(commission, allow_zero=True)
    except (InvalidOperation, ValueError) as error:
        raise FinanceError("Revisa unidades, precio y comisión.") from error
    if not quantity.is_finite() or quantity <= 0 or not price.is_finite() or price <= 0 or side not in {"buy", "sell"}:
        raise FinanceError("Las unidades y el precio deben ser positivos.")
    investment = session.get(Investment, investment_id)
    account = session.get(Account, account_id)
    if investment is None or account is None or not account.active:
        raise FinanceError("Selecciona una inversión y una cuenta válidas.")
    held, _basis, _realized = investment_holdings(session, investment_id, through_date=traded_on)
    if side == "sell" and quantity > held:
        raise FinanceError("No puedes vender más unidades de las que tienes.")
    gross = quantity * price
    if side == "sell" and fee >= gross:
        raise FinanceError("La comisión debe ser inferior al importe de la venta.")
    cash_amount = gross + fee if side == "buy" else gross - fee
    if side == "buy" and account_balances(session)[account_id] < cash_amount:
        raise FinanceError("El saldo de la cuenta es insuficiente para esta compra.")
    latest_trade_date = session.scalar(select(func.max(InvestmentTrade.traded_on)).where(
        InvestmentTrade.investment_id == investment_id))
    trade = InvestmentTrade(investment_id=investment_id, account_id=account_id, side=side,
                            units=quantity, unit_price=price, commission=fee, traded_on=traded_on)
    session.add(trade)
    if latest_trade_date is None or traded_on >= latest_trade_date:
        investment.current_price = price
    session.add(Transaction(
        account_id=account_id,
        kind="expense" if side == "buy" else "income",
        description=f"{'Compra' if side == 'buy' else 'Venta'}: {investment.name}",
        amount=as_money(cash_amount),
        occurred_on=traded_on,
    ))
    session.commit()
    return trade


def net_worth(session: Session) -> Decimal:
    balances = sum(account_balances(session).values(), ZERO)
    assets = session.scalar(select(func.coalesce(func.sum(Asset.value), 0))) or ZERO
    liabilities = session.scalar(select(func.coalesce(func.sum(Liability.balance), 0))) or ZERO
    holdings_value = ZERO
    for investment in session.scalars(select(Investment)):
        units, _cost, _realized = investment_holdings(session, investment.id)
        if investment.current_price is not None:
            holdings_value += units * Decimal(investment.current_price)
    return balances + Decimal(assets) + holdings_value - Decimal(liabilities)


def save_net_worth_snapshot(session: Session, captured_on: date) -> NetWorthSnapshot:
    snapshot = session.scalar(select(NetWorthSnapshot).where(NetWorthSnapshot.captured_on == captured_on))
    if snapshot is None:
        snapshot = NetWorthSnapshot(captured_on=captured_on, net_worth=net_worth(session))
        session.add(snapshot)
    else:
        snapshot.net_worth = net_worth(session)
    session.commit()
    return snapshot

"""Демонстрация дня 2: три новых типа счетов. Запуск: python demo_day2.py"""

import sys
from decimal import Decimal

from bank import (
    AbstractAccount,
    AccountClosedError,
    AccountFrozenError,
    AssetType,
    BankAccount,
    InsufficientFundsError,
    InvalidOperationError,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)
from demo import check, expect_error, problems, section

RATES = {"stocks": 0.10, "bonds": 0.04, "etf": 0.07}  # условные ставки из задания


def show_info(account):
    """Печатает сведения о счёте: по одной строке на каждое поле."""
    print(f"  Сведения о счёте {type(account).__name__}:")
    for key, value in account.get_account_info().items():
        if isinstance(value, dict):
            value = ", ".join(f"{name} {amount}" for name, amount in value.items())
        print(f"    {key}: {value}")


def show_creation():
    section("1. Создание счетов")
    anna = SavingsAccount(
        "Анна Смирнова", "40817810099910007781",
        balance=10000, min_balance=1000, monthly_rate=0.015,
    )
    oleg = SavingsAccount("Олег Титов", balance=500, currency="usd", monthly_rate=0.004)
    petr = PremiumAccount(
        "Пётр Иванов", "40817810099910000042",
        balance=1000, overdraft_limit=5000, fee=50,
    )
    maria = PremiumAccount("Мария Орлова", balance=250000, currency="EUR", fee=5)
    li = InvestmentAccount("Ли Вэй", "40817810099910003310", balance=12000)
    ivan = InvestmentAccount("Иван Петров", balance=3000, status="frozen")
    for account in (anna, oleg, petr, maria, li, ivan):
        print(f"  {account}")
    for account in (anna, petr, li):
        show_info(account)
    check("у счёта без номера номер сгенерирован", len(oleg.account_id) == 8)
    check("ставка в строке счёта показана в процентах", "1.50% в месяц" in str(anna))
    check(
        "лимит премиального счёта в десять раз больше обычного",
        PremiumAccount.WITHDRAWAL_LIMIT == 10 * BankAccount.WITHDRAWAL_LIMIT,
    )


def show_savings():
    section("2. Сберегательный счёт")
    savings = SavingsAccount(
        "Анна Смирнова", "40817810099910007781",
        balance=1000.50, min_balance=500, monthly_rate=0.015,
    )
    print(f"  {savings}")
    print(f"  Проценты за первый месяц: {savings.apply_monthly_interest()}")
    check("баланс после начисления: 1015.51", savings.balance == Decimal("1015.51"))
    print(f"  Проценты за второй месяц: {savings.apply_monthly_interest()}")
    check("проценты на проценты: 1030.74", savings.balance == Decimal("1030.74"))
    print(f"  Снятие 500, новый баланс: {savings.withdraw(500)}")
    print(f"  Снятие 30.74, новый баланс: {savings.withdraw(30.74)}")
    check("остался ровно минимальный остаток 500", savings.balance == 500)
    expect_error(
        "снятие ниже минимального остатка", InsufficientFundsError,
        lambda: savings.withdraw(1),
    )
    check("после отказа баланс прежний", savings.balance == 500)
    plain = SavingsAccount("Олег Титов", "40817810099910005512", balance=100)
    check("при нулевой ставке проценты равны нулю", plain.apply_monthly_interest() == 0)


def show_premium():
    section("3. Премиальный счёт")
    premium = PremiumAccount(
        "Пётр Иванов", "40817810099910000042",
        balance=1000, overdraft_limit=5000, fee=50,
    )
    print(f"  {premium}")
    print(f"  Снятие 1200 и комиссия 50, новый баланс: {premium.withdraw(1200)}")
    check("баланс ушёл в минус: -250", premium.balance == -250)
    print(f"  Снятие 4700 и комиссия 50, новый баланс: {premium.withdraw(4700)}")
    check("баланс дошёл до лимита овердрафта: -5000", premium.balance == -5000)
    expect_error(
        "снятие за пределом овердрафта", InsufficientFundsError,
        lambda: premium.withdraw(1),
    )
    print(f"  Пополнение на 6000 без комиссии, новый баланс: {premium.deposit(6000)}")
    check("долг погашен, баланс 1000", premium.balance == 1000)

    usual = BankAccount("Иван Петров", "40817810099910004312", balance=2000000)
    rich = PremiumAccount("Мария Орлова", "40817810099910009900", balance=2000000)
    print(f"  Лимит на одно снятие у обычного счёта: {usual.WITHDRAWAL_LIMIT}")
    print(f"  Лимит на одно снятие у премиального счёта: {rich.WITHDRAWAL_LIMIT}")
    expect_error(
        "обычный счёт: снятие 150000 сверх лимита", InvalidOperationError,
        lambda: usual.withdraw(150000),
    )
    print(f"  Премиальный счёт: снятие 150000, новый баланс: {rich.withdraw(150000)}")
    expect_error(
        "премиальный счёт: снятие сверх своего лимита", InvalidOperationError,
        lambda: rich.withdraw(1000000.01),
    )
    check("после отказа баланс премиального счёта прежний", rich.balance == 1850000)


def show_premium():
    section("3. Премиальный счёт")
    premium = PremiumAccount(
        "Пётр Иванов", "40817810099910000042",
        balance=1000, overdraft_limit=5000, fee=50,
    )
    print(f"  {premium}")
    print(f"  Снятие 1200 и комиссия 50, новый баланс: {premium.withdraw(1200)}")
    check("баланс ушёл в минус: -250", premium.balance == -250)
    print(f"  Снятие 4700 и комиссия 50, новый баланс: {premium.withdraw(4700)}")
    check("баланс дошёл до лимита овердрафта: -5000", premium.balance == -5000)
    expect_error(
        "снятие за пределом овердрафта", InsufficientFundsError,
        lambda: premium.withdraw(1),
    )
    print(f"  Пополнение на 6000 без комиссии, новый баланс: {premium.deposit(6000)}")
    check("долг погашен, баланс 1000", premium.balance == 1000)

    usual = BankAccount("Иван Петров", "40817810099910004312", balance=2000000)
    rich = PremiumAccount("Мария Орлова", "40817810099910009900", balance=2000000)
    print(f"  Лимит на одно снятие у обычного счёта: {usual.WITHDRAWAL_LIMIT}")
    print(f"  Лимит на одно снятие у премиального счёта: {rich.WITHDRAWAL_LIMIT}")
    expect_error(
        "обычный счёт: снятие 150000 сверх лимита", InvalidOperationError,
        lambda: usual.withdraw(150000),
    )
    print(f"  Премиальный счёт: снятие 150000, новый баланс: {rich.withdraw(150000)}")
    expect_error(
        "премиальный счёт: снятие сверх своего лимита", InvalidOperationError,
        lambda: rich.withdraw(1000000.01),
    )
    check("после отказа баланс премиального счёта прежний", rich.balance == 1850000)


def show_investment():
    section("4. Инвестиционный счёт")
    investor = InvestmentAccount("Ли Вэй", "40817810099910003310", balance=12000)
    check("пустой портфель не растёт", investor.project_yearly_growth(RATES) == 0)
    print(f"  Вложение 4000 в акции, в акциях стало: {investor.invest('stocks', 4000)}")
    print(f"  Ещё 1000 в акции, стало: {investor.invest(AssetType.STOCKS, 1000)}")
    print(f"  Вложение 3000 в облигации: {investor.invest('BONDS', 3000)}")
    print(f"  Вложение 2000 в фонды: {investor.invest('etf', 2000)}")
    print(f"  {investor}")
    check("баланс от вложений не изменился", investor.balance == 12000)
    expect_error(
        "вложение в неизвестный актив", InvalidOperationError,
        lambda: investor.invest("gold", 100),
    )
    expect_error(
        "вложение нулевой суммы", InvalidOperationError,
        lambda: investor.invest("etf", 0),
    )
    expect_error(
        "вложение больше свободных средств", InsufficientFundsError,
        lambda: investor.invest("etf", 2000.01),
    )
    expect_error(
        "снятие вложенных денег", InsufficientFundsError,
        lambda: investor.withdraw(2500),
    )
    print(f"  Снятие свободных 2000, новый баланс: {investor.withdraw(2000)}")

    growth = investor.project_yearly_growth(RATES)
    print(f"  Ожидаемый прирост за год: {growth}")
    check("прирост равен 500 + 120 + 140 = 760.00", growth == Decimal("760.00"))
    expect_error(
        "прогноз без ставки для акций", InvalidOperationError,
        lambda: investor.project_yearly_growth({"bonds": 0.04, "etf": 0.07}),
    )
    expect_error(
        "прогноз с неизвестным активом", InvalidOperationError,
        lambda: investor.project_yearly_growth({"gold": 0.5}),
    )
    expect_error(
        "прогноз со ставкой в процентах вместо доли", InvalidOperationError,
        lambda: investor.project_yearly_growth({"stocks": 10, "bonds": 4, "etf": 7}),
    )
    snapshot = investor.portfolio
    snapshot["stocks"] = 0
    check("копия портфеля не меняет счёт", investor.portfolio["stocks"] == 5000)
    show_info(investor)


def show_polymorphism():
    section("5. Полиморфизм: один вызов, разные ответы")
    usual = BankAccount("Иван Петров", "40817810099910000001", balance=1000)
    savings = SavingsAccount(
        "Анна Смирнова", "40817810099910000002", balance=1000, min_balance=500
    )
    premium = PremiumAccount(
        "Пётр Иванов", "40817810099910000003", balance=1000, fee=50
    )
    investor = InvestmentAccount("Ли Вэй", "40817810099910000004", balance=1000)
    investor.invest("stocks", 600)
    accounts = [usual, savings, premium, investor]

    print("  На каждом счёте 1000. У каждого просим снять 900:")
    for account in accounts:
        try:
            answer = f"выдал, остаток {account.withdraw(900)}"
        except InsufficientFundsError:
            answer = "отказал, столько снять нельзя"
        print(f"    {type(account).__name__}: {answer}")
    balances = [account.balance for account in accounts]
    check("остатки по типам: 100, 1000, 50 и 1000", balances == [100, 1000, 50, 1000])

    for account in accounts:
        print(f"  {account}")
        print(f"    полей в сведениях о счёте: {len(account.get_account_info())}")
    check(
        "все четыре счёта подходят под общий контракт AbstractAccount",
        all(isinstance(account, AbstractAccount) for account in accounts),
    )


def show_statuses():
    section("6. Замороженные и закрытые счета новых типов")
    frozen = SavingsAccount(
        "Анна Смирнова", "40817810099910007781",
        balance=1000, monthly_rate=0.01, status="frozen",
    )
    blocked = InvestmentAccount(
        "Ли Вэй", "40817810099910003310", balance=1000, status="frozen"
    )
    closed = PremiumAccount(
        "Пётр Иванов", "40817810099910000042",
        balance=1000, overdraft_limit=500, status="closed",
    )
    expect_error(
        "начисление процентов по замороженному счёту", AccountFrozenError,
        frozen.apply_monthly_interest,
    )
    expect_error(
        "снятие с замороженного сберегательного счёта", AccountFrozenError,
        lambda: frozen.withdraw(100),
    )
    expect_error(
        "вложение по замороженному счёту", AccountFrozenError,
        lambda: blocked.invest("etf", 100),
    )
    expect_error(
        "снятие с закрытого премиального счёта", AccountClosedError,
        lambda: closed.withdraw(100),
    )
    check(
        "прогноз по замороженному счёту считается",
        blocked.project_yearly_growth(RATES) == 0,
    )
    balances = [frozen.balance, blocked.balance, closed.balance]
    check("балансы трёх счетов не изменились", balances == [1000, 1000, 1000])


def show_bad_parameters():
    section("7. Некорректные параметры при создании")
    bad_accounts = [
        (
            "отрицательный минимальный остаток",
            lambda: SavingsAccount("Анна Смирнова", min_balance=-1),
        ),
        (
            "начальный баланс ниже минимального остатка",
            lambda: SavingsAccount("Анна Смирнова", balance=100, min_balance=500),
        ),
        (
            "ставка 5 вместо 0.05",
            lambda: SavingsAccount("Анна Смирнова", monthly_rate=5),
        ),
        (
            "отрицательный лимит овердрафта",
            lambda: PremiumAccount("Пётр Иванов", overdraft_limit=-100),
        ),
        (
            "отрицательная комиссия",
            lambda: PremiumAccount("Пётр Иванов", fee=-1),
        ),
    ]
    for description, action in bad_accounts:
        expect_error(description, InvalidOperationError, action)


def main():
    parts = [
        show_creation,
        show_savings,
        show_premium,
        show_investment,
        show_polymorphism,
        show_statuses,
        show_bad_parameters,
    ]
    for part in parts:
        part()
    print()
    if problems:
        print(f"ДЕМОНСТРАЦИЯ ПРОВАЛЕНА. Расхождений: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Демонстрация дня 2 завершена успешно: новые типы счетов работают как надо.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

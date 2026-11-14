"""Демонстрация модели счетов. Запуск: python demo.py"""

import sys
from decimal import Decimal

from bank import (
    AbstractAccount,
    AccountClosedError,
    AccountFrozenError,
    AccountStatus,
    BankAccount,
    Currency,
    InsufficientFundsError,
    InvalidOperationError,
)

problems = []  # сюда попадает всё, что пошло не так, как ожидалось


def section(title):
    print(f"\n=== {title} ===")


def check(description, condition):
    """Проверяет, что условие выполнено."""
    if condition:
        print(f"  [ок] {description}")
    else:
        print(f"  [РАСХОЖДЕНИЕ] {description}")
        problems.append(description)


def expect_error(description, error_class, action):
    """Запускает действие и ждёт от него ошибку нужного класса."""
    try:
        action()
    except error_class as error:
        print(f"  [отказ] {description}")
        print(f"          {type(error).__name__}: {error}")
    else:
        print(f"  [РАСХОЖДЕНИЕ] {description}: ошибки {error_class.__name__} не было")
        problems.append(description)


def main():
    section("1. Создание счетов")
    active = BankAccount("Иван Петров", "40817810099910004312", balance=1500)
    auto = BankAccount("Анна Смирнова", balance=300, currency="usd")
    frozen = BankAccount(
        "Пётр Иванов", balance=5000, currency=Currency.EUR, status=AccountStatus.FROZEN
    )
    closed = BankAccount("Мария Орлова", balance=100, currency="KZT", status="closed")
    yuan = BankAccount("Ли Вэй", currency=Currency.CNY)
    for account in (active, auto, frozen, closed, yuan):
        print(f"  {account}")
    print("  Сведения о первом счёте:")
    for key, value in active.get_account_info().items():
        print(f"    {key}: {value}")
    check("номер без указания сгенерирован: 8 символов", len(auto.account_id) == 8)
    check("у двух счетов без номера номера разные", auto.account_id != yuan.account_id)
    check("в строке счёта полный номер скрыт", active.account_id not in str(active))
    check("в строке счёта видны последние 4 символа", "****4312" in str(active))

    section("2. Валидные операции")
    print(f"  Баланс до операций: {active.balance} {active.currency}")
    print(f"  Пополнение на 250.50, новый баланс: {active.deposit(250.50)}")
    print(f"  Снятие 750, новый баланс: {active.withdraw(750)}")
    expected = Decimal("1000.50")
    check(f"баланс после двух операций равен {expected}", active.balance == expected)
    print(f"  Снятие всего остатка, новый баланс: {active.withdraw(active.balance)}")
    check("после снятия остатка баланс равен нулю", active.balance == 0)

    section("3. Замороженный счёт")
    expect_error("пополнение", AccountFrozenError, lambda: frozen.deposit(100))
    expect_error("снятие", AccountFrozenError, lambda: frozen.withdraw(100))
    check("баланс замороженного счёта не изменился", frozen.balance == 5000)

    section("4. Закрытый счёт")
    expect_error("пополнение", AccountClosedError, lambda: closed.deposit(100))
    expect_error("снятие", AccountClosedError, lambda: closed.withdraw(100))
    check("баланс закрытого счёта не изменился", closed.balance == 100)

    section("5. Некорректные суммы")
    for bad in [0, -50, "100", True, None, float("nan"), float("inf"), 10.555]:
        description = f"пополнение на {bad!r}"
        expect_error(description, InvalidOperationError, lambda: auto.deposit(bad))
    expect_error("снятие суммы -1", InvalidOperationError, lambda: auto.withdraw(-1))
    expect_error(
        "плохая сумма по замороженному счёту: сумма проверяется раньше статуса",
        InvalidOperationError,
        lambda: frozen.deposit(-1),
    )
    check("баланс после всех отказов не изменился", auto.balance == 300)

    section("6. Нехватка средств")
    expect_error(
        "снятие 500 при балансе 300", InsufficientFundsError, lambda: auto.withdraw(500)
    )
    check("баланс после отказа не изменился", auto.balance == 300)

    section("7. Некорректные данные при создании")
    bad_accounts = [
        ("пустой владелец", lambda: BankAccount("   ")),
        ("слишком короткий номер", lambda: BankAccount("Иван", "12")),
        ("неизвестная валюта", lambda: BankAccount("Иван", currency="GBP")),
        ("неизвестный статус", lambda: BankAccount("Иван", status="lost")),
        ("отрицательный начальный баланс", lambda: BankAccount("Иван", balance=-1)),
    ]
    for description, action in bad_accounts:
        expect_error(description, InvalidOperationError, action)

    section("8. Защита модели")
    expect_error(
        "создание абстрактного счёта напрямую",
        TypeError,
        lambda: AbstractAccount("1234", "Иван", 0, AccountStatus.ACTIVE),
    )
    expect_error(
        "присваивание баланса извне",
        AttributeError,
        lambda: setattr(frozen, "balance", 0),
    )
    info = frozen.get_account_info()
    info["balance"] = 0
    check("изменение словаря сведений не меняет счёт", frozen.balance == 5000)

    print()
    if problems:
        print(f"ДЕМОНСТРАЦИЯ ПРОВАЛЕНА. Расхождений: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Демонстрация завершена успешно: модель ведёт себя как ожидалось.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

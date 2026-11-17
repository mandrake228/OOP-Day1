"""Демонстрация дня 4: транзакции, очередь, процессор. Запуск: python demo_day4.py"""

import sys
from datetime import datetime
from decimal import Decimal

from bank import (
    AccountClosedError,
    AccountFrozenError,
    Bank,
    InsufficientFundsError,
    InvalidOperationError,
    NightOperationError,
    PremiumAccount,
    Priority,
    SavingsAccount,
    Transaction,
    TransactionProcessor,
    TransactionQueue,
)
from demo import check, expect_error, problems, section
from demo_day3 import PASSWORD, DemoClock, make_client

A1, A2 = "40817810000000001001", "40817840000000001002"  # Анна: рубли и доллары
P1 = "40817810000000002001"  # премиальный счёт Петра
L1 = "40817810000000003001"  # сберегательный счёт Ли
M1, M2 = "40817978000000004001", "40817810000000004002"  # Мария: евро и рубли
O1 = "40817810000000005001"  # счёт Олега
OUTSIDE = "40702810900000009999"  # счёт в другом банке
NOON = datetime(2026, 11, 16, 12, 0)  # полдень: с него начинают часы демонстрации


def simple(number):
    """Пополнение счёта Анны на 100 рублей с ID вида tx07: для проверок очереди."""
    return Transaction(
        "deposit", 100, recipient=A1, transaction_id=f"tx{number:02d}",
        created_at=NOON,
    )


def expect_refusal(description, error_class, processor, transaction):
    """Исполняет транзакцию и ждёт, что процессор запишет отказ нужного класса."""
    before = len(processor.get_errors())
    processor.process(transaction)
    errors = processor.get_errors()[before:]
    if errors and errors[0]["error"] == error_class.__name__:
        print(f"  [отказ] {description}")
        print(f"          {errors[0]['error']}: {errors[0]['reason']}")
    else:
        print(f"  [РАСХОЖДЕНИЕ] {description}: отказа {error_class.__name__} не было")
        problems.append(description)


class Stand:
    """Стенд для раздела: банк, пять клиентов, семь счетов, очередь и процессор."""

    def __init__(self):
        self.clock = DemoClock()  # часы из демонстрации дня 3: показывают полдень
        self.bank = Bank(clock=self.clock.now)
        people = [
            ("anna", "Смирнова Анна Сергеевна"),
            ("petr", "Иванов Пётр Алексеевич"),
            ("liwei", "Ли Вэй"),
            ("maria", "Орлова Мария Игоревна"),
            ("oleg", "Титов Олег Николаевич"),
        ]
        for client_id, full_name in people:
            client = make_client(client_id, full_name, email=f"{client_id}@example.com")
            self.bank.add_client(client, PASSWORD)
        open_account = self.bank.open_account
        open_account("anna", account_id=A1, balance=10000)
        open_account("anna", account_id=A2, balance=300, currency="USD")
        open_account(
            "petr", PremiumAccount, account_id=P1, balance=1000,
            overdraft_limit=5000, fee=50,
        )
        open_account(
            "liwei", SavingsAccount, account_id=L1, balance=20000, min_balance=5000
        )
        open_account("maria", account_id=M1, balance=500, currency="EUR")
        open_account("maria", account_id=M2)
        open_account("oleg", account_id=O1, balance=200)
        self.bank.freeze_account(M2)  # этот счёт заморожен с самого начала
        self.queue = TransactionQueue()
        self.processor = TransactionProcessor(self.bank)

    def make(self, number, kind, amount, **fields):
        """Создаёт транзакцию с ID вида tx07 и временем по часам стенда."""
        return Transaction(
            kind, amount, transaction_id=f"tx{number:02d}",
            created_at=self.clock.now(), **fields,
        )

    def balance(self, account_id):
        """Баланс счёта по номеру."""
        return self.bank.get_account(account_id).balance

    def run(self):
        """Запускает процессор и возвращает ID обработанных транзакций."""
        handled = self.processor.process_queue(self.queue)
        return [transaction.transaction_id for transaction in handled]

    def show_accounts(self, title):
        """Печатает все счета банка."""
        print(f"  {title}:")
        for account in self.bank.search_accounts():
            print(f"    {account}")


def show_transactions():
    section("1. Транзакции")
    deposit = Transaction(
        "deposit", 5000, recipient=A1, transaction_id="tx01", created_at=NOON
    )
    withdrawal = Transaction(
        "withdrawal", 2000, sender=L1, transaction_id="tx02", created_at=NOON
    )
    transfer = Transaction(
        "Transfer", 100, currency="usd", sender=A2, recipient=A1,
        transaction_id="tx03", created_at=NOON,
    )
    external = Transaction("external_transfer", 10000, sender=L1, recipient=OUTSIDE)
    for transaction in (deposit, withdrawal, transfer, external):
        print(f"  {transaction}")
    print("  Сведения о переводе:")
    for key, value in transfer.get_transaction_info().items():
        print(f"    {key}: {value}")
    generated = len(external.transaction_id) == 8
    check("ID без указания сгенерирован: 8 символов", generated)
    other = Transaction("deposit", 1, recipient=A1)
    different = other.transaction_id != external.transaction_id
    check("у двух транзакций без ID они разные", different)
    timed = isinstance(other.created_at, datetime)
    check("время создания без указания взято у компьютера", timed)
    fresh = (transfer.status, transfer.fee, transfer.attempts) == ("pending", 0, 0)
    check("новая транзакция ожидает: комиссия 0.00, попыток 0", fresh)
    found = transfer.transaction_type == "transfer" and transfer.currency == "USD"
    check("тип и валюта найдены по коду в любом регистре", found)
    check("в строке транзакции полный номер счёта скрыт", A1 not in str(transfer))

    bad = [
        ("неизвестный тип", "gift", 100, {"recipient": A1}),
        ("нулевая сумма", "deposit", 0, {"recipient": A1}),
        ("сумма строкой", "deposit", "100", {"recipient": A1}),
        ("неизвестная валюта", "deposit", 100, {"currency": "GBP", "recipient": A1}),
        ("пополнение без получателя", "deposit", 100, {}),
        ("пополнение с отправителем", "deposit", 100, {"sender": A2, "recipient": A1}),
        ("перевод без получателя", "transfer", 100, {"sender": A1}),
        ("перевод на тот же счёт", "transfer", 100, {"sender": A1, "recipient": A1}),
        ("короткий номер счёта", "deposit", 100, {"recipient": "12"}),
        ("короткий ID", "deposit", 100, {"recipient": A1, "transaction_id": "x"}),
        ("время строкой", "deposit", 100, {"recipient": A1, "created_at": "12:00"}),
    ]
    for description, kind, amount, fields in bad:
        expect_error(
            description, InvalidOperationError,
            lambda: Transaction(kind, amount, **fields),
        )
    expect_error(
        "присваивание суммы извне", AttributeError,
        lambda: setattr(transfer, "amount", 1),
    )
    info = transfer.get_transaction_info()
    info["amount"] = 1
    check("изменение сведений не меняет транзакцию", transfer.amount == 100)

    transfer.complete(0, NOON)  # в работе этот метод вызывает процессор
    finished = transfer.status == "completed" and transfer.finished_at == NOON
    check("транзакция выполнена, время завершения записано", finished)
    final = [
        ("отмена выполненной транзакции", lambda: transfer.cancel(NOON)),
        ("отклонение выполненной транзакции", lambda: transfer.fail("поздно", NOON)),
        ("повторное выполнение", lambda: transfer.complete(0, NOON)),
        ("отклонение без причины", lambda: deposit.fail("   ", NOON)),
    ]
    for description, action in final:
        expect_error(description, InvalidOperationError, action)
    check("отказ не изменил транзакцию: она ожидает", deposit.status == "pending")


def show_queue():
    section("2. Очередь")
    queue = TransactionQueue()
    slow, urgent, usual = simple(1), simple(2), simple(3)
    one_pm = NOON.replace(hour=13)
    queue.add(slow, priority="low")
    queue.add(urgent, priority=Priority.HIGH, run_at=one_pm)  # отложена до 13:00
    queue.add(usual)
    print("  Очередь в порядке обслуживания:")
    for entry in queue.get_entries():
        run_at = entry["run_at"]
        when = "сразу" if run_at is None else f"не раньше {run_at:%H:%M}"
        name = entry["transaction"].transaction_id
        print(f"    {name} | {entry['priority']} | {when}")
    order = [entry["transaction"].transaction_id for entry in queue.get_entries()]
    check("порядок: срочная, обычная, несрочная", order == ["tx02", "tx03", "tx01"])
    check("в очереди три транзакции", len(queue) == 3)

    check("12:00: срочная отложена, выдана обычная", queue.next_ready(NOON) is usual)
    almost = NOON.replace(minute=59)
    check("12:59: срочная всё ещё ждёт", queue.next_ready(almost) is usual)
    check("13:00: срочная выдана точно в срок", queue.next_ready(one_pm) is urgent)
    check("выдача не убирает транзакцию из очереди", len(queue) == 3)
    queue.reschedule("tx02", NOON)
    check("после переноса на 12:00 срочная первая", queue.next_ready(NOON) is urgent)

    cancelled = queue.cancel("tx02", at=NOON)
    marked = cancelled.status == "cancelled" and cancelled.finished_at == NOON
    check("отмена: статус cancelled и время отмены записаны", marked)
    check("отменённая транзакция покинула очередь", len(queue) == 2)
    queue.cancel("tx03")  # момент не указан: очередь берёт время компьютера
    timed = isinstance(usual.finished_at, datetime)
    check("отмена без указания времени тоже ставит отметку", timed)

    extra = simple(4)
    refusals = [
        ("повторная постановка в очередь", lambda: queue.add(slow)),
        ("в очередь передана не транзакция", lambda: queue.add("tx05")),
        ("неизвестный приоритет", lambda: queue.add(extra, priority="urgent")),
        ("время исполнения строкой", lambda: queue.add(extra, run_at="13:00")),
        ("отмена неизвестного ID", lambda: queue.cancel("tx99")),
        ("повторная отмена", lambda: queue.cancel("tx02")),
        ("постановка отменённой транзакции", lambda: queue.add(urgent)),
        ("удаление ожидающей транзакции", lambda: queue.remove("tx01")),
    ]
    for description, action in refusals:
        expect_error(description, InvalidOperationError, action)
    check("после всех отказов в очереди одна транзакция", len(queue) == 1)


def show_ten():
    section("3. Десять транзакций")
    stand = Stand()
    bank, queue, make, clock = stand.bank, stand.queue, stand.make, stand.clock
    stand.show_accounts("Счета до обработки")
    total_before = bank.get_total_balance()

    ten = [
        make(1, "deposit", 5000, recipient=A1),
        make(2, "withdrawal", 2000, sender=L1),
        make(3, "transfer", 3000, sender=A1, recipient=L1),
        make(4, "transfer", 100, currency="USD", sender=A2, recipient=A1),
        make(5, "external_transfer", 10000, sender=L1, recipient=OUTSIDE),
        make(6, "transfer", 4000, sender=P1, recipient=A1),
        make(7, "transfer", 900, sender=O1, recipient=A1),
        make(8, "transfer", 500, sender=A1, recipient=M2),
        make(9, "deposit", 1000, recipient=O1),
        make(10, "withdrawal", 100, currency="EUR", sender=M1),
    ]
    priorities = {"tx03": "high", "tx06": "low", "tx09": "high"}  # остальные normal
    later = NOON.replace(minute=1)  # 12:01
    for transaction in ten:
        name = transaction.transaction_id
        queue.add(
            transaction, priority=priorities.get(name, "normal"),
            run_at=later if name == "tx09" else None,  # tx09 отложена до 12:01
        )
    check("десять транзакций созданы и стоят в очереди", len(queue) == 10)
    order = [entry["transaction"].transaction_id for entry in queue.get_entries()]
    print(f"  Порядок обслуживания: {', '.join(order)}")
    queue.cancel("tx10", at=clock.now())
    check("tx10 отменена, в очереди осталось девять", len(queue) == 9)

    first = stand.run()
    print(f"  Запуск в 12:00, обработаны: {', '.join(first)}")
    expected = ["tx03", "tx01", "tx02", "tx04", "tx05", "tx07", "tx08", "tx06"]
    check("срочная tx03 первая, несрочная tx06 последняя", first == expected)
    check("повторный запуск в 12:00 ничего не обрабатывает", stand.run() == [])
    clock.set(12, 1)
    second = stand.run()
    print(f"  Запуск в 12:01, обработаны: {', '.join(second)}")
    check("отложенная tx09 раньше повторов", second == ["tx09", "tx07", "tx08"])
    clock.set(12, 2)
    third = stand.run()
    print(f"  Запуск в 12:02, обработаны: {', '.join(third)}")
    check("в третьем запуске осталась только tx08", third == ["tx08"])

    print("  Итог по транзакциям:")
    for transaction in ten:
        note = f"попыток: {transaction.attempts}, комиссия: {transaction.fee}"
        print(f"    {transaction} | {note}")
    print(f"  Причина отказа tx08: {ten[7].failure_reason}")
    statuses = [transaction.status for transaction in ten]
    counts = [statuses.count(name) for name in ("completed", "failed", "cancelled")]
    check("итог: 8 выполнены, 1 отклонена, 1 отменена", counts == [8, 1, 1])
    check("tx07 выполнена со второй попытки", ten[6].attempts == 2)
    check("tx08 отклонена после третьей попытки", ten[7].attempts == 3)
    check("комиссия внешнего перевода tx05 равна 100.00", ten[4].fee == 100)
    check("очередь пуста", len(queue) == 0)

    stand.show_accounts("Счета после обработки")
    balances = [str(stand.balance(name)) for name in (A1, A2, P1, L1, M1, M2, O1)]
    expected = [
        "25900.00", "200.00", "-3050.00", "10900.00", "500.00", "0.00", "300.00",
    ]
    check("балансы всех семи счетов сошлись с расчётом", balances == expected)
    total_after = bank.get_total_balance()
    print(f"  Сумма банка в RUB: было {total_before}, стало {total_after}")
    grown = total_after - total_before == Decimal("2850.00")
    check("сумма в RUB выросла на 2850.00", grown)


def show_rules():
    section("4. Правила переводов")
    stand = Stand()
    bank, processor, make = stand.bank, stand.processor, stand.make
    balance, process = stand.balance, stand.processor.process

    print("  Правило 1: перевод не уводит счёт в минус, кроме премиального")
    poor = make(1, "transfer", 500, sender=O1, recipient=A1)
    expect_refusal("обычный счёт: 500 при балансе 200", InsufficientFundsError,
                   processor, poor)
    check("деньги не двигались", balance(O1) == 200 and balance(A1) == 10000)
    process(make(2, "transfer", 3000, sender=P1, recipient=A1))
    check("премиальный ушёл в минус: 1000 - 3000 - 50 = -2050", balance(P1) == -2050)
    process(make(3, "transfer", 1000, sender=P1, recipient=A1))
    check("премиальный переводит и из минуса: -3100", balance(P1) == -3100)
    over = make(4, "transfer", 2000, sender=P1, recipient=A1)
    expect_refusal("премиальный счёт сверх овердрафта", InsufficientFundsError,
                   processor, over)
    saver = make(5, "transfer", 16000, sender=L1, recipient=A1)
    expect_refusal("сберегательный счёт: минимальный остаток", InsufficientFundsError,
                   processor, saver)
    check("сберегательный счёт не изменился", balance(L1) == 20000)

    print("  Правило 2: замороженный счёт не отдаёт и не получает деньги")
    from_frozen = make(6, "transfer", 100, sender=M2, recipient=A1)
    expect_refusal("счёт отправителя заморожен", AccountFrozenError,
                   processor, from_frozen)
    before = balance(A1)
    to_frozen = make(7, "transfer", 500, sender=A1, recipient=M2)
    expect_refusal("счёт получателя заморожен", AccountFrozenError,
                   processor, to_frozen)
    check("у отправителя ничего не списано", balance(A1) == before)
    check("отказ временный: транзакция ждёт повтора", to_frozen.status == "pending")
    bank.close_account(O1)
    to_closed = make(8, "deposit", 100, recipient=O1)
    expect_refusal("счёт получателя закрыт", AccountClosedError, processor, to_closed)
    at_once = to_closed.status == "failed" and to_closed.attempts == 1
    check("закрытый счёт: отклонена сразу, с первой попытки", at_once)

    print("  Правило 3: внешний перевод стоит 1% от суммы")
    external = make(9, "external_transfer", 10000, sender=L1, recipient=OUTSIDE)
    fee = processor.calculate_fee(external)
    check("комиссию можно узнать заранее: 100.00", fee == 100)
    process(external)
    charged = balance(L1) == 9900 and external.fee == 100
    check("списано 10100.00, комиссия записана в транзакцию", charged)
    odd = make(10, "external_transfer", Decimal("333.33"), sender=A1, recipient=OUTSIDE)
    before = balance(A1)
    process(odd)
    rounded = odd.fee == Decimal("3.33") and before - balance(A1) == Decimal("336.66")
    check("комиссия округлена до копеек: 3.33", rounded)
    inner = make(11, "transfer", 1000, sender=A1, recipient=L1)
    process(inner)
    check("перевод внутри банка — без комиссии", inner.fee == 0)
    before = balance(P1)
    process(make(12, "external_transfer", 1000, sender=P1, recipient=OUTSIDE))
    both = before - balance(P1) == 1060
    check("премиальный: 1000 + комиссия перевода 10 + комиссия счёта 50", both)
    wrong = make(13, "external_transfer", 100, sender=A1, recipient=L1)
    expect_refusal("внешний перевод на счёт своего банка", InvalidOperationError,
                   processor, wrong)


def show_conversion():
    section("5. Конвертация")
    stand = Stand()
    bank, processor, make = stand.bank, stand.processor, stand.make
    balance, convert = stand.balance, stand.processor.convert

    print("  Курсы процессора: сколько рублей стоит единица валюты")
    for currency, rate in processor.rates.items():
        print(f"    {currency}: {rate}")
    samples = [
        (100, "USD", "RUB", "9000.00"),
        (5000, "RUB", "USD", "55.56"),
        (100, "EUR", "USD", "111.11"),
        (1000, "KZT", "RUB", "200.00"),
        (100, "CNY", "RUB", "1250.00"),
    ]
    for amount, source, target, expected in samples:
        result = convert(amount, source, target)
        check(f"{amount} {source} — это {result} {target}", str(result) == expected)
    same = convert(Decimal("77.77"), "EUR", "eur") == Decimal("77.77")
    check("в той же валюте сумма не меняется", same)
    expect_error(
        "0.01 KZT в USD: меньше одной копейки", InvalidOperationError,
        lambda: convert(Decimal("0.01"), "KZT", "USD"),
    )

    processor.process(make(1, "transfer", 100, currency="USD", sender=A2, recipient=A1))
    moved = balance(A2) == 200 and balance(A1) == 19000
    check("100 USD с долларового счёта на рублёвый: +9000 RUB", moved)
    processor.process(make(2, "transfer", 100, currency="USD", sender=A1, recipient=M1))
    moved = balance(A1) == 10000 and balance(M1) == 590
    check("100 USD с рублёвого счёта на счёт в евро: -9000 RUB, +90 EUR", moved)
    abroad = make(
        3, "external_transfer", 10, currency="USD", sender=A1, recipient=OUTSIDE
    )
    processor.process(abroad)
    charged = abroad.fee == Decimal("0.10") and balance(A1) == 9091
    check("внешний перевод 10 USD: комиссия 0.10 USD, списано 909 RUB", charged)
    tiny = make(4, "transfer", Decimal("0.01"), currency="KZT", sender=A1, recipient=A2)
    expect_refusal("перевод 0.01 KZT с рублёвого счёта", InvalidOperationError,
                   processor, tiny)
    intact = balance(A1) == 9091 and balance(A2) == 200
    check("счета после отказа не изменились", intact)

    own = TransactionProcessor(bank, rates={"usd": 95})
    check("свой курс доллара: 1 USD — это 95 RUB", own.convert(1, "USD", "RUB") == 95)
    check("остальные курсы прежние", own.convert(1, "EUR", "RUB") == 100)
    bad_rates = [
        ("нулевой курс", {"USD": 0}),
        ("курс строкой", {"USD": "90"}),
        ("курс неизвестной валюты", {"GBP": 120}),
        ("курсы списком, а не словарём", [90]),
    ]
    for description, rates in bad_rates:
        expect_error(
            description, InvalidOperationError,
            lambda: TransactionProcessor(bank, rates=rates),
        )
    processor.rates.clear()
    check("очистка полученных курсов не меняет процессор", len(processor.rates) == 5)


def show_retries():
    section("6. Повторные попытки")
    stand = Stand()
    bank, queue, processor = stand.bank, stand.queue, stand.processor
    make, clock = stand.make, stand.clock

    print("  Не хватило денег, потом они пришли")
    short = make(1, "transfer", 900, sender=O1, recipient=A1)
    queue.add(short)
    stand.run()
    waiting = (short.status, short.attempts) == ("pending", 1)
    check("12:00: отказ, транзакция ждёт, попыток 1", waiting)
    check("она осталась в очереди", len(queue) == 1)
    processor.process(make(2, "deposit", 1000, recipient=O1))  # деньги пришли
    clock.set(12, 0, 30)
    check("12:00:30: минута не прошла, повтора нет", stand.run() == [])
    clock.set(12, 1)
    stand.run()
    passed = (short.status, short.attempts) == ("completed", 2)
    check("12:01: выполнена со второй попытки", passed)

    print("  Счёт был заморожен, потом его разморозили")
    gift = make(3, "deposit", 100, recipient=M2)
    queue.add(gift)
    stand.run()
    check("12:01: счёт заморожен, транзакция ждёт", gift.status == "pending")
    bank.unfreeze_account(M2)
    clock.set(12, 2)
    stand.run()
    arrived = gift.status == "completed" and stand.balance(M2) == 100
    check("12:02: после разморозки выполнена", arrived)

    print("  Три отказа подряд")
    hopeless = make(4, "transfer", 5000, sender=O1, recipient=A1)
    queue.add(hopeless)
    for minute in (2, 3, 4):
        clock.set(12, minute)
        stand.run()
        print(f"    12:0{minute} | попытка {hopeless.attempts} | {hopeless.status}")
    rejected = (hopeless.status, hopeless.attempts) == ("failed", 3)
    check("после третьей попытки транзакция отклонена", rejected)
    explained = bool(hopeless.failure_reason) and hopeless.finished_at == clock.now()
    check("причина отказа и время завершения записаны", explained)
    check("отклонённая транзакция покинула очередь", len(queue) == 0)

    print("  Окончательный отказ: повторять бесполезно")
    lost = make(5, "transfer", 100, sender=A1, recipient="00000000")
    expect_refusal("счёт получателя не найден", InvalidOperationError, processor, lost)
    big = make(6, "transfer", 150000, sender=A1, recipient=L1)
    expect_refusal("сумма больше лимита на одно снятие", InvalidOperationError,
                   processor, big)
    at_once = (lost.status, lost.attempts, big.status, big.attempts)
    check("обе отклонены с первой попытки", at_once == ("failed", 1, "failed", 1))

    print("  Отмена и повторное исполнение")
    again = make(7, "transfer", 5000, sender=O1, recipient=A1)
    queue.add(again)
    stand.run()
    queue.cancel("tx07", at=clock.now())
    check("транзакцию, ждущую повтора, можно отменить", again.status == "cancelled")
    expect_error(
        "повторное исполнение выполненной транзакции", InvalidOperationError,
        lambda: processor.process(short),
    )


def show_errors():
    section("7. Журнал ошибок")
    stand = Stand()
    queue, processor, make = stand.queue, stand.processor, stand.make

    good = make(1, "deposit", 500, recipient=A1)
    poor = make(2, "transfer", 5000, sender=O1, recipient=A1)
    lost = make(3, "withdrawal", 100, sender="00000000")
    for transaction in (good, poor, lost):
        queue.add(transaction)
    for minute in (0, 1, 2):
        stand.clock.set(12, minute)
        stand.run()

    journal = processor.get_errors()
    print("  Журнал ошибок процессора:")
    for record in journal:
        mark = "окончательный" if record["final"] else "будет повтор"
        when, name = record["time"], record["transaction_id"]
        print(f"    {when:%H:%M} | {name} | попытка {record['attempt']} | {mark}")
        print(f"          {record['error']}: {record['reason']}")
    check("в журнале четыре записи", len(journal) == 4)
    finals = [record["final"] for record in journal]
    expected = [False, True, False, True]
    check("окончательные отказы: второй и четвёртый", finals == expected)
    check("о транзакции tx02 три записи", len(processor.get_errors("tx02")) == 3)
    check("о выполненной tx01 записей нет", processor.get_errors("tx01") == [])
    check("по неизвестному ID записей нет", processor.get_errors("tx99") == [])
    matches = poor.failure_reason == journal[-1]["reason"]
    check("причина отказа в транзакции — текст последней ошибки", matches)
    reasons = " ".join(record["reason"] for record in journal)
    check("в причинах нет полных номеров счетов", O1 not in reasons)

    journal.clear()
    processor.get_errors()[0]["reason"] = "стёрто"
    fresh = processor.get_errors()
    intact = len(fresh) == 4 and fresh[0]["reason"] != "стёрто"
    check("журнал нельзя изменить через полученный список", intact)
    expect_error(
        "в процессор передана не транзакция", InvalidOperationError,
        lambda: processor.process("tx01"),
    )
    expect_error(
        "в процессор передана не очередь", InvalidOperationError,
        lambda: processor.process_queue([good]),
    )
    check("ошибки вызова в журнал не попали", len(processor.get_errors()) == 4)


def show_night():
    section("8. Ночной запрет")
    stand = Stand()
    bank, queue, processor = stand.bank, stand.queue, stand.processor
    make, clock, balance = stand.make, stand.clock, stand.balance

    clock.set(23, 59, 59)
    evening = make(1, "transfer", 100, sender=A1, recipient=L1)
    processor.process(evening)
    check("23:59:59 — перевод проходит", evening.status == "completed")
    clock.set(0, 0)
    midnight = make(2, "transfer", 100, sender=A1, recipient=L1)
    expect_refusal("00:00:00 — перевод", NightOperationError, processor, midnight)

    clock.set(2, 30)
    lost = "00000000"  # такого счёта в банке нет
    night = [
        ("пополнение", "deposit", {"recipient": A1}),
        ("снятие", "withdrawal", {"sender": A1}),
        ("перевод", "transfer", {"sender": P1, "recipient": A1}),
        ("внешний перевод", "external_transfer", {"sender": L1, "recipient": OUTSIDE}),
        ("перевод на неизвестный счёт", "transfer", {"sender": A1, "recipient": lost}),
    ]
    refused = []
    for number, (description, kind, fields) in enumerate(night, start=3):
        transaction = make(number, kind, 500, **fields)
        expect_refusal(f"02:30 — {description}", NightOperationError,
                       processor, transaction)
        refused.append(transaction)
    at_once = all(
        (transaction.status, transaction.attempts) == ("failed", 1)
        for transaction in refused
    )
    check("ночной отказ окончательный: отклонены с первой попытки", at_once)
    balances = [str(balance(name)) for name in (A1, P1, L1)]
    check("ночью деньги не двигались", balances == ["9900.00", "1000.00", "20100.00"])

    print("  Очередь ночью")
    ready = make(8, "deposit", 100, recipient=A1)
    morning = make(9, "deposit", 100, recipient=A1)
    queue.add(ready)
    queue.add(morning, run_at=clock.now().replace(hour=5, minute=0))  # до 05:00
    check("02:30 — очередь выдала только готовую транзакцию", stand.run() == ["tx08"])
    rejected = ready.status == "failed" and len(queue) == 1
    check("готовая отклонена, отложенная до 05:00 осталась ждать", rejected)
    clock.set(4, 59, 59)
    last = make(10, "deposit", 100, recipient=A1)
    expect_refusal("04:59:59 — пополнение", NightOperationError, processor, last)
    check("04:59:59 — отложенная ещё ждёт", stand.run() == [])
    clock.set(5, 0)
    check("05:00:00 — очередь исполняет отложенную", stand.run() == ["tx09"])
    arrived = morning.status == "completed" and balance(A1) == 10000
    check("отложенная выполнена, на счёте снова 10000.00", arrived)

    journal = bank.get_suspicious_actions()
    print("  Журнал подозрительных действий банка:")
    for record in journal:
        when, who = record["time"], record["client_id"]
        print(f"    {when:%H:%M} | {record['action']} | {who} | {record['reason']}")
    check("каждая ночная попытка помечена: восемь записей", len(journal) == 8)
    owners = [record["client_id"] for record in journal]
    expected = ["anna", "anna", "anna", "petr", "liwei", "anna", "anna", "anna"]
    check("запись называет клиента: у пополнения это получатель", owners == expected)
    kinds = {record["action"] for record in journal}
    known = {"deposit", "withdrawal", "transfer", "external_transfer"}
    check("запись называет тип транзакции", kinds == known)
    reasons = " ".join(record["reason"] for record in journal)
    check("в причинах нет полных номеров счетов", A1 not in reasons)
    errors = processor.get_errors()
    final = len(errors) == 8 and all(record["final"] for record in errors)
    check("в журнале ошибок процессора те же восемь отказов, все окончательные", final)


def main():
    parts = [
        show_transactions,
        show_queue,
        show_ten,
        show_rules,
        show_conversion,
        show_retries,
        show_errors,
        show_night,
    ]
    for part in parts:
        part()
    print()
    if problems:
        print(f"ДЕМОНСТРАЦИЯ ПРОВАЛЕНА. Расхождений: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Демонстрация дня 4 завершена успешно: транзакции и очередь работают.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Демонстрация дня 6: вся банковская система в действии. Запуск: python demo_day6.py"""

import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bank import (
    AuthenticationError,
    Bank,
    BankSystem,
    ClientBlockedError,
    ClientSession,
    InvalidOperationError,
    InvestmentAccount,
    NightOperationError,
    PremiumAccount,
    SavingsAccount,
)
from demo import check, expect_error, problems, section
from demo_day3 import PASSWORD, WRONG, DemoClock, make_client

A1, A2 = "40817810000000001001", "40817840000000001002"  # Анна: рубли и доллары
P1, P2 = "40817810000000002001", "40817978000000002002"  # Пётр: премиальный и евро
L1, L2 = "40817810000000003001", "40817156000000003002"  # Ли: сберегательный и юани
M1, M2 = "40817810000000004001", "40817810000000004002"  # Мария: два рублёвых
O1, O2 = "40817810000000005001", "40817398000000005002"  # Олег: вклады и тенге
S1, S2 = "40817810000000006001", "40817810000000006002"  # София: два рублёвых
T1 = "40817810000000007001"  # Тимур
ACCOUNTS = (A1, A2, P1, P2, L1, L2, M1, M2, O1, O2, S1, S2, T1)
OUTSIDE = "40702810900000009999"  # счёт в другом банке
LOST = "00000000"  # такого счёта в банке нет
CLIENTS = [
    ("anna", "Смирнова Анна Сергеевна"),
    ("petr", "Иванов Пётр Алексеевич"),
    ("liwei", "Ли Вэй"),
    ("maria", "Орлова Мария Игоревна"),
    ("oleg", "Титов Олег Николаевич"),
    ("sofia", "Кузнецова София Андреевна"),
    ("timur", "Алиев Тимур Рашидович"),
]


def at(hour, minute=0, day=16):
    """Момент по часам демонстрации: 16 ноября 2026 года или другой день ноября."""
    return datetime(2026, 11, day, hour, minute)


def ids(first, last):
    """ID транзакций системы подряд: ids(1, 3) — это T0001, T0002, T0003."""
    return [f"T{number:04d}" for number in range(first, last + 1)]


class World:
    """Мир демонстрации: часы, банк с клиентами и счетами, банковская система."""

    def __init__(self, folder):
        self.clock = DemoClock()  # часы из демонстрации дня 3
        self.clock.moment = at(8)  # утро 16 ноября: банк открывается
        self.bank = Bank(clock=self.clock.now)
        for client_id, full_name in CLIENTS:
            client = make_client(client_id, full_name, email=f"{client_id}@example.com")
            self.bank.add_client(client, PASSWORD)
        self.open_accounts()
        self.path = Path(folder) / "audit.log"  # файл журнала во временной папке
        self.system = BankSystem(self.bank, audit_file=self.path)
        self.before = None  # общий баланс до симуляции: его запишет раздел 1

    def open_accounts(self):
        """Тринадцать счетов семи клиентов; один заморожен, один закрыт."""
        open_account = self.bank.open_account
        open_account("anna", account_id=A1, balance=150000)
        open_account("anna", account_id=A2, balance=2000, currency="USD")
        open_account(
            "petr", PremiumAccount, account_id=P1, balance=300000,
            overdraft_limit=50000, fee=100,
        )
        open_account("petr", account_id=P2, balance=1500, currency="EUR")
        open_account(
            "liwei", SavingsAccount, account_id=L1, balance=80000, min_balance=10000
        )
        open_account("liwei", account_id=L2, balance=20000, currency="CNY")
        open_account("maria", account_id=M1, balance=30000)
        open_account("maria", account_id=M2)
        invest = open_account("oleg", InvestmentAccount, account_id=O1, balance=250000)
        invest.invest("bonds", 150000)  # снять можно только 100 000
        open_account("oleg", account_id=O2, balance=400000, currency="KZT")
        open_account("sofia", account_id=S1, balance=60000)
        open_account("sofia", account_id=S2)
        open_account("timur", account_id=T1, balance=20000)
        self.bank.freeze_account(M2)  # заморожен с самого начала
        self.bank.close_account(S2)  # закрыт с самого начала

    def balances(self):
        """Балансы тринадцати счетов строками, в порядке ACCOUNTS."""
        return [str(self.bank.get_account(name).balance) for name in ACCOUNTS]


BEFORE = "RUB 890000.00, USD 2000.00, EUR 1500.00, KZT 400000.00, CNY 20000.00"


def money(totals):
    """Суммы по валютам одной строкой: RUB 890000.00, USD 2000.00, ..."""
    return ", ".join(f"{code} {amount}" for code, amount in totals.items())


def show_init(world):
    section("1. Инициализация")
    bank = world.bank
    clients = bank.get_clients_ranking()  # все клиенты банка, по рублёвым счетам
    print(f"  Клиентов: {len(clients)}")
    for row in clients:
        print(f"    {row['client_id']:6} {row['full_name']}")
    accounts = bank.search_accounts()  # все счета банка в порядке открытия
    print(f"  Счетов: {len(accounts)}")
    for account in accounts:
        owner = bank.get_owner_id(account.account_id)
        print(
            f"    {owner:6} {type(account).__name__:17} ****{account.account_id[-4:]} "
            f"{account.balance:>10} {account.currency} {account.status}"
        )
    known = sorted((row["client_id"], row["full_name"]) for row in clients)
    check("клиентов от 5 до 10: в банке все семеро",
          5 <= len(clients) <= 10 and known == sorted(CLIENTS))
    check("счетов от 10 до 15: их 13",
          10 <= len(accounts) <= 15 and len(accounts) == 13)
    kinds = {type(account).__name__ for account in accounts}
    currencies = {account.currency for account in accounts}
    check("все четыре типа счетов и все пять валют",
          (len(kinds), len(currencies)) == (4, 5))
    statuses = [bank.get_account(name).status for name in (M2, S2)]
    check("один счёт заморожен, один закрыт", statuses == ["frozen", "closed"])
    world.before = world.system.total_balance()
    print(f"  Общий баланс до: {money(world.before['by_currency'])}")
    print(f"  Всего в рублях: {world.before['total_rub']}")
    check("суммы по каждой валюте до симуляции сошлись",
          money(world.before["by_currency"]) == BEFORE)
    check("общий баланс до симуляции — 1550000.00 рублей",
          world.before["total_rub"] == Decimal("1550000.00"))
    expect_error("система без банка", InvalidOperationError, lambda: BankSystem("bank"))


WAVES = [  # момент; шаги до приёма; заявки: тип, сумма, поля; шаги после приёма
    (at(9), [], [
        ("deposit", 5000, {"recipient": M1}),
        ("transfer", 3000, {"sender": A1, "recipient": M1}),
        ("withdrawal", 2000, {"sender": L1}),
        ("transfer", 100, {"currency": "USD", "sender": A2, "recipient": A1}),
        ("external_transfer", 10000, {"sender": L1, "recipient": OUTSIDE}),
        ("deposit", 1000, {"currency": "EUR", "recipient": P2}),
        ("withdrawal", 500, {"sender": S1}),
        ("transfer", 2000, {"sender": T1, "recipient": S1}),
        ("deposit", 50000, {"currency": "KZT", "recipient": O2}),
        ("transfer", 200, {"currency": "CNY", "sender": L2, "recipient": P1}),
        ("transfer", 500, {"sender": M1, "recipient": M2}),
        ("transfer", 1000, {"sender": A1, "recipient": LOST}),
        ("withdrawal", 5000, {"sender": S2}),
        ("external_transfer", 1000, {"sender": P1, "recipient": M1}),
    ], [("run", at(9)), ("run", at(9, 1)), ("run", at(9, 2))]),
    (at(10), [], [
        ("withdrawal", 60000, {"sender": O1}),
        ("transfer", 70000, {"sender": P1, "recipient": L1}),
        ("withdrawal", 100, {"sender": M1}),
        ("withdrawal", 100, {"sender": M1}),
        ("withdrawal", 100, {"sender": M1}),
        ("withdrawal", 100, {"sender": M1}),
        ("transfer", 55000, {"sender": A1, "recipient": S1}),
        ("withdrawal", 120000, {"sender": P1}),
        ("withdrawal", 150000, {"sender": A1}),
        ("external_transfer", 800, {"currency": "USD", "sender": A2,
                                    "recipient": OUTSIDE}),
    ], [("run", at(10))]),
    (at(12), [], [
        ("deposit", 1000, {"recipient": T1, "priority": "low"}),
        ("transfer", 5000, {"sender": S1, "recipient": M1, "priority": "high"}),
        ("withdrawal", 1000, {"sender": A1, "run_at": at(12, 30)}),
        ("transfer", 300, {"sender": M1, "recipient": A1}),
        ("withdrawal", 70000, {"sender": S1}),
    ], [("cancel", "T0028"), ("queue", None), ("run", at(12)), ("run", at(12, 1)),
        ("run", at(12, 2)), ("run", at(12, 30))]),
    (at(13), [("block", "timur")], [
        ("withdrawal", 1000, {"sender": T1}),
        ("deposit", 500, {"recipient": T1}),
        ("transfer", 1000, {"sender": S1, "recipient": T1}),
    ], [("run", at(13))]),
    (at(23, 30), [], [
        ("transfer", 2000, {"sender": P1, "recipient": A1, "run_at": at(5, day=17)}),
        ("withdrawal", 500, {"sender": O1}),
    ], [("run", at(23, 30))]),
    (at(2, 30, day=17), [], [
        ("withdrawal", 100, {"sender": M1}),
        ("withdrawal", 60000, {"sender": A1}),
    ], [("run", at(2, 30, day=17)), ("run", at(5, day=17))]),
    (at(9, day=17), [], [
        ("deposit", 10000, {"recipient": L1}),
        ("transfer", 25000, {"sender": O1, "recipient": O2}),
        ("withdrawal", 300, {"currency": "USD", "sender": A2}),
        ("transfer", 15000, {"sender": A1, "recipient": M1}),
    ], [("run", at(9, day=17))]),
]
RUNS = [  # что обработал каждый из тринадцати запусков, по порядку
    ids(1, 14), ["T0011"], ["T0011"],
    ids(15, 24),
    ["T0026", "T0029", "T0025"], ["T0029"], ["T0029"], ["T0027"],
    ids(30, 32),
    ["T0034"], ["T0035", "T0036"], ["T0033"],
    ids(37, 40),
]


def do_step(world, action, value):
    """Шаг волны: запуск очереди, отмена, взгляд на очередь или вход с ошибками."""
    system = world.system
    if action == "run":
        world.clock.moment = value
        handled = system.run()
        print(f"    запуск {value:%d.%m %H:%M}: {', '.join(handled)}")
        return handled
    if action == "cancel":
        info = system.cancel(value)
        print(f"    отменена {value}: статус {info['status']}")
        return info["status"]
    if action == "queue":
        waiting = []
        for item in system.get_queue():
            when = "" if item["run_at"] is None else f" с {item['run_at']:%H:%M}"
            waiting.append(f"{item['transaction_id']} {item['priority']}{when}")
        print(f"    в очереди: {', '.join(waiting)}")
        return waiting
    # остался шаг "block": три неверных пароля подряд блокируют клиента
    errors = [AuthenticationError, AuthenticationError, ClientBlockedError]
    for attempt, error in enumerate(errors, start=1):
        expect_error(f"вход {value} с неверным паролем, попытка {attempt}", error,
                     lambda: system.login(value, WRONG))
    return None


def show_simulation(world):
    section("2. Симуляция: сорок транзакций")
    system = world.system
    world.clock.moment = at(8, 30)
    bad = [
        ("нулевая сумма", lambda: system.submit("deposit", 0, recipient=A1)),
        ("перевод на тот же счёт",
         lambda: system.submit("transfer", 100, sender=A1, recipient=A1)),
        ("неизвестный приоритет",
         lambda: system.submit("deposit", 100, recipient=A1, priority="urgent")),
    ]
    for description, action in bad:
        expect_error(f"заявка: {description}", InvalidOperationError, action)
    results = []
    for moment, before, requests, after in WAVES:
        world.clock.moment = moment
        for action, value in before:  # шаги до приёма: в 13:00 блокируется Тимур
            results.append((action, do_step(world, action, value)))
        names = [
            system.submit(kind, amount, **fields)
            for kind, amount, fields in requests
        ]
        print(f"  {moment:%d.%m %H:%M} принято {len(names)}: {names[0]}–{names[-1]}")
        for action, value in after:
            results.append((action, do_step(world, action, value)))
    names = [info["transaction_id"] for info in system.get_transactions()]
    check("принято 40 транзакций, ID с T0001 по T0040 подряд", names == ids(1, 40))
    runs = [value for action, value in results if action == "run"]
    check("тринадцать запусков, порядок обработки сошёлся", runs == RUNS)
    waiting = [value for action, value in results if action == "queue"]
    check("перед запуском в 12:00 очередь: срочная, обычные, несрочная", waiting == [
        ["T0026 high", "T0027 normal с 12:30", "T0029 normal", "T0025 low"],
    ])
    check("после всех запусков очередь пуста", system.get_queue() == [])


def path_of(audit, name):
    """Путь транзакции по журналу аудита: её события по порядку."""
    return [record["event"].value for record in audit.filter(transaction_id=name)]


def show_log(world):
    section("3. Журнал событий")
    audit = world.system.audit
    records = audit.get_records()
    lines = world.path.read_text(encoding="utf-8").splitlines()
    windows = [
        ("Волна 12:00", at(12), at(12, 30)),
        ("Вечер и ночь", at(23, 30), at(5, day=17)),
    ]
    for title, since, until in windows:
        print(f"  {title}: строки файла журнала")
        for record, line in zip(records, lines):  # запись и строка идут парами
            if since <= record["time"] <= until:
                print(f"    {line}")
    print("  Путь заблокированной T0016: строки файла журнала")
    for record, line in zip(records, lines):
        if record["transaction_id"] == "T0016":
            print(f"    {line}")
    check("в файле 123 строки — столько же, сколько записей",
          len(lines) == len(records) == 123)
    by_event, by_level = {}, {}
    for record in records:
        event, level = record["event"].value, record["level"].value
        by_event[event] = by_event.get(event, 0) + 1
        by_level[level] = by_level.get(level, 0) + 1
    print(f"  Записей по событиям: {by_event}")
    print(f"  Записей по уровням: {by_level}")
    check("по событиям: в очередь 40, оценок 39, исполнено 26, отказов 14, "
          "блокировок 3, отмена 1", by_event == {
              "queued": 40, "risk": 39, "completed": 26, "refused": 14,
              "blocked": 3, "cancelled": 1,
          })
    check("по уровням: info 95, warning 11, error 10, critical 7",
          by_level == {"info": 95, "warning": 11, "error": 10, "critical": 7})
    check("записей об Анне 30", len(audit.filter(client_id="anna")) == 30)
    check("путь T0029: приём, оценка, три отказа",
          path_of(audit, "T0029") == ["queued", "risk"] + ["refused"] * 3)
    check("путь T0028: приём и отмена",
          path_of(audit, "T0028") == ["queued", "cancelled"])
    check("путь T0016: приём, оценка, блокировка",
          path_of(audit, "T0016") == ["queued", "risk", "blocked"])
    queued = [
        (record["data"].get("priority"), record["data"].get("run_at"))
        for record in audit.filter(event="queued", transaction_id="T0027")
    ]
    check("в данных приёма T0027 приоритет и время исполнения",
          queued == [("normal", at(12, 30))])
    quiet = audit.filter(event="queued") + audit.filter(event="cancelled")
    check("приём и отмена — обычные события уровня info",
          {record["level"] for record in quiet} == {"info"})


NEW = "low 1 new_recipient"  # перевод на новый счёт
BIG = "medium 3 large_amount"  # крупная сумма
RISKY = "high 4 large_amount, new_recipient"  # крупная сумма на новый счёт
OUTCOMES = [  # T0001–T0040: риск, баллы и сигналы; статус; попыток; класс ошибки
    ("low 0", "completed", 1, "-"), (NEW, "completed", 1, "-"),
    ("low 0", "completed", 1, "-"), ("low 0", "completed", 1, "-"),
    (NEW, "completed", 1, "-"), (BIG, "completed", 1, "-"),
    ("low 0", "completed", 1, "-"), (NEW, "completed", 1, "-"),
    ("low 0", "completed", 1, "-"), (NEW, "completed", 1, "-"),
    ("low 0", "failed", 3, "AccountFrozenError"),
    (NEW, "failed", 1, "InvalidOperationError"),
    ("low 0", "failed", 1, "AccountClosedError"),
    (NEW, "failed", 1, "InvalidOperationError"),
    (BIG, "completed", 1, "-"), (RISKY, "failed", 1, "HighRiskError"),
    ("low 0", "completed", 1, "-"), ("low 0", "completed", 1, "-"),
    ("low 0", "completed", 1, "-"),
    ("medium 2 frequent_operations", "completed", 1, "-"),
    (RISKY, "failed", 1, "HighRiskError"), (BIG, "completed", 1, "-"),
    (BIG, "failed", 1, "InvalidOperationError"),
    (RISKY, "failed", 1, "HighRiskError"),
    ("low 0", "completed", 1, "-"), (NEW, "completed", 1, "-"),
    ("low 0", "completed", 1, "-"), ("-", "cancelled", 0, "-"),
    (BIG, "failed", 3, "InsufficientFundsError"),
    ("low 0", "failed", 1, "ClientBlockedError"),
    ("low 0", "failed", 1, "ClientBlockedError"),
    (NEW, "completed", 1, "-"), (NEW, "completed", 1, "-"),
    ("low 0", "completed", 1, "-"),
    ("medium 2 night_operation", "failed", 1, "NightOperationError"),
    ("high 5 large_amount, night_operation", "failed", 1, "NightOperationError"),
    ("low 0", "completed", 1, "-"), ("low 0", "completed", 1, "-"),
    ("low 0", "completed", 1, "-"), ("low 0", "completed", 1, "-"),
]
AFTER = [  # балансы после симуляции, в порядке ACCOUNTS
    "142000.00", "1600.00", "180300.00", "2500.00", "77900.00", "19800.00",
    "57600.00", "0.00", "164500.00", "575000.00", "55500.00", "0.00", "20000.00",
]
SIGNALS = {"large_amount", "frequent_operations", "new_recipient", "night_operation"}


def error_of(audit, name):
    """Класс ошибки последнего отказа транзакции по журналу аудита или дефис."""
    refusals = [
        record for record in audit.filter(transaction_id=name)
        if record["event"] in ("refused", "blocked")
    ]
    return refusals[-1]["data"]["error"] if refusals else "-"


def risk_of(info):
    """Оценка риска строкой: уровень, баллы и сигналы. Без оценки — дефис."""
    risk = info["risk"]
    if risk is None:
        return "-"
    signals = ", ".join(signal.value for signal in risk["signals"])
    return f"{risk['level']} {risk['score']} {signals}".strip()


def show_results(world):
    section("4. Итоги симуляции")
    system, audit = world.system, world.system.audit
    infos = system.get_transactions()
    print("  ID | тип | сумма | риск, баллы, сигналы | статус | попыток | отказ")
    table = []
    for info in infos:
        level = risk_of(info)
        error = error_of(audit, info["transaction_id"])
        if info["status"] != "failed":
            error = "-"  # у выполненной и отменённой отказа нет
        table.append((level, info["status"], info["attempts"], error))
        print(f"    {info['transaction_id']} | {info['transaction_type']} | "
              f"{info['amount']} {info['currency']} | {level} | {info['status']} | "
              f"{info['attempts']} | {error}")
    check("риск, сигналы, статус, попытки и отказ всех сорока сошлись",
          table == OUTCOMES)
    fired = {
        signal.value for info in infos if info["risk"] is not None
        for signal in info["risk"]["signals"]
    }
    check("в симуляции сработали все четыре сигнала риска", fired == SIGNALS)
    statuses = [info["status"] for info in infos]
    counts = [statuses.count(name) for name in ("completed", "failed", "cancelled")]
    check("выполнено 26, отклонено 13, отменена 1", counts == [26, 13, 1])
    print(f"  Счета после: {', '.join(world.balances())}")
    check("балансы всех тринадцати счетов сошлись с расчётом",
          world.balances() == AFTER)
    marks = world.bank.get_suspicious_actions()
    print("  Журнал подозрительных действий банка:")
    for mark in marks:
        print(f"    {mark['time']:%d.%m %H:%M} | {mark['action']} | "
              f"{mark['client_id']} | {mark['reason']}")
    check("в журнале банка 7 записей: пароли Тимура, его операции, две ночные", [
        (mark["action"], mark["client_id"]) for mark in marks
    ] == [("authenticate_client", "timur")] * 3 + [
        ("withdrawal", "timur"), ("deposit", "timur"),
        ("withdrawal", "maria"), ("withdrawal", "anna"),
    ])
    night = [
        info for info in infos if info["status"] == "completed"
        and at(0, day=17) <= info["finished_at"] < at(5, day=17)
    ]
    check("ночью не исполнено ничего", night == [])
    check("заявку уже заблокированного Тимура приняли, а отклонили при исполнении",
          path_of(audit, "T0030") == ["queued", "risk", "refused"])
    timur = [info["status"] for info in infos[29:32]]  # T0030, T0031, T0032
    check("Тимур заблокирован: его снятие и пополнение отклонены, перевод ему прошёл",
          timur == ["failed", "failed", "completed"])
    blocked = [info["transaction_id"] for info in infos
               if error_of(audit, info["transaction_id"]) == "HighRiskError"]
    check("днём заблокированы три опасные: T0016, T0021, T0024",
          blocked == ["T0016", "T0021", "T0024"])


DIRECTIONS = {"in": "зачисление", "out": "списание", "own": "между своими"}


def print_history(history):
    """Печатает историю: строка на операцию, под отклонённой — причина отказа."""
    print("  История: ID | направление | тип | сумма | откуда → куда | статус | "
          "комиссия | создана → завершена")
    for row in history:
        done = "-"
        if row["finished_at"] is not None:
            done = f"{row['finished_at']:%d.%m %H:%M}"
        print(f"    {row['transaction_id']} | {DIRECTIONS[row['direction']]} | "
              f"{row['transaction_type']} | {row['amount']} {row['currency']} | "
              f"{row['sender'] or '-'} → {row['recipient'] or '-'} | {row['status']} | "
              f"{row['fee']} | {row['created_at']:%d.%m %H:%M} → {done}")
        if row["failure_reason"] is not None:
            print(f"      причина отказа: {row['failure_reason']}")


def show_cabinet(world):
    section("5. Кабинет клиента")
    system, bank = world.system, world.bank
    world.clock.moment = at(9, 30, day=17)
    session = system.login("anna", PASSWORD)
    print(f"  Вошла {session.client_id}. Её счета:")
    accounts = session.accounts()
    for info in accounts:
        print(f"    {info['account_id']} {info['account_type']} {info['balance']} "
              f"{info['currency']} {info['status']}")
    check("у Анны два счёта: 142000.00 RUB и 1600.00 USD",
          [(info["balance"], info["currency"]) for info in accounts]
          == [(Decimal("142000.00"), "RUB"), (Decimal("1600.00"), "USD")])
    history = session.history()
    print_history(history)
    check("в истории 12 операций, и входящие тоже", [
        (row["transaction_id"], row["direction"]) for row in history
    ] == [
        ("T0002", "out"), ("T0004", "own"), ("T0012", "out"), ("T0021", "out"),
        ("T0023", "out"), ("T0024", "out"), ("T0027", "out"), ("T0028", "in"),
        ("T0033", "in"), ("T0036", "out"), ("T0039", "out"), ("T0040", "out"),
    ])
    ends = [(row["sender"], row["recipient"]) for row in history[:1]]
    check("свой номер целиком, чужой — маской", ends == [(A1, "****4001")])
    check("причина отказа есть у отклонённых, и только у них", all(
        (row["failure_reason"] is not None) == (row["status"] == "failed")
        for row in history
    ))
    timing = [(row["created_at"], row["finished_at"]) for row in history
              if row["transaction_id"] == "T0027"]
    check("отложенная T0027 создана в 12:00, а завершена в 12:30",
          timing == [(at(12), at(12, 30))])
    dollars = [(row["transaction_id"], row["direction"]) for row in session.history(A2)]
    check("история долларового счёта: три списания",
          dollars == [("T0004", "out"), ("T0024", "out"), ("T0039", "out")])
    rows = session.suspicious_operations()
    for row in rows:
        mark = "заблокирована" if row["blocked"] else "не заблокирована"
        print(f"    подозрительная: {row['transaction_id']} {row['risk_level']} {mark}")
    check("подозрительных у Анны 4: две заблокированы, ночную отклонил банк", [
        (row["transaction_id"], row["risk_level"], row["blocked"]) for row in rows
    ] == [("T0021", "high", True), ("T0023", "medium", False),
          ("T0024", "high", True), ("T0036", "high", False)])
    expect_error("история чужого счёта", InvalidOperationError,
                 lambda: session.history(M1))
    expect_error("кабинет без верного пароля", AuthenticationError,
                 lambda: ClientSession(system, "oleg", WRONG))
    expect_error("вход заблокированного Тимура", ClientBlockedError,
                 lambda: system.login("timur", PASSWORD))
    world.clock.moment = at(3, day=18)
    expect_error("вход ночью", NightOperationError,
                 lambda: system.login("anna", PASSWORD))
    check("кабинет, открытый днём, читается и ночью", len(session.accounts()) == 2)
    check("в журнале банка теперь 10 записей", len(bank.get_suspicious_actions()) == 10)
    world.clock.moment = at(9, day=18)
    sofia = system.login("sofia", PASSWORD)
    for _ in range(3):  # кто-то трижды ошибся паролем Софии
        try:
            system.login("sofia", WRONG)
        except (AuthenticationError, ClientBlockedError):
            pass
    expect_error("кабинет Софии после её блокировки", ClientBlockedError,
                 lambda: sofia.accounts())
    last = [(mark["action"], mark["client_id"])
            for mark in bank.get_suspicious_actions()[-1:]]
    check("попытка чтения записана в журнал банка",
          last == [("view_accounts", "sofia")])


TOTALS = "RUB 697800.00, USD 1600.00, EUR 2500.00, KZT 575000.00, CNY 19800.00"
SUSPICIOUS = [  # подозрительные операции по порядку: ID, клиент, риск, блокировка
    ("T0006", "petr", "medium", False), ("T0015", "oleg", "medium", False),
    ("T0016", "petr", "high", True), ("T0020", "maria", "medium", False),
    ("T0021", "anna", "high", True), ("T0022", "petr", "medium", False),
    ("T0023", "anna", "medium", False), ("T0024", "anna", "high", True),
    ("T0029", "sofia", "medium", False), ("T0035", "maria", "medium", False),
    ("T0036", "anna", "high", False),
]
PROFILES = {  # операций; по уровням low, medium, high; заблокировано; уровень
    "anna": (10, [6, 1, 3], 2, "high"), "petr": (5, [2, 2, 1], 1, "high"),
    "liwei": (4, [4, 0, 0], 0, "low"), "maria": (7, [5, 2, 0], 0, "medium"),
    "oleg": (4, [3, 1, 0], 0, "medium"), "sofia": (5, [4, 1, 0], 0, "medium"),
    "timur": (4, [4, 0, 0], 0, "low"),
}


def show_reports(world):
    section("6. Отчёты")
    system, bank = world.system, world.bank
    top = system.top_clients(4)  # три места топа и четвёртое для сравнения
    plain = bank.get_clients_ranking()[:4]  # рейтинг банка: только рублёвые счета
    print("  Топ с пересчётом валют | рейтинг банка только по рублям")
    for row, other in zip(top, plain):
        print(f"    {row['place']}. {row['client_id']:6} {row['total_rub']:>10} | "
              f"{other['place']}. {other['client_id']:6} {other['total']:>10}")
    places = [(row["client_id"], row["total_rub"]) for row in top]
    check("топ-3: Пётр 430300.00, Ли 325400.00, Анна 286000.00", places[:3] == [
        ("petr", Decimal("430300.00")), ("liwei", Decimal("325400.00")),
        ("anna", Decimal("286000.00")),
    ])
    check("четвёртый — Олег с 279500.00",
          places[3:] == [("oleg", Decimal("279500.00"))])
    check("топ из трёх мест — те же первые три",
          system.top_clients() == top[:3])
    check("без пересчёта второй был бы Олег",
          [other["client_id"] for other in plain[:3]] == ["petr", "oleg", "anna"])
    stats = system.transaction_statistics()
    print(f"  Статистика транзакций: всего {stats['total']}")
    for key in ("by_status", "by_type", "by_risk"):
        print(f"    {key}: {stats[key]}")
    print(f"    выполнено на {stats['completed_rub']} RUB, "
          f"комиссий {stats['fees_rub']} RUB")
    check("статистика транзакций сошлась", stats == {
        "total": 40,
        "by_status": {"pending": 0, "completed": 26, "failed": 13, "cancelled": 1},
        "by_type": {"deposit": 6, "withdrawal": 17, "transfer": 14,
                    "external_transfer": 3},
        "by_risk": {"low": 28, "medium": 7, "high": 4, "not_assessed": 1},
        "completed_rub": Decimal("411900.00"), "fees_rub": Decimal("100.00"),
    })
    after = system.total_balance()
    print(f"  Общий баланс после: {money(after['by_currency'])}")
    print(f"  Всего в рублях: {world.before['total_rub']} → {after['total_rub']}")
    check("суммы по каждой валюте после симуляции сошлись",
          money(after["by_currency"]) == TOTALS)
    check("общий баланс после — 1454300.00 рублей",
          after["total_rub"] == Decimal("1454300.00"))
    change = after["total_rub"] - world.before["total_rub"]
    check("разница -95700.00: пополнения минус снятия, внешний перевод и плата",
          change == Decimal("126000") - Decimal("211400") - Decimal("10100") - 200)
    report = system.report
    rows = report.suspicious_operations()
    print(f"  Подозрительные операции (день 5): {len(rows)}")
    for row in rows:
        mark = "заблокирована" if row["blocked"] else "не заблокирована"
        print(f"    {row['transaction_id']} {row['client_id']:6} "
              f"{row['risk_level']:6} {mark}")
    check("подозрительных 11, порядок и блокировки сошлись", [
        (row["transaction_id"], row["client_id"], row["risk_level"], row["blocked"])
        for row in rows
    ] == SUSPICIOUS)
    print("  Риск-профили (день 5):")
    for client_id, wanted in PROFILES.items():
        profile = report.client_risk_profile(client_id)
        print(f"    {client_id:6} операций {profile['operations']}, "
              f"по уровням {profile['by_level']}, "
              f"заблокировано {profile['blocked']}, уровень {profile['level']}")
        summary = (profile["operations"], list(profile["by_level"].values()),
                   profile["blocked"], profile["level"])
        check(f"профиль {client_id} сошёлся", summary == wanted)
    errors = report.error_statistics()
    print(f"  Статистика ошибок (день 5): всего {errors['total']}, "
          f"временных {errors['temporary']}, окончательных {errors['final']}, "
          f"блокировок {errors['blocked']}")
    check("статистика ошибок сошлась", errors == {
        "total": 17, "temporary": 4, "final": 13, "blocked": 3,
        "by_error": {"AccountFrozenError": 3, "InvalidOperationError": 3,
                     "AccountClosedError": 1, "HighRiskError": 3,
                     "InsufficientFundsError": 3, "ClientBlockedError": 2,
                     "NightOperationError": 2},
    })
    expect_error("топ из нуля мест", InvalidOperationError,
                 lambda: system.top_clients(0))
    expect_error("топ из True мест", InvalidOperationError,
                 lambda: system.top_clients(True))


def main():
    parts = [
        show_init,
        show_simulation,
        show_log,
        show_results,
        show_cabinet,
        show_reports,
    ]
    with tempfile.TemporaryDirectory() as folder:  # папку с журналом уберёт with
        world = World(folder)
        for part in parts:
            part(world)
    print()
    if problems:
        print(f"ДЕМОНСТРАЦИЯ ПРОВАЛЕНА. Расхождений: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Демонстрация дня 6 завершена успешно: вся банковская система работает.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

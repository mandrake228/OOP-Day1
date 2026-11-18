"""Демонстрация дня 5: аудит и риск-анализ. Запуск: python demo_day5.py"""

import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bank import (
    AuditLevel,
    AuditLog,
    AuditReport,
    Bank,
    DuplicateTransactionIdError,
    HighRiskError,
    InvalidOperationError,
    NightOperationError,
    PremiumAccount,
    RiskAnalyzer,
    SavingsAccount,
    SecureProcessor,
    Transaction,
    TransactionProcessor,
    TransactionQueue,
)
from demo import check, expect_error, problems, section
from demo_day3 import PASSWORD, DemoClock, make_client
from demo_day4 import expect_refusal

A1, A2 = "40817810000000001001", "40817840000000001002"  # Анна: рубли и доллары
P1 = "40817810000000002001"  # премиальный счёт Петра
L1 = "40817810000000003001"  # сберегательный счёт Ли
M1, M2 = "40817810000000004001", "40817810000000004002"  # Мария: два рублёвых
ACCOUNTS = (A1, A2, P1, L1, M1, M2)
OUTSIDE = "40702810900000009999"  # счёт в другом банке
LOST = "00000000"  # такого счёта в банке нет


def at(hour, minute=0, second=0, day=16):
    """Момент по часам демонстрации: 16 ноября 2026 года или другой день ноября."""
    return datetime(2026, 11, day, hour, minute, second)


NOON = at(12)  # полдень: с него начинают часы демонстрации


def codes(values):
    """Коды элементов перечислений списком: их удобно печатать и сравнивать."""
    return [value.value for value in values]


def ids(records):
    """ID транзакций из записей журнала; у записи без транзакции — дефис."""
    return [record["transaction_id"] or "-" for record in records]


class Stand:
    """Стенд для раздела: банк, четыре клиента, шесть счетов и защищённый процессор."""

    def __init__(self, file_path=None):
        self.clock = DemoClock()  # часы из демонстрации дня 3: показывают полдень
        self.bank = Bank(clock=self.clock.now)
        people = [
            ("anna", "Смирнова Анна Сергеевна"),
            ("petr", "Иванов Пётр Алексеевич"),
            ("liwei", "Ли Вэй"),
            ("maria", "Орлова Мария Игоревна"),
        ]
        for client_id, full_name in people:
            client = make_client(client_id, full_name, email=f"{client_id}@example.com")
            self.bank.add_client(client, PASSWORD)
        open_account = self.bank.open_account
        open_account("anna", account_id=A1, balance=150000)
        open_account("anna", account_id=A2, balance=2000, currency="USD")
        open_account(
            "petr", PremiumAccount, account_id=P1, balance=300000,
            overdraft_limit=50000, fee=100,
        )
        open_account(
            "liwei", SavingsAccount, account_id=L1, balance=80000, min_balance=10000
        )
        open_account("maria", account_id=M1, balance=30000)
        open_account("maria", account_id=M2)
        self.bank.freeze_account(M2)  # этот счёт заморожен с самого начала
        self.audit = AuditLog(file_path=file_path)
        self.analyzer = RiskAnalyzer(self.bank)
        self.processor = SecureProcessor(self.bank, self.analyzer, self.audit)
        self.queue = TransactionQueue()

    def make(self, number, kind, amount, **fields):
        """Создаёт транзакцию с ID вида tx07 и временем по часам стенда."""
        return Transaction(
            kind, amount, transaction_id=f"tx{number:02d}",
            created_at=self.clock.now(), **fields,
        )

    def balances(self):
        """Балансы шести счетов строками: А1, А2, П1, Л1, М1, М2."""
        return [str(self.bank.get_account(name).balance) for name in ACCOUNTS]

    def run(self):
        """Запускает защищённый процессор и возвращает ID обработанных транзакций."""
        handled = self.processor.process_queue(self.queue)
        return [transaction.transaction_id for transaction in handled]


def show_log():
    section("1. Журнал аудита")
    log = AuditLog()
    added = log.add(
        NOON, "info", "completed", "Транзакция tx01 выполнена.",
        client_id="anna", transaction_id="tx01", data={"attempt": 1},
    )
    later = [
        (1, AuditLevel.WARNING, "risk", "Риск tx02: средний.", "anna", "tx02"),
        (2, "ERROR", "Refused", "  Счёт получателя не найден.  ", "petr", "tx03"),
        (3, "critical", "blocked", "Транзакция tx04 заблокирована.", "anna", "tx04"),
        (4, "info", "risk", "Запись без клиента и транзакции.", None, None),
    ]
    for minute, level, event, message, client_id, transaction_id in later:
        log.add(
            at(12, minute), level, event, message,
            client_id=client_id, transaction_id=transaction_id,
        )
    print("  Записи журнала:")
    for record in log.get_records():
        fields = [record["level"], record["event"], record["client_id"] or "-",
                  record["transaction_id"] or "-", record["message"]]
        print(f"    {record['time']:%H:%M} | {' | '.join(fields)}")
    records = log.get_records()
    check("в журнале пять записей", len(log) == 5)
    check("add вернул готовую запись с семью ключами", len(added) == 7)
    third = records[2]
    found = (third["level"], third["event"]) == ("error", "refused")
    check("уровень и событие найдены по коду в любом регистре", found)
    check("пробелы по краям сообщения обрезаны",
          third["message"] == "Счёт получателя не найден.")
    empty = (records[4]["client_id"], records[4]["transaction_id"], records[4]["data"])
    check("клиент, транзакция и данные необязательны", empty == (None, None, {}))

    picks = [
        ("уровень не ниже warning", {"min_level": "warning"}, ["tx02", "tx03", "tx04"]),
        ("событие risk", {"event": "risk"}, ["tx02", "-"]),
        ("клиент anna", {"client_id": "anna"}, ["tx01", "tx02", "tx04"]),
        ("транзакция tx03", {"transaction_id": "tx03"}, ["tx03"]),
        ("с 12:02 включительно", {"since": at(12, 2)}, ["tx03", "tx04", "-"]),
        ("по 12:01 включительно", {"until": at(12, 1)}, ["tx01", "tx02"]),
        ("anna и не ниже error", {"client_id": "anna", "min_level": "error"}, ["tx04"]),
        ("клиент, которого нет", {"client_id": "oleg"}, []),
    ]
    for description, conditions, expected in picks:
        got = ids(log.filter(**conditions))
        check(f"отбор «{description}»: {', '.join(got) or 'пусто'}", got == expected)

    got = log.get_records()
    got.clear()
    got = log.get_records()
    got[0]["message"] = "стёрто"
    got[0]["data"]["attempt"] = 99
    check("изменение полученных записей не меняет журнал",
          log.get_records()[0] == added)
    bad = [
        ("неизвестный уровень", lambda: log.add(NOON, "loud", "risk", "Текст.")),
        ("неизвестное событие", lambda: log.add(NOON, "info", "party", "Текст.")),
        ("пустое сообщение", lambda: log.add(NOON, "info", "risk", "   ")),
        ("сообщение в две строки", lambda: log.add(NOON, "info", "risk", "А.\nБ.")),
        ("время строкой", lambda: log.add("12:00", "info", "risk", "Текст.")),
        ("ID клиента числом", lambda: log.add(NOON, "info", "risk", "Т.", client_id=7)),
        ("данные списком", lambda: log.add(NOON, "info", "risk", "Т.", data=[1])),
        ("отбор по неизвестному уровню", lambda: log.filter(min_level="loud")),
        ("отбор по ID транзакции числом", lambda: log.filter(transaction_id=3)),
        ("отбор с началом периода строкой", lambda: log.filter(since="12:00")),
    ]
    for description, action in bad:
        expect_error(description, InvalidOperationError, action)
    check("отказы ничего не добавили в журнал", len(log) == 5)


def show_file():
    section("2. Журнал в файле")
    with tempfile.TemporaryDirectory() as folder:  # папку уберёт сам with
        path = Path(folder) / "audit.log"
        log = AuditLog(file_path=path)
        created = path.exists() and path.read_text(encoding="utf-8") == ""
        check("файл появился сразу при создании журнала и пуст", created)
        check("журнал знает путь своего файла", log.file_path == path)
        log.add(
            NOON, "info", "completed", "Транзакция tx01 выполнена.",
            client_id="anna", transaction_id="tx01",
        )
        log.add(
            at(12, 1), "warning", "risk", "Риск транзакции tx02: средний.",
            client_id="anna", transaction_id="tx02",
        )
        log.add(at(12, 2), "info", "risk", "Запись без клиента и транзакции.")
        lines = path.read_text(encoding="utf-8").splitlines()
        print("  Строки файла:")
        for line in lines:
            print(f"    {line}")
        check("строк в файле столько же, сколько записей: 3",
              len(lines) == len(log) == 3)
        fields = [line.split(" | ") for line in lines]
        check("в каждой строке шесть полей", all(len(row) == 6 for row in fields))
        check("вместо пустых клиента и транзакции — дефисы",
              fields[2][3:5] == ["-", "-"])
        check("русский текст читается", fields[0][5] == "Транзакция tx01 выполнена.")

        second = AuditLog(file_path=str(path))  # тот же файл, путь строкой
        second.add(
            at(12, 3), "error", "refused", "Счёт получателя не найден.",
            client_id="petr", transaction_id="tx03",
        )
        after = path.read_text(encoding="utf-8").splitlines()
        appended = len(after) == 4 and after[:3] == lines
        check("второй журнал дописал файл, а не затёр: строк 4", appended)
        check("память у каждого журнала своя: 3 и 1", (len(log), len(second)) == (3, 1))
        missing = Path(folder) / "no-such-folder" / "audit.log"
        expect_error(
            "путь в несуществующую папку", InvalidOperationError,
            lambda: AuditLog(file_path=missing),
        )
        expect_error("путь числом", InvalidOperationError,
                     lambda: AuditLog(file_path=5))
    check("журнал без файла: путь пуст", AuditLog().file_path is None)
    check("временная папка убрана вместе с файлом", not path.exists())


def fresh(bank, transaction):
    """Оценка анализатором без памяти: сигналы, баллы и уровень риска."""
    result = RiskAnalyzer(bank).assess(transaction)
    return codes(result["signals"]), result["score"], result["level"]


def analyzer_amounts(stand):
    print("  Крупная сумма: граница включительная, валюта — по курсу")
    bank, make = stand.bank, stand.make
    below = fresh(bank, make(1, "deposit", Decimal("49999.99"), recipient=A1))
    edge = fresh(bank, make(2, "deposit", 50000, recipient=A1))
    check("49999.99 RUB — сигнала нет, риск низкий", below == ([], 0, "low"))
    check("50000.00 RUB — сигнал, 3 балла, риск средний",
          edge == (["large_amount"], 3, "medium"))
    analyzer = RiskAnalyzer(bank)
    below = analyzer.assess(
        make(3, "deposit", Decimal("555.55"), currency="USD", recipient=A2)
    )
    above = analyzer.assess(
        make(4, "deposit", Decimal("555.56"), currency="USD", recipient=A2)
    )
    check("555.55 USD — это 49999.50 RUB, сигнала нет",
          (below["amount_rub"], below["signals"]) == (Decimal("49999.50"), ()))
    check("555.56 USD — это 50000.40 RUB, сигнал есть",
          (above["amount_rub"], codes(above["signals"]))
          == (Decimal("50000.40"), ["large_amount"]))


def analyzer_frequency(stand):
    print("  Частые операции: считаются по клиенту, окно — десять минут")
    bank, make, clock = stand.bank, stand.make, stand.clock
    near, far = RiskAnalyzer(bank), RiskAnalyzer(bank)  # одни события, разные часы
    for number, minute in ((1, 0), (2, 1), (3, 2)):
        clock.moment = at(12, minute)
        transaction = make(number, "deposit", 100, recipient=A1)
        near.assess(transaction)
        far.assess(transaction)
    fourth = make(4, "withdrawal", 10, currency="USD", sender=A2)  # другой счёт Анны
    clock.moment = at(12, 5)
    check("12:05 — четвёртая операция Анны за 10 минут: сигнал",
          codes(near.assess(fourth)["signals"]) == ["frequent_operations"])
    maria = make(5, "deposit", 100, recipient=M1)
    check("12:05 — первая операция Марии: чужая серия не мешает",
          near.assess(maria)["score"] == 0)
    clock.moment = at(12, 10)
    check("12:10 — та же операция: 12:00 выпала из окна, сигнала нет",
          far.assess(fourth)["signals"] == ())


def analyzer_recipients(stand):
    print("  Перевод на новый счёт: операции раз в 10 минут, чтобы частота не мешала")
    make, clock = stand.make, stand.clock
    analyzer = RiskAnalyzer(stand.bank)
    transfers = [
        ("первый перевод Анны Марии — новый счёт", "transfer", A1, M1, 1),
        ("второй перевод туда же — знакомый", "transfer", A1, M1, 0),
        ("тому же получателю со счёта в долларах — знакомый", "transfer", A2, M1, 0),
        ("между своими счетами — не новый", "transfer", A1, A2, 0),
        ("внешний перевод — новый счёт", "external_transfer", A1, OUTSIDE, 1),
        ("Мария переводит Анне — новый для Марии", "transfer", M1, A1, 1),
    ]
    for number, (description, kind, sender, recipient, score) in enumerate(transfers):
        clock.moment = at(13, 10 * number)
        transaction = make(number + 1, kind, 10, sender=sender, recipient=recipient)
        check(description, analyzer.assess(transaction)["score"] == score)


def analyzer_night(stand):
    print("  Операция ночью: границы ночи берутся у банка")
    moments = [
        (at(23, 59, 59), False), (at(0), True), (at(4, 59, 59), True), (at(5), False),
    ]
    for number, (moment, night) in enumerate(moments, 1):
        stand.clock.moment = moment
        transaction = stand.make(number, "deposit", 100, recipient=A1)
        signals, score, level = fresh(stand.bank, transaction)
        verdict = "ночь, 2 балла" if night else "не ночь"
        check(f"{moment:%H:%M:%S} — {verdict}", ("night_operation" in signals) is night)


def analyzer_memory(stand):
    print("  Сочетания и память анализатора")
    bank, make, clock = stand.bank, stand.make, stand.clock
    clock.moment = NOON
    analyzer = RiskAnalyzer(bank)
    big = make(1, "transfer", 70000, sender=P1, recipient=L1)
    first = analyzer.assess(big)
    check("крупная сумма на новый счёт: 4 балла, риск высокий",
          (first["score"], first["level"]) == (4, "high"))
    clock.moment = at(12, 10)
    small = make(2, "transfer", 100, sender=P1, recipient=L1)
    check("после высокого риска получатель всё ещё новый",
          codes(analyzer.assess(small)["signals"]) == ["new_recipient"])
    lost = analyzer.assess(make(3, "withdrawal", 60000, sender=LOST))
    check("счёт неизвестен: клиента нет, но крупная сумма видна",
          (lost["client_id"], codes(lost["signals"])) == (None, ["large_amount"]))
    clock.moment = at(2, 30, day=17)
    check("повторная оценка та же, хотя на часах ночь", analyzer.assess(big) == first)
    copy = analyzer.assess(big)
    copy["level"] = "low"
    check("оценка отдаётся копией", analyzer.assess(big)["level"] == "high")
    kept = (big.status, big.attempts, stand.balances()[2])
    check("оценка не меняет транзакцию и счёт", kept == ("pending", 0, "300000.00"))
    check("у анализатора две оценки Петра", len(analyzer.get_assessments("petr")) == 2)
    expect_error("анализатор без банка", InvalidOperationError,
                 lambda: RiskAnalyzer("bank"))
    expect_error("курсы не для всех валют", InvalidOperationError,
                 lambda: RiskAnalyzer(bank, rates={"USD": 90}))
    expect_error("оценка не транзакции", InvalidOperationError,
                 lambda: analyzer.assess("tx01"))


def show_analyzer():
    section("3. Анализатор риска")
    stand = Stand()
    points = [f"{code} {weight}" for code, weight in RiskAnalyzer.WEIGHTS.items()]
    print(f"  Баллы за сигналы: {', '.join(points)}")
    print(f"  Крупная сумма от {RiskAnalyzer.LARGE_AMOUNT} RUB; часто — уже "
          f"{RiskAnalyzer.FREQUENT_LIMIT} операции за {RiskAnalyzer.FREQUENT_WINDOW}")
    print(f"  Риск средний от {RiskAnalyzer.MEDIUM_SCORE} баллов, "
          f"высокий от {RiskAnalyzer.HIGH_SCORE}")
    for part in (analyzer_amounts, analyzer_frequency, analyzer_recipients,
                 analyzer_night, analyzer_memory):
        part(stand)


def blocking_by_risk(stand):
    processor, audit, make = stand.processor, stand.audit, stand.make
    before = stand.balances()
    print("  Высокий риск: блокировка")
    danger = make(1, "transfer", 70000, sender=P1, recipient=L1)
    expect_refusal("крупный перевод на новый счёт", HighRiskError, processor, danger)
    stopped = (danger.status, danger.attempts, str(danger.fee)) == ("failed", 1, "0.00")
    check("статус failed, одна попытка, комиссия 0.00", stopped)
    check("ни один счёт не изменился", stand.balances() == before)
    pairs = [(r["event"], r["level"]) for r in audit.filter(transaction_id="tx01")]
    check("в аудите две критические записи: оценка и блокировка",
          pairs == [("risk", "critical"), ("blocked", "critical")])
    data = [r["data"] for r in audit.filter(event="blocked")]
    check("в данных блокировки класс ошибки, номер попытки и пометка final",
          data == [{"error": "HighRiskError", "attempt": 1, "final": True}])

    print("  Средний и низкий риск: исполнение")
    medium = make(2, "withdrawal", 60000, sender=P1)
    low = make(3, "deposit", 500, recipient=A1)
    check("снятие 60000 (средний риск) выполнено",
          processor.process(medium) == "completed")
    check("пополнение 500 (низкий риск) выполнено",
          processor.process(low) == "completed")
    levels = [r["level"] for r in audit.filter(transaction_id="tx02")]
    check("о среднем риске — warning, об исполнении — info",
          levels == ["warning", "info"])

    print("  Правила дня 4 действуют")
    frozen = make(4, "transfer", 500, sender=M1, recipient=M2)
    stand.queue.add(frozen)
    for minute in (0, 1, 2):
        stand.clock.moment = at(12, minute)
        stand.run()
    check("перевод на замороженный счёт: три попытки, отклонён",
          (frozen.status, frozen.attempts) == ("failed", 3))
    events = [r["event"] for r in audit.filter(transaction_id="tx04")]
    check("оценка риска одна, записей об отказе три",
          events == ["risk", "refused", "refused", "refused"])
    check("повторы не считаются новыми операциями Марии",
          len(stand.analyzer.get_assessments("maria")) == 1)
    same = make(5, "transfer", 70000, sender=P1, recipient=L1)
    plain = TransactionProcessor(stand.bank)
    check("обычный процессор дня 4 ту же опасную операцию исполняет",
          plain.process(same) == "completed")


def blocking_at_night(stand):
    print("  Ночью: сначала оценка риска, потом ночной запрет банка")
    processor, audit, make = stand.processor, stand.audit, stand.make
    stand.clock.moment = at(2, 30, day=17)
    before = stand.balances()
    small = make(6, "withdrawal", 100, sender=A1)
    big = make(7, "withdrawal", 60000, sender=A1)
    expect_refusal("снятие 100 (средний риск)", NightOperationError, processor, small)
    expect_refusal("снятие 60000 (высокий риск)", NightOperationError, processor, big)
    once = small.attempts == big.attempts == 1
    check("деньги не двигались, у каждой одна попытка",
          once and stand.balances() == before)
    night = audit.filter(since=at(0, day=17))
    rows = [(r["transaction_id"], r["event"], r["level"]) for r in night]
    check("в аудите обе: оценка риска и окончательный отказ", rows == [
        ("tx06", "risk", "warning"), ("tx06", "refused", "error"),
        ("tx07", "risk", "critical"), ("tx07", "refused", "error"),
    ])
    marks = [(m["action"], m["client_id"]) for m in stand.bank.get_suspicious_actions()]
    check("обе попытки в журнале подозрительных действий банка",
          marks == [("withdrawal", "anna"), ("withdrawal", "anna")])


def blocking_reused_id(stand):
    print("  Чужой ID: оценку другой транзакции не выдают")
    processor, analyzer, make = stand.processor, stand.analyzer, stand.make
    before, risks = stand.balances(), len(stand.audit.filter(event="risk"))
    night = make(3, "withdrawal", 100, sender=A1)  # ID как у tx03; на часах 02:30
    expect_refusal("ночью с ID tx03 первым отказывает банк", NightOperationError,
                   processor, night)
    marks = [(m["action"], m["client_id"]) for m in stand.bank.get_suspicious_actions()]
    check("попытка записана в журнал подозрительных действий банка",
          marks[2:] == [("withdrawal", "anna")])

    stand.clock.moment = at(12, day=17)
    reused = make(3, "transfer", 70000, sender=P1, recipient=L1)  # снова ID tx03
    expect_refusal("днём крупный перевод на новый счёт с ID tx03",
                   DuplicateTransactionIdError, processor, reused)
    check("статус failed, одна попытка",
          (reused.status, reused.attempts) == ("failed", 1))
    expect_error("анализатор не отдаёт оценку tx03 другой транзакции",
                 DuplicateTransactionIdError, lambda: analyzer.assess(reused))
    kept = [a["amount_rub"] for a in analyzer.get_assessments()
            if a["transaction_id"] == "tx03"]
    check("у tx03 одна оценка: пополнения на 500", kept == [Decimal("500")])
    queued = make(2, "withdrawal", 90000, sender=P1)  # ID как у tx02
    stand.queue.add(queued)
    stand.run()
    check("через очередь так же: отказ с первой попытки, очередь пуста",
          (queued.status, queued.attempts, len(stand.queue)) == ("failed", 1, 0))
    check("ни один счёт не изменился", stand.balances() == before)
    check("записей об оценке риска не прибавилось",
          len(stand.audit.filter(event="risk")) == risks)
    errors = [r["data"]["error"] for r in stand.audit.filter(event="refused")]
    check("в аудите три новых отказа: ночь и два чужих ID", errors[-3:] == [
        "NightOperationError", "DuplicateTransactionIdError",
        "DuplicateTransactionIdError",
    ])


def show_blocking():
    section("4. Блокировка опасных операций")
    stand = Stand()
    blocking_by_risk(stand)
    blocking_at_night(stand)
    blocking_reused_id(stand)
    processor = stand.processor
    check("защищённый процессор — наследник процессора дня 4",
          isinstance(processor, TransactionProcessor))
    check("он отдаёт свои анализатор и журнал аудита",
          processor.analyzer is stand.analyzer and processor.audit is stand.audit)
    expect_error("защищённый процессор без анализатора", InvalidOperationError,
                 lambda: SecureProcessor(stand.bank, "analyzer", stand.audit))
    expect_error("защищённый процессор без журнала аудита", InvalidOperationError,
                 lambda: SecureProcessor(stand.bank, stand.analyzer, []))


TWELVE = [  # номер, тип, сумма, стороны и валюта, когда исполнять (None — сразу)
    (1, "deposit", 5000, {"recipient": M1}, None),
    (2, "transfer", 3000, {"sender": A1, "recipient": M1}, None),
    (3, "withdrawal", 2000, {"sender": L1}, None),
    (4, "transfer", 100, {"currency": "USD", "sender": A2, "recipient": A1}, None),
    (5, "external_transfer", 10000, {"sender": L1, "recipient": OUTSIDE}, None),
    (6, "transfer", 500, {"sender": M1, "recipient": M2}, None),
    (7, "transfer", 1000, {"sender": A1, "recipient": LOST}, None),
    (8, "transfer", 1000, {"sender": A1, "recipient": M1}, at(12, 3)),
    (9, "withdrawal", 60000, {"sender": A1}, at(12, 4)),
    (10, "withdrawal", 50000, {"sender": L1}, at(12, 6)),
    (11, "transfer", 70000, {"sender": P1, "recipient": L1}, at(12, 20)),
    (12, "transfer", 2000, {"sender": M1, "recipient": A1}, at(2, 30, day=17)),
]
RUNS = [NOON, at(12, 3), at(12, 4), at(12, 6), at(12, 20), at(2, 30, day=17)]


def play_twelve(stand):
    """Ставит двенадцать транзакций в очередь и запускает процессор шесть раз."""
    twelve = []
    for number, kind, amount, fields, run_at in TWELVE:
        transaction = stand.make(number, kind, amount, **fields)
        stand.queue.add(transaction, run_at=run_at)
        twelve.append(transaction)
    runs = []
    for moment in RUNS:
        stand.clock.moment = moment
        runs.append((moment, stand.run()))
    return twelve, runs


def show_twelve():
    section("5. Обычные и подозрительные транзакции")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "audit.log"
        stand = Stand(file_path=path)
        print(f"  Счета до: {', '.join(stand.balances())}")
        twelve, runs = play_twelve(stand)
        for moment, handled in runs:
            print(f"  Запуск {moment:%d.%m %H:%M}: {', '.join(handled)}")
        order = [handled for moment, handled in runs]
        check("шесть запусков, порядок обработки сошёлся", order == [
            ["tx01", "tx02", "tx03", "tx04", "tx05", "tx06", "tx07"],
            ["tx06", "tx08"], ["tx06", "tx09"], ["tx10"], ["tx11"], ["tx12"],
        ])
        print("  Транзакция | сигналы | баллы | риск | статус | попыток")
        table = []
        for transaction in twelve:
            result = stand.analyzer.assess(transaction)  # оценка уже есть: та же
            row = (codes(result["signals"]), result["score"], result["level"],
                   transaction.status, transaction.attempts)
            table.append(row)
            signals = ", ".join(row[0]) or "-"
            print(f"    {transaction.transaction_id} | {signals} | {row[1]} | "
                  f"{row[2]} | {row[3]} | {row[4]}")
        check("сигналы, баллы, риск и исход всех двенадцати сошлись", table == [
            ([], 0, "low", "completed", 1),
            (["new_recipient"], 1, "low", "completed", 1),
            ([], 0, "low", "completed", 1),
            ([], 0, "low", "completed", 1),
            (["new_recipient"], 1, "low", "completed", 1),
            ([], 0, "low", "failed", 3),
            (["new_recipient"], 1, "low", "failed", 1),
            (["frequent_operations"], 2, "medium", "completed", 1),
            (["large_amount", "frequent_operations"], 5, "high", "failed", 1),
            (["large_amount"], 3, "medium", "completed", 1),
            (["large_amount", "new_recipient"], 4, "high", "failed", 1),
            (["new_recipient", "night_operation"], 3, "medium", "failed", 1),
        ])
        print(f"  Причина отказа tx09: {twelve[8].failure_reason}")
        print(f"  Причина отказа tx12: {twelve[11].failure_reason}")
        print(f"  Счета после: {', '.join(stand.balances())}")
        check("балансы сошлись с расчётом", stand.balances() == [
            "155000.00", "1900.00", "300000.00", "17900.00", "39000.00", "0.00",
        ])
        statuses = [transaction.status for transaction in twelve]
        counts = (statuses.count("completed"), statuses.count("failed"))
        check("семь выполнены, пять отклонены; очередь пуста",
              counts == (7, 5) and len(stand.queue) == 0)
        marks = stand.bank.get_suspicious_actions()
        check("в журнале банка одна ночная попытка: Мария",
              [mark["client_id"] for mark in marks] == ["maria"])
        lines = path.read_text(encoding="utf-8").splitlines()
        print("  Файл журнала аудита:")
        for line in lines:
            print(f"    {line}")
        check("в файле 26 строк, по одной на запись",
              len(lines) == len(stand.audit) == 26)


def show_reports():
    section("6. Отчёты аудита")
    stand = Stand()
    play_twelve(stand)
    audit = stand.audit
    report = AuditReport(audit)

    print("  Подозрительные операции:")
    rows = report.suspicious_operations()
    for row in rows:
        mark = "заблокирована" if row["blocked"] else "не заблокирована"
        signals = ", ".join(codes(row["signals"]))
        print(f"    {row['time']:%d.%m %H:%M} | {row['transaction_id']} | "
              f"{row['client_id']} | {row['risk_level']} | {row['score']} | "
              f"{signals} | {mark}")
    got = [(row["transaction_id"], row["risk_level"], row["blocked"]) for row in rows]
    check("пять подозрительных, заблокированы две", got == [
        ("tx08", "medium", False), ("tx09", "high", True), ("tx10", "medium", False),
        ("tx11", "high", True), ("tx12", "medium", False),
    ])

    print("  Риск-профили:")
    expected = {  # операций, по уровням low/medium/high, заблокировано, уровень
        "anna": (5, [3, 1, 1], 1, "high"),
        "petr": (1, [0, 0, 1], 1, "high"),
        "liwei": (3, [2, 1, 0], 0, "medium"),
        "maria": (3, [2, 1, 0], 0, "medium"),
        "oleg": (0, [0, 0, 0], 0, "low"),
    }
    for client_id, wanted in expected.items():
        profile = report.client_risk_profile(client_id)
        fired = {code: count for code, count in profile["signals"].items() if count}
        print(f"    {client_id}: операций {profile['operations']}, "
              f"по уровням {profile['by_level']}, сигналы {fired}, "
              f"заблокировано {profile['blocked']}, уровень {profile['level']}")
        summary = (profile["operations"], list(profile["by_level"].values()),
                   profile["blocked"], profile["level"])
        check(f"профиль {client_id} сошёлся", summary == wanted)
    maria = report.client_risk_profile("maria")["signals"]
    check("у Марии сработали новый счёт и ночь",
          (maria["new_recipient"], maria["night_operation"]) == (1, 1))

    stats = report.error_statistics()
    print(f"  Статистика ошибок: всего {stats['total']}, "
          f"временных {stats['temporary']}, окончательных {stats['final']}, "
          f"блокировок {stats['blocked']}")
    print(f"    по классам: {stats['by_error']}")
    check("статистика ошибок сошлась", stats == {
        "total": 7, "temporary": 2, "final": 5, "blocked": 2,
        "by_error": {"AccountFrozenError": 3, "InvalidOperationError": 1,
                     "HighRiskError": 2, "NightOperationError": 1},
    })

    levels = [record["level"] for record in audit.get_records()]
    exact = [levels.count(level) for level in AuditLevel]
    at_least = [len(audit.filter(min_level=level)) for level in AuditLevel]
    print(f"  Записей по уровням info, warning, error, critical: {exact}")
    print(f"  Записей с уровнем не ниже каждого из них: {at_least}")
    check("по уровням 14, 5, 3, 4; не ниже — 26, 12, 7, 4",
          (exact, at_least) == ([14, 5, 3, 4], [26, 12, 7, 4]))
    anna = len(audit.filter(client_id="anna"))
    anna_warning = len(audit.filter(client_id="anna", min_level="warning"))
    check("записей об Анне 10, из них не ниже warning 4",
          (anna, anna_warning) == (10, 4))
    period = len(audit.filter(since=at(12, 4), until=at(12, 20)))
    check("записей с 12:04 по 12:20 включительно 7", period == 7)

    empty = AuditReport(AuditLog())
    blank = (empty.suspicious_operations(), empty.client_risk_profile("anna")["level"],
             empty.error_statistics()["total"])
    check("по пустому журналу отчёты пусты", blank == ([], "low", 0))
    expect_error("отчёт без журнала аудита", InvalidOperationError,
                 lambda: AuditReport([]))
    expect_error("риск-профиль по ID числом", InvalidOperationError,
                 lambda: report.client_risk_profile(7))


def main():
    parts = [
        show_log,
        show_file,
        show_analyzer,
        show_blocking,
        show_twelve,
        show_reports,
    ]
    for part in parts:
        part()
    print()
    if problems:
        print(f"ДЕМОНСТРАЦИЯ ПРОВАЛЕНА. Расхождений: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Демонстрация дня 5 завершена успешно: аудит и риск-анализ работают.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

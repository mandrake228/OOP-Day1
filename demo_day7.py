"""Демонстрация дня 7: отчёты и графики. Запуск: .venv\\Scripts\\python demo_day7.py"""

import codecs
import contextlib
import csv
import io
import json
import sys
import tempfile
import textwrap
from decimal import Decimal
from pathlib import Path

import demo_day6 as day6
from bank import Bank, BankSystem, InvalidOperationError, ReportBuilder
from demo import check, expect_error, problems, section

HERE = Path(__file__).resolve().parent  # папка проекта: запуск возможен из любой папки
A1, A2 = day6.A1, day6.A2  # рублёвый и долларовый счета Анны
PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])  # подпись любого PNG
CHARTS = [
    "client_anna_balance.png", "client_anna_accounts.png",
    "bank_currencies.png", "bank_clients.png",
    "risk_levels.png", "risk_errors.png",
]


def prepare(folder):
    """Мир и симуляция дня 6 без печати. Часы — на 17.11 10:00."""
    with contextlib.redirect_stdout(io.StringIO()):  # вывод дня 6 здесь не нужен
        world = day6.World(folder)
        day6.show_simulation(world)
    world.clock.moment = day6.at(10, day=17)
    return world


def print_report(builder, report):
    """Текст отчёта с отступом: так он не сливается с разделами демонстрации."""
    print(textwrap.indent(builder.render_text(report), "  "), end="")


def money_as_text(values):
    """Тот же словарь, но деньги строкой: так его сверяют с ожидаемым и с JSON."""
    return {key: str(value) if isinstance(value, Decimal) else value
            for key, value in values.items()}


def texts(table):
    """Строки таблицы отчёта списками строк, в порядке столбцов."""
    return [[str(row[column]) for column in table["columns"]] for row in table["rows"]]


def read_csv(path):
    """Все строки CSV-файла списками полей."""
    with open(path, encoding="utf-8-sig", newline="") as file:
        return list(csv.reader(file))


def png_size(path):
    """Ширина и высота PNG из его первых байтов. Не PNG — None."""
    data = Path(path).read_bytes()
    if data[:8] != PNG:
        return None
    width = int.from_bytes(data[16:20], "big")  # первый блок IHDR: ширина,
    height = int.from_bytes(data[20:24], "big")  # затем высота
    return width, height


def show_prepare(world, version):
    section("1. Подготовка")
    check("симуляция дня 6 прошла без расхождений", problems == [])
    print(f"  matplotlib {version}")
    wanted = (HERE / "requirements.txt").read_text(encoding="utf-8").strip()
    check("установлена та версия, что записана в requirements.txt",
          wanted == f"matplotlib=={version}")
    print(f"  Часы банка: {world.bank.now():%d.%m.%Y %H:%M}")
    expect_error("построитель без системы", InvalidOperationError,
                 lambda: ReportBuilder("system"))


def chain_ok(world, moves):
    """«Было» каждого движения равно прошлому «стало», последнее «стало» — балансу."""
    last = {}
    for move in moves:
        account_id = move["account_id"]
        if account_id in last and last[account_id] != move["before"]:
            return False
        last[account_id] = move["after"]
    balances = {name: world.bank.get_account(name).balance for name in last}
    return bool(last) and balances == last


ANNA = {  # итоги отчёта по Анне; деньги строкой, как в JSON
    "client_id": "anna", "full_name": "Смирнова Анна Сергеевна", "status": "active",
    "accounts": 2, "total_rub": "286000.00", "operations": 12, "pending": 0,
    "completed": 6, "failed": 5, "cancelled": 1, "suspicious": 4, "blocked": 2,
}
TIMUR = {  # заблокированный клиент: отчёт по нему строится как по любому
    "client_id": "timur", "full_name": "Алиев Тимур Рашидович", "status": "blocked",
    "accounts": 1, "total_rub": "20000.00", "operations": 5, "pending": 0,
    "completed": 3, "failed": 2, "cancelled": 0, "suspicious": 0, "blocked": 0,
}
HISTORY = [  # операции Анны из кабинета дня 6: ID и направление
    ("T0002", "out"), ("T0004", "own"), ("T0012", "out"), ("T0021", "out"),
    ("T0023", "out"), ("T0024", "out"), ("T0027", "out"), ("T0028", "in"),
    ("T0033", "in"), ("T0036", "out"), ("T0039", "out"), ("T0040", "out"),
]
MOVES = [  # движения Анны: транзакция, счёт, было, стало
    ("T0002", A1, "150000.00", "147000.00"),
    ("T0004", A2, "2000.00", "1900.00"),
    ("T0004", A1, "147000.00", "156000.00"),
    ("T0027", A1, "156000.00", "155000.00"),
    ("T0033", A1, "155000.00", "157000.00"),
    ("T0039", A2, "1900.00", "1600.00"),
    ("T0040", A1, "157000.00", "142000.00"),
]


def show_client(world, builder):
    section("2. Отчёт по клиенту")
    audit, bank = world.system.audit, world.bank
    before = (len(audit), len(bank.get_suspicious_actions()))
    report = builder.client_report("anna")
    print_report(builder, report)
    check("итоги Анны сошлись", money_as_text(report["summary"]) == ANNA)
    tables = report["tables"]
    check("счета: 142000.00 RUB и 1600.00 USD, то есть 144000.00 RUB",
          texts(tables["accounts"]) == [
              [A1, "BankAccount", "RUB", "active", "142000.00", "142000.00"],
              [A2, "BankAccount", "USD", "active", "1600.00", "144000.00"],
          ])
    history = [(row["transaction_id"], row["direction"])
               for row in tables["history"]["rows"]]
    check("операции — те же 12, что в кабинете дня 6", history == HISTORY)
    others = [row[key] for row in tables["history"]["rows"]
              for key in ("sender", "recipient") if row[key] not in (None, A1, A2)]
    check("чужие номера — только маской",
          others != [] and all(value.startswith("****") for value in others))
    moves = [(row["transaction_id"], row["account_id"], str(row["before"]),
              str(row["after"])) for row in tables["moves"]["rows"]]
    check("семь движений Анны сошлись", moves == MOVES)
    check("«было» каждого движения — прошлое «стало», последнее — баланс",
          chain_ok(world, tables["moves"]["rows"]))
    lines = report["charts"]["balance"]["series"]
    check("на графике движения две линии, в рублях",
          [line["label"] for line in lines] == ["****1001 RUB", "****1002 USD"])
    timur = builder.client_report("timur")["summary"]
    check("Тимур заблокирован, а отчёт по нему обычный", money_as_text(timur) == TIMUR)
    expect_error("отчёт по неизвестному клиенту", InvalidOperationError,
                 lambda: builder.client_report("nobody"))
    world.clock.moment = day6.at(3, day=18)
    night = builder.client_report("anna")
    world.clock.moment = day6.at(10, day=17)
    check("ночью отчёт строится, и итоги те же", night["summary"] == report["summary"])
    check("отчёты не тронули ни журнал аудита, ни журнал банка",
          (len(audit), len(bank.get_suspicious_actions())) == before)
    spoiled = audit.filter(event="completed")[:1]
    for record in spoiled:
        record["data"]["moves"].clear()  # портим полученную копию записи
    check("журнал системы не изменить: копии на всю глубину, дописать нельзя",
          audit.filter(event="completed")[:1] != spoiled and not hasattr(audit, "add"))
    expect_error("история клиента None вместо ID", InvalidOperationError,
                 lambda: world.system.client_history(None))
    return report


BANK = {  # итоги отчёта по банку
    "clients": 7, "accounts": 13, "total_rub": "1454300.00", "transactions": 40,
    "pending": 0, "completed": 26, "failed": 13, "cancelled": 1,
    "completed_rub": "411900.00", "fees_rub": "100.00",
}
BANK_ACCOUNTS = [line.split() for line in [  # все счета банка, номера под маской
    "anna ****1001 BankAccount RUB active 142000.00 142000.00",
    "anna ****1002 BankAccount USD active 1600.00 144000.00",
    "petr ****2001 PremiumAccount RUB active 180300.00 180300.00",
    "petr ****2002 BankAccount EUR active 2500.00 250000.00",
    "liwei ****3001 SavingsAccount RUB active 77900.00 77900.00",
    "liwei ****3002 BankAccount CNY active 19800.00 247500.00",
    "maria ****4001 BankAccount RUB active 57600.00 57600.00",
    "maria ****4002 BankAccount RUB frozen 0.00 0.00",
    "oleg ****5001 InvestmentAccount RUB active 164500.00 164500.00",
    "oleg ****5002 BankAccount KZT active 575000.00 115000.00",
    "sofia ****6001 BankAccount RUB active 55500.00 55500.00",
    "sofia ****6002 BankAccount RUB closed 0.00 0.00",
    "timur ****7001 BankAccount RUB active 20000.00 20000.00",
]]
RISK = {  # итоги отчёта по рискам
    "low": 28, "medium": 7, "high": 4, "not_assessed": 1, "suspicious": 11,
    "blocked": 3, "refusals": 17, "temporary": 4, "final": 13, "bank_marks": 7,
}
RISK_ROWS = [line.split("|") for line in [  # подозрительные операции, как в CSV
    "2026-11-16T09:00:00|T0006|petr|medium|3|large_amount|false",
    "2026-11-16T10:00:00|T0015|oleg|medium|3|large_amount|false",
    "2026-11-16T10:00:00|T0016|petr|high|4|large_amount, new_recipient|true",
    "2026-11-16T10:00:00|T0020|maria|medium|2|frequent_operations|false",
    "2026-11-16T10:00:00|T0021|anna|high|4|large_amount, new_recipient|true",
    "2026-11-16T10:00:00|T0022|petr|medium|3|large_amount|false",
    "2026-11-16T10:00:00|T0023|anna|medium|3|large_amount|false",
    "2026-11-16T10:00:00|T0024|anna|high|4|large_amount, new_recipient|true",
    "2026-11-16T12:00:00|T0029|sofia|medium|3|large_amount|false",
    "2026-11-17T02:30:00|T0035|maria|medium|2|night_operation|false",
    "2026-11-17T02:30:00|T0036|anna|high|5|large_amount, night_operation|false",
]]
ERRORS = {  # отказы по классам ошибок, всего 17
    "AccountFrozenError": 3, "InvalidOperationError": 3, "AccountClosedError": 1,
    "HighRiskError": 3, "InsufficientFundsError": 3, "ClientBlockedError": 2,
    "NightOperationError": 2,
}


def show_bank(builder):
    section("3. Отчёт по банку")
    report = builder.bank_report()
    print_report(builder, report)
    check("итоги банка сошлись", money_as_text(report["summary"]) == BANK)
    tables = report["tables"]
    check("13 счетов сошлись целиком, все номера под маской",
          texts(tables["accounts"]) == BANK_ACCOUNTS)
    check("суммы по пяти валютам сошлись", texts(tables["totals"]) == [
        ["RUB", "697800.00", "697800.00"], ["USD", "1600.00", "144000.00"],
        ["EUR", "2500.00", "250000.00"], ["KZT", "575000.00", "115000.00"],
        ["CNY", "19800.00", "247500.00"],
    ])
    clients = [(row["place"], row["client_id"], str(row["total_rub"]))
               for row in tables["clients"]["rows"]]
    check("все семь клиентов по убыванию суммы в рублях", clients == [
        (1, "petr", "430300.00"), (2, "liwei", "325400.00"), (3, "anna", "286000.00"),
        (4, "oleg", "279500.00"), (5, "maria", "57600.00"), (6, "sofia", "55500.00"),
        (7, "timur", "20000.00"),
    ])
    anna = [total for _, name, total in clients if name == "anna"]
    check("сумма Анны в таблице клиентов — та же, что в отчёте по ней",
          anna == [ANNA["total_rub"]])
    return report


def show_risk(builder):
    section("4. Отчёт по рискам")
    report = builder.risk_report()
    print_report(builder, report)
    check("итоги по рискам сошлись", report["summary"] == RISK)
    tables = report["tables"]
    suspicious = [(row["transaction_id"], row["client_id"], str(row["risk_level"]),
                   row["blocked"]) for row in tables["suspicious"]["rows"]]
    check("11 подозрительных — те же, что в дне 6, заблокированы три",
          suspicious == day6.SUSPICIOUS)
    scores = [[str(row["score"]), ", ".join(row["signals"])]
              for row in tables["suspicious"]["rows"]]
    check("баллы и сигналы каждой подозрительной операции сошлись",
          scores == [row[4:6] for row in RISK_ROWS])
    errors = {row["error"]: row["count"] for row in tables["errors"]["rows"]}
    check("отказы по семи классам ошибок, всего 17", errors == ERRORS)
    profiles = {row["client_id"]: (
        row["operations"], [row["low"], row["medium"], row["high"]], row["blocked"],
        str(row["level"])) for row in tables["profiles"]["rows"]}
    check("риск-профили семи клиентов — те же, что в дне 6",
          profiles == day6.PROFILES)
    check("профили идут в порядке рейтинга банка", list(profiles) == [
        "petr", "oleg", "anna", "liwei", "maria", "sofia", "timur"])
    check("подписи круга уровней риска — по-русски",
          report["charts"]["levels"]["labels"]
          == ["Низкий риск", "Средний риск", "Высокий риск", "Без оценки"])
    return report


EXPORTS = {  # отчёт: итоги, число строк в таблицах, первая строка главной таблицы
    "client_anna": (ANNA, {"history": 12, "accounts": 2, "moves": 7}, {
        "transaction_id": "T0002", "created_at": "2026-11-16T09:00:00",
        "direction": "out", "transaction_type": "transfer", "amount": "3000.00",
        "currency": "RUB", "sender": A1, "recipient": "****4001",
        "status": "completed", "fee": "0.00", "risk_level": "low",
        "failure_reason": None,
    }),
    "bank": (BANK, {"accounts": 13, "totals": 5, "clients": 7}, {
        "client_id": "anna", "account_id": "****1001", "account_type": "BankAccount",
        "currency": "RUB", "status": "active", "balance": "142000.00",
        "balance_rub": "142000.00",
    }),
    "risk": (RISK, {"suspicious": 11, "errors": 7, "profiles": 7}, {
        "time": "2026-11-16T09:00:00", "transaction_id": "T0006", "client_id": "petr",
        "risk_level": "medium", "score": 3, "signals": ["large_amount"],
        "blocked": False,
    }),
}
MAIN = {"client_anna": "history", "bank": "accounts", "risk": "suspicious"}
HEADERS = {  # заголовки главных таблиц в CSV
    "client_anna": ("transaction_id,created_at,direction,transaction_type,amount,"
                    "currency,sender,recipient,status,fee,risk_level,failure_reason"),
    "bank": "client_id,account_id,account_type,currency,status,balance,balance_rub",
    "risk": "time,transaction_id,client_id,risk_level,score,signals,blocked",
}
T0012 = ["T0012", "2026-11-16T09:00:00", "out", "transfer", "1000.00", "RUB", A1,
         "****0000", "failed", "0.00", "low",
         "Счёт получателя ****0000 в банке не найден."]  # строка CSV с кириллицей
T0028 = ["T0028", "2026-11-16T12:00:00", "in", "transfer", "300.00", "RUB", "****4001",
         A1, "cancelled", "0.00", "", ""]  # отменена до оценки: два пустых поля


def show_export(world, builder, reports, folder):
    section("5. Экспорт в JSON и CSV")
    tables = {}
    for number, report in enumerate(reports):
        name = report["name"]
        json_path = builder.export_to_json(report, folder / f"{name}.json")
        csv_path = builder.export_to_csv(report, folder / f"{name}.csv")
        back = json.loads(json_path.read_text(encoding="utf-8"))
        tables[name] = read_csv(csv_path)
        print(f"  {json_path.name}: {json_path.stat().st_size} байт; "
              f"{csv_path.name}: строк {len(tables[name])}")
        summary, sizes, first = EXPORTS.get(name, ({}, {}, {}))
        check(f"{name}: JSON прочитан, итоги и время те же",
              back.get("summary") == summary
              and back.get("generated_at") == "2026-11-17T10:00:00")
        rows = back.get("tables", {})
        check(f"{name}: в JSON все таблицы и первая строка главной",
              {key: len(table["rows"]) for key, table in rows.items()} == sizes
              and rows.get(MAIN.get(name), {}).get("rows", [])[:1] == [first])
        check(f"{name}: в JSON описания обоих графиков",
              [f"{name}_{key}.png" for key in back.get("charts", {})]
              == CHARTS[2 * number:2 * number + 2])
    headers = {name: [line.split(",")] for name, line in HEADERS.items()}
    check("client_anna.csv: заголовок, 12 строк, кириллица и пустые поля на месте",
          tables["client_anna"][:1] == headers["client_anna"]
          and len(tables["client_anna"]) == 13
          and T0012 in tables["client_anna"] and T0028 in tables["client_anna"])
    check("bank.csv совпал целиком: заголовок и 13 счетов",
          tables["bank"] == headers["bank"] + BANK_ACCOUNTS)
    check("risk.csv совпал целиком: заголовок и 11 операций, сигналы одним полем",
          tables["risk"] == headers["risk"] + RISK_ROWS)
    raw = (folder / "client_anna.csv").read_bytes()
    check("CSV начинается с BOM, строки кончаются CRLF",
          raw.startswith(codecs.BOM_UTF8) and raw.count(b"\r\n") == 13)
    text = (folder / "client_anna.json").read_text(encoding="utf-8")
    check("в JSON кириллица как есть, деньги строкой",
          "Смирнова Анна Сергеевна" in text and '"total_rub": "286000.00"' in text)
    moves = builder.export_to_csv(reports[0], folder / "client_anna_moves.csv",
                                  table="moves")
    check("CSV таблицы moves по имени: заголовок и первое движение",
          read_csv(moves)[:2] == [
              ["time", "transaction_id", "account_id", "before", "after"],
              ["2026-11-16T09:00:00", "T0002", A1, "150000.00", "147000.00"],
          ])
    expect_error("JSON в папку, которой нет", InvalidOperationError,
                 lambda: builder.export_to_json(reports[0], folder / "нет" / "a.json"))
    expect_error("CSV неизвестной таблицы", InvalidOperationError,
                 lambda: builder.export_to_csv(reports[0], folder / "a.csv", table="x"))
    expect_error("путь числом", InvalidOperationError,
                 lambda: builder.export_to_json(reports[1], 5))
    expect_error("не отчёт: словарь с одним полем kind", InvalidOperationError,
                 lambda: builder.export_to_json({"kind": "bank"}, folder / "a.json"))
    log = world.system.audit.file_path
    lines = len(log.read_text(encoding="utf-8").splitlines())
    expect_error("JSON поверх файла журнала аудита", InvalidOperationError,
                 lambda: builder.export_to_json(reports[2], log))
    check("файл журнала цел, лишних файлов от отказов нет",
          len(log.read_text(encoding="utf-8").splitlines()) == lines
          and not (folder / "a.json").exists() and not (folder / "a.csv").exists())


EMPTY_BANK = {  # итоги отчёта по банку без клиентов и транзакций
    "clients": 0, "accounts": 0, "total_rub": "0.00", "transactions": 0,
    "pending": 0, "completed": 0, "failed": 0, "cancelled": 0,
    "completed_rub": "0.00", "fees_rub": "0.00",
}


def nothing_to_draw(chart):
    """Нечего рисовать: нет линий, нет столбцов или нет ни одной доли больше нуля."""
    if chart["type"] == "line":
        return chart["series"] == []
    if chart["type"] == "bar":
        return chart["labels"] == []
    return all(value <= 0 for value in chart["values"])


def show_charts(builder, reports, folder):
    section("6. Графики")
    saved = []
    for report in reports:
        saved += builder.save_charts(report, folder)
    for path in saved:
        print(f"  {path.name}: {path.stat().st_size} байт, размер {png_size(path)}")
    check("шесть файлов с нужными именами", [path.name for path in saved] == CHARTS)
    check("все шесть — PNG 800 на 500 точек",
          [png_size(path) for path in saved] == [(800, 500)] * 6)
    first = [path.read_bytes() for path in saved]
    again = [path.read_bytes() for report in reports
             for path in builder.save_charts(report, folder)]
    check("повторное сохранение даёт те же байты", first == again)
    empty = ReportBuilder(BankSystem(Bank()))  # банк без клиентов и транзакций
    blank = [empty.bank_report(), empty.risk_report()]
    check("пустой банк: итоги по нулям, счетов и клиентов в таблицах нет",
          money_as_text(blank[0]["summary"]) == EMPTY_BANK
          and set(blank[1]["summary"].values()) == {0}
          and texts(blank[0]["tables"]["accounts"]) == []
          and texts(blank[0]["tables"]["clients"]) == [])
    drawings = [chart for report in blank for chart in report["charts"].values()]
    check("пустой банк: рисовать нечего на всех четырёх графиках",
          len(drawings) == 4 and all(nothing_to_draw(chart) for chart in drawings))
    place = folder / "empty"
    place.mkdir(exist_ok=True)
    pictures = [path for report in blank for path in empty.save_charts(report, place)]
    check("пустой банк: четыре графика «Нет данных» сохранены",
          [png_size(path) for path in pictures] == [(800, 500)] * 4)
    header = read_csv(empty.export_to_csv(blank[0], place / "clients.csv", "clients"))
    check("пустая таблица в CSV — одна строка заголовков",
          header == [["place", "client_id", "full_name", "total_rub"]])
    expect_error("графики в папку, которой нет", InvalidOperationError,
                 lambda: builder.save_charts(reports[1], folder / "нет"))
    forged = dict(reports[1], name="..\\outside")
    expect_error("имя отчёта, которое уводит файл из папки", InvalidOperationError,
                 lambda: builder.save_charts(forged, place))
    check("отказ не оставил файлов вне папки", list(folder.glob("outside*")) == [])


def run(world, version, folder):
    """Шесть разделов по порядку: подготовка, три отчёта, экспорт, графики."""
    builder = ReportBuilder(world.system)
    show_prepare(world, version)
    reports = [show_client(world, builder), show_bank(builder), show_risk(builder)]
    show_export(world, builder, reports, folder)
    show_charts(builder, reports, folder)


def main():
    args = sys.argv[1:]
    if len(args) > 1 or (args and args[0].startswith("-")):
        print(r"Запуск: .venv\Scripts\python demo_day7.py [папка для отчётов]")
        return 1
    try:
        import matplotlib  # без него графиков не будет: проверяем заранее
    except ModuleNotFoundError:
        print("Для дня 7 нужен matplotlib. Поставьте его в окружение проекта:")
        print("  python -m venv .venv")
        print(r"  .venv\Scripts\python -m pip install -r requirements.txt")
        print(r"и запускайте так: .venv\Scripts\python demo_day7.py")
        return 1
    keep = Path(args[0]) if args else None  # папка, где оставить файлы
    if keep is not None and keep.exists() and not keep.is_dir():
        print(f"«{keep}» — файл, а нужна папка для отчётов.")
        return 1
    with tempfile.TemporaryDirectory() as work:  # всё временное уберёт with
        world = prepare(work)
        folder = Path(work) if keep is None else keep
        folder.mkdir(parents=True, exist_ok=True)
        run(world, matplotlib.__version__, folder)
    print()
    if problems:
        print(f"ДЕМОНСТРАЦИЯ ПРОВАЛЕНА. Расхождений: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    if keep is not None:
        print(f"Отчёты и графики сохранены в папке {keep}.")
    print("Демонстрация дня 7 завершена успешно: отчёты и графики работают.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

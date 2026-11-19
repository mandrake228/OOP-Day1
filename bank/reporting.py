"""Построитель отчётов: по клиенту, по банку, по рискам. Текст, JSON, CSV, графики."""

import csv
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .enums import AccountStatus, AuditEvent, RiskLevel, TransactionStatus
from .errors import InvalidOperationError
from .system import BankSystem
from .transactions import mask

KINDS = ("client", "bank", "risk")  # три типа отчётов
MAIN_TABLES = {"client": "history", "bank": "accounts", "risk": "suspicious"}
REPORT_KEYS = ("kind", "name", "title", "generated_at", "summary", "tables", "charts")
LABELS = {  # русские подписи итогов и столбцов для текстового отчёта
    "client_id": "Клиент", "full_name": "ФИО", "status": "Статус",
    "accounts": "Счетов", "total_rub": "Всего, RUB", "operations": "Операций",
    "completed": "Выполнено", "failed": "Отклонено", "cancelled": "Отменено",
    "pending": "Ожидает", "suspicious": "Подозрительных", "blocked": "Заблокировано",
    "clients": "Клиентов", "transactions": "Транзакций", "completed_rub": "Оборот, RUB",
    "fees_rub": "Комиссии, RUB", "low": "Низкий риск", "medium": "Средний риск",
    "high": "Высокий риск", "not_assessed": "Без оценки", "refusals": "Отказов",
    "temporary": "Временных", "final": "Окончательных", "bank_marks": "Записей банка",
    "account_id": "Счёт", "account_type": "Тип счёта", "currency": "Валюта",
    "balance": "Баланс", "balance_rub": "Баланс, RUB", "transaction_id": "ID",
    "created_at": "Создана", "direction": "Направление", "transaction_type": "Тип",
    "amount": "Сумма", "sender": "Откуда", "recipient": "Куда", "fee": "Комиссия",
    "risk_level": "Риск", "failure_reason": "Причина отказа", "time": "Время",
    "before": "Было", "after": "Стало", "place": "Место", "score": "Баллы",
    "signals": "Сигналы", "error": "Ошибка", "count": "Сколько", "level": "Уровень",
}


def plain(value):
    """Значение для JSON: деньги и время строкой, коды вместо перечислений."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)  # строкой: точность до копейки не теряется
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value  # строки, целые числа, True, False и None JSON понимает сам


def cell(value):
    """Значение для ячейки CSV: всё строкой, пустое — пустая строка."""
    value = plain(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def text_cell(value):
    """Значение для текстового отчёта: привычные даты, «да» и «нет», дефис."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, datetime):
        return f"{value:%d.%m.%Y %H:%M}"
    return cell(value)


def make_table(columns, rows):
    """Таблица отчёта: столбцы по порядку и строки только с этими столбцами."""
    return {
        "columns": list(columns),
        "rows": [{column: row[column] for column in columns} for row in rows],
    }


def file_safe(name):
    """Годится ли имя для имени файла: только буквы, цифры и подчёркивание."""
    return isinstance(name, str) and name.replace("_", "").isalnum()


def is_number(value):
    """Целое число или конечный Decimal: то, что можно нарисовать."""
    if isinstance(value, Decimal):
        return value.is_finite()
    return isinstance(value, int) and not isinstance(value, bool)


def valid_table(table):
    """Таблица отчёта: столбцы-строки и строки-словари ровно с этими ключами."""
    if not isinstance(table, dict) or list(table) != ["columns", "rows"]:
        return False
    columns, rows = table["columns"], table["rows"]
    if not isinstance(columns, list) or not isinstance(rows, list):
        return False
    if not all(isinstance(column, str) for column in columns):
        return False
    return all(isinstance(row, dict) and list(row) == columns for row in rows)


def valid_line(line):
    """Линия графика: подпись и точки «время, число»."""
    if not isinstance(line, dict) or not isinstance(line.get("label"), str):
        return False
    points = line.get("points")
    return isinstance(points, list) and all(
        isinstance(point, tuple) and len(point) == 2
        and isinstance(point[0], datetime) and is_number(point[1])
        for point in points
    )


def valid_chart(chart):
    """Описание графика: тип, заголовок и данные той формы, что ждёт рисовальщик."""
    if not isinstance(chart, dict) or not isinstance(chart.get("title"), str):
        return False
    if chart.get("type") == "line":
        series = chart.get("series")
        return isinstance(series, list) and all(valid_line(line) for line in series)
    if chart.get("type") not in ("pie", "bar"):
        return False
    labels, values = chart.get("labels"), chart.get("values")
    if not isinstance(labels, list) or not isinstance(values, list):
        return False
    return (
        len(labels) == len(values)
        and all(isinstance(label, str) for label in labels)
        and all(is_number(value) for value in values)
    )


class ReportBuilder:
    """Строит отчёты по банковской системе и сохраняет их в файлы."""

    # столбцы всех таблиц: по ним строятся таблицы и заголовки CSV
    HISTORY_COLUMNS = ("transaction_id", "created_at", "direction", "transaction_type",
                       "amount", "currency", "sender", "recipient", "status", "fee",
                       "risk_level", "failure_reason")
    ACCOUNT_COLUMNS = ("account_id", "account_type", "currency", "status", "balance",
                       "balance_rub")
    MOVE_COLUMNS = ("time", "transaction_id", "account_id", "before", "after")
    BANK_ACCOUNT_COLUMNS = ("client_id", *ACCOUNT_COLUMNS)
    TOTAL_COLUMNS = ("currency", "balance", "balance_rub")
    CLIENT_COLUMNS = ("place", "client_id", "full_name", "total_rub")
    SUSPICIOUS_COLUMNS = ("time", "transaction_id", "client_id", "risk_level", "score",
                          "signals", "blocked")
    ERROR_COLUMNS = ("error", "count")
    PROFILE_COLUMNS = ("client_id", "operations", *(level.value for level in RiskLevel),
                       "blocked", "level")  # уровни — из перечисления: новый не выпадет

    def __init__(self, system):
        if not isinstance(system, BankSystem):
            raise InvalidOperationError("Отчёты: нужен объект BankSystem.")
        self._system = system

    def _report(self, kind, name, title, summary, tables, charts):
        """Отчёт в общей форме: одна структура для всех трёх типов."""
        return {
            "kind": kind,
            "name": name,  # из него строятся имена файлов графиков
            "title": title,
            "generated_at": self._system.bank.now(),
            "summary": summary,
            "tables": tables,
            "charts": charts,
        }

    def _account_row(self, account, shown_id):
        """Строка счёта для таблиц. Номер показан так, как решил отчёт."""
        system = self._system
        return {
            "client_id": system.bank.get_owner_id(account.account_id),
            "account_id": shown_id,
            "account_type": type(account).__name__,
            "currency": account.currency,
            "status": account.status,
            "balance": account.balance,
            "balance_rub": system.to_rub(account.balance, account.currency),
        }

    def _moves(self, account_ids):
        """Движения по этим счетам из журнала аудита: когда, чем, было, стало."""
        moves = []
        for record in self._system.audit.filter(event=AuditEvent.COMPLETED):
            for move in record["data"].get("moves", []):
                if move["account_id"] in account_ids:
                    moves.append({
                        "time": record["time"],
                        "transaction_id": record["transaction_id"],
                        "account_id": move["account_id"],
                        "before": move["before"],
                        "after": move["after"],
                    })
        return moves

    def _balance_line(self, account, moves):
        """Линия графика: баланс счёта в рублях до движений, после каждого и сейчас."""
        own = [move for move in moves if move["account_id"] == account.account_id]
        if not own:
            return None  # движений не было: линии нет
        points = [(own[0]["time"], own[0]["before"])]
        points += [(move["time"], move["after"]) for move in own]
        points.append((self._system.bank.now(), account.balance))
        to_rub = self._system.to_rub
        return {
            "label": f"{mask(account.account_id)} {account.currency}",
            "points": [(time, to_rub(value, account.currency))
                       for time, value in points],
        }

    def client_report(self, client_id):
        """Отчёт по клиенту: итоги, операции, счета, движения и два графика."""
        bank, system = self._system.bank, self._system
        info = bank.get_client_info(client_id)  # неизвестный клиент — ошибка
        accounts = bank.search_accounts(client_id=client_id)
        rows = [self._account_row(account, account.account_id)  # свои — целиком
                for account in accounts]
        alive = [row for row in rows if row["status"] is not AccountStatus.CLOSED]
        history = system.client_history(client_id)  # чужие номера уже под маской
        by_status = {status.value: 0 for status in TransactionStatus}
        for item in history:
            by_status[item["status"]] += 1
            risk = item["risk"]
            item["risk_level"] = None if risk is None else risk["level"]
        moves = self._moves({account.account_id for account in accounts})
        suspicious = system.client_suspicious_operations(client_id)
        summary = {
            "client_id": info["client_id"],
            "full_name": info["full_name"],
            "status": info["status"],
            "accounts": len(accounts),
            "total_rub": system.client_total_rub(client_id),  # та же сумма, что в топе
            "operations": len(history),
            **by_status,  # pending, completed, failed, cancelled
            "suspicious": len(suspicious),
            "blocked": sum(1 for row in suspicious if row["blocked"]),
        }
        lines = [self._balance_line(account, moves) for account in accounts]
        charts = {
            "balance": {"type": "line", "title": f"Движение баланса {client_id}, RUB",
                        "series": [line for line in lines if line is not None]},
            "accounts": {"type": "bar", "title": f"Счета клиента {client_id}, RUB",
                         "labels": [f"{mask(row['account_id'])} {row['currency']}"
                                    for row in alive],
                         "values": [row["balance_rub"] for row in alive]},
        }
        tables = {
            "history": make_table(self.HISTORY_COLUMNS, history),
            "accounts": make_table(self.ACCOUNT_COLUMNS, rows),
            "moves": make_table(self.MOVE_COLUMNS, moves),
        }
        title = f"Отчёт по клиенту {client_id}"
        return self._report("client", f"client_{client_id}", title, summary, tables,
                            charts)

    def bank_report(self):
        """Отчёт по банку: итоги, все счета под маской, валюты, клиенты, два графика."""
        bank, system = self._system.bank, self._system
        accounts = bank.search_accounts()  # все счета в порядке открытия
        rows = [self._account_row(account, mask(account.account_id))  # только маски
                for account in accounts]
        total = system.total_balance()
        totals = [{
            "currency": code,
            "balance": amount,
            "balance_rub": system.to_rub(amount, code),
        } for code, amount in total["by_currency"].items()]
        clients = bank.get_clients_ranking()
        top = system.top_clients(len(clients)) if clients else []  # ноль мест нельзя
        stats = system.transaction_statistics()
        summary = {
            "clients": len(clients),
            "accounts": len(accounts),
            "total_rub": total["total_rub"],
            "transactions": stats["total"],
            **stats["by_status"],  # pending, completed, failed, cancelled
            "completed_rub": stats["completed_rub"],
            "fees_rub": stats["fees_rub"],
        }
        charts = {
            "currencies": {"type": "pie", "title": "Деньги банка по валютам, в RUB",
                           "labels": [row["currency"] for row in totals],
                           "values": [row["balance_rub"] for row in totals]},
            "clients": {"type": "bar", "title": "Клиенты по сумме на счетах, RUB",
                        "labels": [row["client_id"] for row in top],
                        "values": [row["total_rub"] for row in top]},
        }
        tables = {
            "accounts": make_table(self.BANK_ACCOUNT_COLUMNS, rows),
            "totals": make_table(self.TOTAL_COLUMNS, totals),
            "clients": make_table(self.CLIENT_COLUMNS, top),
        }
        return self._report("bank", "bank", "Отчёт по банку", summary, tables, charts)

    def risk_report(self):
        """Отчёт по рискам: итоги, подозрительные, отказы, профили, два графика."""
        bank, system = self._system.bank, self._system
        audit_report = system.report  # отчёты дня 5 по журналу аудита
        stats = system.transaction_statistics()
        errors = audit_report.error_statistics()
        suspicious = audit_report.suspicious_operations()
        profiles = []
        for row in bank.get_clients_ranking():  # клиенты в порядке рейтинга банка
            profile = audit_report.client_risk_profile(row["client_id"])
            profiles.append({
                "client_id": row["client_id"],
                "operations": profile["operations"],
                **profile["by_level"],  # low, medium, high
                "blocked": profile["blocked"],
                "level": profile["level"],
            })
        summary = {
            **stats["by_risk"],  # low, medium, high, not_assessed
            "suspicious": len(suspicious),
            "blocked": errors["blocked"],
            "refusals": errors["total"],
            "temporary": errors["temporary"],
            "final": errors["final"],
            "bank_marks": len(bank.get_suspicious_actions()),
        }
        charts = {
            "levels": {"type": "pie", "title": "Транзакции по уровню риска",
                       "labels": [LABELS.get(key, key) for key in stats["by_risk"]],
                       "values": list(stats["by_risk"].values())},
            "errors": {"type": "bar", "title": "Отказы по классам ошибок",
                       "labels": list(errors["by_error"]),
                       "values": list(errors["by_error"].values()),
                       "integer": True},  # счёт отказов: деления оси целые
        }
        error_rows = [{"error": name, "count": count}
                      for name, count in errors["by_error"].items()]
        tables = {
            "suspicious": make_table(self.SUSPICIOUS_COLUMNS, suspicious),
            "errors": make_table(self.ERROR_COLUMNS, error_rows),
            "profiles": make_table(self.PROFILE_COLUMNS, profiles),
        }
        return self._report("risk", "risk", "Отчёт по рискам", summary, tables, charts)

    @staticmethod
    def _check_report(report):
        """Экспорт принимает только отчёт той формы, что строит построитель."""
        good = (
            isinstance(report, dict) and tuple(report) == REPORT_KEYS
            and report["kind"] in KINDS and file_safe(report["name"])
            and isinstance(report["title"], str)
            and isinstance(report["generated_at"], datetime)
            and isinstance(report["summary"], dict)
            and isinstance(report["tables"], dict)
            and isinstance(report["charts"], dict)
            and all(isinstance(name, str) and valid_table(table)
                    for name, table in report["tables"].items())
            and all(file_safe(name) and valid_chart(chart)
                    for name, chart in report["charts"].items())
        )
        if not good:
            raise InvalidOperationError("Экспорт: нужен отчёт ReportBuilder.")

    def _target(self, path, label):
        """Путь файла: строка или Path, папка есть, это не папка и не журнал аудита."""
        if not isinstance(path, (str, Path)):
            raise InvalidOperationError(f"{label}: путь — строка или Path.")
        path = Path(path)
        if not path.parent.is_dir():
            raise InvalidOperationError(f"{label}: папки «{path.parent.name}» нет.")
        if path.is_dir():
            raise InvalidOperationError(f"{label}: «{path.name}» — папка, а не файл.")
        log = self._system.audit.file_path
        if log is not None and path.exists() and path.samefile(log):
            raise InvalidOperationError(f"{label}: файл журнала аудита не затирают.")
        return path

    def render_text(self, report):
        """Отчёт текстом: заголовок, время, итоги и все таблицы."""
        self._check_report(report)
        lines = [
            f"=== {report['title']} ===",
            f"Сформирован: {text_cell(report['generated_at'])}",
            "Итоги:",
        ]
        for key, value in report["summary"].items():
            lines.append(f"  {LABELS.get(key, key)}: {text_cell(value)}")
        for name, table in report["tables"].items():
            lines.append(f"Таблица {name}, строк: {len(table['rows'])}")
            columns = table["columns"]
            header = [LABELS.get(column, column) for column in columns]
            lines.append("  " + " | ".join(header))
            for row in table["rows"]:
                cells = [text_cell(row[column]) for column in columns]
                lines.append("  " + " | ".join(cells))
        return "\n".join(lines) + "\n"

    def export_to_json(self, report, path):
        """Весь отчёт в JSON: UTF-8, кириллица как есть, отступ в два пробела."""
        self._check_report(report)
        path = self._target(path, "JSON")
        try:  # сначала весь текст в памяти: при сбое файл не тронут
            text = json.dumps(plain(report), ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            raise InvalidOperationError(
                "JSON: в отчёте есть значение, которое нельзя записать."
            ) from None
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)
        return path

    def export_to_csv(self, report, path, table=None):
        """Одна таблица отчёта в CSV: без имени — главная. UTF-8 с BOM для Excel."""
        self._check_report(report)
        path = self._target(path, "CSV")
        name = MAIN_TABLES[report["kind"]] if table is None else table
        if not isinstance(name, str) or name not in report["tables"]:
            raise InvalidOperationError(f"CSV: таблицы «{name}» в отчёте нет.")
        data = report["tables"][name]
        lines = [data["columns"]]  # сначала все строки в памяти, потом файл
        for row in data["rows"]:
            lines.append([cell(row[column]) for column in data["columns"]])
        with open(path, "w", encoding="utf-8-sig", newline="") as file:
            csv.writer(file).writerows(lines)  # запятая, кавычки где нужно, CRLF
        return path

    def save_charts(self, report, folder):
        """Сохраняет графики отчёта в PNG и возвращает пути файлов по порядку."""
        self._check_report(report)
        if not isinstance(folder, (str, Path)) or not Path(folder).is_dir():
            raise InvalidOperationError("Графики: нужна папка, которая уже есть.")
        paths = [  # все пути проверены до того, как появится первый файл
            self._target(Path(folder) / f"{report['name']}_{name}.png", "Графики")
            for name in report["charts"]
        ]
        try:
            from . import charts  # matplotlib загружается только здесь
        except ModuleNotFoundError as error:
            if not (error.name or "").startswith("matplotlib"):
                raise  # пропал не matplotlib, а что-то своё: подсказка не поможет
            raise ModuleNotFoundError(
                "Графики: нужен matplotlib. Поставьте его в окружение проекта: "
                r".venv\Scripts\python -m pip install -r requirements.txt"
            ) from error
        for chart, path in zip(report["charts"].values(), paths):
            charts.draw(chart, path)
        return paths

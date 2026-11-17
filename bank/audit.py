"""Журнал аудита: записи о событиях банка в памяти и, если нужно, в файле."""

from pathlib import Path

from .accounts import BankAccount
from .enums import AuditEvent, AuditLevel
from .errors import InvalidOperationError
from .transactions import validate_moment

LEVELS = list(AuditLevel)  # порядок объявления — это порядок важности


def optional_text(value, label):
    """Пустое значение или непустая строка без пробелов по краям."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidOperationError(f"{label}: нужна непустая строка или None.")
    return value.strip()


def copy_record(record):
    """Копия записи: новый словарь записи и новый словарь данных."""
    copy = dict(record)
    copy["data"] = dict(record["data"])
    return copy


class AuditLog:
    """Журнал аудита. Только пополняется: записи нельзя удалить или исправить."""

    def __init__(self, *, file_path=None):
        if file_path is not None:
            if not isinstance(file_path, (str, Path)):
                raise InvalidOperationError("Файл журнала: нужна строка или Path.")
            file_path = Path(file_path)
            try:
                with open(file_path, "a", encoding="utf-8"):
                    pass  # файл появился или уже был: негодный путь виден сразу
            except OSError:
                raise InvalidOperationError(
                    f"Файл журнала: не удалось открыть {file_path.name} на дозапись."
                ) from None
        self._file_path = file_path  # None: журнал живёт только в памяти
        self._records = []

    @property
    def file_path(self):
        return self._file_path

    def __len__(self):
        return len(self._records)

    def add(
        self, moment, level, event, message, *, client_id=None, transaction_id=None,
        data=None,
    ):
        """Проверяет запись, дописывает её в файл и в память, возвращает копию."""
        moment = validate_moment(moment, "Время записи")
        level = BankAccount._validate_choice(level, AuditLevel, "Уровень важности")
        event = BankAccount._validate_choice(event, AuditEvent, "Событие")
        if not isinstance(message, str) or not message.strip():
            raise InvalidOperationError("Сообщение записи: нужна непустая строка.")
        if len(message.strip().splitlines()) > 1:  # одна запись — одна строка файла
            raise InvalidOperationError("Сообщение записи: переносы строк запрещены.")
        client_id = optional_text(client_id, "ID клиента")
        transaction_id = optional_text(transaction_id, "ID транзакции")
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise InvalidOperationError("Данные записи: нужен словарь или None.")
        record = {
            "time": moment,
            "level": level,
            "event": event,
            "message": message.strip(),
            "client_id": client_id,
            "transaction_id": transaction_id,
            "data": dict(data),  # своя копия: снаружи данные журнала не изменить
        }
        if self._file_path is not None:  # сначала файл: при сбое запись не добавится
            with open(self._file_path, "a", encoding="utf-8") as file:
                file.write(self._line(record) + "\n")
        self._records.append(record)
        return copy_record(record)

    @staticmethod
    def _line(record):
        """Строка файла: шесть полей через « | », вместо пустого поля — дефис."""
        return " | ".join([
            f"{record['time']:%Y-%m-%d %H:%M:%S}",
            record["level"].value,
            record["event"].value,
            record["client_id"] or "-",
            record["transaction_id"] or "-",
            record["message"],
        ])

    def get_records(self):
        """Все записи копиями в порядке добавления."""
        return self.filter()

    def filter(
        self, *, min_level=None, event=None, client_id=None, transaction_id=None,
        since=None, until=None,
    ):
        """Записи, подходящие под все переданные условия, копиями по порядку."""
        weakest = None
        if min_level is not None:
            level = BankAccount._validate_choice(min_level, AuditLevel, "Фильтр")
            weakest = LEVELS.index(level)
        if event is not None:
            event = BankAccount._validate_choice(event, AuditEvent, "Фильтр")
        texts = {"ID клиента": client_id, "ID транзакции": transaction_id}
        for label, value in texts.items():
            if value is not None and not isinstance(value, str):
                raise InvalidOperationError(f"Фильтр: {label} должен быть строкой.")
        if since is not None:
            since = validate_moment(since, "Фильтр: начало периода")
        if until is not None:
            until = validate_moment(until, "Фильтр: конец периода")
        found = []
        for record in self._records:
            if weakest is not None and LEVELS.index(record["level"]) < weakest:
                continue
            if since is not None and record["time"] < since:
                continue
            if until is not None and record["time"] > until:
                continue
            same = (
                self._fits(event, record["event"])
                and self._fits(client_id, record["client_id"])
                and self._fits(transaction_id, record["transaction_id"])
            )
            if same:
                found.append(copy_record(record))
        return found

    @staticmethod
    def _fits(wanted, actual):
        """Условие не задано или совпало."""
        return wanted is None or actual == wanted

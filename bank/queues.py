"""Очередь транзакций: приоритет, отложенные операции и отмена."""

from datetime import datetime

from .accounts import BankAccount
from .enums import Priority, TransactionStatus
from .errors import InvalidOperationError
from .transactions import Transaction, validate_moment


def validate_run_at(run_at):
    """Время исполнения: дата со временем или None, то есть «можно сразу»."""
    if run_at is None:
        return None
    return validate_moment(run_at, "Время исполнения")


class TransactionQueue:
    """Хранит ожидающие транзакции и решает, какую исполнять следующей."""

    def __init__(self):
        self._entries = {}  # ID транзакции -> запись: транзакция, приоритет, время

    def __len__(self):
        return len(self._entries)

    def _find(self, transaction_id):
        """Находит запись очереди по ID транзакции или сообщает, что её нет."""
        if not isinstance(transaction_id, str) or transaction_id not in self._entries:
            raise InvalidOperationError(
                f"Транзакции с ID «{transaction_id}» в очереди нет."
            )
        return self._entries[transaction_id]

    def add(self, transaction, *, priority=Priority.NORMAL, run_at=None):
        """Ставит транзакцию в очередь и возвращает её ID."""
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError("Очередь: нужен объект Transaction.")
        name = transaction.transaction_id
        if transaction.status is not TransactionStatus.PENDING:
            raise InvalidOperationError(
                f"Очередь: транзакция {name} уже в статусе {transaction.status}."
            )
        if name in self._entries:
            raise InvalidOperationError(
                f"Очередь: транзакция {name} уже стоит в очереди."
            )
        priority = BankAccount._validate_choice(priority, Priority, "Приоритет")
        run_at = validate_run_at(run_at)
        self._entries[name] = {
            "transaction": transaction,
            "priority": priority,
            "run_at": run_at,
        }
        return name

    def get_entries(self):
        """Записи в порядке обслуживания: сначала срочные, внутри — по очереди."""
        result = []
        for priority in Priority:  # high, normal, low: как объявлено в перечислении
            for entry in self._entries.values():  # в порядке добавления
                if entry["priority"] is priority:
                    result.append(dict(entry))  # копия: очередь снаружи не изменить
        return result

    def next_ready(self, now):
        """Первая готовая транзакция или None. Из очереди её не убирает."""
        now = validate_moment(now, "Текущее время")
        for entry in self.get_entries():
            transaction, run_at = entry["transaction"], entry["run_at"]
            if transaction.status is not TransactionStatus.PENDING:
                continue  # завершили в обход очереди: на исполнение не выдаём
            if run_at is None or run_at <= now:
                return transaction
        return None

    def cancel(self, transaction_id, *, at=None):
        """Отменяет транзакцию: меняет её статус и убирает из очереди."""
        entry = self._find(transaction_id)
        moment = datetime.now() if at is None else at  # без at — время компьютера
        entry["transaction"].cancel(moment)
        del self._entries[transaction_id]
        return entry["transaction"]

    def reschedule(self, transaction_id, run_at):
        """Назначает новое время исполнения. Место в очереди остаётся прежним."""
        entry = self._find(transaction_id)
        entry["run_at"] = validate_run_at(run_at)

    def remove(self, transaction_id):
        """Убирает завершённую транзакцию. Этот метод вызывает процессор."""
        entry = self._find(transaction_id)
        if entry["transaction"].status is TransactionStatus.PENDING:
            raise InvalidOperationError(
                f"Очередь: транзакция {transaction_id} ещё ожидает. "
                "Её можно только отменить."
            )
        del self._entries[transaction_id]

"""Транзакция: запись об одной операции с деньгами."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from .accounts import BankAccount
from .enums import Currency, TransactionStatus, TransactionType
from .errors import InvalidOperationError

NEEDS_SENDER = (  # у этих типов есть счёт, с которого уходят деньги
    TransactionType.WITHDRAWAL,
    TransactionType.TRANSFER,
    TransactionType.EXTERNAL_TRANSFER,
)
NEEDS_RECIPIENT = (  # у этих типов есть счёт, на который приходят деньги
    TransactionType.DEPOSIT,
    TransactionType.TRANSFER,
    TransactionType.EXTERNAL_TRANSFER,
)


def mask(account_id):
    """Прячет номер счёта: оставляет четыре последних символа."""
    return "нет" if account_id is None else "****" + account_id[-4:]


def validate_moment(value, label):
    """Принимает только дату со временем."""
    if not isinstance(value, datetime):
        kind = type(value).__name__
        raise InvalidOperationError(f"{label}: нужны дата и время, а пришло {kind}.")
    return value


def validate_number(value, label):
    """Проверяет номер счёта или ID: буквы и цифры, не меньше 4 символов."""
    if not isinstance(value, str):
        raise InvalidOperationError(f"{label}: нужна строка.")
    value = value.strip()
    if len(value) < 4 or not value.isalnum():
        raise InvalidOperationError(
            f"{label}: нужны только буквы и цифры, не меньше 4 символов."
        )
    return value


def validate_party(value, needed, label):
    """Проверяет сторону транзакции: отправителя или получателя."""
    if needed and value is None:
        raise InvalidOperationError(f"{label}: для этого типа транзакции он нужен.")
    if not needed and value is not None:
        raise InvalidOperationError(f"{label}: у этого типа транзакции его нет.")
    return None if value is None else validate_number(value, label)


class Transaction:
    """Одна операция с деньгами. Проверяет свои данные при создании."""

    def __init__(
        self, transaction_type, amount, *, currency=Currency.RUB, sender=None,
        recipient=None, transaction_id=None, created_at=None,
    ):
        kind = BankAccount._validate_choice(
            transaction_type, TransactionType, "Тип транзакции"
        )
        amount = BankAccount._validate_amount(amount, "Сумма транзакции")
        currency = BankAccount._validate_choice(currency, Currency, "Валюта")
        sender = validate_party(sender, kind in NEEDS_SENDER, "Отправитель")
        recipient = validate_party(recipient, kind in NEEDS_RECIPIENT, "Получатель")
        if sender is not None and sender == recipient:
            raise InvalidOperationError("Получатель: он совпадает с отправителем.")
        if transaction_id is None:
            transaction_id = uuid4().hex[:8]  # ID не дали: берём короткий UUID
        else:
            transaction_id = validate_number(transaction_id, "ID транзакции")
        if created_at is None:
            created_at = datetime.now()  # время не дали: берём время компьютера
        self._created_at = validate_moment(created_at, "Время создания")
        self._transaction_id = transaction_id
        self._transaction_type = kind
        self._amount = amount
        self._currency = currency
        self._sender = sender
        self._recipient = recipient
        self._status = TransactionStatus.PENDING  # новая транзакция всегда ожидает
        self._fee = Decimal("0.00")  # комиссию запишет процессор при исполнении
        self._failure_reason = None
        self._attempts = 0
        self._finished_at = None

    @property
    def transaction_id(self):
        return self._transaction_id

    @property
    def transaction_type(self):
        return self._transaction_type

    @property
    def amount(self):
        return self._amount

    @property
    def currency(self):
        return self._currency

    @property
    def fee(self):
        return self._fee

    @property
    def sender(self):
        return self._sender

    @property
    def recipient(self):
        return self._recipient

    @property
    def status(self):
        return self._status

    @property
    def failure_reason(self):
        return self._failure_reason

    @property
    def attempts(self):
        return self._attempts

    @property
    def created_at(self):
        return self._created_at

    @property
    def finished_at(self):
        return self._finished_at

    def _check_pending(self):
        """Менять можно только ожидающую транзакцию."""
        if self._status is not TransactionStatus.PENDING:
            raise InvalidOperationError(
                f"Транзакция {self._transaction_id} уже в статусе {self._status}: "
                "изменить её нельзя."
            )

    def start_attempt(self):
        """Засчитывает попытку исполнения и возвращает её номер."""
        self._check_pending()
        self._attempts += 1
        return self._attempts

    def complete(self, fee, moment):
        """Отмечает транзакцию выполненной. Этот метод вызывает процессор."""
        self._check_pending()
        fee = BankAccount._validate_amount(fee, "Комиссия", allow_zero=True)
        self._finished_at = validate_moment(moment, "Время завершения")
        self._fee = fee
        self._status = TransactionStatus.COMPLETED
        return self._status

    def fail(self, reason, moment):
        """Отмечает транзакцию отклонённой. Этот метод вызывает процессор."""
        self._check_pending()
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidOperationError("Причина отказа: нужна непустая строка.")
        self._finished_at = validate_moment(moment, "Время завершения")
        self._failure_reason = reason.strip()
        self._status = TransactionStatus.FAILED
        return self._status

    def cancel(self, moment):
        """Отмечает транзакцию отменённой. Этот метод вызывает очередь."""
        self._check_pending()
        self._finished_at = validate_moment(moment, "Время завершения")
        self._status = TransactionStatus.CANCELLED
        return self._status

    def get_transaction_info(self):
        return {
            "transaction_id": self._transaction_id,
            "transaction_type": self._transaction_type.value,
            "amount": self._amount,
            "currency": self._currency.value,
            "fee": self._fee,
            "sender": self._sender,
            "recipient": self._recipient,
            "status": self._status.value,
            "failure_reason": self._failure_reason,
            "attempts": self._attempts,
            "created_at": self._created_at,
            "finished_at": self._finished_at,
        }

    def __str__(self):
        return (
            f"{type(self).__name__} | {self._transaction_type} | "
            f"{self._transaction_id} | {self._status} | "
            f"{self._amount:.2f} {self._currency} | "
            f"{mask(self._sender)} -> {mask(self._recipient)}"
        )

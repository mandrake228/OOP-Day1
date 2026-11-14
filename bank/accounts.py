"""Модель счетов: общий контракт и обычный банковский счёт."""

from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from .enums import AccountStatus, Currency
from .errors import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)

CENT = Decimal("0.01")  # самая мелкая часть денег: одна копейка или один цент


class AbstractAccount(ABC):
    """Общий контракт: что есть у любого счёта и что он обязан уметь."""

    def __init__(self, account_id, owner, balance, status):
        self._account_id = account_id
        self._owner = owner
        self._balance = balance
        self._status = status

    @property
    def account_id(self):
        return self._account_id

    @property
    def owner(self):
        return self._owner

    @property
    def balance(self):
        return self._balance

    @property
    def status(self):
        return self._status

    @abstractmethod
    def deposit(self, amount):
        """Пополнить счёт и вернуть новый баланс."""

    @abstractmethod
    def withdraw(self, amount):
        """Снять деньги и вернуть новый баланс."""

    @abstractmethod
    def get_account_info(self):
        """Вернуть сведения о счёте словарём."""


class BankAccount(AbstractAccount):
    """Обычный банковский счёт. Проверяет всё, что ему передают."""

    def __init__(
        self,
        owner,
        account_id=None,
        balance=0,
        currency=Currency.RUB,
        status=AccountStatus.ACTIVE,
    ):
        owner = self._validate_owner(owner)
        account_id = self._validate_account_id(account_id)
        balance = self._validate_amount(balance, "Начальный баланс", allow_zero=True)
        status = self._validate_choice(status, AccountStatus, "Статус счёта")
        currency = self._validate_choice(currency, Currency, "Валюта")
        super().__init__(account_id, owner, balance, status)
        self._currency = currency

    @property
    def currency(self):
        return self._currency

    @staticmethod
    def _validate_owner(owner):
        if not isinstance(owner, str) or not owner.strip():
            raise InvalidOperationError("Владелец: нужно непустое имя строкой.")
        return owner.strip()

    @staticmethod
    def _validate_account_id(account_id):
        if account_id is None:
            return uuid4().hex[:8]  # номер не дали: берём короткий UUID
        if not isinstance(account_id, str):
            raise InvalidOperationError("Номер счёта: нужна строка.")
        account_id = account_id.strip()
        if len(account_id) < 4 or not account_id.isalnum():
            raise InvalidOperationError(
                "Номер счёта: нужны только буквы и цифры, не меньше 4 символов."
            )
        return account_id

    @staticmethod
    def _validate_choice(value, choices, label):
        if isinstance(value, choices):
            return value
        if isinstance(value, str):
            for choice in choices:
                if choice.value.lower() == value.strip().lower():
                    return choice
        allowed = ", ".join(choice.value for choice in choices)
        raise InvalidOperationError(
            f"{label}: «{value}» не подходит. Можно: {allowed}."
        )

    @staticmethod
    def _validate_amount(amount, label, allow_zero=False):
        if isinstance(amount, bool) or not isinstance(amount, (int, float, Decimal)):
            kind = type(amount).__name__
            raise InvalidOperationError(f"{label}: нужно число, а пришло {kind}.")
        value = Decimal(str(amount))
        if not value.is_finite():
            raise InvalidOperationError(f"{label}: сумма должна быть конечным числом.")
        if value.is_signed():
            raise InvalidOperationError(f"{label}: сумма не может быть отрицательной.")
        if value == 0 and not allow_zero:
            raise InvalidOperationError(f"{label}: сумма должна быть больше нуля.")
        try:
            cents = value.quantize(CENT)
        except InvalidOperation:
            raise InvalidOperationError(f"{label}: сумма слишком большая.") from None
        if cents != value:
            raise InvalidOperationError(
                f"{label}: у суммы может быть не больше двух знаков после запятой."
            )
        return cents

    def _masked_id(self):
        return "****" + self._account_id[-4:]

    def _check_status(self):
        if self._status is AccountStatus.FROZEN:
            raise AccountFrozenError(
                f"Счёт {self._masked_id()} заморожен: операции временно недоступны."
            )
        if self._status is AccountStatus.CLOSED:
            raise AccountClosedError(
                f"Счёт {self._masked_id()} закрыт: операции больше невозможны."
            )

    def deposit(self, amount):
        value = self._validate_amount(amount, f"Пополнение счёта {self._masked_id()}")
        self._check_status()
        self._balance += value
        return self._balance

    def withdraw(self, amount):
        value = self._validate_amount(amount, f"Снятие со счёта {self._masked_id()}")
        self._check_status()
        if value > self._balance:
            raise InsufficientFundsError(
                f"Счёт {self._masked_id()}: недостаточно средств. "
                f"Запрошено {value} {self._currency}, "
                f"доступно {self._balance} {self._currency}."
            )
        self._balance -= value
        return self._balance

    def get_account_info(self):
        return {
            "account_type": type(self).__name__,
            "account_id": self._account_id,
            "owner": self._owner,
            "status": self._status.value,
            "balance": self._balance,
            "currency": self._currency.value,
        }

    def __str__(self):
        return (
            f"{type(self).__name__} | {self._owner} | {self._masked_id()} | "
            f"{self._status} | {self._balance:.2f} {self._currency}"
        )

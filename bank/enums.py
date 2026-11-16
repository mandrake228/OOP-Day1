"""Статусы счёта и валюты."""

from enum import StrEnum


class AccountStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    KZT = "KZT"
    CNY = "CNY"


class AssetType(StrEnum):
    STOCKS = "stocks"  # акции
    BONDS = "bonds"  # облигации
    ETF = "etf"  # биржевые фонды


class ClientStatus(StrEnum):
    ACTIVE = "active"  # клиент может входить и получать счета
    BLOCKED = "blocked"  # заблокирован после трёх неверных паролей подряд


class TransactionType(StrEnum):
    DEPOSIT = "deposit"  # пополнение: деньги приходят в банк
    WITHDRAWAL = "withdrawal"  # снятие: деньги уходят из банка
    TRANSFER = "transfer"  # перевод между счетами этого банка
    EXTERNAL_TRANSFER = "external_transfer"  # перевод на счёт в другом банке


class TransactionStatus(StrEnum):
    PENDING = "pending"  # ожидает исполнения
    COMPLETED = "completed"  # выполнена
    FAILED = "failed"  # отклонена: у неё есть причина отказа
    CANCELLED = "cancelled"  # отменена до исполнения


class Priority(StrEnum):
    HIGH = "high"  # порядок строк здесь — это порядок обслуживания в очереди
    NORMAL = "normal"
    LOW = "low"

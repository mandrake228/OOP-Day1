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


class AuditLevel(StrEnum):
    INFO = "info"  # обычное событие; строки идут от слабого к сильному
    WARNING = "warning"  # предупреждение
    ERROR = "error"  # ошибка
    CRITICAL = "critical"  # критическое событие


class AuditEvent(StrEnum):
    RISK = "risk"  # оценка риска
    COMPLETED = "completed"  # транзакция выполнена
    REFUSED = "refused"  # отказ при исполнении
    BLOCKED = "blocked"  # блокировка из-за высокого риска


class RiskLevel(StrEnum):
    LOW = "low"  # строки идут от низкого к высокому
    MEDIUM = "medium"
    HIGH = "high"


class RiskSignal(StrEnum):
    LARGE_AMOUNT = "large_amount"  # крупная сумма
    FREQUENT_OPERATIONS = "frequent_operations"  # частые операции
    NEW_RECIPIENT = "new_recipient"  # перевод на новый счёт
    NIGHT_OPERATION = "night_operation"  # операция ночью

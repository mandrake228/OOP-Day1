"""Ошибки модели счетов."""


class AccountError(Exception):
    """Общий предок всех ошибок счёта."""


class AccountFrozenError(AccountError):
    """Счёт заморожен: операции временно запрещены."""


class AccountClosedError(AccountError):
    """Счёт закрыт: операции запрещены навсегда."""


class InvalidOperationError(AccountError):
    """Неверные данные: сумма, владелец, номер, валюта или статус."""


class InsufficientFundsError(AccountError):
    """На счёте меньше денег, чем просят снять."""

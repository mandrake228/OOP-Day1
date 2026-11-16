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


class AuthenticationError(AccountError):
    """Вход не удался: неверный ID клиента или пароль."""


class ClientBlockedError(AccountError):
    """Клиент заблокирован: вход и операции по его просьбе запрещены."""


class NightOperationError(AccountError):
    """Ночные часы: банк не выполняет операции."""

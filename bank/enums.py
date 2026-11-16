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

"""Банк: клиенты, счета и защита."""

import hashlib
import hmac
import secrets
from datetime import datetime, time
from decimal import Decimal

from .accounts import BankAccount
from .clients import Client
from .enums import AccountStatus, ClientStatus, Currency
from .errors import (
    AuthenticationError,
    ClientBlockedError,
    InvalidOperationError,
    NightOperationError,
)

HASH_ITERATIONS = 600_000  # столько раз перемешивается пароль: подбирать долго


def hash_password(password, salt):
    """Превращает пароль в хеш. Получить пароль обратно из хеша нельзя."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ITERATIONS)


def is_account_class(value):
    """Отвечает, класс ли это счёта: BankAccount или его наследник."""
    return isinstance(value, type) and issubclass(value, BankAccount)


class Bank:
    """Управляющий класс: знает всех клиентов и все счета и следит за защитой."""

    MAX_LOGIN_ATTEMPTS = 3  # столько неверных паролей подряд блокируют клиента
    NIGHT_START = time(0, 0)  # с этого времени операции запрещены
    NIGHT_END = time(5, 0)  # с этого времени снова разрешены

    def __init__(self, *, clock=None):
        if clock is None:
            clock = datetime.now  # своих часов не дали: берём время компьютера
        if not callable(clock):
            raise InvalidOperationError(
                "Часы банка: нужна функция, которая возвращает текущее время."
            )
        self._clock = clock
        self._clients = {}  # ID клиента -> клиент
        self._accounts = {}  # номер счёта -> счёт
        self._owners = {}  # номер счёта -> ID клиента
        self._passwords = {}  # ID клиента -> (соль, хеш пароля)
        self._failed_logins = {}  # ID клиента -> неверных паролей подряд
        self._suspicious = []  # журнал подозрительных действий

    def _mark(self, action, reason, client_id=None, account_id=None):
        """Записывает подозрительное действие в журнал."""
        self._suspicious.append({
            "time": self._clock(),
            "action": action,
            "client_id": client_id if isinstance(client_id, str) else None,
            "account_id": account_id if isinstance(account_id, str) else None,
            "reason": reason,
        })

    def _check_time(self, action, client_id=None, account_id=None):
        """Ночью помечает попытку как подозрительную и отказывает."""
        now = self._clock()
        if self.NIGHT_START <= now.time() < self.NIGHT_END:
            reason = f"Операция в ночные часы: {now:%H:%M}."
            self._mark(action, reason, client_id, account_id)
            raise NightOperationError(
                f"Сейчас {now:%H:%M}. С {self.NIGHT_START:%H:%M} до "
                f"{self.NIGHT_END:%H:%M} банк не выполняет операции."
            )

    def get_suspicious_actions(self, client_id=None):
        """Возвращает копию журнала: весь или только по одному ID клиента."""
        return [
            dict(record)
            for record in self._suspicious
            if client_id is None or record["client_id"] == client_id
        ]

    def add_client(self, client, password):
        """Регистрирует клиента вместе с паролем и возвращает его ID."""
        client_id = client.client_id if isinstance(client, Client) else None
        self._check_time("add_client", client_id)
        if client_id is None:
            raise InvalidOperationError("Регистрация: нужен объект Client.")
        if client_id in self._clients:
            raise InvalidOperationError(f"Регистрация: ID «{client_id}» уже занят.")
        if (
            not isinstance(password, str)
            or not 8 <= len(password) <= 128
            or not password.strip()
        ):
            raise InvalidOperationError(
                "Пароль: нужна строка от 8 до 128 символов, не из одних пробелов."
            )
        salt = secrets.token_bytes(16)  # случайная добавка, у каждого клиента своя
        self._passwords[client_id] = (salt, hash_password(password, salt))
        self._failed_logins[client_id] = 0
        self._clients[client_id] = client
        return client_id

    def _find_client(self, client_id):
        """Находит клиента по ID или сообщает, что такого нет."""
        if not isinstance(client_id, str) or client_id not in self._clients:
            raise InvalidOperationError(f"Клиент с ID «{client_id}» не найден.")
        return self._clients[client_id]

    def _check_client_active(self, client, action, account_id=None):
        """Заблокированному клиенту отказывает и помечает обращение."""
        if client.status is ClientStatus.BLOCKED:
            reason = "Обращение от имени заблокированного клиента."
            self._mark(action, reason, client.client_id, account_id)
            raise ClientBlockedError(
                f"Клиент {client.client_id} заблокирован: операция недоступна."
            )

    def open_account(self, client_id, account_type=BankAccount, **params):
        """Открывает клиенту счёт нужного типа и возвращает этот счёт."""
        self._check_time("open_account", client_id)
        client = self._find_client(client_id)
        self._check_client_active(client, "open_account")
        if not is_account_class(account_type):
            raise InvalidOperationError(
                "Тип счёта: нужен класс счёта, например SavingsAccount."
            )
        account = account_type(client.full_name, status=AccountStatus.ACTIVE, **params)
        if account.account_id in self._accounts:
            raise InvalidOperationError("Номер счёта: такой счёт в банке уже есть.")
        client.add_account(account.account_id)
        self._accounts[account.account_id] = account
        self._owners[account.account_id] = client_id
        return account

    def _find_account(self, account_id):
        """Находит счёт по номеру или сообщает, что такого нет."""
        if not isinstance(account_id, str) or account_id not in self._accounts:
            raise InvalidOperationError("Счёт с таким номером в банке не найден.")
        return self._accounts[account_id]

    def _owner_of(self, account_id):
        """ID клиента, которому открыт счёт. Если счёта нет, то None."""
        return self._owners.get(account_id) if isinstance(account_id, str) else None

    def freeze_account(self, account_id):
        """Замораживает счёт. Работает и ночью: защита не ждёт утра."""
        return self._find_account(account_id).freeze()

    def unfreeze_account(self, account_id):
        """Размораживает счёт и возвращает его новый статус."""
        self._check_time("unfreeze_account", self._owner_of(account_id), account_id)
        return self._find_account(account_id).unfreeze()

    def close_account(self, account_id):
        """Закрывает счёт по просьбе клиента и возвращает новый статус."""
        owner_id = self._owner_of(account_id)
        self._check_time("close_account", owner_id, account_id)
        account = self._find_account(account_id)
        self._check_client_active(self._clients[owner_id], "close_account", account_id)
        return account.close()

    def authenticate_client(self, client_id, password):
        """Проверяет ID и пароль. Три ошибки подряд блокируют клиента."""
        action = "authenticate_client"
        self._check_time(action, client_id)
        if not isinstance(client_id, str) or client_id not in self._clients:
            self._mark(action, "Вход с неизвестным ID клиента.", client_id)
            raise AuthenticationError("Неверный ID клиента или пароль.")
        client = self._clients[client_id]
        self._check_client_active(client, action)
        salt, stored = self._passwords[client_id]
        right = isinstance(password, str) and hmac.compare_digest(
            stored, hash_password(password, salt)
        )
        if right:
            self._failed_logins[client_id] = 0  # верный вход обнуляет счёт ошибок
            return True
        self._failed_logins[client_id] += 1
        attempt = self._failed_logins[client_id]
        reason = f"Неверный пароль: попытка {attempt} из {self.MAX_LOGIN_ATTEMPTS}."
        if attempt < self.MAX_LOGIN_ATTEMPTS:
            self._mark(action, reason, client_id)
            raise AuthenticationError("Неверный ID клиента или пароль.")
        client.block()
        self._mark(action, reason + " Клиент заблокирован.", client_id)
        raise ClientBlockedError(
            f"Клиент {client_id} заблокирован после {attempt} неверных попыток "
            "входа подряд."
        )

    def search_accounts(
        self, *, client_id=None, owner=None, account_type=None, status=None,
        currency=None,
    ):
        """Ищет счета по условиям. Без условий возвращает все счета банка."""
        if client_id is not None and not isinstance(client_id, str):
            raise InvalidOperationError("Поиск: ID клиента должен быть строкой.")
        if owner is not None and (not isinstance(owner, str) or not owner.strip()):
            raise InvalidOperationError("Поиск: нужна непустая часть имени владельца.")
        if account_type is not None and not is_account_class(account_type):
            raise InvalidOperationError("Поиск: тип счёта должен быть классом счёта.")
        if status is not None:
            status = BankAccount._validate_choice(status, AccountStatus, "Статус счёта")
        if currency is not None:
            currency = BankAccount._validate_choice(currency, Currency, "Валюта")
        found = []
        for account_id, account in self._accounts.items():
            if client_id is not None and self._owners[account_id] != client_id:
                continue
            if owner is not None and owner.strip().lower() not in account.owner.lower():
                continue
            if account_type is not None and type(account) is not account_type:
                continue
            if status is not None and account.status is not status:
                continue
            if currency is not None and account.currency is not currency:
                continue
            found.append(account)
        return found

    def get_total_balance(self, *, currency=Currency.RUB, client_id=None):
        """Складывает балансы незакрытых счетов в одной валюте."""
        currency = BankAccount._validate_choice(currency, Currency, "Валюта")
        if client_id is not None:
            self._find_client(client_id)  # неизвестный клиент — это ошибка
        total = Decimal("0.00")
        for account in self.search_accounts(client_id=client_id, currency=currency):
            if account.status is not AccountStatus.CLOSED:
                total += account.balance
        return total

    def get_clients_ranking(self, *, currency=Currency.RUB):
        """Все клиенты по убыванию суммы на счетах в одной валюте."""
        currency = BankAccount._validate_choice(currency, Currency, "Валюта")
        ranking = []
        for client_id, client in self._clients.items():
            total = self.get_total_balance(currency=currency, client_id=client_id)
            ranking.append(
                {"client_id": client_id, "full_name": client.full_name, "total": total}
            )
        ranking.sort(key=lambda row: row["total"], reverse=True)
        for place, row in enumerate(ranking, start=1):
            row["place"] = place
        return ranking

    def now(self):
        """Текущее время по часам банка."""
        return self._clock()

    def has_account(self, account_id):
        """Отвечает, есть ли в банке счёт с таким номером."""
        return isinstance(account_id, str) and account_id in self._accounts

    def get_account(self, account_id):
        """Возвращает счёт по номеру или сообщает, что такого нет."""
        return self._find_account(account_id)

    def check_operation_time(self, action, account_id=None):
        """Ночью отказывает в операции со счётом и помечает попытку. Днём молчит."""
        if not isinstance(action, str) or not action.strip():
            raise InvalidOperationError("Проверка времени: нужно название операции.")
        self._check_time(action, self._owner_of(account_id), account_id)

    def get_owner_id(self, account_id):
        """ID клиента, которому открыт счёт. Счёта нет — None. Работает и ночью."""
        return self._owner_of(account_id)

    def check_client_active(self, client_id, action, account_id=None):
        """Заблокированному клиенту отказывает и помечает обращение. Иначе молчит."""
        if not isinstance(action, str) or not action.strip():
            raise InvalidOperationError("Проверка клиента: нужно название операции.")
        client = self._find_client(client_id)  # неизвестный клиент — ошибка
        self._check_client_active(client, action, account_id)

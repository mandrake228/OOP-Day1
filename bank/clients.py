"""Клиент банка: личные данные, контакты и список номеров счетов."""

from datetime import date, datetime
from uuid import uuid4

from .enums import ClientStatus
from .errors import InvalidOperationError


def age_on(birth_date, day):
    """Считает, сколько полных лет человеку в указанный день."""
    had_birthday = (day.month, day.day) >= (birth_date.month, birth_date.day)
    return day.year - birth_date.year - (0 if had_birthday else 1)


def validate_date(value, label):
    """Принимает только дату. У даты со временем время отбрасывает."""
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, date):
        kind = type(value).__name__
        raise InvalidOperationError(f"{label}: нужна дата, а пришло {kind}.")
    return value


def validate_client_id(client_id):
    """Проверяет ID клиента. Если его не дали, придумывает короткий UUID."""
    if client_id is None:
        return uuid4().hex[:8]
    if not isinstance(client_id, str):
        raise InvalidOperationError("ID клиента: нужна строка.")
    client_id = client_id.strip()
    if len(client_id) < 4 or not client_id.isalnum():
        raise InvalidOperationError(
            "ID клиента: нужны только буквы и цифры, не меньше 4 символов."
        )
    return client_id


def validate_phone(phone):
    """Проверяет телефон и убирает из него пробелы, скобки и дефисы."""
    if not isinstance(phone, str):
        raise InvalidOperationError("Телефон: нужна строка.")
    text = phone.strip()
    plus = "+" if text.startswith("+") else ""
    digits = text.removeprefix("+")
    for extra in " -()":
        digits = digits.replace(extra, "")
    if not (digits.isascii() and digits.isdigit() and 10 <= len(digits) <= 15):
        raise InvalidOperationError(
            "Телефон: нужно от 10 до 15 цифр. Можно «+» в начале, пробелы, "
            "скобки и дефисы."
        )
    return plus + digits


def validate_email(email):
    """Проверяет адрес почты и переводит его в нижний регистр."""
    if not isinstance(email, str):
        raise InvalidOperationError("Почта: нужна строка.")
    text = email.strip().lower()
    name, _, domain = text.partition("@")
    parts = domain.split(".")
    has_space = any(char.isspace() for char in text)
    if has_space or not name or "@" in domain or len(parts) < 2 or "" in parts:
        raise InvalidOperationError(
            "Почта: нужен адрес вида имя@домен.зона без пробелов."
        )
    return text


class Client:
    """Клиент банка. Проверяет свои данные при создании."""

    MIN_AGE = 18  # моложе клиентом стать нельзя

    def __init__(
        self, full_name, birth_date, *, client_id=None, phone=None, email=None,
        today=None,
    ):
        if not isinstance(full_name, str) or not full_name.strip():
            raise InvalidOperationError("ФИО: нужно непустое имя строкой.")
        birth_date = validate_date(birth_date, "Дата рождения")
        if today is None:
            today = date.today()  # дату проверки не дали: берём сегодняшнюю
        today = validate_date(today, "Дата проверки возраста")
        if birth_date > today:
            raise InvalidOperationError("Дата рождения: она позже даты проверки.")
        age = age_on(birth_date, today)
        if age < self.MIN_AGE:
            raise InvalidOperationError(
                f"Возраст: клиенту {age}, а нужно не меньше {self.MIN_AGE}."
            )
        if phone is None and email is None:
            raise InvalidOperationError("Контакты: нужен телефон или почта.")
        self._client_id = validate_client_id(client_id)
        self._full_name = full_name.strip()
        self._birth_date = birth_date
        self._phone = None if phone is None else validate_phone(phone)
        self._email = None if email is None else validate_email(email)
        self._status = ClientStatus.ACTIVE
        self._account_ids = []

    @property
    def client_id(self):
        return self._client_id

    @property
    def full_name(self):
        return self._full_name

    @property
    def birth_date(self):
        return self._birth_date

    @property
    def status(self):
        return self._status

    @property
    def account_ids(self):
        return list(self._account_ids)  # копия: снаружи список не изменить

    @property
    def contacts(self):
        return {"phone": self._phone, "email": self._email}

    def add_account(self, account_id):
        """Запоминает номер нового счёта. Этот метод вызывает банк."""
        if not isinstance(account_id, str) or not account_id.strip():
            raise InvalidOperationError("Номер счёта: нужна непустая строка.")
        if account_id in self._account_ids:
            raise InvalidOperationError("Номер счёта: такой у клиента уже есть.")
        self._account_ids.append(account_id)

    def block(self):
        """Блокирует клиента. Этот метод вызывает банк."""
        self._status = ClientStatus.BLOCKED

    def get_client_info(self):
        return {
            "client_id": self._client_id,
            "full_name": self._full_name,
            "birth_date": self._birth_date,
            "status": self._status.value,
            "phone": self._phone,
            "email": self._email,
            "account_ids": list(self._account_ids),
        }

    def __str__(self):
        return (
            f"{type(self).__name__} | {self._full_name} | {self._client_id} | "
            f"{self._status} | счетов: {len(self._account_ids)}"
        )

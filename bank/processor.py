"""Процессор транзакций: комиссии, конвертация, повторные попытки, журнал ошибок."""

from datetime import timedelta
from decimal import Decimal

from .accounts import BankAccount
from .advanced import to_cents
from .bank import Bank
from .enums import AccountStatus, Currency, TransactionStatus, TransactionType
from .errors import (
    AccountClosedError,
    AccountError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from .queues import TransactionQueue
from .transactions import Transaction, mask

# После этих отказов попытку стоит повторить: счёт разморозят, деньги придут.
TEMPORARY = (AccountFrozenError, InsufficientFundsError)


def validate_exchange_rate(rate, currency):
    """Проверяет курс валюты: конечное число больше нуля."""
    if isinstance(rate, bool) or not isinstance(rate, (int, float, Decimal)):
        kind = type(rate).__name__
        raise InvalidOperationError(f"Курс {currency}: нужно число, а пришло {kind}.")
    value = Decimal(str(rate))
    if not value.is_finite() or value <= 0:
        raise InvalidOperationError(f"Курс {currency}: нужно число больше нуля.")
    return value


class TransactionProcessor:
    """Исполняет транзакции над счетами банка."""

    MAX_ATTEMPTS = 3  # больше трёх попыток транзакция не получает
    RETRY_DELAY = timedelta(minutes=1)  # столько ждёт повторная попытка
    EXTERNAL_FEE_RATE = Decimal("0.01")  # комиссия за внешний перевод: 1%
    DEFAULT_RATES = {  # учебные курсы: сколько рублей стоит единица валюты
        Currency.RUB: Decimal("1"),
        Currency.USD: Decimal("90"),
        Currency.EUR: Decimal("100"),
        Currency.KZT: Decimal("0.2"),
        Currency.CNY: Decimal("12.5"),
    }

    def __init__(self, bank, *, rates=None):
        if not isinstance(bank, Bank):
            raise InvalidOperationError("Процессор: нужен объект Bank.")
        table = dict(self.DEFAULT_RATES)  # копия: таблицу класса не трогаем
        if rates is not None:
            if not isinstance(rates, dict):
                raise InvalidOperationError("Курсы: нужен словарь «валюта: курс».")
            for code, rate in rates.items():
                currency = BankAccount._validate_choice(code, Currency, "Валюта курса")
                table[currency] = validate_exchange_rate(rate, currency)
        self._bank = bank
        self._rates = table
        self._errors = []  # журнал ошибок

    @property
    def rates(self):
        return dict(self._rates)  # копия: курсы процессора снаружи не изменить

    def convert(self, amount, source, target):
        """Пересчитывает сумму из валюты source в валюту target."""
        value = BankAccount._validate_amount(amount, "Сумма для конвертации")
        source = BankAccount._validate_choice(source, Currency, "Исходная валюта")
        target = BankAccount._validate_choice(target, Currency, "Целевая валюта")
        if source is target:
            return value  # валюта та же: ни пересчёта, ни округления
        result = to_cents(value * self._rates[source] / self._rates[target])
        if result == 0:
            raise InvalidOperationError(
                f"Конвертация: {value} {source} — это меньше 0.01 {target}."
            )
        return result

    def calculate_fee(self, transaction):
        """Считает комиссию транзакции в её валюте. Ничего не меняет."""
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError("Комиссия: нужен объект Transaction.")
        if transaction.transaction_type is TransactionType.EXTERNAL_TRANSFER:
            return to_cents(transaction.amount * self.EXTERNAL_FEE_RATE)
        return Decimal("0.00")  # остальные типы процессор исполняет бесплатно

    def _find(self, account_id, role):
        """Находит в банке счёт отправителя или получателя."""
        if not self._bank.has_account(account_id):
            raise InvalidOperationError(
                f"Счёт {role} {mask(account_id)} в банке не найден."
            )
        return self._bank.get_account(account_id)

    @staticmethod
    def _check_open(account, role):
        """Замороженный и закрытый счёт в транзакции участвовать не может."""
        number = mask(account.account_id)
        if account.status is AccountStatus.FROZEN:
            raise AccountFrozenError(f"Счёт {role} {number} заморожен.")
        if account.status is AccountStatus.CLOSED:
            raise AccountClosedError(f"Счёт {role} {number} закрыт.")

    def _check_bank_rules(self, transaction):
        """Правила банка: ночной запрет и блокировка клиента. Банк сам помечает."""
        account_id = transaction.sender or transaction.recipient
        action = transaction.transaction_type.value
        self._bank.check_operation_time(action, account_id)  # ночью — отказ
        owner_id = self._bank.get_owner_id(account_id)
        if owner_id is not None:  # счёта нет в банке — об этом скажет _find
            self._bank.check_client_active(owner_id, action, account_id)

    def _execute(self, transaction):
        """Двигает деньги по счетам и возвращает комиссию. При отказе — ошибка."""
        self._check_bank_rules(transaction)  # первым отвечает банк
        sender = recipient = debit = credit = None
        if transaction.sender is not None:
            sender = self._find(transaction.sender, "отправителя")
        if transaction.transaction_type is TransactionType.EXTERNAL_TRANSFER:
            if self._bank.has_account(transaction.recipient):
                raise InvalidOperationError(
                    f"Внешний перевод: счёт {mask(transaction.recipient)} открыт "
                    "в этом банке. Для него нужен обычный перевод."
                )
        elif transaction.recipient is not None:
            recipient = self._find(transaction.recipient, "получателя")
        if sender is not None:
            self._check_open(sender, "отправителя")
        if recipient is not None:
            self._check_open(recipient, "получателя")

        fee = self.calculate_fee(transaction)
        currency = transaction.currency
        if sender is not None:  # обе суммы считаем до первого движения денег
            debit = self.convert(transaction.amount + fee, currency, sender.currency)
        if recipient is not None:
            credit = self.convert(transaction.amount, currency, recipient.currency)
        if sender is not None:
            sender.withdraw(debit)  # здесь работают правила типа счёта
        if recipient is not None:
            recipient.deposit(credit)
        return fee

    def process(self, transaction):
        """Делает одну попытку исполнить транзакцию и возвращает её статус."""
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError("Процессор: нужен объект Transaction.")
        attempt = transaction.start_attempt()  # завершённая транзакция откажет здесь
        now = self._bank.now()
        try:
            fee = self._execute(transaction)
        except AccountError as error:
            retry = isinstance(error, TEMPORARY) and attempt < self.MAX_ATTEMPTS
            self._errors.append({
                "time": now,
                "transaction_id": transaction.transaction_id,
                "attempt": attempt,
                "error": type(error).__name__,
                "reason": str(error),
                "final": not retry,
            })
            if not retry:
                transaction.fail(str(error), now)
        else:
            transaction.complete(fee, now)
        return transaction.status

    def get_errors(self, transaction_id=None):
        """Возвращает копию журнала ошибок: весь или по одной транзакции."""
        return [
            dict(record)
            for record in self._errors
            if transaction_id is None or record["transaction_id"] == transaction_id
        ]

    def process_queue(self, queue):
        """Исполняет все готовые транзакции очереди и возвращает их список."""
        if not isinstance(queue, TransactionQueue):
            raise InvalidOperationError("Процессор: нужен объект TransactionQueue.")
        now = self._bank.now()  # момент запуска: один на весь запуск
        handled = []
        transaction = queue.next_ready(now)
        while transaction is not None:
            self.process(transaction)
            if transaction.status is TransactionStatus.PENDING:
                # временный отказ: следующая попытка будет через RETRY_DELAY
                queue.reschedule(transaction.transaction_id, now + self.RETRY_DELAY)
            else:
                queue.remove(transaction.transaction_id)
            handled.append(transaction)
            transaction = queue.next_ready(now)
        return handled

"""Анализатор риска: оценивает транзакцию по четырём сигналам."""

from datetime import timedelta
from decimal import Decimal

from .bank import Bank
from .enums import Currency, RiskLevel, RiskSignal, TransactionType
from .errors import InvalidOperationError
from .processor import TransactionProcessor, validate_exchange_rate
from .transactions import Transaction

TRANSFERS = (TransactionType.TRANSFER, TransactionType.EXTERNAL_TRANSFER)


class RiskAnalyzer:
    """Оценивает риск транзакций одного банка и помнит свои оценки."""

    LARGE_AMOUNT = Decimal("50000.00")  # с этой суммы в рублях операция крупная
    FREQUENT_LIMIT = 3  # столько прежних операций за окно — это уже «часто»
    FREQUENT_WINDOW = timedelta(minutes=10)  # окно для счёта частых операций
    WEIGHTS = {  # баллы за каждый сигнал
        RiskSignal.LARGE_AMOUNT: 3,
        RiskSignal.FREQUENT_OPERATIONS: 2,
        RiskSignal.NEW_RECIPIENT: 1,
        RiskSignal.NIGHT_OPERATION: 2,
    }
    MEDIUM_SCORE = 2  # с этой суммы баллов риск средний
    HIGH_SCORE = 4  # с этой суммы баллов риск высокий

    def __init__(self, bank, *, rates=None):
        if not isinstance(bank, Bank):
            raise InvalidOperationError("Анализатор: нужен объект Bank.")
        if rates is None:
            rates = TransactionProcessor.DEFAULT_RATES  # те же курсы, что у процессора
        if not isinstance(rates, dict):
            raise InvalidOperationError("Курсы анализатора: нужен словарь.")
        table = {}
        for currency in Currency:
            if currency not in rates:
                raise InvalidOperationError(f"Курсы анализатора: нет курса {currency}.")
            table[currency] = validate_exchange_rate(rates[currency], currency)
        self._bank = bank
        self._rates = table
        self._assessments = {}  # ID транзакции -> оценка
        self._known = {}  # ID клиента -> множество знакомых ему получателей

    def _client_of(self, transaction):
        """Клиент операции: владелец счёта отправителя, у пополнения — получателя."""
        account_id = transaction.sender or transaction.recipient
        return self._bank.get_owner_id(account_id)

    def _is_frequent(self, client_id, now):
        """У клиента уже есть FREQUENT_LIMIT оценок за последние FREQUENT_WINDOW."""
        recent = [
            old for old in self._assessments.values()
            if old["client_id"] == client_id
            and now - old["time"] < self.FREQUENT_WINDOW
        ]
        return len(recent) >= self.FREQUENT_LIMIT

    def _is_new_recipient(self, transaction, client_id):
        """Перевод на чужой счёт, на который клиент ещё не переводил."""
        recipient = transaction.recipient
        if self._bank.get_owner_id(recipient) == client_id:
            return False  # свой счёт новым не бывает
        return recipient not in self._known.get(client_id, set())

    def _is_night(self, now):
        """Ночь по границам банка: от NIGHT_START включительно до NIGHT_END."""
        return self._bank.NIGHT_START <= now.time() < self._bank.NIGHT_END

    def _level(self, score):
        """Уровень риска по сумме баллов."""
        if score >= self.HIGH_SCORE:
            return RiskLevel.HIGH
        if score >= self.MEDIUM_SCORE:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def assess(self, transaction):
        """Оценивает транзакцию один раз и возвращает копию оценки."""
        if not isinstance(transaction, Transaction):
            raise InvalidOperationError("Анализатор: нужен объект Transaction.")
        name = transaction.transaction_id
        if name in self._assessments:
            return dict(self._assessments[name])  # оценка уже есть: не пересчитываем
        now = self._bank.now()
        client_id = self._client_of(transaction)
        amount_rub = transaction.amount * self._rates[transaction.currency]
        signals = []
        if amount_rub >= self.LARGE_AMOUNT:
            signals.append(RiskSignal.LARGE_AMOUNT)
        if client_id is not None and self._is_frequent(client_id, now):
            signals.append(RiskSignal.FREQUENT_OPERATIONS)
        new = (
            transaction.transaction_type in TRANSFERS
            and client_id is not None
            and self._is_new_recipient(transaction, client_id)
        )
        if new:
            signals.append(RiskSignal.NEW_RECIPIENT)
        if self._is_night(now):
            signals.append(RiskSignal.NIGHT_OPERATION)
        score = sum(self.WEIGHTS[signal] for signal in signals)
        level = self._level(score)
        if new and level is not RiskLevel.HIGH:
            # получатель становится знакомым, если перевод не опасный
            self._known.setdefault(client_id, set()).add(transaction.recipient)
        self._assessments[name] = {
            "transaction_id": name,
            "client_id": client_id,
            "time": now,
            "amount_rub": amount_rub,
            "signals": tuple(signals),
            "score": score,
            "level": level,
        }
        return dict(self._assessments[name])

    def get_assessments(self, client_id=None):
        """Копии оценок в порядке появления: все или одного клиента."""
        return [
            dict(assessment)
            for assessment in self._assessments.values()
            if client_id is None or assessment["client_id"] == client_id
        ]

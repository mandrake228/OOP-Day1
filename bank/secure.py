"""Защищённый процессор: оценка риска, блокировка опасного и журнал аудита."""

from .audit import AuditLog
from .enums import AuditEvent, AuditLevel, RiskLevel, RiskSignal, TransactionStatus
from .errors import DuplicateTransactionIdError, HighRiskError, InvalidOperationError
from .processor import TransactionProcessor
from .risk import RiskAnalyzer
from .transactions import Transaction

RISK_NAMES = {
    RiskLevel.LOW: "низкий",
    RiskLevel.MEDIUM: "средний",
    RiskLevel.HIGH: "высокий",
}
SIGNAL_NAMES = {
    RiskSignal.LARGE_AMOUNT: "крупная сумма",
    RiskSignal.FREQUENT_OPERATIONS: "частые операции",
    RiskSignal.NEW_RECIPIENT: "перевод на новый счёт",
    RiskSignal.NIGHT_OPERATION: "операция ночью",
}
AUDIT_LEVELS = {  # уровень риска -> уровень важности записи об оценке
    RiskLevel.LOW: AuditLevel.INFO,
    RiskLevel.MEDIUM: AuditLevel.WARNING,
    RiskLevel.HIGH: AuditLevel.CRITICAL,
}


def describe(assessment):
    """Уровень риска и сигналы по-русски: «средний (частые операции)»."""
    names = ", ".join(SIGNAL_NAMES[signal] for signal in assessment["signals"])
    return f"{RISK_NAMES[assessment['level']]} ({names or 'сигналов нет'})"


class SecureProcessor(TransactionProcessor):
    """Процессор дня 4 с оценкой риска перед движением денег и журналом аудита."""

    def __init__(self, bank, analyzer, audit, *, rates=None):
        super().__init__(bank, rates=rates)  # банк и курсы проверяет предок
        if not isinstance(analyzer, RiskAnalyzer):
            raise InvalidOperationError("Защищённый процессор: нужен RiskAnalyzer.")
        if not isinstance(audit, AuditLog):
            raise InvalidOperationError("Защищённый процессор: нужен AuditLog.")
        self._analyzer = analyzer
        self._audit = audit

    @property
    def analyzer(self):
        return self._analyzer

    @property
    def audit(self):
        return self._audit

    def _execute(self, transaction):
        """Расширяет шаг предка: сначала оценка риска, опасное — блокировать."""
        try:
            assessment = self._analyzer.assess(transaction)  # раньше проверок дня 4
        except DuplicateTransactionIdError:
            self._check_bank_rules(transaction)  # первым отвечает банк
            raise  # банк не отказал — отказ анализатора: ID занят
        if assessment["level"] is RiskLevel.HIGH:
            self._check_bank_rules(transaction)  # первым отвечает банк
            raise HighRiskError(
                f"Транзакция {transaction.transaction_id} заблокирована: "
                f"риск {describe(assessment)}."
            )
        return super()._execute(transaction)  # правила банка и все правила дня 4

    def _note(self, level, event, message, name, client_id, data):
        """Одна запись журнала аудита о транзакции. Время — по часам банка."""
        self._audit.add(
            self._bank.now(), level, event, message,
            client_id=client_id, transaction_id=name, data=data,
        )

    def _balances(self, transaction):
        """Балансы счетов транзакции в этом банке: номер -> баланс."""
        if not isinstance(transaction, Transaction):
            return {}  # ошибку вызова сообщит предок
        return {
            number: self._bank.get_account(number).balance
            for number in (transaction.sender, transaction.recipient)
            if self._bank.has_account(number)  # внешнего счёта в банке нет
        }

    def process(self, transaction):
        """Расширяет попытку предка: после неё записывает в аудит, что вышло."""
        before = self._balances(transaction)  # балансы до попытки
        status = super().process(transaction)  # ошибки вызова вылетят здесь
        name = transaction.transaction_id
        try:
            assessment = self._analyzer.assess(transaction)  # та же оценка, не новая
        except DuplicateTransactionIdError:
            assessment = None  # ID занят другой транзакцией: своей оценки у неё нет
        account_id = transaction.sender or transaction.recipient
        client_id = self._bank.get_owner_id(account_id)  # тот же клиент, что в оценке
        # об оценке пишем один раз, при первой попытке; нет оценки — нет и записи
        if assessment is not None and transaction.attempts == 1:
            risk = {
                "risk_level": assessment["level"],
                "score": assessment["score"],
                "signals": assessment["signals"],
            }
            level = AUDIT_LEVELS[assessment["level"]]
            message = f"Риск транзакции {name}: {describe(assessment)}."
            self._note(level, AuditEvent.RISK, message, name, client_id, risk)
        if status is TransactionStatus.COMPLETED:
            after = self._balances(transaction)
            moves = [  # отправитель, потом получатель; только изменившиеся
                {"account_id": number, "before": before[number],
                 "after": after[number]}
                for number in after if before[number] != after[number]
            ]
            done = {"attempt": transaction.attempts, "fee": transaction.fee,
                    "moves": moves}
            level, event = AuditLevel.INFO, AuditEvent.COMPLETED
            message = f"Транзакция {name} выполнена."
            self._note(level, event, message, name, client_id, done)
            return status
        error = self.get_errors(name)[-1]  # что записал предок об этой попытке
        if error["error"] == HighRiskError.__name__:
            level, event = AuditLevel.CRITICAL, AuditEvent.BLOCKED
        elif error["final"]:
            level, event = AuditLevel.ERROR, AuditEvent.REFUSED
        else:
            level, event = AuditLevel.WARNING, AuditEvent.REFUSED
        refusal = {key: error[key] for key in ("error", "attempt", "final")}
        self._note(level, event, error["reason"], name, client_id, refusal)
        return status

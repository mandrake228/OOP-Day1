"""Защищённый процессор: оценка риска, блокировка опасного и журнал аудита."""

from .audit import AuditLog
from .enums import AuditEvent, AuditLevel, RiskLevel, RiskSignal, TransactionStatus
from .errors import HighRiskError, InvalidOperationError
from .processor import TransactionProcessor
from .risk import RiskAnalyzer

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
        assessment = self._analyzer.assess(transaction)  # раньше всех проверок дня 4
        if assessment["level"] is RiskLevel.HIGH:
            # ночью банк откажет сам и пометит попытку, как любую ночную операцию
            account_id = transaction.sender or transaction.recipient
            action = transaction.transaction_type.value
            self._bank.check_operation_time(action, account_id)
            raise HighRiskError(
                f"Транзакция {transaction.transaction_id} заблокирована: "
                f"риск {describe(assessment)}."
            )
        return super()._execute(transaction)  # ночной запрет и все правила дня 4

    def _note(self, level, event, message, name, client_id, data):
        """Одна запись журнала аудита о транзакции. Время — по часам банка."""
        self._audit.add(
            self._bank.now(), level, event, message,
            client_id=client_id, transaction_id=name, data=data,
        )

    def process(self, transaction):
        """Расширяет попытку предка: после неё записывает в аудит, что вышло."""
        status = super().process(transaction)  # ошибки вызова вылетят здесь
        name = transaction.transaction_id
        assessment = self._analyzer.assess(transaction)  # та же оценка, не новая
        client_id = assessment["client_id"]
        if transaction.attempts == 1:  # об оценке пишем один раз: при первой попытке
            risk = {
                "risk_level": assessment["level"],
                "score": assessment["score"],
                "signals": assessment["signals"],
            }
            level = AUDIT_LEVELS[assessment["level"]]
            message = f"Риск транзакции {name}: {describe(assessment)}."
            self._note(level, AuditEvent.RISK, message, name, client_id, risk)
        if status is TransactionStatus.COMPLETED:
            done = {"attempt": transaction.attempts, "fee": transaction.fee}
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

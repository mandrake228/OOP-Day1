"""Отчёты аудита. Все три строятся только по журналу аудита."""

from .audit import AuditLog
from .enums import AuditEvent, AuditLevel, RiskLevel, RiskSignal
from .errors import InvalidOperationError

REFUSALS = (AuditEvent.REFUSED, AuditEvent.BLOCKED)  # события об отказах


class AuditReport:
    """Отчёты по журналу аудита. Ничего не меняют, каждый раз считают заново."""

    def __init__(self, audit):
        if not isinstance(audit, AuditLog):
            raise InvalidOperationError("Отчёт: нужен объект AuditLog.")
        self._audit = audit

    def _blocked(self, client_id=None):
        """ID транзакций, по которым в журнале есть запись о блокировке."""
        records = self._audit.filter(event=AuditEvent.BLOCKED, client_id=client_id)
        return {record["transaction_id"] for record in records}

    def suspicious_operations(self):
        """Операции со средним и высоким риском в порядке событий."""
        blocked = self._blocked()
        rows = []
        risky = self._audit.filter(event=AuditEvent.RISK, min_level=AuditLevel.WARNING)
        for record in risky:
            data = record["data"]
            rows.append({
                "time": record["time"],
                "transaction_id": record["transaction_id"],
                "client_id": record["client_id"],
                "risk_level": data["risk_level"],
                "score": data["score"],
                "signals": data["signals"],
                "blocked": record["transaction_id"] in blocked,
            })
        return rows

    def client_risk_profile(self, client_id):
        """Сводка по операциям клиента: сколько, с каким риском, какие сигналы."""
        if not isinstance(client_id, str):
            raise InvalidOperationError("Риск-профиль: ID клиента должен быть строкой.")
        by_level = {level.value: 0 for level in RiskLevel}
        signals = {signal.value: 0 for signal in RiskSignal}
        for record in self._audit.filter(event=AuditEvent.RISK, client_id=client_id):
            by_level[record["data"]["risk_level"].value] += 1
            for signal in record["data"]["signals"]:
                signals[signal.value] += 1
        level = RiskLevel.LOW
        for candidate in RiskLevel:  # от низкого к высокому: останется наивысший
            if by_level[candidate.value]:
                level = candidate
        return {
            "client_id": client_id,
            "operations": sum(by_level.values()),
            "by_level": by_level,
            "signals": signals,
            "blocked": len(self._blocked(client_id)),
            "level": level,
        }

    def error_statistics(self):
        """Отказы при исполнении: всего, временные, окончательные, блокировки."""
        records = [r for r in self._audit.filter() if r["event"] in REFUSALS]
        by_error = {}
        for record in records:
            name = record["data"]["error"]
            by_error[name] = by_error.get(name, 0) + 1
        final = sum(1 for record in records if record["data"]["final"])
        return {
            "total": len(records),
            "temporary": len(records) - final,
            "final": final,
            "blocked": len(self._blocked()),
            "by_error": by_error,
        }

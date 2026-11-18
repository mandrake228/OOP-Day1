"""Банковская система: банк, очередь, анализатор, аудит и процессор вместе."""

from decimal import Decimal

from .accounts import BankAccount
from .advanced import to_cents
from .audit import AuditLog
from .bank import Bank
from .enums import (
    AuditEvent,
    AuditLevel,
    Currency,
    Priority,
    RiskLevel,
    TransactionStatus,
    TransactionType,
)
from .errors import InvalidOperationError
from .queues import TransactionQueue
from .reports import AuditReport
from .risk import RiskAnalyzer
from .secure import SecureProcessor
from .transactions import Transaction, mask

TYPE_NAMES = {  # тип транзакции по-русски: для сообщений журнала
    TransactionType.DEPOSIT: "пополнение",
    TransactionType.WITHDRAWAL: "снятие",
    TransactionType.TRANSFER: "перевод",
    TransactionType.EXTERNAL_TRANSFER: "внешний перевод",
}


class BankSystem:
    """Вся система банка за одной дверью: приём, исполнение, кабинет, отчёты."""

    ID_PREFIX = "T"  # ID транзакций системы: T0001, T0002, ...

    def __init__(self, bank, *, audit_file=None):
        if not isinstance(bank, Bank):
            raise InvalidOperationError("Система: нужен объект Bank.")
        self._bank = bank
        self._audit = AuditLog(file_path=audit_file)
        self._analyzer = RiskAnalyzer(bank)  # курсы — те же, что у процессора
        self._processor = SecureProcessor(bank, self._analyzer, self._audit)
        self._queue = TransactionQueue()
        self._report = AuditReport(self._audit)
        self._transactions = {}  # ID -> транзакция, её приоритет и время исполнения

    @property
    def bank(self):
        return self._bank

    @property
    def audit(self):
        return self._audit

    @property
    def report(self):
        return self._report

    def _client_of(self, transaction):
        """Клиент операции: владелец счёта отправителя, у пополнения — получателя."""
        return self._bank.get_owner_id(transaction.sender or transaction.recipient)

    def _note(self, event, message, transaction, data):
        """Обычная запись журнала аудита о транзакции, время — по часам банка."""
        self._audit.add(
            self._bank.now(), AuditLevel.INFO, event, message,
            client_id=self._client_of(transaction),
            transaction_id=transaction.transaction_id, data=data,
        )

    def submit(
        self, transaction_type, amount, *, currency=Currency.RUB, sender=None,
        recipient=None, priority=Priority.NORMAL, run_at=None,
    ):
        """Создаёт транзакцию со своим ID, ставит в очередь, пишет об этом в аудит."""
        name = f"{self.ID_PREFIX}{len(self._transactions) + 1:04d}"  # T0001, T0002
        transaction = Transaction(
            transaction_type, amount, currency=currency, sender=sender,
            recipient=recipient, transaction_id=name, created_at=self._bank.now(),
        )
        self._queue.add(transaction, priority=priority, run_at=run_at)
        entries = self._queue.get_entries()  # копии записей очереди
        entry = next(e for e in entries if e["transaction"] is transaction)
        self._transactions[name] = {
            "transaction": transaction,
            "priority": entry["priority"],  # элемент Priority: проверила очередь
            "run_at": entry["run_at"],
        }
        kind = TYPE_NAMES[transaction.transaction_type]
        when = ""
        if entry["run_at"] is not None:
            when = f", не раньше {entry['run_at']:%d.%m %H:%M}"
        message = (
            f"Транзакция {name} принята в очередь: {kind} {transaction.amount} "
            f"{transaction.currency}, приоритет {entry['priority']}{when}."
        )
        data = {"priority": entry["priority"], "run_at": entry["run_at"]}
        self._note(AuditEvent.QUEUED, message, transaction, data)
        return name

    def _info(self, name):
        """Данные транзакции: её собственные, клиент, приём и оценка риска."""
        entry = self._transactions[name]
        transaction = entry["transaction"]
        info = transaction.get_transaction_info()  # новый словарь при каждом вызове
        info["client_id"] = self._client_of(transaction)
        info["priority"] = entry["priority"]
        info["run_at"] = entry["run_at"]
        info["risk"] = None  # отменённую до первой попытки анализатор не видел
        for assessment in self._analyzer.get_assessments():
            if assessment["transaction_id"] == name:
                info["risk"] = {
                    key: assessment[key] for key in ("level", "score", "signals")
                }
        return info

    def get_transaction(self, transaction_id):
        """Данные одной транзакции системы по её ID."""
        known = isinstance(transaction_id, str) and transaction_id in self._transactions
        if not known:
            raise InvalidOperationError(
                f"Транзакции с ID «{transaction_id}» в системе нет."
            )
        return self._info(transaction_id)

    def get_transactions(self, *, status=None, client_id=None):
        """Данные транзакций по порядку: все, одного статуса или одного клиента."""
        if status is not None:
            status = BankAccount._validate_choice(status, TransactionStatus, "Статус")
        if client_id is not None and not isinstance(client_id, str):
            raise InvalidOperationError("Отбор: ID клиента должен быть строкой.")
        found = []
        for name, entry in self._transactions.items():
            transaction = entry["transaction"]
            if status is not None and transaction.status is not status:
                continue
            owners = {
                self._bank.get_owner_id(transaction.sender),
                self._bank.get_owner_id(transaction.recipient),
            }
            if client_id is not None and client_id not in owners:
                continue  # ни один из двух счетов не принадлежит клиенту
            found.append(self._info(name))
        return found

    def cancel(self, transaction_id):
        """Отменяет ожидающую транзакцию, пишет об этом в аудит, возвращает данные."""
        transaction = self._queue.cancel(transaction_id, at=self._bank.now())
        message = f"Транзакция {transaction.transaction_id} отменена до исполнения."
        self._note(AuditEvent.CANCELLED, message, transaction, {})
        return self.get_transaction(transaction.transaction_id)

    def run(self):
        """Исполняет все готовые транзакции очереди и возвращает их ID по порядку."""
        handled = self._processor.process_queue(self._queue)
        return [transaction.transaction_id for transaction in handled]

    def get_queue(self):
        """Что ждёт в очереди, в порядке обслуживания. Самих транзакций не отдаёт."""
        waiting = []
        for entry in self._queue.get_entries():
            transaction = entry["transaction"]
            waiting.append({
                "transaction_id": transaction.transaction_id,
                "transaction_type": transaction.transaction_type.value,
                "amount": transaction.amount,
                "currency": transaction.currency.value,
                "priority": entry["priority"],
                "run_at": entry["run_at"],
            })
        return waiting

    def _to_rub(self, amount, currency):
        """Сумма в рублях по курсам процессора, с округлением до копеек."""
        rates = self._processor.rates  # копия таблицы курсов процессора
        return to_cents(amount * rates[currency] / rates[Currency.RUB])

    def total_balance(self):
        """Общий баланс: незакрытые счета по каждой валюте и всего в рублях."""
        by_currency = {}
        total = Decimal("0.00")
        for currency in Currency:
            amount = self._bank.get_total_balance(currency=currency)  # правило дня 3
            by_currency[currency.value] = amount
            total += self._to_rub(amount, currency)
        return {"by_currency": by_currency, "total_rub": total}

    def _client_total_rub(self, client_id):
        """Сумма на незакрытых счетах клиента в рублях: каждая валюта пересчитана."""
        total = Decimal("0.00")
        for currency in Currency:
            amount = self._bank.get_total_balance(
                currency=currency, client_id=client_id
            )
            total += self._to_rub(amount, currency)
        return total

    def top_clients(self, count=3):
        """Первые count клиентов по сумме на счетах в рублях, с пересчётом валют."""
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise InvalidOperationError("Топ клиентов: нужно целое число от 1.")
        rows = []
        for row in self._bank.get_clients_ranking():  # все клиенты банка
            rows.append({
                "client_id": row["client_id"],
                "full_name": row["full_name"],
                "total_rub": self._client_total_rub(row["client_id"]),
            })
        rows.sort(key=lambda row: row["total_rub"], reverse=True)  # равные — на месте
        top = rows[:count]
        for place, row in enumerate(top, start=1):
            row["place"] = place
        return top

    def transaction_statistics(self):
        """Статистика транзакций системы: статусы, типы, риск, оборот и комиссии."""
        by_status = {status.value: 0 for status in TransactionStatus}
        by_type = {kind.value: 0 for kind in TransactionType}
        by_risk = {level.value: 0 for level in RiskLevel}
        by_risk["not_assessed"] = 0
        completed = fees = Decimal("0.00")
        for name in self._transactions:
            info = self._info(name)
            by_status[info["status"]] += 1
            by_type[info["transaction_type"]] += 1
            if info["risk"] is None:
                by_risk["not_assessed"] += 1
            else:
                by_risk[info["risk"]["level"].value] += 1
            if info["status"] == TransactionStatus.COMPLETED:
                currency = Currency(info["currency"])
                completed += self._to_rub(info["amount"], currency)
                fees += self._to_rub(info["fee"], currency)
        return {
            "total": len(self._transactions),
            "by_status": by_status,
            "by_type": by_type,
            "by_risk": by_risk,
            "completed_rub": completed,
            "fees_rub": fees,
        }

    def login(self, client_id, password):
        """Вход клиента в кабинет. Правила входа — банка, как в третьем дне."""
        return ClientSession(self, client_id, password)


class ClientSession:
    """Кабинет клиента. Создать его — значит войти по ID и паролю."""

    def __init__(self, system, client_id, password):
        if not isinstance(system, BankSystem):
            raise InvalidOperationError("Кабинет: нужен объект BankSystem.")
        system.bank.authenticate_client(client_id, password)  # ночь, пароль, блокировка
        self._system = system
        self._client_id = client_id

    @property
    def client_id(self):
        return self._client_id

    def _check(self, action):
        """Если клиента заблокировали после входа, банк откажет и пометит попытку."""
        self._system.bank.check_client_active(self._client_id, action)

    def _accounts(self):
        """Счета клиента в порядке открытия."""
        return self._system.bank.search_accounts(client_id=self._client_id)

    def accounts(self):
        """Все счета клиента: тип, номер, владелец, статус, баланс, валюта."""
        self._check("view_accounts")
        return [account.get_account_info() for account in self._accounts()]

    def history(self, account_id=None):
        """Операции по счетам клиента по порядку: направление, чужие номера скрыты."""
        self._check("view_history")
        mine = {account.account_id for account in self._accounts()}
        if account_id is not None and (
            not isinstance(account_id, str) or account_id not in mine
        ):
            raise InvalidOperationError("История: такого счёта у вас нет.")
        chosen = mine if account_id is None else {account_id}
        rows = []
        for info in self._system.get_transactions(client_id=self._client_id):
            out, came = info["sender"] in chosen, info["recipient"] in chosen
            if not (out or came):
                continue  # операция другого счёта клиента
            info["direction"] = "own" if out and came else ("out" if out else "in")
            for key in ("sender", "recipient"):
                if info[key] is not None and info[key] not in mine:
                    info[key] = mask(info[key])  # чужой номер: ****1234
            rows.append(info)
        return rows

    def suspicious_operations(self):
        """Операции клиента со средним и высоким риском, с отметкой о блокировке."""
        self._check("view_suspicious")
        return [
            row for row in self._system.report.suspicious_operations()
            if row["client_id"] == self._client_id
        ]

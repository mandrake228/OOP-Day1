"""Продвинутые типы счетов: сберегательный, премиальный, инвестиционный."""

from decimal import ROUND_HALF_UP, Decimal

from .accounts import CENT, BankAccount
from .enums import AssetType
from .errors import InsufficientFundsError, InvalidOperationError


def to_cents(value):
    """Округляет сумму до копеек: половина копейки и больше — вверх."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def validate_rate(rate, label):
    """Проверяет ставку. Ставка — это доля: 10% записывается как 0.10."""
    if isinstance(rate, bool) or not isinstance(rate, (int, float, Decimal)):
        kind = type(rate).__name__
        raise InvalidOperationError(f"{label}: нужно число, а пришло {kind}.")
    value = Decimal(str(rate))
    if not value.is_finite() or not 0 <= value <= 1:
        raise InvalidOperationError(
            f"{label}: ставка — это доля от 0 до 1. Например, 10% — это 0.10."
        )
    return value


class SavingsAccount(BankAccount):
    """Сберегательный счёт: минимальный остаток и проценты раз в месяц."""

    def __init__(self, *args, min_balance=0, monthly_rate=0, **kwargs):
        super().__init__(*args, **kwargs)
        self._min_balance = self._validate_amount(
            min_balance, "Минимальный остаток", allow_zero=True
        )
        self._monthly_rate = validate_rate(monthly_rate, "Месячная ставка")
        if self._balance < self._min_balance:
            raise InvalidOperationError(
                f"Начальный баланс {self._balance} меньше "
                f"минимального остатка {self._min_balance}."
            )

    @property
    def min_balance(self):
        return self._min_balance

    @property
    def monthly_rate(self):
        return self._monthly_rate


    def withdraw(self, amount):
        value = self._start_withdrawal(amount)
        available = self._balance - self._min_balance
        if value > available:
            raise InsufficientFundsError(
                f"Счёт {self._masked_id()}: недостаточно средств. "
                f"Запрошено {value} {self._currency}, доступно {available} "
                f"{self._currency} сверх минимального остатка {self._min_balance}."
            )
        self._balance -= value
        return self._balance

    def apply_monthly_interest(self):
        """Начисляет проценты за один месяц и возвращает их сумму."""
        self._check_status()
        interest = to_cents(self._balance * self._monthly_rate)
        self._balance += interest
        return interest

    def get_account_info(self):
        info = super().get_account_info()
        info["min_balance"] = self._min_balance
        info["monthly_rate"] = self._monthly_rate
        return info

    def __str__(self):
        return (
            f"{super().__str__()} | мин. остаток {self._min_balance:.2f} | "
            f"{self._monthly_rate * 100:.2f}% в месяц"
        )


class PremiumAccount(BankAccount):
    """Премиальный счёт: большой лимит, овердрафт и комиссия за снятие."""

    WITHDRAWAL_LIMIT = Decimal("1000000.00")  # в десять раз больше обычного

    def __init__(self, *args, overdraft_limit=0, fee=0, **kwargs):
        super().__init__(*args, **kwargs)
        self._overdraft_limit = self._validate_amount(
            overdraft_limit, "Лимит овердрафта", allow_zero=True
        )
        self._fee = self._validate_amount(fee, "Комиссия", allow_zero=True)

    @property
    def overdraft_limit(self):
        return self._overdraft_limit

    @property
    def fee(self):
        return self._fee

    def withdraw(self, amount):
        value = self._start_withdrawal(amount)
        total = value + self._fee
        available = self._balance + self._overdraft_limit
        if total > available:
            raise InsufficientFundsError(
                f"Счёт {self._masked_id()}: недостаточно средств. "
                f"Запрошено {value} и комиссия {self._fee} {self._currency}, "
                f"доступно {available} {self._currency} с учётом овердрафта."
            )
        self._balance -= total
        return self._balance

    def get_account_info(self):
        info = super().get_account_info()
        info["overdraft_limit"] = self._overdraft_limit
        info["fee"] = self._fee
        info["withdrawal_limit"] = self.WITHDRAWAL_LIMIT
        return info

    def __str__(self):
        return (
            f"{super().__str__()} | овердрафт до {self._overdraft_limit:.2f} | "
            f"комиссия {self._fee:.2f}"
        )


class InvestmentAccount(BankAccount):
    """Инвестиционный счёт: часть денег вложена в активы и не снимается."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._portfolio = {asset: Decimal("0.00") for asset in AssetType}

    @property
    def portfolio(self):
        return dict(self._portfolio)  # копия: снаружи портфель не изменить

    def _invested(self):
        return sum(self._portfolio.values())

    def _available(self):
        return self._balance - self._invested()

    def invest(self, asset_type, amount):
        """Вкладывает свободные деньги в актив. Возвращает сумму в этом активе."""
        asset = self._validate_choice(asset_type, AssetType, "Тип актива")
        value = self._validate_amount(amount, f"Вложение со счёта {self._masked_id()}")
        self._check_status()
        available = self._available()
        if value > available:
            raise InsufficientFundsError(
                f"Счёт {self._masked_id()}: недостаточно свободных средств. "
                f"Запрошено {value} {self._currency}, "
                f"свободно {available} {self._currency}."
            )
        self._portfolio[asset] += value
        return self._portfolio[asset]

    def withdraw(self, amount):
        value = self._start_withdrawal(amount)
        available = self._available()
        if value > available:
            raise InsufficientFundsError(
                f"Счёт {self._masked_id()}: недостаточно свободных средств. "
                f"Запрошено {value} {self._currency}, свободно {available} "
                f"{self._currency}, в портфеле {self._invested()} {self._currency}."
            )
        self._balance -= value
        return self._balance

    def project_yearly_growth(self, growth_rates):
        """Считает ожидаемый прирост портфеля за год. На счёте ничего не меняет."""
        if not isinstance(growth_rates, dict):
            raise InvalidOperationError(
                "Ставки прироста: нужен словарь «тип актива: ставка»."
            )
        rates = {}
        for key, rate in growth_rates.items():
            asset = self._validate_choice(key, AssetType, "Тип актива")
            rates[asset] = validate_rate(rate, f"Годовая ставка для {asset}")
        growth = Decimal("0")
        for asset, amount in self._portfolio.items():
            if amount == 0:
                continue
            if asset not in rates:
                raise InvalidOperationError(f"Ставки прироста: нет ставки для {asset}.")
            growth += amount * rates[asset]
        return to_cents(growth)

    def get_account_info(self):
        info = super().get_account_info()
        info["portfolio"] = {
            asset.value: amount for asset, amount in self._portfolio.items()
        }
        info["invested"] = self._invested()
        info["available"] = self._available()
        return info

    def __str__(self):
        return f"{super().__str__()} | в портфеле {self._invested():.2f}"

"""Демонстрация дня 3: клиенты, банк и защита. Запуск: python demo_day3.py"""

import sys
from datetime import date, datetime
from decimal import Decimal

from bank import (
    AccountClosedError,
    AccountFrozenError,
    AuthenticationError,
    Bank,
    BankAccount,
    Client,
    ClientBlockedError,
    ClientStatus,
    InvalidOperationError,
    InvestmentAccount,
    NightOperationError,
    PremiumAccount,
    SavingsAccount,
)
from demo import check, expect_error, problems, section

TODAY = date(2026, 11, 16)  # «сегодня» демонстрации: от дня запуска она не зависит
PASSWORD = "sezam-otkroysya"  # пароль всех клиентов демонстрации
WRONG = "ne-tot-parol"  # неверный пароль


class DemoClock:
    """Часы демонстрации: показывают то время, которое им поставили."""

    def __init__(self):
        self.moment = datetime(2026, 11, 16, 12, 0)  # полдень: банк работает

    def set(self, hour, minute=0, second=0):
        self.moment = self.moment.replace(hour=hour, minute=minute, second=second)

    def now(self):
        return self.moment


def make_client(client_id, full_name, **contacts):
    """Создаёт взрослого клиента с заданным ID."""
    return Client(
        full_name, date(1990, 1, 1), client_id=client_id, today=TODAY, **contacts
    )


class Stand:
    """Стенд для раздела: банк со своими часами, пять клиентов и пять счетов."""

    def __init__(self):
        self.clock = DemoClock()
        self.bank = Bank(clock=self.clock.now)
        join = self.join
        self.anna = join("anna", "Смирнова Анна Сергеевна", phone="+7 900 000-00-01")
        self.petr = join("petr", "Иванов Пётр Алексеевич", email="petr@example.com")
        self.li = join("liwei", "Ли Вэй", email="li.wei@example.org")
        self.maria = join("maria", "Орлова Мария Игоревна", phone="8 900 000 00 04")
        self.oleg = join("oleg", "Титов Олег Николаевич", phone="+7 900 000-00-05")
        open_account = self.bank.open_account
        self.savings = open_account(
            "anna", SavingsAccount, account_id="40817810000000001001",
            balance=10000, min_balance=1000, monthly_rate=0.015,
        )
        self.usd = open_account(
            "anna", account_id="40817840000000001002", balance=300, currency="USD"
        )
        self.premium = open_account(
            "petr", PremiumAccount, account_id="40817810000000002001",
            balance=1000, overdraft_limit=5000, fee=50,
        )
        self.invest = open_account(
            "liwei", InvestmentAccount, account_id="40817810000000003001", balance=12000
        )
        self.euro = open_account(
            "maria", account_id="40817978000000004001", balance=500, currency="EUR"
        )

    def join(self, client_id, full_name, **contacts):
        """Создаёт клиента, регистрирует его в банке и возвращает."""
        client = make_client(client_id, full_name, **contacts)
        self.bank.add_client(client, PASSWORD)
        return client


def show_clients():
    section("1. Клиенты")
    anna = Client(
        "Смирнова Анна Сергеевна", date(1990, 5, 17), client_id="anna",
        phone="+7 (900) 000-00-01", email="Anna@Example.com", today=TODAY,
    )
    petr = Client("Иванов Пётр Алексеевич", date(1985, 3, 2), phone="8 900 000 00 02")
    li = Client("Ли Вэй", date(2000, 12, 31), email="li.wei@example.org")
    for client in (anna, petr, li):
        print(f"  {client}")
    print("  Сведения о первом клиенте:")
    for key, value in anna.get_client_info().items():
        print(f"    {key}: {value}")
    check("ID без указания сгенерирован: 8 символов", len(petr.client_id) == 8)
    check("у двух клиентов без ID они разные", petr.client_id != li.client_id)
    contacts = anna.contacts
    check("телефон хранится без пробелов и скобок", contacts["phone"] == "+79000000001")
    check("почта хранится строчными буквами", contacts["email"] == "anna@example.com")
    text = f"{anna} {li}"
    hidden = "+7" not in text and "@" not in text
    check("в строке о клиенте нет телефона и почты", hidden)

    born = date(2008, 11, 16)  # этому клиенту 18 исполняется ровно в день проверки
    adult = Client("Новиков Юрий Павлович", born, email="yuri@example.com", today=TODAY)
    check("18 лет исполнилось в день проверки: клиент создан", adult.status == "active")
    late = date(2008, 11, 17)  # а этому 18 исполнится только завтра
    expect_error(
        "18 лет исполнится завтра", InvalidOperationError,
        lambda: Client("Юный Клиент", late, email="young@example.com", today=TODAY),
    )
    leap = date(2008, 2, 29)
    expect_error(
        "родился 29 февраля, проверка 28.02.2026: ещё 17", InvalidOperationError,
        lambda: Client("Клиент", leap, email="l@example.com", today=date(2026, 2, 28)),
    )
    spring = Client("Клиент", leap, email="l@example.com", today=date(2026, 3, 1))
    check("родился 29 февраля, проверка 01.03.2026: уже 18", spring.birth_date == leap)

    day, phone = date(1990, 5, 17), "+79000000001"
    bad_clients = [
        ("пустое ФИО", lambda: Client("   ", day, phone=phone)),
        ("дата рождения строкой", lambda: Client("Иван", "17.05.1990", phone=phone)),
        ("нет ни телефона, ни почты", lambda: Client("Иван", day)),
        ("телефон с буквами", lambda: Client("Иван", day, phone="+7 900 abc")),
        ("почта без зоны", lambda: Client("Иван", day, email="ivan@example")),
        ("короткий ID", lambda: Client("Иван", day, client_id="12", phone=phone)),
    ]
    for description, action in bad_clients:
        expect_error(description, InvalidOperationError, action)

    expect_error("присваивание ФИО извне", AttributeError,
                 lambda: setattr(anna, "full_name", "Другое Имя"))
    anna.account_ids.append("чужой номер")
    anna.contacts["phone"] = "000"
    untouched = anna.account_ids == [] and anna.contacts["phone"] == "+79000000001"
    check("список счетов и контакты отдаются копиями", untouched)


def show_registration():
    section("2. Регистрация в банке")
    bank = Bank(clock=DemoClock().now)
    anna = make_client("anna", "Смирнова Анна Сергеевна", phone="+7 900 000-00-01")
    petr = make_client("petr", "Иванов Пётр Алексеевич", email="petr@example.com")
    anna_id = bank.add_client(anna, PASSWORD)
    check("регистрация возвращает ID клиента", anna_id == "anna")
    bank.add_client(petr, PASSWORD)
    print(f"  Зарегистрированы: {anna.full_name} и {petr.full_name}")

    twin = make_client("anna", "Другая Анна", phone="+7 900 000-00-07")
    expect_error("ID уже занят", InvalidOperationError,
                 lambda: bank.add_client(twin, PASSWORD))
    expect_error("вместо клиента строка", InvalidOperationError,
                 lambda: bank.add_client("Анна", PASSWORD))
    guest = make_client("guest", "Гость Иван Иванович", phone="+7 900 000-00-08")
    for bad in ["12345", " " * 8, 12345678]:
        expect_error(f"пароль {bad!r}", InvalidOperationError,
                     lambda: bank.add_client(guest, bad))
    check("после отказов в банке два клиента", len(bank.get_clients_ranking()) == 2)
    text = f"{anna} {anna.get_client_info()}"
    check("пароля нет ни в строке о клиенте, ни в сведениях", PASSWORD not in text)

    plain = Bank()  # банк без своих часов живёт по времени компьютера
    try:
        registered = plain.add_client(guest, PASSWORD) == "guest"
    except NightOperationError:
        registered = False  # демонстрацию запустили ночью: отказ тоже верный исход
    marks = len(plain.get_suspicious_actions())
    check(
        "банк без своих часов: клиент принят, а ночью отказ записан в журнал",
        marks == (0 if registered else 1),
    )


def show_accounts():
    section("3. Открытие счетов")
    bank = Bank(clock=DemoClock().now)
    anna = make_client("anna", "Смирнова Анна Сергеевна", phone="+7 900 000-00-01")
    petr = make_client("petr", "Иванов Пётр Алексеевич", email="petr@example.com")
    for client in (anna, petr):
        bank.add_client(client, PASSWORD)
    opened = [
        bank.open_account(
            "anna", SavingsAccount, account_id="40817810000000001001",
            balance=10000, min_balance=1000, monthly_rate=0.015,
        ),
        bank.open_account("anna", balance=300, currency="USD"),
        bank.open_account(
            "petr", PremiumAccount, account_id="40817810000000002001",
            balance=1000, overdraft_limit=5000, fee=50,
        ),
        bank.open_account(
            "petr", InvestmentAccount, account_id="40817978000000002002",
            balance=500, currency="EUR",
        ),
    ]
    for account in opened:
        print(f"  {account}")
    for client in (anna, petr):
        print(f"  {client}")
    numbers = [account.account_id for account in opened]
    check("владелец счёта — ФИО клиента", opened[0].owner == anna.full_name)
    check("все счета открыты активными", all(a.status == "active" for a in opened))
    check("номера счетов записаны у клиентов", anna.account_ids == numbers[:2])
    check("номер без указания сгенерирован: 8 символов", len(numbers[1]) == 8)
    check("открыты все четыре типа счетов", len({type(a) for a in opened}) == 4)

    refusals = [
        ("неизвестный клиент", lambda: bank.open_account("nobody")),
        ("тип счёта строкой", lambda: bank.open_account("anna", "savings")),
        ("номер уже занят", lambda: bank.open_account("petr", account_id=numbers[0])),
        (
            "баланс ниже минимального остатка",
            lambda: bank.open_account(
                "anna", SavingsAccount, balance=100, min_balance=500
            ),
        ),
    ]
    for description, action in refusals:
        expect_error(description, InvalidOperationError, action)
    expect_error("статус в параметрах счёта: его задаёт банк", TypeError,
                 lambda: bank.open_account("anna", status="frozen"))
    same = len(bank.search_accounts()) == 4 and len(anna.account_ids) == 2
    check("после отказов счетов по-прежнему четыре", same)


def show_login():
    section("4. Вход и блокировка")
    stand = Stand()
    bank, anna = stand.bank, stand.anna

    def login(client_id, password):
        return lambda: bank.authenticate_client(client_id, password)

    check("верный пароль: вход выполнен", bank.authenticate_client("anna", PASSWORD))
    expect_error("неверный пароль", AuthenticationError, login("anna", WRONG))
    expect_error("неизвестный ID", AuthenticationError, login("nobody", PASSWORD))
    expect_error("вторая ошибка подряд", AuthenticationError, login("anna", WRONG))
    check("вход обнуляет счёт ошибок", bank.authenticate_client("anna", PASSWORD))
    for attempt in (1, 2):
        expect_error(f"снова ошибка, попытка {attempt}", AuthenticationError,
                     login("anna", WRONG))
    check("после двух ошибок подряд клиент ещё активен", anna.status == "active")
    expect_error("третья ошибка подряд", ClientBlockedError, login("anna", WRONG))
    check("клиент заблокирован", anna.status is ClientStatus.BLOCKED)
    print(f"  {anna}")

    expect_error("верный пароль после блокировки", ClientBlockedError,
                 login("anna", PASSWORD))
    expect_error("открытие счёта заблокированному клиенту", ClientBlockedError,
                 lambda: bank.open_account("anna"))
    expect_error("закрытие счёта заблокированного клиента", ClientBlockedError,
                 lambda: bank.close_account(stand.usd.account_id))
    frozen = bank.freeze_account(stand.savings.account_id)
    check("заморозить счёт заблокированного клиента банк может", frozen == "frozen")

    for attempt in (1, 2):
        expect_error(f"Пётр ошибся, попытка {attempt}", AuthenticationError,
                     login("petr", WRONG))
    check("ошибки Анны Петру не мешают", bank.authenticate_client("petr", PASSWORD))


def show_freezing():
    section("5. Заморозка, разморозка, закрытие")
    stand = Stand()
    bank, savings, premium = stand.bank, stand.savings, stand.premium
    number = savings.account_id

    check("заморозка возвращает новый статус", bank.freeze_account(number) == "frozen")
    print(f"  {savings}")
    expect_error("пополнение замороженного счёта", AccountFrozenError,
                 lambda: savings.deposit(100))
    expect_error("снятие с замороженного счёта", AccountFrozenError,
                 lambda: savings.withdraw(100))
    expect_error("повторная заморозка", AccountFrozenError,
                 lambda: bank.freeze_account(number))
    expect_error("закрытие замороженного счёта", AccountFrozenError,
                 lambda: bank.close_account(number))
    check("после разморозки счёт активен", bank.unfreeze_account(number) == "active")
    check("баланс после заморозки прежний", savings.balance == 10000)
    check("после разморозки снятие проходит", savings.withdraw(1000) == 9000)
    expect_error("разморозка активного счёта", InvalidOperationError,
                 lambda: bank.unfreeze_account(number))

    premium.withdraw(1200)  # 1000 - 1200 - комиссия 50 = -250: счёт ушёл в долг
    print(f"  {premium}")
    expect_error("закрытие счёта с долгом", InvalidOperationError,
                 lambda: bank.close_account(premium.account_id))

    check("закрытие возвращает новый статус", bank.close_account(number) == "closed")
    print(f"  {savings}")
    expect_error("пополнение закрытого счёта", AccountClosedError,
                 lambda: savings.deposit(100))
    again = [
        ("повторное закрытие", bank.close_account),
        ("заморозка закрытого счёта", bank.freeze_account),
        ("разморозка закрытого счёта", bank.unfreeze_account),
    ]
    for description, method in again:
        expect_error(description, AccountClosedError, lambda: method(number))
    check("закрытие не тронуло баланс", savings.balance == 9000)
    check("закрытый счёт остался в списке клиента", number in stand.anna.account_ids)
    expect_error("неизвестный номер счёта", InvalidOperationError,
                 lambda: bank.freeze_account("0000"))


def show_night():
    section("6. Ночной запрет")
    stand = Stand()
    bank, clock = stand.bank, stand.clock
    number = stand.savings.account_id

    clock.set(23, 59, 59)
    check("23:59:59 — счёт открывается", bank.open_account("oleg").status == "active")
    clock.set(0, 0)
    expect_error("00:00:00 — открытие счёта", NightOperationError,
                 lambda: bank.open_account("oleg"))

    clock.set(2, 30)
    guest = make_client("guest", "Гость Иван Иванович", phone="+7 900 000-00-08")
    night_calls = [
        ("регистрация клиента", lambda: bank.add_client(guest, PASSWORD)),
        ("открытие счёта", lambda: bank.open_account("anna")),
        ("закрытие счёта", lambda: bank.close_account(stand.usd.account_id)),
        ("вход с верным паролем", lambda: bank.authenticate_client("anna", PASSWORD)),
    ]
    for description, action in night_calls:
        expect_error(f"02:30 — {description}", NightOperationError, action)
    check("02:30 — заморозка работает", bank.freeze_account(number) == "frozen")
    expect_error("02:30 — разморозка", NightOperationError,
                 lambda: bank.unfreeze_account(number))
    for attempt in (1, 2, 3):
        expect_error(f"02:30 — неверный пароль, попытка {attempt}", NightOperationError,
                     lambda: bank.authenticate_client("anna", WRONG))
    reads = (
        len(bank.search_accounts()) == 6
        and bank.get_total_balance() == 23000
        and len(bank.get_clients_ranking()) == 5
    )
    check("02:30 — поиск, сумма и рейтинг работают", reads)

    clock.set(4, 59, 59)
    expect_error("04:59:59 — разморозка", NightOperationError,
                 lambda: bank.unfreeze_account(number))
    clock.set(5, 0)
    check("05:00:00 — разморозка проходит", bank.unfreeze_account(number) == "active")
    check(
        "три ночные ошибки не заблокировали клиента: утром он входит",
        bank.authenticate_client("anna", PASSWORD),
    )


def show_search():
    section("7. Поиск счетов")
    stand = Stand()
    bank = stand.bank
    bank.freeze_account(stand.premium.account_id)
    print("  Все счета банка:")
    for account in bank.search_accounts():
        print(f"    {account}")

    searches = [
        ("счета клиента anna", {"client_id": "anna"}, 2),
        ("в имени владельца есть «смирн»", {"owner": "смирн"}, 2),
        ("сберегательные", {"account_type": SavingsAccount}, 1),
        ("обычные, без продвинутых типов", {"account_type": BankAccount}, 2),
        ("замороженные", {"status": "FROZEN"}, 1),
        ("в рублях", {"currency": "rub"}, 3),
        ("рублёвые счета клиента anna", {"client_id": "anna", "currency": "RUB"}, 1),
        ("в юанях", {"currency": "CNY"}, 0),
        ("счета неизвестного клиента", {"client_id": "nobody"}, 0),
    ]
    for description, filters, expected in searches:
        count = len(bank.search_accounts(**filters))
        check(f"{description}: найдено {count}", count == expected)

    bad_searches = [
        ("неизвестный статус", {"status": "lost"}),
        ("неизвестная валюта", {"currency": "GBP"}),
        ("тип счёта строкой", {"account_type": "savings"}),
        ("пустая строка вместо имени", {"owner": "   "}),
    ]
    for description, filters in bad_searches:
        expect_error(description, InvalidOperationError,
                     lambda: bank.search_accounts(**filters))
    bank.search_accounts().clear()
    check("очистка найденного списка не меняет банк", len(bank.search_accounts()) == 5)


def show_totals():
    section("8. Общая сумма и рейтинг")
    stand = Stand()
    bank = stand.bank
    stand.premium.withdraw(1200)  # 1000 - 1200 - комиссия 50 = -250: Пётр в долгу
    stand.invest.invest("stocks", 10000)  # вложенные деньги остаются в балансе
    bank.freeze_account(stand.invest.account_id)  # замороженный счёт тоже считается

    total = bank.get_total_balance()
    print(f"  Всего в рублях: {total}")
    check("в RUB: 10000 - 250 + 12000 = 21750", total == Decimal("21750.00"))
    check("в USD: один счёт на 300", bank.get_total_balance(currency="usd") == 300)
    check("в CNY счетов нет: ноль", bank.get_total_balance(currency="CNY") == 0)
    check("рубли одного клиента", bank.get_total_balance(client_id="anna") == 10000)

    ranking = bank.get_clients_ranking()
    print("  Рейтинг клиентов в рублях:")
    for row in ranking:
        print(f"    {row['place']}. {row['full_name']}: {row['total']}")
    order = [row["client_id"] for row in ranking]
    check(
        "больше денег — выше; при равенстве выше тот, кто пришёл раньше",
        order == ["liwei", "anna", "maria", "oleg", "petr"],
    )

    bank.close_account(stand.savings.account_id)
    after = bank.get_total_balance()
    check("закрытый счёт в сумму не входит: стало 11750", after == Decimal("11750.00"))
    expect_error("сумма по неизвестному клиенту", InvalidOperationError,
                 lambda: bank.get_total_balance(client_id="nobody"))
    expect_error("рейтинг в неизвестной валюте", InvalidOperationError,
                 lambda: bank.get_clients_ranking(currency="GBP"))
    ranking.clear()
    same = len(bank.get_clients_ranking()) == 5
    check("очистка полученного рейтинга не меняет банк", same)


def show_suspicious():
    section("9. Подозрительные действия")
    stand = Stand()
    bank, clock = stand.bank, stand.clock
    usd_number = stand.usd.account_id

    bank.authenticate_client("anna", PASSWORD)
    check("успешный вход следа не оставляет", bank.get_suspicious_actions() == [])
    expect_error("вход с неизвестным ID", AuthenticationError,
                 lambda: bank.authenticate_client("nobody", PASSWORD))
    for attempt in (1, 2, 3):
        error = ClientBlockedError if attempt == 3 else AuthenticationError
        expect_error(f"неверный пароль, попытка {attempt}", error,
                     lambda: bank.authenticate_client("petr", WRONG))
    expect_error("открытие счёта заблокированному клиенту", ClientBlockedError,
                 lambda: bank.open_account("petr"))
    clock.set(3, 15)
    expect_error("закрытие счёта ночью", NightOperationError,
                 lambda: bank.close_account(usd_number))

    journal = bank.get_suspicious_actions()
    print("  Журнал подозрительных действий:")
    for record in journal:
        when, who = record["time"], record["client_id"]
        print(f"    {when:%H:%M} | {record['action']} | {who} | {record['reason']}")
    check("в журнале шесть записей", len(journal) == 6)
    about_petr = bank.get_suspicious_actions("petr")
    check("четыре из них про клиента petr", len(about_petr) == 4)
    about_nobody = bank.get_suspicious_actions("nobody")
    check("попытка входа с неизвестным ID тоже записана", len(about_nobody) == 1)
    night = journal[-1]
    known = night["client_id"] == "anna" and night["account_id"] == usd_number
    check("ночная запись знает клиента и номер счёта", known)
    reasons = " ".join(record["reason"] for record in journal)
    clean = not any(secret in reasons for secret in (WRONG, PASSWORD, usd_number))
    check("в причинах нет ни пароля, ни полного номера счёта", clean)

    journal.clear()
    bank.get_suspicious_actions()[0]["reason"] = "стёрто"
    fresh = bank.get_suspicious_actions()
    check(
        "журнал нельзя изменить через полученный список",
        len(fresh) == 6 and fresh[0]["reason"] != "стёрто",
    )


def main():
    parts = [
        show_clients,
        show_registration,
        show_accounts,
        show_login,
        show_freezing,
        show_night,
        show_search,
        show_totals,
        show_suspicious,
    ]
    for part in parts:
        part()
    print()
    if problems:
        print(f"ДЕМОНСТРАЦИЯ ПРОВАЛЕНА. Расхождений: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Демонстрация дня 3 завершена успешно: клиенты, банк и защита работают.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

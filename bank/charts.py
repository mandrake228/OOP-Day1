"""Рисует графики отчётов в PNG. Только этому модулю проекта нужен matplotlib."""

from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

SIZE = (8, 5)  # размер картинки в дюймах
DPI = 100  # точек на дюйм: картинка 800 на 500 точек


def draw(chart, path):
    """Рисует один график по его описанию из отчёта и сохраняет в PNG."""
    figure = Figure(figsize=SIZE, dpi=DPI, layout="constrained")  # без pyplot
    axes = figure.subplots()
    axes.set_title(chart["title"])
    painters = {"pie": draw_pie, "bar": draw_bar, "line": draw_line}
    if not painters[chart["type"]](axes, chart):
        draw_nothing(axes)
    figure.savefig(path, format="png")


def draw_pie(axes, chart):
    """Круговая диаграмма: только положительные доли. Нечего рисовать — False."""
    pairs = [(label, float(value))
             for label, value in zip(chart["labels"], chart["values"]) if value > 0]
    if not pairs:
        return False
    axes.pie([value for _, value in pairs], labels=[label for label, _ in pairs],
             autopct="%1.1f%%")
    return True


def draw_bar(axes, chart):
    """Столбцы с подписанными значениями. Нечего рисовать — False."""
    if not chart["labels"]:
        return False
    places = range(len(chart["labels"]))  # по месту: одинаковые подписи не сольются
    bars = axes.bar(places, [float(value) for value in chart["values"]])
    axes.bar_label(bars, fmt="%.0f")
    axes.set_xticks(places, chart["labels"])
    axes.tick_params(axis="x", labelrotation=20)
    if chart.get("integer"):
        axes.yaxis.set_major_locator(MaxNLocator(integer=True))
    return True


def draw_line(axes, chart):
    """Ступенчатые линии во времени: баланс держится до следующего движения."""
    if not chart["series"]:
        return False
    for line in chart["series"]:
        times = [time for time, _ in line["points"]]
        values = [float(value) for _, value in line["points"]]
        axes.step(times, values, where="post", marker="o", label=line["label"])
    axes.xaxis.set_major_formatter(DateFormatter("%d.%m %H:%M"))
    axes.tick_params(axis="x", labelrotation=30)
    axes.legend()
    axes.grid(True)
    return True


def draw_nothing(axes):
    """Вместо графика — надпись «Нет данных»."""
    axes.text(0.5, 0.5, "Нет данных", ha="center", va="center")
    axes.set_axis_off()

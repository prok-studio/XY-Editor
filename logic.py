"""
Логика программы без интерфейса: шаблоны графиков, слои, геометрия.
Здесь нет ни Kivy, ни numpy - только стандартный Python (проще собирать в .apk).
"""

import math

NAN = float("nan")


def to_float(text):
    """Строка -> число. Понимает и запятую: 2,5."""
    return float(str(text).strip().replace(",", "."))


# --------------------------------------------------------------------------
# Сетка и обрезка
# --------------------------------------------------------------------------

def nice_step(span, target=6):
    """Красивый шаг сетки (1, 2, 5 * 10^n) так, чтобы было около target линий."""
    raw = span / float(target)
    if not (raw > 0 and math.isfinite(raw)):
        return 1.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def ticks(lo, hi, step):
    out = []
    k = math.ceil(lo / step)
    v = k * step
    while v <= hi + step * 1e-9 and len(out) < 200:
        out.append(v)
        k += 1
        v = k * step
    return out


def clip_segment(x0, y0, x1, y1, xmin, xmax, ymin, ymax):
    """Обрезка отрезка прямоугольником (алгоритм Лянга-Барски). None - вне окна."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0),
                 (-dy, y0 - ymin), (dy, ymax - y0)):
        if p == 0:
            if q < 0:
                return None
        else:
            t = q / p
            if p < 0:
                if t > t1:
                    return None
                if t > t0:
                    t0 = t
            else:
                if t < t0:
                    return None
                if t < t1:
                    t1 = t
    sx, sy = (x0, y0) if t0 == 0.0 else (x0 + t0 * dx, y0 + t0 * dy)
    ex, ey = (x1, y1) if t1 == 1.0 else (x0 + t1 * dx, y0 + t1 * dy)
    return sx, sy, ex, ey


def curve_runs(xs, ys, view):
    """Ломаную режет по окну и по разрывам (nan/inf). Возвращает список кусков."""
    xmin, xmax, ymin, ymax = view
    runs, cur = [], []
    for i in range(len(xs) - 1):
        ax, ay, bx, by = xs[i], ys[i], xs[i + 1], ys[i + 1]
        if not (math.isfinite(ax) and math.isfinite(ay)
                and math.isfinite(bx) and math.isfinite(by)):
            if cur:
                runs.append(cur)
                cur = []
            continue
        c = clip_segment(ax, ay, bx, by, xmin, xmax, ymin, ymax)
        if c is None:
            if cur:
                runs.append(cur)
                cur = []
            continue
        cx0, cy0, cx1, cy1 = c
        if cur and cur[-1] == (cx0, cy0):
            cur.append((cx1, cy1))
        else:
            if cur:
                runs.append(cur)
            cur = [(cx0, cy0), (cx1, cy1)]
    if cur:
        runs.append(cur)
    return runs


# --------------------------------------------------------------------------
# Шаблоны графиков
# --------------------------------------------------------------------------

# Чтобы добавить свой шаблон - допиши сюда новую запись.
# params: (имя параметра, значение по умолчанию); f: функция y(x, *параметры)
# Особый вид "polyline": ломаная - у неё вместо параметров список вершин.
TEMPLATES = {
    "Прямая: y = k·x + b": {
        "params": [("k", 1), ("b", 0)],
        "f": lambda x, k, b: k * x + b,
    },
    "Ломаная (несколько звеньев)": {
        "polyline": True,
        "params": [],
        "default_points": [(0, 0), (5, 5)],
    },
    "Парабола: y = a·x² + b·x + c": {
        "params": [("a", 1), ("b", 0), ("c", 0)],
        "f": lambda x, a, b, c: a * x ** 2 + b * x + c,
    },
    "Синусоида: y = A·sin(ω·x + φ)": {
        "params": [("A", 1), ("ω", 1), ("φ", 0)],
        "f": lambda x, A, w, p: A * math.sin(w * x + p),
    },
    "Гипербола: y = k / x": {
        "params": [("k", 1)],
        "f": lambda x, k: k / x,
        "breaks": True,  # не соединять ветки через разрыв
    },
    "Экспонента: y = a·e^(b·x)": {
        "params": [("a", 1), ("b", 0.5)],
        "f": lambda x, a, b: a * math.exp(b * x),
    },
}

LAYER_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                "#9467bd", "#8c564b", "#e377c2", "#17becf"]

SAMPLES = 400


def _safe_eval(f, x, args):
    try:
        v = float(f(x, *args))
    except (ZeroDivisionError, OverflowError, ValueError):
        return NAN
    return v if math.isfinite(v) else NAN


def _sign(v):
    return (v > 0) - (v < 0)


def template_kind(name):
    """Короткое название вида графика: 'Прямая', 'Ломаная', ..."""
    return name.split(":")[0].split("(")[0].strip()


class Layer:
    """Один слой: вид графика + свои числа + цвет + видимость."""

    counter = 0

    def __init__(self, template, color):
        Layer.counter += 1
        self.name = "Слой %d" % Layer.counter
        self.color = color
        self.visible = True
        self.set_template(template)

    def set_template(self, template):
        """Меняет вид графика; числа сбрасываются на значения по умолчанию."""
        self.template = template
        tpl = TEMPLATES[template]
        self.params = {n: str(d) for n, d in tpl["params"]}
        self.vertices = [[str(x), str(y)] for x, y in tpl.get("default_points", [])]
        self._last = None

    def copy_from(self, src):
        self.set_template(src.template)
        self.color = src.color
        self.params = dict(src.params)
        self.vertices = [list(v) for v in src.vertices]

    @property
    def is_polyline(self):
        return bool(TEMPLATES[self.template].get("polyline"))

    def compute(self, view):
        """(xs, ys, это_ломаная). Если ввод неполный - возвращает прошлый результат."""
        x0, x1, y0, y1 = view
        tpl = TEMPLATES[self.template]
        try:
            if tpl.get("polyline"):
                pts = [(to_float(a), to_float(b)) for a, b in self.vertices]
                self._last = ([p[0] for p in pts], [p[1] for p in pts], True)
            else:
                args = [to_float(self.params[p]) for p, _ in tpl["params"]]
                n = SAMPLES
                xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
                ys = [_safe_eval(tpl["f"], x, args) for x in xs]
                if tpl.get("breaks"):
                    for i in range(1, n):
                        a, b = ys[i - 1], ys[i]
                        if (math.isfinite(a) and math.isfinite(b)
                                and _sign(a) != _sign(b) and abs(b - a) > (y1 - y0)):
                            ys[i] = NAN
                self._last = (xs, ys, False)
        except (ValueError, KeyError):
            pass  # пока вводится что-то неполное - оставляем прошлое
        return self._last


# --------------------------------------------------------------------------
# Плоскость: построения и измерения
# --------------------------------------------------------------------------

KIND_NAMES = {"line": "Прямая", "ray": "Луч", "segment": "Отрезок"}


def shape_ends(kind, a, b, view):
    """Концы для рисования (до обрезки по окну). None - если точки совпадают."""
    (ax, ay), (bx, by) = a, b
    if kind == "segment":
        return ax, ay, bx, by
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    if n == 0:
        return None
    x0, x1, y0, y1 = view
    big = 1e3 * ((x1 - x0) + (y1 - y0) + abs(ax) + abs(ay) + abs(bx) + abs(by) + 1)
    ux, uy = dx / n, dy / n
    if kind == "ray":  # из A через B в бесконечность
        return ax, ay, ax + ux * big, ay + uy * big
    return ax - ux * big, ay - uy * big, ax + ux * big, ay + uy * big


def distance_text(na, nb, pa, pb):
    return "|%s%s| = %.6g" % (na, nb, math.hypot(pb[0] - pa[0], pb[1] - pa[1]))


def midpoint_text(na, nb, pa, pb):
    return "Середина %s%s: (%.6g; %.6g)" % (na, nb, (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)


def _sign_abs(v):
    v += 0.0  # убираем «-0»
    return ("-" if v < 0 else "+"), abs(v)


def equation_text(pa, pb):
    (x1, y1), (x2, y2) = pa, pb
    a, b = y2 - y1, x1 - x2
    c = -(a * x1 + b * y1)
    sb, ab = _sign_abs(b)
    sc, ac = _sign_abs(c)
    text = "Общий вид: %.6g·x %s %.6g·y %s %.6g = 0" % (a + 0.0, sb, ab, sc, ac)
    if abs(b) > 1e-12:
        sm, am = _sign_abs(-c / b)
        text += "\ny = %.6g·x %s %.6g" % (-a / b + 0.0, sm, am)
    else:
        text += "\nx = %.6g" % (x1 + 0.0)
    return text

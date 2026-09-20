"""
XY Editor - мобильная версия (Kivy).

Запуск на компьютере для проверки:   pip install kivy   ->   python main.py
Сборка в .apk:                       см. buildozer.spec и README.txt

Вкладки:
  «Графики»   - слои; у каждого слоя свой вид графика (в т.ч. ломаная из
                нескольких звеньев); все слои рисуются на одном холсте.
  «Плоскость» - точки с именами, прямые, лучи, отрезки, измерения.

График: тяни пальцем - сдвиг, два пальца - масштаб (на ПК: колёсико мыши).
"""

import math
import os

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hexrgba

from logic import (KIND_NAMES, LAYER_COLORS, TEMPLATES, Layer, clip_segment,
                   curve_runs, distance_text, equation_text, midpoint_text,
                   nice_step, shape_ends, template_kind, ticks, to_float)

# --------------------------------------------------------------------------
# Цвета
# --------------------------------------------------------------------------

BG = hexrgba("#f5f6fa")
CARD_BORDER = hexrgba("#d9dde8")
FG = hexrgba("#1f2430")
MUTED = hexrgba("#7a8194")
ACCENT = hexrgba("#4f6bed")
ACCENT_DARK = hexrgba("#3d55c9")
ACCENT_SOFT = hexrgba("#e3e8fd")
FIELD = hexrgba("#eef0f6")
BTN = hexrgba("#e9ecf5")
BTN_PRESS = hexrgba("#d0d6e8")
SUCCESS = hexrgba("#0f9d58")
DANGER = hexrgba("#c62828")
WHITE = (1, 1, 1, 1)


# --------------------------------------------------------------------------
# Свои «плоские» виджеты
# --------------------------------------------------------------------------

class Txt(Label):
    """Подпись с переносом строк (высота подстраивается под текст)."""

    def __init__(self, **kw):
        kw.setdefault("color", FG)
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        kw.setdefault("font_size", sp(14))
        kw.setdefault("size_hint_y", None)
        super().__init__(**kw)
        self.bind(width=lambda *_: setattr(self, "text_size", (self.width, None)))
        self.bind(texture_size=lambda *_: setattr(
            self, "height", max(self.texture_size[1], dp(24))))


class RowLabel(Label):
    """Подпись внутри строки фиксированной высоты."""

    def __init__(self, **kw):
        kw.setdefault("color", FG)
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        kw.setdefault("font_size", sp(14))
        super().__init__(**kw)
        self.bind(size=lambda *_: setattr(self, "text_size", self.size))


class FlatButton(Button):
    STYLES = {
        "normal": (BTN, BTN_PRESS, FG),
        "accent": (ACCENT, ACCENT_DARK, WHITE),
        "danger": (BTN, BTN_PRESS, DANGER),
    }

    def __init__(self, kind="normal", **kw):
        self._base, self._press, fg = self.STYLES[kind]
        kw.update(background_normal="", background_down="",
                  background_color=self._base, color=fg, font_size=sp(14))
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        super().__init__(**kw)
        self.bind(state=self._on_state)

    def _on_state(self, _w, state):
        self.background_color = self._press if state == "down" else self._base


class ChipButton(ToggleButton):
    """Кнопка-переключатель (список слоёв/объектов, верхнее меню)."""

    def __init__(self, solid=False, **kw):
        self._solid = solid
        kw.update(background_normal="", background_down="", font_size=sp(14))
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        super().__init__(**kw)
        self.bind(state=self._on_state)
        self._on_state(self, self.state)

    def _on_state(self, _w, state):
        if state == "down":
            self.background_color = ACCENT if self._solid else ACCENT_SOFT
            self.color = WHITE if self._solid else ACCENT
        else:
            self.background_color = BTN
            self.color = FG if not self._solid else MUTED


def make_input(text="", setter=None, **kw):
    ti = TextInput(text=str(text), multiline=False, write_tab=False,
                   background_normal="", background_active="",
                   background_color=FIELD, foreground_color=FG,
                   cursor_color=ACCENT, font_size=sp(15),
                   padding=[dp(10), dp(10), dp(10), dp(10)],
                   size_hint_y=None, height=dp(40), **kw)
    if setter:
        ti.bind(text=lambda _w, value: setter(value))
    return ti


def make_spinner(text, values, **kw):
    return Spinner(text=text, values=values, background_normal="",
                   background_color=FIELD, color=FG, font_size=sp(14),
                   size_hint_y=None, height=dp(40), **kw)


class VBox(GridLayout):
    """Вертикальный контейнер, высота = сумме высот детей."""

    def __init__(self, **kw):
        kw.setdefault("cols", 1)
        kw.setdefault("size_hint_y", None)
        super().__init__(**kw)
        self.bind(minimum_height=self.setter("height"))


class Card(VBox):
    """Белая карточка с заголовком."""

    def __init__(self, title=None, **kw):
        kw.setdefault("padding", dp(12))
        kw.setdefault("spacing", dp(8))
        super().__init__(**kw)
        with self.canvas.before:
            Color(*CARD_BORDER)
            self._border = RoundedRectangle(radius=[dp(12)])
            Color(*WHITE)
            self._fill = RoundedRectangle(radius=[dp(11)])
        self.bind(pos=self._update, size=self._update)
        if title:
            self.add_widget(Txt(text=title, bold=True, color=ACCENT))

    def _update(self, *_):
        self._border.pos, self._border.size = self.pos, self.size
        self._fill.pos = (self.x + dp(1), self.y + dp(1))
        self._fill.size = (self.width - dp(2), self.height - dp(2))


def make_scroll():
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    content = VBox(spacing=dp(10), padding=[dp(10), dp(6), dp(10), dp(16)])
    scroll.add_widget(content)
    return scroll, content


def notify(title, message):
    Popup(title=title, content=Label(text=message, font_size=sp(15)),
          size_hint=(0.85, 0.28)).open()


# --------------------------------------------------------------------------
# Область с графиком (рисуется прямо на canvas Kivy)
# --------------------------------------------------------------------------

class PlotWidget(Widget):
    """
    Координатная плоскость: сетка, оси через ноль, подписи, кривые, точки.
    Сдвиг - пальцем, масштаб - двумя пальцами (или колёсиком мыши).
    """

    def __init__(self, on_view_change=None, equal=False, **kw):
        super().__init__(**kw)
        self.rng = [-10.0, 10.0, -10.0, 10.0]   # x мин, x макс, y мин, y макс
        self.equal = equal
        self.items = []
        self.legend = []
        self.title = ""
        self.on_view_change = on_view_change
        self._touches = []
        self._tex = {}
        self._trigger = Clock.create_trigger(self._draw, -1)
        self.bind(pos=self._trigger, size=self._trigger)

    # ---------- геометрия ----------

    def plot_rect(self):
        px0, py0 = self.x + dp(40), self.y + dp(22)
        return px0, py0, self.width - dp(40) - dp(10), self.height - dp(22) - dp(24)

    def view(self):
        """Реальные границы (с учётом одинакового масштаба осей)."""
        x0, x1, y0, y1 = self.rng
        _, _, pw, ph = self.plot_rect()
        if self.equal and pw > 0 and ph > 0:
            s = max((x1 - x0) / pw, (y1 - y0) / ph)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            x0, x1 = cx - s * pw / 2, cx + s * pw / 2
            y0, y1 = cy - s * ph / 2, cy + s * ph / 2
        return x0, x1, y0, y1

    def set_content(self, items, legend=(), title=""):
        self.items, self.legend, self.title = items, list(legend), title
        self._trigger()

    def _changed(self):
        self._trigger()
        if self.on_view_change:
            self.on_view_change(self.rng)

    # ---------- жесты ----------

    def pan(self, dx, dy):
        x0, x1, y0, y1 = self.view()
        _, _, pw, ph = self.plot_rect()
        if pw <= 0 or ph <= 0:
            return
        ddx, ddy = -dx / pw * (x1 - x0), -dy / ph * (y1 - y0)
        self.rng = [x0 + ddx, x1 + ddx, y0 + ddy, y1 + ddy]
        self._changed()

    def zoom(self, factor, pos):
        x0, x1, y0, y1 = self.view()
        px0, py0, pw, ph = self.plot_rect()
        if pw <= 0 or ph <= 0:
            return
        cx = x0 + (pos[0] - px0) / pw * (x1 - x0)
        cy = y0 + (pos[1] - py0) / ph * (y1 - y0)
        nx0, nx1 = cx - (cx - x0) * factor, cx + (x1 - cx) * factor
        ny0, ny1 = cy - (cy - y0) * factor, cy + (y1 - cy) * factor
        if nx1 - nx0 < 1e-6 or ny1 - ny0 < 1e-6 or nx1 - nx0 > 1e9 or ny1 - ny0 > 1e9:
            return
        self.rng = [nx0, nx1, ny0, ny1]
        self._changed()

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if touch.is_mouse_scrolling:
            self.zoom(0.85 if touch.button == "scrollup" else 1 / 0.85, touch.pos)
            return True
        touch.grab(self)
        self._touches.append(touch)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if len(self._touches) == 1:
            self.pan(touch.dx, touch.dy)
        elif len(self._touches) >= 2 and touch in self._touches[:2]:
            a, b = self._touches[:2]
            cur = math.hypot(a.x - b.x, a.y - b.y)
            pa = a.ppos if touch is a else a.pos
            pb = b.ppos if touch is b else b.pos
            prev = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
            if cur > 1 and prev > 1:
                self.zoom(prev / cur, ((a.x + b.x) / 2, (a.y + b.y) / 2))
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if touch in self._touches:
                self._touches.remove(touch)
            return True
        return False

    # ---------- рисование ----------

    def _text(self, s, size=10):
        key = (s, size)
        tex = self._tex.get(key)
        if tex is None:
            label = CoreLabel(text=s, font_size=sp(size))
            label.refresh()
            tex = label.texture
            if len(self._tex) > 400:
                self._tex.clear()
            self._tex[key] = tex
        return tex

    def _draw(self, *_):
        canvas = self.canvas
        canvas.clear()
        with canvas:
            Color(*WHITE)
            Rectangle(pos=self.pos, size=self.size)
        px0, py0, pw, ph = self.plot_rect()
        x0, x1, y0, y1 = self.view()
        if pw < dp(40) or ph < dp(40) or x1 <= x0 or y1 <= y0:
            return
        view = (x0, x1, y0, y1)

        def tx(v):
            return px0 + (v - x0) / (x1 - x0) * pw

        def ty(v):
            return py0 + (v - y0) / (y1 - y0) * ph

        sx, sy = nice_step(x1 - x0), nice_step(y1 - y0)
        xt, yt = ticks(x0, x1, sx), ticks(y0, y1, sy)

        with canvas:
            # сетка
            Color(0, 0, 0, 0.12)
            for v in xt:
                Line(points=[tx(v), py0, tx(v), py0 + ph], width=1)
            for v in yt:
                Line(points=[px0, ty(v), px0 + pw, ty(v)], width=1)
            # подписи делений
            Color(0.3, 0.3, 0.35, 1)
            for v in xt:
                tex = self._text("%g" % v)
                X = tx(v) - tex.width / 2
                if X >= px0 - dp(4) and X + tex.width <= px0 + pw + dp(8):
                    Rectangle(texture=tex, size=tex.size, pos=(X, self.y + dp(4)))
            for v in yt:
                tex = self._text("%g" % v)
                Rectangle(texture=tex, size=tex.size,
                          pos=(px0 - tex.width - dp(4), ty(v) - tex.height / 2))
            # оси через ноль
            Color(0, 0, 0, 1)
            if y0 <= 0 <= y1:
                Line(points=[px0, ty(0), px0 + pw, ty(0)], width=1.2)
            if x0 <= 0 <= x1:
                Line(points=[tx(0), py0, tx(0), py0 + ph], width=1.2)
            Color(0, 0, 0, 0.35)
            Line(rectangle=(px0, py0, pw, ph), width=1)

            # содержимое
            for it in self.items:
                kind = it["kind"]
                if kind == "curve":
                    Color(*it["color"])
                    for run in curve_runs(it["xs"], it["ys"], view):
                        pts = []
                        for X, Y in run:
                            pts += [tx(X), ty(Y)]
                        Line(points=pts, width=dp(1.8), cap="round", joint="round")
                    if it.get("markers"):
                        r = dp(3.5)
                        for X, Y in zip(it["xs"], it["ys"]):
                            if x0 <= X <= x1 and y0 <= Y <= y1:
                                Ellipse(pos=(tx(X) - r, ty(Y) - r), size=(2 * r, 2 * r))
                elif kind == "segment":
                    c = clip_segment(*it["ends"], x0, x1, y0, y1)
                    if c:
                        Color(*it["color"])
                        Line(points=[tx(c[0]), ty(c[1]), tx(c[2]), ty(c[3])],
                             width=dp(1.8), cap="round")
                elif kind == "point":
                    X, Y = it["x"], it["y"]
                    if x0 <= X <= x1 and y0 <= Y <= y1:
                        r = dp(4)
                        Color(0, 0, 0, 1)
                        Ellipse(pos=(tx(X) - r, ty(Y) - r), size=(2 * r, 2 * r))
                        tex = self._text(it["text"], 11)
                        Color(0.1, 0.1, 0.15, 1)
                        Rectangle(texture=tex, size=tex.size,
                                  pos=(tx(X) + dp(6), ty(Y) + dp(6)))

            # заголовок
            if self.title:
                tex = self._text(self.title, 11)
                Color(0.2, 0.2, 0.25, 1)
                Rectangle(texture=tex, size=tex.size,
                          pos=(px0 + (pw - tex.width) / 2, py0 + ph + dp(4)))

            # легенда
            if self.legend:
                texs = [self._text(name, 10) for name, _ in self.legend]
                w = max(t.width for t in texs) + dp(30)
                h = len(texs) * dp(16) + dp(6)
                Color(1, 1, 1, 0.85)
                Rectangle(pos=(px0 + dp(6), py0 + ph - h - dp(6)), size=(w, h))
                for i, ((_, col), tex) in enumerate(zip(self.legend, texs)):
                    yy = py0 + ph - dp(6) - (i + 1) * dp(16)
                    Color(*col)
                    Rectangle(pos=(px0 + dp(12), yy + dp(6)), size=(dp(14), dp(3)))
                    Color(0.15, 0.15, 0.2, 1)
                    Rectangle(texture=tex, size=tex.size,
                              pos=(px0 + dp(30), yy + (dp(16) - tex.height) / 2))


# --------------------------------------------------------------------------
# Карточка «Границы осей»
# --------------------------------------------------------------------------

class RangeCard(Card):
    def __init__(self, plot, on_change, defaults=(-10, 10, -10, 10)):
        super().__init__("Границы осей")
        self.plot, self.on_change, self._sync = plot, on_change, False
        grid = GridLayout(cols=4, size_hint_y=None, height=dp(86), spacing=dp(6),
                          row_default_height=dp(40), row_force_default=True)
        self.inputs = []
        for label, value in zip(("x мин", "x макс", "y мин", "y макс"), defaults):
            grid.add_widget(RowLabel(text=label, size_hint_x=None, width=dp(50)))
            ti = make_input(value, self._edited)
            grid.add_widget(ti)
            self.inputs.append(ti)
        self.add_widget(grid)
        plot.rng = [float(v) for v in defaults]

    def get(self):
        try:
            x0, x1, y0, y1 = (to_float(t.text) for t in self.inputs)
        except ValueError:
            return None
        return (x0, x1, y0, y1) if x0 < x1 and y0 < y1 else None

    def _edited(self, _value):
        if self._sync:
            return
        rng = self.get()
        if rng is None:
            return  # пока вводится что-то неполное - молча ждём
        self.plot.rng = list(rng)
        self.plot._trigger()
        self.on_change()

    def show(self, rng):
        """Показать границы (после сдвига/масштаба жестами)."""
        self._sync = True
        for ti, v in zip(self.inputs, rng):
            ti.text = "%.6g" % v
        self._sync = False


# --------------------------------------------------------------------------
# Вкладка 1: графики со слоями
# --------------------------------------------------------------------------

class TemplatesTab(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(4), **kw)
        self.layers, self.current, self.rows = [], None, {}
        self.pal_buttons = []

        self.plot = PlotWidget(on_view_change=self.on_plot_view, size_hint_y=0.42)
        self.add_widget(self.plot)
        scroll, content = make_scroll()
        self.add_widget(scroll)

        # --- слои ---
        lc = Card("Слои")
        self.list_box = VBox(spacing=dp(4))
        lc.add_widget(self.list_box)
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        row.add_widget(FlatButton(text="+ Слой", kind="accent",
                                  on_release=lambda *_: self.add_layer()))
        row.add_widget(FlatButton(text="Копия",
                                  on_release=lambda *_: self.duplicate_layer()))
        row.add_widget(FlatButton(text="Удалить", kind="danger",
                                  on_release=lambda *_: self.delete_layer()))
        lc.add_widget(row)
        content.add_widget(lc)

        # --- настройки выбранного слоя ---
        self.editor = Card("Настройки слоя")
        self.editor_body = VBox(spacing=dp(8))
        self.editor.add_widget(self.editor_body)
        content.add_widget(self.editor)

        self.ranges = RangeCard(self.plot, self.redraw)
        content.add_widget(self.ranges)
        content.add_widget(Txt(text="Меняй числа - график обновляется сам. "
                                    "Тяни график пальцем, два пальца - масштаб.",
                               color=MUTED, font_size=sp(12)))

        self.add_layer()

    def on_plot_view(self, rng):
        self.ranges.show(rng)
        self.redraw()

    # ---------- слои ----------

    @staticmethod
    def label(layer):
        return "%s  ·  %s" % (layer.name, template_kind(layer.template))

    def new_layer(self, template):
        return Layer(template, LAYER_COLORS[Layer.counter % len(LAYER_COLORS)])

    def add_layer(self):
        layer = self.new_layer(next(iter(TEMPLATES)))
        self.layers.append(layer)
        self.current = layer
        self.rebuild_list()
        self.build_editor()
        self.redraw()

    def duplicate_layer(self):
        if self.current is None:
            return
        layer = self.new_layer(self.current.template)
        layer.copy_from(self.current)
        self.layers.append(layer)
        self.current = layer
        self.rebuild_list()
        self.build_editor()
        self.redraw()

    def delete_layer(self):
        if self.current is None:
            return
        idx = self.layers.index(self.current)
        del self.layers[idx]
        self.current = self.layers[min(idx, len(self.layers) - 1)] if self.layers else None
        self.rebuild_list()
        self.build_editor()
        self.redraw()

    def select_layer(self, layer):
        self.current = layer
        self.mark_current()
        self.build_editor()

    def rebuild_list(self):
        self.list_box.clear_widgets()
        self.rows = {}
        for layer in self.layers:
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            cb = CheckBox(active=layer.visible, size_hint_x=None, width=dp(40),
                          color=ACCENT)
            cb.bind(active=lambda _w, val, l=layer: self.set_visible(l, val))
            btn = ChipButton(text=self.label(layer), group="layers",
                             allow_no_selection=False)
            btn.bind(on_release=lambda _b, l=layer: self.select_layer(l))
            row.add_widget(cb)
            row.add_widget(btn)
            self.list_box.add_widget(row)
            self.rows[layer] = btn
        self.mark_current()

    def mark_current(self):
        if self.current in self.rows:
            self.rows[self.current].state = "down"

    def set_visible(self, layer, value):
        layer.visible = value
        self.redraw()

    # ---------- редактор выбранного слоя ----------

    def build_editor(self):
        body = self.editor_body
        body.clear_widgets()
        layer = self.current
        if layer is None:
            body.add_widget(Txt(text="Нет слоёв. Нажми «+ Слой».", color=MUTED))
            return

        def rename(value):
            layer.name = value
            if layer in self.rows:
                self.rows[layer].text = self.label(layer)
            self.redraw()

        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        row.add_widget(RowLabel(text="Название", size_hint_x=None, width=dp(84)))
        row.add_widget(make_input(layer.name, rename))
        body.add_widget(row)

        spinner = make_spinner(layer.template, list(TEMPLATES))
        spinner.bind(text=self.on_template)
        body.add_widget(spinner)

        # палитра цвета слоя
        pal = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        self.pal_buttons = []
        for hexcol in LAYER_COLORS:
            b = Button(background_normal="", background_down="",
                       background_color=hexrgba(hexcol), color=WHITE,
                       font_size=sp(20), text="•" if hexcol == layer.color else "")
            b.bind(on_release=lambda _b, c=hexcol: self.set_color(c))
            pal.add_widget(b)
            self.pal_buttons.append((hexcol, b))
        body.add_widget(pal)

        self.params_box = VBox(spacing=dp(6))
        body.add_widget(self.params_box)
        self.build_params()

    def set_color(self, hexcol):
        self.current.color = hexcol
        for c, b in self.pal_buttons:
            b.text = "•" if c == hexcol else ""
        self.redraw()

    def on_template(self, _spinner, value):
        layer = self.current
        if layer is None or value == layer.template:
            return
        layer.set_template(value)
        if layer in self.rows:
            self.rows[layer].text = self.label(layer)
        self.build_params()
        self.redraw()

    def build_params(self):
        box = self.params_box
        box.clear_widgets()
        layer = self.current
        if layer.is_polyline:
            self.build_polyline_editor()
            return
        for name, _ in TEMPLATES[layer.template]["params"]:
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            row.add_widget(RowLabel(text=name + " =", size_hint_x=None, width=dp(56),
                                    halign="right"))
            row.add_widget(make_input(layer.params[name],
                                      lambda v, n=name: self.set_param(n, v)))
            box.add_widget(row)

    def set_param(self, name, value):
        self.current.params[name] = value
        self.redraw()

    # ----- ломаная -----

    def build_polyline_editor(self):
        box, layer = self.params_box, self.current
        box.add_widget(Txt(text="Каждое звено начинается там, где закончилось "
                                "предыдущее.", color=MUTED, font_size=sp(12)))
        for i, vertex in enumerate(layer.vertices):
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            title = "Начало" if i == 0 else "Конец звена %d" % i
            row.add_widget(RowLabel(text=title, size_hint_x=None, width=dp(112)))
            row.add_widget(make_input(vertex[0], lambda v, vt=vertex: self.set_vertex(vt, 0, v),
                                      hint_text="x"))
            row.add_widget(make_input(vertex[1], lambda v, vt=vertex: self.set_vertex(vt, 1, v),
                                      hint_text="y"))
            if i >= 2:  # минимум одно звено (две вершины) остаётся всегда
                row.add_widget(FlatButton(text="X", kind="danger", size_hint_x=None,
                                          width=dp(40),
                                          on_release=lambda _b, i=i: self.remove_vertex(i)))
            else:
                row.add_widget(Widget(size_hint_x=None, width=dp(40)))
            box.add_widget(row)
        box.add_widget(FlatButton(text="+ Добавить звено", kind="accent",
                                  on_release=lambda *_: self.add_vertex()))

    def set_vertex(self, vertex, idx, value):
        vertex[idx] = value
        self.redraw()

    def add_vertex(self):
        layer = self.current
        try:
            lx, ly = (to_float(v) for v in layer.vertices[-1])
            if len(layer.vertices) >= 2:  # повторяем шаг предыдущего звена
                px, py = (to_float(v) for v in layer.vertices[-2])
                dx, dy = lx - px, ly - py
            else:
                dx, dy = 1.0, 1.0
            nx, ny = lx + dx, ly + dy
        except ValueError:
            nx, ny = 0.0, 0.0
        layer.vertices.append(["%g" % nx, "%g" % ny])
        self.build_params()
        self.redraw()

    def remove_vertex(self, index):
        del self.current.vertices[index]
        self.build_params()
        self.redraw()

    # ---------- рисование ----------

    def redraw(self):
        view = self.plot.view()
        items, shown = [], []
        for layer in self.layers:
            if not layer.visible:
                continue
            data = layer.compute(view)
            if data is None:
                continue
            xs, ys, poly = data
            items.append({"kind": "curve", "xs": xs, "ys": ys, "markers": poly,
                          "color": hexrgba(layer.color)})
            shown.append(layer)
        title = shown[0].template if len(shown) == 1 else ("Слои" if shown else "")
        legend = [(l.name or l.template, hexrgba(l.color)) for l in shown] \
            if len(shown) > 1 else []
        self.plot.set_content(items, legend, title)


# --------------------------------------------------------------------------
# Вкладка 2: координатная плоскость
# --------------------------------------------------------------------------

class PlaneTab(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(4), **kw)
        self.points = {}    # имя -> (x, y)
        self.shapes = []    # (вид, имя_A, имя_B)
        self.entries = []   # ("point", имя) / ("shape", индекс)
        self.sel = None

        self.plot = PlotWidget(on_view_change=self.on_plot_view, equal=True,
                               size_hint_y=0.42)
        self.add_widget(self.plot)
        scroll, content = make_scroll()
        self.add_widget(scroll)

        # --- точка ---
        pc = Card("Точка")
        grid = GridLayout(cols=2, size_hint_y=None, height=dp(132), spacing=dp(6),
                          row_default_height=dp(40), row_force_default=True)
        self.name_in, self.x_in, self.y_in = make_input("A"), make_input("0"), make_input("0")
        for label, w in (("Имя", self.name_in), ("x", self.x_in), ("y", self.y_in)):
            grid.add_widget(RowLabel(text=label, size_hint_x=None, width=dp(50)))
            grid.add_widget(w)
        pc.add_widget(grid)
        pc.add_widget(FlatButton(text="Добавить / обновить", kind="accent",
                                 on_release=lambda *_: self.add_point()))
        content.add_widget(pc)

        # --- построения и измерения ---
        sc = Card("Построения и измерения")
        pair = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.a_sp, self.b_sp = make_spinner("", []), make_spinner("", [])
        pair.add_widget(self.a_sp)
        pair.add_widget(self.b_sp)
        sc.add_widget(pair)
        bg = GridLayout(cols=3, size_hint_y=None, height=dp(86), spacing=dp(6),
                        row_default_height=dp(40), row_force_default=True)
        for text, cmd in (("Прямая", lambda: self.add_shape("line")),
                          ("Луч", lambda: self.add_shape("ray")),
                          ("Отрезок", lambda: self.add_shape("segment")),
                          ("Расстояние", self.measure_distance),
                          ("Середина", self.measure_midpoint),
                          ("Уравнение", self.measure_equation)):
            bg.add_widget(FlatButton(text=text, on_release=lambda _b, c=cmd: c()))
        sc.add_widget(bg)
        self.result = Txt(text="", color=SUCCESS, bold=True)
        sc.add_widget(self.result)
        content.add_widget(sc)

        # --- список объектов ---
        oc = Card("Объекты")
        self.obj_box = VBox(spacing=dp(4))
        oc.add_widget(self.obj_box)
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        row.add_widget(FlatButton(text="Удалить", kind="danger",
                                  on_release=lambda *_: self.delete_selected()))
        row.add_widget(FlatButton(text="Очистить всё",
                                  on_release=lambda *_: self.clear_all()))
        oc.add_widget(row)
        content.add_widget(oc)

        self.ranges = RangeCard(self.plot, self.redraw)
        content.add_widget(self.ranges)
        eq = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        cb = CheckBox(active=True, size_hint_x=None, width=dp(40), color=ACCENT)
        cb.bind(active=lambda _w, val: self.set_equal(val))
        eq.add_widget(cb)
        eq.add_widget(RowLabel(text="Одинаковый масштаб осей"))
        content.add_widget(eq)

        self.refresh()

    def on_plot_view(self, rng):
        self.ranges.show(rng)
        self.redraw()

    def set_equal(self, value):
        self.plot.rng = list(self.plot.view())
        self.plot.equal = value
        self.ranges.show(self.plot.rng)
        self.redraw()

    # ---------- работа с данными ----------

    def add_point(self):
        name = self.name_in.text.strip()
        if not name:
            notify("Точка", "Введи имя точки.")
            return
        try:
            x, y = to_float(self.x_in.text), to_float(self.y_in.text)
        except ValueError:
            notify("Точка", "x и y должны быть числами.")
            return
        self.points[name] = (x, y)  # если имя уже есть - точка перемещается
        self.refresh()

    def get_ab(self, need_distinct=True):
        a, b = self.a_sp.text, self.b_sp.text
        if a not in self.points or b not in self.points:
            notify("Выбор точек", "Выбери точки 1 и 2 (сначала добавь их).")
            return None
        if need_distinct and self.points[a] == self.points[b]:
            notify("Выбор точек", "Точки совпадают - так не построить.")
            return None
        return a, b

    def add_shape(self, kind):
        ab = self.get_ab()
        if ab:
            self.shapes.append((kind, *ab))
            self.refresh()

    def delete_selected(self):
        if not self.sel:
            return
        kind, ref = self.sel
        if kind == "point":
            self.points.pop(ref, None)
            # вместе с точкой удаляем всё, что на неё опирается
            self.shapes = [s for s in self.shapes if ref not in (s[1], s[2])]
        elif ref < len(self.shapes):
            del self.shapes[ref]
        self.sel = None
        self.refresh()

    def clear_all(self):
        self.points.clear()
        self.shapes.clear()
        self.sel = None
        self.result.text = ""
        self.refresh()

    def select_entry(self, entry):
        """Выбрал точку в списке - её данные попадают в поля."""
        self.sel = entry
        kind, ref = entry
        if kind == "point" and ref in self.points:
            x, y = self.points[ref]
            self.name_in.text, self.x_in.text, self.y_in.text = ref, "%g" % x, "%g" % y

    # ---------- вычисления ----------

    def measure_distance(self):
        ab = self.get_ab(need_distinct=False)
        if ab:
            self.result.text = distance_text(ab[0], ab[1], self.points[ab[0]], self.points[ab[1]])

    def measure_midpoint(self):
        ab = self.get_ab(need_distinct=False)
        if ab:
            self.result.text = midpoint_text(ab[0], ab[1], self.points[ab[0]], self.points[ab[1]])

    def measure_equation(self):
        ab = self.get_ab()
        if ab:
            self.result.text = equation_text(self.points[ab[0]], self.points[ab[1]])

    # ---------- отображение ----------

    def refresh(self):
        names = list(self.points)
        for sp_ in (self.a_sp, self.b_sp):
            sp_.values = names
            if sp_.text not in names:
                sp_.text = ""
        if len(names) >= 2:
            if not self.a_sp.text:
                self.a_sp.text = names[0]
            if not self.b_sp.text:
                self.b_sp.text = names[1]

        self.obj_box.clear_widgets()
        self.entries = []
        for name, (x, y) in self.points.items():
            self.entries.append(("point", name, "Точка %s (%g; %g)" % (name, x, y)))
        for i, (kind, a, b) in enumerate(self.shapes):
            self.entries.append(("shape", i, "%s %s%s" % (KIND_NAMES[kind], a, b)))
        for kind, ref, text in self.entries:
            btn = ChipButton(text=text, group="objects", allow_no_selection=False)
            btn.bind(on_release=lambda _b, e=(kind, ref): self.select_entry(e))
            self.obj_box.add_widget(btn)
            if self.sel == (kind, ref):
                btn.state = "down"
        self.redraw()

    def redraw(self):
        view = self.plot.view()
        items, legend = [], []
        for i, (kind, a, b) in enumerate(self.shapes):
            color = hexrgba(LAYER_COLORS[i % len(LAYER_COLORS)])
            ends = shape_ends(kind, self.points[a], self.points[b], view)
            if ends:
                items.append({"kind": "segment", "ends": ends, "color": color})
                legend.append(("%s %s%s" % (KIND_NAMES[kind], a, b), color))
        for name, (x, y) in self.points.items():
            items.append({"kind": "point", "x": x, "y": y,
                          "text": "%s (%g; %g)" % (name, x, y)})
        self.plot.set_content(items, legend)


# --------------------------------------------------------------------------

ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Images", "XY.png")


class CoordApp(App):
    title = "XY Editor"
    if os.path.exists(ICON):
        icon = ICON  # значок окна на ПК (на Android значок задаёт buildozer.spec)

    def build(self):
        Window.clearcolor = BG
        Window.softinput_mode = "below_target"  # клавиатура не закрывает поле ввода

        root = BoxLayout(orientation="vertical", spacing=dp(6),
                         padding=[dp(8), dp(6), dp(8), 0])
        root.add_widget(Label(text="XY Editor", bold=True,
                              font_size=sp(19), color=FG,
                              size_hint_y=None, height=dp(36)))

        nav = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        b1 = ChipButton(text="Графики", solid=True, group="nav",
                        allow_no_selection=False, state="down")
        b2 = ChipButton(text="Плоскость", solid=True, group="nav",
                        allow_no_selection=False)
        nav.add_widget(b1)
        nav.add_widget(b2)
        root.add_widget(nav)

        sm = ScreenManager(transition=NoTransition())
        s1, s2 = Screen(name="tpl"), Screen(name="plane")
        s1.add_widget(TemplatesTab())
        s2.add_widget(PlaneTab())
        sm.add_widget(s1)
        sm.add_widget(s2)
        root.add_widget(sm)

        b1.bind(on_release=lambda *_: setattr(sm, "current", "tpl"))
        b2.bind(on_release=lambda *_: setattr(sm, "current", "plane"))
        return root


if __name__ == "__main__":
    CoordApp().run()

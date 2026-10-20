# -*- coding: utf-8 -*-
"""
محفظة الذهب - نسخة الأندرويد (Kivy)
Gold Portfolio - Android version (Kivy)

تحويل من تطبيق Tkinter (EXE) إلى تطبيق أندرويد.
المزايا: شراء/بيع بالغرام (FIFO)، فروق شراء/بيع الراجحي،
عملات USD/SAR/AED، سجل العمليات، حاسبة الزكاة، ومخطط سعر الغرام.
"""
import os
import json
import time
from datetime import datetime

from kivy.app import App
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle

# ---------- دعم النص العربي (تشكيل + اتجاه) ----------
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def ar(txt):
        try:
            return get_display(arabic_reshaper.reshape(str(txt)))
        except Exception:
            return str(txt)
except Exception:
    def ar(txt):
        return str(txt)

# ---------- الخط العربي (بمسار مطلق + تسجيل آمن) ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
FONT = None
try:
    from kivy.core.text import LabelBase
    from kivy.resources import resource_add_path
    resource_add_path(APP_DIR)
    _assets = os.path.join(APP_DIR, "assets")
    if os.path.isdir(_assets):
        resource_add_path(_assets)
    for _name in ("Tajawal-Regular.ttf", "NotoNaskhArabic-Regular.ttf", "Amiri-Regular.ttf"):
        _fp = os.path.join(_assets, _name)
        if os.path.exists(_fp):
            try:
                LabelBase.register(name="arabic", fn_regular=_fp)
                FONT = "arabic"   # اسم مسجّل (أكثر استقراراً من المسار)
            except Exception:
                FONT = None
            break
except Exception:
    FONT = None


def A(**kw):
    """خصائص افتراضية للنصوص (الخط العربي)."""
    if FONT:
        kw.setdefault("font_name", FONT)
    return kw


# ---------- تخزين البيانات ----------
def data_dir():
    try:
        from android.storage import app_storage_path  # noqa
        d = app_storage_path()
    except Exception:
        d = os.path.join(os.path.expanduser("~"), ".gold_portfolio")
    os.makedirs(d, exist_ok=True)
    return d


DATA_FILE = os.path.join(data_dir(), "gold_portfolio_data.json")

# أسعار الصرف التقريبية مقابل الريال السعودي (العملة الأساس)
CURRENCIES = {"SAR": 1.0, "USD": 0.2667, "AED": 0.9793}


DEFAULT_STATE = {
    "buy_price": 0.0,      # سعر شراء الغرام الحالي (الراجحي)
    "sell_price": 0.0,     # سعر بيع الغرام الحالي (الراجحي)
    "currency": "SAR",
    "lots": [],            # دفعات الشراء المتبقية: {grams, price, date}
    "ledger": [],          # سجل العمليات
    "price_history": [],   # عينات سعر الغرام [ts, price]
    "alert_price": 0.0,    # تنبيه سعر
}


def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            for k, v in DEFAULT_STATE.items():
                s.setdefault(k, v if not isinstance(v, (list, dict)) else type(v)())
            return s
        except Exception:
            pass
    return {k: (v.copy() if isinstance(v, (list, dict)) else v)
            for k, v in DEFAULT_STATE.items()}


def save_state(s):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save error:", e)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------- مخطط سعر الغرام (يُرسم داخلياً بدون مكتبات) ----------
class PriceChart(Widget):
    def __init__(self, points, **kw):
        super().__init__(**kw)
        self.points = points
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *a):
        self.canvas.clear()
        pts = self.points
        with self.canvas:
            Color(0.12, 0.12, 0.14, 1)
            Rectangle(pos=self.pos, size=self.size)
            if len(pts) < 2:
                return
            vals = [p[1] for p in pts]
            vmin, vmax = min(vals), max(vals)
            if vmax == vmin:
                vmax = vmin + 1
            pad = dp(12)
            w = self.width - 2 * pad
            h = self.height - 2 * pad
            # شبكة
            Color(0.3, 0.3, 0.3, 0.5)
            for i in range(5):
                y = self.y + pad + h * i / 4.0
                Line(points=[self.x + pad, y, self.x + pad + w, y], width=0.8)
            # الخط
            line = []
            n = len(pts)
            for i, (_, v) in enumerate(pts):
                x = self.x + pad + w * i / (n - 1)
                y = self.y + pad + h * (v - vmin) / (vmax - vmin)
                line += [x, y]
            Color(1, 0.78, 0.2, 1)
            Line(points=line, width=1.6)


GOLD = (0.83, 0.68, 0.21, 1)
DARK = (0.09, 0.09, 0.11, 1)
GREEN = (0.15, 0.6, 0.3, 1)
RED = (0.7, 0.2, 0.2, 1)


def lbl(text, **kw):
    kw = A(**kw)
    kw.setdefault("color", (1, 1, 1, 1))
    return Label(text=ar(text), **kw)


def btn(text, cb, bg=GOLD, **kw):
    kw = A(**kw)
    b = Button(text=ar(text), background_normal="", background_color=bg,
               color=(0, 0, 0, 1) if bg == GOLD else (1, 1, 1, 1), **kw)
    b.bind(on_release=cb)
    return b


class GoldApp(App):
    def build(self):
        self.title = "Gold Portfolio"
        Window.clearcolor = DARK
        self.s = load_state()
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))

        # عنوان
        root.add_widget(lbl("محفظة الذهب 🌑", font_size="22sp", bold=True,
                            color=GOLD, size_hint_y=None, height=dp(40)))

        # أسعار الغرام (الراجحي)
        pr = GridLayout(cols=2, size_hint_y=None, height=dp(96), spacing=dp(6))
        pr.add_widget(lbl("سعر شراء الغرام (ريال)", font_size="13sp"))
        self.in_buy = TextInput(text=str(self.s["buy_price"]), multiline=False,
                                input_filter="float", size_hint_y=None, height=dp(40))
        pr.add_widget(self.in_buy)
        pr.add_widget(lbl("سعر بيع الغرام (ريال)", font_size="13sp"))
        self.in_sell = TextInput(text=str(self.s["sell_price"]), multiline=False,
                                 input_filter="float", size_hint_y=None, height=dp(40))
        pr.add_widget(self.in_sell)
        root.add_widget(pr)

        # صف العملة + تحديث
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.cur = Spinner(text=self.s["currency"], values=list(CURRENCIES.keys()),
                           size_hint_x=0.3, **A())
        self.cur.bind(text=lambda *a: self.refresh())
        row.add_widget(self.cur)
        row.add_widget(btn("حفظ / تحديث السعر", self.update_price))
        root.add_widget(row)

        # أزرار العمليات
        ops = GridLayout(cols=3, size_hint_y=None, height=dp(44), spacing=dp(6))
        ops.add_widget(btn("➕ شراء", self.open_buy, bg=GREEN, font_size="13sp"))
        ops.add_widget(btn("➖ أمر بيع", self.open_sell, bg=RED, font_size="13sp"))
        ops.add_widget(btn("🔔 تنبيه سعر", self.open_alert, bg=(0.3,0.3,0.4,1),
                           color=(1,1,1,1), font_size="13sp"))
        root.add_widget(ops)

        ops2 = GridLayout(cols=3, size_hint_y=None, height=dp(44), spacing=dp(6))
        ops2.add_widget(btn("📜 السجل", self.open_ledger, bg=(0.3,0.3,0.4,1), font_size="13sp"))
        ops2.add_widget(btn("📐 الزكاة", self.open_zakat, bg=(0.3,0.3,0.4,1), font_size="13sp"))
        ops2.add_widget(btn("📈 المخطط", self.open_chart, bg=(0.3,0.3,0.4,1), font_size="13sp"))
        root.add_widget(ops2)

        # الملخص
        self.summary = lbl("", font_size="14sp", size_hint_y=None, height=dp(110),
                           halign="right", valign="top")
        self.summary.bind(size=lambda w, *a: setattr(w, "text_size", (w.width, None)))
        root.add_widget(self.summary)

        # قائمة الدفعات
        root.add_widget(lbl("الدفعات المتبقية:", font_size="14sp", bold=True,
                            size_hint_y=None, height=dp(26), halign="right"))
        sc = ScrollView()
        self.lots_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.lots_box.bind(minimum_height=self.lots_box.setter("height"))
        sc.add_widget(self.lots_box)
        root.add_widget(sc)

        self.refresh()
        return root

    # ---------- أدوات ----------
    def rate(self):
        return CURRENCIES.get(self.cur.text, 1.0)

    def fmt(self, sar_value):
        return "%.2f %s" % (sar_value * self.rate(), self.cur.text)

    def _f(self, widget):
        try:
            return float(widget.text or 0)
        except Exception:
            return 0.0

    def total_grams(self):
        return sum(l["grams"] for l in self.s["lots"])

    def popup(self, title, content, size=(0.9, 0.9)):
        p = Popup(title=ar(title), content=content, size_hint=size,
                  title_font=FONT if FONT else None)
        return p

    def toast(self, msg):
        bx = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        bx.add_widget(lbl(msg, halign="right"))
        p = self.popup("تنبيه", bx, size=(0.8, 0.4))
        bx.add_widget(btn("حسناً", lambda *a: p.dismiss()))
        p.open()

    # ---------- السعر ----------
    def update_price(self, *a):
        self.s["buy_price"] = self._f(self.in_buy)
        self.s["sell_price"] = self._f(self.in_sell)
        self.s["currency"] = self.cur.text
        if self.s["buy_price"] > 0:
            self.s["price_history"].append([time.time(), self.s["buy_price"]])
            cutoff = time.time() - 24 * 3600
            self.s["price_history"] = [p for p in self.s["price_history"] if p[0] >= cutoff]
        # فحص تنبيه السعر
        ap = self.s.get("alert_price", 0)
        if ap > 0 and self.s["sell_price"] >= ap:
            self.toast("🔔 وصل سعر البيع إلى الهدف: %.2f ريال" % ap)
        save_state(self.s)
        self.refresh()

    # ---------- تحديث الواجهة ----------
    def refresh(self):
        grams = self.total_grams()
        cost = sum(l["grams"] * l["price"] for l in self.s["lots"])
        cur_val = grams * self.s["sell_price"]
        unreal = cur_val - cost
        realized = sum(e.get("profit", 0) for e in self.s["ledger"] if e["type"] == "sell")
        txt = (
            "الرصيد: %.3f غرام\n" % grams +
            "تكلفة الشراء: %s\n" % self.fmt(cost) +
            "القيمة الحالية (بيع): %s\n" % self.fmt(cur_val) +
            "ربح/خسارة غير محقق: %s\n" % self.fmt(unreal) +
            "ربح محقق: %s" % self.fmt(realized)
        )
        self.summary.text = ar(txt)
        # الدفعات
        self.lots_box.clear_widgets()
        if not self.s["lots"]:
            self.lots_box.add_widget(lbl("لا توجد دفعات", size_hint_y=None,
                                         height=dp(30), color=(0.7,0.7,0.7,1)))
        for i, l in enumerate(self.s["lots"]):
            t = "%s | %.3fغ @ %.2f ريال" % (l.get("date", ""), l["grams"], l["price"])
            self.lots_box.add_widget(lbl(t, size_hint_y=None, height=dp(30),
                                         halign="right", font_size="13sp"))

    # ---------- شراء ----------
    def open_buy(self, *a):
        bx = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        bx.add_widget(lbl("الكمية (غرام):", halign="right", size_hint_y=None, height=dp(26)))
        g = TextInput(multiline=False, input_filter="float", size_hint_y=None, height=dp(44))
        bx.add_widget(g)
        bx.add_widget(lbl("سعر الشراء للغرام (ريال):", halign="right",
                          size_hint_y=None, height=dp(26)))
        pr = TextInput(text=str(self.s["buy_price"]), multiline=False,
                       input_filter="float", size_hint_y=None, height=dp(44))
        bx.add_widget(pr)
        p = self.popup("➕ شراء ذهب", bx, size=(0.9, 0.6))

        def do(*_):
            grams = self._f(g)
            price = self._f(pr)
            if grams <= 0 or price <= 0:
                return self.toast("أدخل كمية وسعراً صحيحين")
            self.s["lots"].append({"grams": grams, "price": price, "date": now_str()})
            self.s["ledger"].append({"date": now_str(), "type": "buy", "grams": grams,
                                     "price": price, "value": grams * price})
            save_state(self.s)
            p.dismiss()
            self.refresh()
        bx.add_widget(btn("تأكيد الشراء", do, bg=GREEN))
        p.open()

    # ---------- أمر بيع (بالكمية + FIFO) ----------
    def open_sell(self, *a):
        bx = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        bx.add_widget(lbl("الرصيد المتاح: %.3f غرام" % self.total_grams(),
                          halign="right", size_hint_y=None, height=dp(26)))
        bx.add_widget(lbl("الكمية المراد بيعها (غرام):", halign="right",
                          size_hint_y=None, height=dp(26)))
        g = TextInput(multiline=False, input_filter="float", size_hint_y=None, height=dp(44))
        bx.add_widget(g)
        bx.add_widget(lbl("سعر البيع للغرام (الراجحي - ريال):", halign="right",
                          size_hint_y=None, height=dp(26)))
        pr = TextInput(text=str(self.s["sell_price"]), multiline=False,
                       input_filter="float", size_hint_y=None, height=dp(44))
        bx.add_widget(pr)
        p = self.popup("➖ أمر بيع", bx, size=(0.9, 0.7))

        def do(*_):
            qty = self._f(g)
            price = self._f(pr)   # يُثبَّت سعر البيع عند لحظة البيع
            if qty <= 0 or price <= 0:
                return self.toast("أدخل كمية وسعراً صحيحين")
            if qty > self.total_grams() + 1e-9:
                return self.toast("الكمية أكبر من الرصيد")
            # خصم FIFO
            remaining = qty
            cost_basis = 0.0
            while remaining > 1e-9 and self.s["lots"]:
                lot = self.s["lots"][0]
                take = min(remaining, lot["grams"])
                cost_basis += take * lot["price"]
                lot["grams"] -= take
                remaining -= take
                if lot["grams"] <= 1e-9:
                    self.s["lots"].pop(0)
            proceeds = qty * price
            profit = proceeds - cost_basis
            self.s["ledger"].append({"date": now_str(), "type": "sell", "grams": qty,
                                     "price": price, "value": proceeds, "profit": profit})
            save_state(self.s)
            p.dismiss()
            self.refresh()
            sign = "▲ ربح" if profit >= 0 else "▼ خسارة"
            self.toast("تم بيع %.3fغ\n%s محقق: %s" % (qty, sign, self.fmt(profit)))
        bx.add_widget(btn("تأكيد البيع", do, bg=RED, color=(1,1,1,1)))
        p.open()

    # ---------- تنبيه السعر ----------
    def open_alert(self, *a):
        bx = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        bx.add_widget(lbl("نبّهني عندما يبلغ سعر البيع (ريال):", halign="right",
                          size_hint_y=None, height=dp(26)))
        v = TextInput(text=str(self.s.get("alert_price", 0)), multiline=False,
                      input_filter="float", size_hint_y=None, height=dp(44))
        bx.add_widget(v)
        p = self.popup("🔔 تنبيه سعر", bx, size=(0.85, 0.5))

        def do(*_):
            self.s["alert_price"] = self._f(v)
            save_state(self.s)
            p.dismiss()
            self.toast("تم حفظ التنبيه")
        bx.add_widget(btn("حفظ", do))
        p.open()

    # ---------- سجل العمليات ----------
    def open_ledger(self, *a):
        bx = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        sc = ScrollView()
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(3))
        box.bind(minimum_height=box.setter("height"))
        if not self.s["ledger"]:
            box.add_widget(lbl("السجل فارغ", size_hint_y=None, height=dp(30)))
        for e in reversed(self.s["ledger"]):
            if e["type"] == "buy":
                t = "➕ شراء | %s | %.3fغ @ %.2f = %.2f" % (
                    e["date"], e["grams"], e["price"], e["value"])
                c = (0.8, 0.8, 0.8, 1)
            else:
                t = "➖ بيع | %s | %.3fغ @ %.2f | ربح: %.2f" % (
                    e["date"], e["grams"], e["price"], e.get("profit", 0))
                c = GREEN if e.get("profit", 0) >= 0 else RED
            box.add_widget(lbl(t, size_hint_y=None, height=dp(30), halign="right",
                               font_size="12sp", color=c))
        sc.add_widget(box)
        bx.add_widget(sc)
        p = self.popup("📜 سجل العمليات", bx)
        rowb = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))

        def clear(*_):
            self.s["ledger"] = []
            save_state(self.s)
            p.dismiss()
            self.refresh()
        rowb.add_widget(btn("مسح السجل", clear, bg=RED, color=(1,1,1,1)))
        rowb.add_widget(btn("إغلاق", lambda *_: p.dismiss()))
        bx.add_widget(rowb)
        p.open()

    # ---------- حاسبة الزكاة ----------
    def open_zakat(self, *a):
        grams = self.total_grams()
        value = grams * self.s["sell_price"]
        nisab_g = 85.0
        zakat = value * 0.025 if grams >= nisab_g else 0.0
        bx = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        txt = (
            "الرصيد: %.3f غرام\n" % grams +
            "النصاب: %.0f غرام\n" % nisab_g +
            "القيمة الحالية: %s\n\n" % self.fmt(value) +
            ("بلغ النصاب ✓\nالزكاة (2.5%%): %s" % self.fmt(zakat)
             if grams >= nisab_g else
             "لم يبلغ النصاب — لا زكاة")
        )
        l = lbl(txt, halign="right", valign="top", font_size="15sp")
        l.bind(size=lambda w, *x: setattr(w, "text_size", (w.width, None)))
        bx.add_widget(l)
        p = self.popup("📐 حاسبة الزكاة", bx, size=(0.85, 0.6))
        bx.add_widget(btn("إغلاق", lambda *_: p.dismiss()))
        p.open()

    # ---------- مخطط اليوم ----------
    def open_chart(self, *a):
        bx = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        bx.add_widget(lbl("سعر الغرام خلال آخر 24 ساعة", size_hint_y=None,
                          height=dp(26), halign="center"))
        chart = PriceChart(self.s["price_history"])
        bx.add_widget(chart)
        hist = self.s["price_history"]
        if hist:
            mn = min(p[1] for p in hist)
            mx = max(p[1] for p in hist)
            bx.add_widget(lbl("أعلى: %.2f  |  أدنى: %.2f  |  عينات: %d"
                              % (mx, mn, len(hist)), size_hint_y=None, height=dp(26)))
        else:
            bx.add_widget(lbl("لا توجد بيانات بعد — حدّث السعر أكثر من مرة",
                              size_hint_y=None, height=dp(26)))
        p = self.popup("📈 مخطط اليوم", bx)
        bx.add_widget(btn("إغلاق", lambda *_: p.dismiss(), size_hint_y=None, height=dp(44)))
        p.open()


if __name__ == "__main__":
    try:
        GoldApp().run()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            with open(os.path.join(data_dir(), "last_crash.txt"), "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        print("GOLD_APP_CRASH:\n" + tb)
        raise

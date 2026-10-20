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
import ssl
import threading
import urllib.request
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
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle

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
    d = None
    try:
        from android.storage import app_storage_path  # noqa
        d = app_storage_path()
    except Exception:
        d = None
    if not d:
        d = os.path.join(os.path.expanduser("~"), ".gold_portfolio")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = "."
    return d


try:
    DATA_FILE = os.path.join(data_dir(), "gold_portfolio_data.json")
except Exception:
    DATA_FILE = "gold_portfolio_data.json"

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


GOLD = (0.902, 0.700, 0.133, 1)      # ذهبي
GOLD_D = (0.72, 0.54, 0.07, 1)
BG = (0.055, 0.063, 0.086, 1)        # خلفية داكنة
DARK = BG
CARD = (0.102, 0.118, 0.153, 1)      # بطاقة
CARD2 = (0.137, 0.157, 0.200, 1)
GREEN = (0.180, 0.800, 0.443, 1)
RED = (0.906, 0.298, 0.235, 1)
BLUE = (0.204, 0.596, 0.859, 1)
TEXT = (0.945, 0.953, 0.965, 1)
MUTE = (0.611, 0.639, 0.690, 1)


class Card(BoxLayout):
    """حاوية بخلفية مستديرة الزوايا."""
    def __init__(self, bg=CARD, radius=16, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._col = Color(*bg)
            self._rect = RoundedRectangle(radius=[radius])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size


class RoundButton(ButtonBehavior, Label):
    """زر بزوايا مستديرة."""
    def __init__(self, bg=GOLD, radius=14, **kw):
        super().__init__(**kw)
        self._bg = bg
        with self.canvas.before:
            self._col = Color(*bg)
            self._rect = RoundedRectangle(radius=[radius])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def on_state(self, *a):
        # تعتيم بسيط عند الضغط
        c = self._bg
        if self.state == "down":
            self._col.rgba = (c[0]*0.8, c[1]*0.8, c[2]*0.8, c[3])
        else:
            self._col.rgba = c


def lbl(text, **kw):
    kw = A(**kw)
    kw.setdefault("color", TEXT)
    return Label(text=ar(text), **kw)


def btn(text, cb, bg=GOLD, **kw):
    kw = A(**kw)
    kw.setdefault("color", (0.06, 0.06, 0.09, 1) if bg == GOLD else TEXT)
    kw.setdefault("bold", True)
    b = RoundButton(text=ar(text), bg=bg, **kw)
    b.bind(on_release=cb)
    return b


def styled_input(text="", **kw):
    kw.setdefault("multiline", False)
    kw.setdefault("size_hint_y", None)
    kw.setdefault("height", dp(46))
    i = TextInput(text=text, background_normal="", background_active="",
                  background_color=CARD2, foreground_color=TEXT,
                  cursor_color=GOLD, padding=(dp(12), dp(12)),
                  font_size="16sp", **kw)
    return i


class GoldApp(App):
    def build(self):
        # شبكة أمان: إن فشل بناء الواجهة نعرض الخطأ على الشاشة
        # بدل أن يُغلق التطبيق (شاشة سوداء + تكرار).
        try:
            return self._build_ui()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            try:
                with open(os.path.join(data_dir(), "last_crash.txt"), "w",
                          encoding="utf-8") as f:
                    f.write(tb)
            except Exception:
                pass
            print("GOLD_APP_CRASH:\n" + tb)
            # شاشة خطأ بخط افتراضي (بدون الخط العربي) لتظهر دائماً
            Window.clearcolor = (0, 0, 0, 1)
            sc = ScrollView()
            msg = Label(text="APP ERROR:\n\n" + tb, color=(1, 0.5, 0.5, 1),
                        font_size="12sp", size_hint_y=None, halign="left",
                        valign="top", padding=(dp(10), dp(10)))
            msg.bind(texture_size=lambda w, v: setattr(w, "height", v[1]),
                     width=lambda w, v: setattr(w, "text_size", (v, None)))
            sc.add_widget(msg)
            return sc

    def _build_ui(self):
        self.title = "Gold Portfolio"
        Window.clearcolor = BG
        self.s = load_state()
        # الصفحة بأكملها قابلة للتمرير لكي تظهر الواجهة كاملة
        root = ScrollView(do_scroll_x=False, bar_width=dp(4))
        col = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12),
                        size_hint_y=None)
        col.bind(minimum_height=col.setter("height"))
        root.add_widget(col)

        # ===== Header =====
        header = Card(bg=CARD, radius=18, orientation="vertical",
                      size_hint_y=None, height=dp(70), padding=(dp(16), dp(10)))
        header.add_widget(lbl("🏆  محفظة الذهب", font_size="24sp", bold=True,
                              color=GOLD, halign="right", valign="middle"))
        header.add_widget(lbl("إدارة استثمار الذهب بأسعار الراجحي", font_size="12sp",
                              color=MUTE, halign="right", valign="middle",
                              size_hint_y=None, height=dp(18)))
        for w in header.children:
            w.bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
        col.add_widget(header)

        # ===== أسعار الغرام =====
        pcard = Card(bg=CARD, radius=18, orientation="vertical",
                     size_hint_y=None, height=dp(228), padding=dp(14), spacing=dp(8))
        pcard.add_widget(lbl("أسعار الغرام (الراجحي)", font_size="14sp", bold=True,
                             color=GOLD, halign="right", size_hint_y=None, height=dp(24)))
        pcard.children[0].bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
        pr = GridLayout(cols=2, size_hint_y=None, height=dp(118), spacing=dp(8))
        pr.add_widget(lbl("سعر شراء الغرام (ريال)", font_size="13sp",
                          color=MUTE, halign="right", valign="middle"))
        self.in_buy = styled_input(text=str(self.s["buy_price"]), input_filter="float")
        pr.add_widget(self.in_buy)
        pr.add_widget(lbl("سعر بيع الغرام (ريال)", font_size="13sp",
                          color=MUTE, halign="right", valign="middle"))
        self.in_sell = styled_input(text=str(self.s["sell_price"]), input_filter="float")
        pr.add_widget(self.in_sell)
        for w in pr.children:
            if isinstance(w, Label):
                w.bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
        pcard.add_widget(pr)
        # زر جلب السعر اللحظي من الإنترنت
        self.live_btn = btn("🌐  جلب السعر اللحظي من الإنترنت",
                            self.fetch_live_price, bg=GOLD_D, color=TEXT,
                            size_hint_y=None, height=dp(44), font_size="13sp")
        pcard.add_widget(self.live_btn)
        col.add_widget(pcard)

        # ===== صف العملة + تحديث =====
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        self.cur = Spinner(text=self.s["currency"], values=list(CURRENCIES.keys()),
                           size_hint_x=0.32, background_normal="", background_color=CARD2,
                           color=TEXT, **A())
        self.cur.bind(text=lambda *a: self.refresh())
        row.add_widget(self.cur)
        row.add_widget(btn("💾  حفظ / تحديث السعر", self.update_price))
        col.add_widget(row)

        # ===== الملخص =====
        self.sum_card = Card(bg=CARD2, radius=18, orientation="vertical",
                             size_hint_y=None, height=dp(176), padding=dp(16), spacing=dp(6))
        col.add_widget(self.sum_card)

        # ===== أزرار العمليات =====
        ops = GridLayout(cols=3, size_hint_y=None, height=dp(50), spacing=dp(8))
        ops.add_widget(btn("➕ شراء", self.open_buy, bg=GREEN, font_size="14sp"))
        ops.add_widget(btn("➖ أمر بيع", self.open_sell, bg=RED, font_size="14sp"))
        ops.add_widget(btn("🔔 تنبيه", self.open_alert, bg=BLUE, font_size="14sp"))
        col.add_widget(ops)

        ops2 = GridLayout(cols=3, size_hint_y=None, height=dp(50), spacing=dp(8))
        ops2.add_widget(btn("📜 السجل", self.open_ledger, bg=CARD2, font_size="14sp"))
        ops2.add_widget(btn("📐 الزكاة", self.open_zakat, bg=CARD2, font_size="14sp"))
        ops2.add_widget(btn("📈 المخطط", self.open_chart, bg=CARD2, font_size="14sp"))
        col.add_widget(ops2)

        # ===== قائمة الدفعات =====
        col.add_widget(lbl("الدفعات المتبقية", font_size="15sp", bold=True, color=GOLD,
                           size_hint_y=None, height=dp(28), halign="right"))
        col.children[0].bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
        self.lots_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.lots_box.bind(minimum_height=self.lots_box.setter("height"))
        col.add_widget(self.lots_box)

        self.refresh()
        # جلب السعر اللحظي تلقائياً عند بدء التشغيل (صامت)
        Clock.schedule_once(lambda dt: self.fetch_live_price(silent=True), 1.0)
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
                  title_font=FONT if FONT else None, title_color=GOLD,
                  title_size="17sp", separator_color=GOLD,
                  background_color=(0, 0, 0, 0.6))
        return p

    def toast(self, msg):
        bx = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        bx.add_widget(lbl(msg, halign="right"))
        p = self.popup("تنبيه", bx, size=(0.8, 0.4))
        bx.add_widget(btn("حسناً", lambda *a: p.dismiss()))
        p.open()

    # ---------- السعر اللحظي من الإنترنت ----------
    def fetch_live_price(self, *a, **kw):
        """جلب سعر الذهب اللحظي (سبوت) وتعبئة حقلي السعر — في خيط منفصل."""
        self._silent = bool(kw.get("silent", False))
        try:
            self.live_btn.text = ar("… جارٍ جلب السعر")
        except Exception:
            pass
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        err = None
        gram_sar = 0.0
        url = "https://api.gold-api.com/price/XAU"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = None
        # محاولة عادية ثم سياق SSL غير متحقق (لبيانات عامة غير حساسة)
        try:
            raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
        except Exception:
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                raw = urllib.request.urlopen(req, timeout=20, context=ctx).read().decode("utf-8")
            except Exception as e:
                err = str(e)
        if raw is not None:
            try:
                data = json.loads(raw)
                usd_per_oz = float(data.get("price", 0))
                if usd_per_oz <= 0:
                    raise ValueError("no price")
                # أونصة → غرام (31.1035) ثم USD → SAR (1/0.2667 ≈ 3.75)
                usd_per_gram = usd_per_oz / 31.1035
                gram_sar = usd_per_gram / CURRENCIES["USD"]
            except Exception as e:
                err = str(e)
        Clock.schedule_once(lambda dt: self._apply_live_price(gram_sar, err), 0)

    def _apply_live_price(self, gram_sar, err):
        try:
            self.live_btn.text = ar("🌐  جلب السعر اللحظي من الإنترنت")
        except Exception:
            pass
        if err or gram_sar <= 0:
            if getattr(self, "_silent", False):
                return
            return self.toast("تعذّر جلب السعر — تأكد من اتصال الإنترنت")
        # سعر السبوت 24 قيراطاً (تقريبي) — يمكن تعديله يدوياً لسعر الراجحي
        val = round(gram_sar, 2)
        self.in_buy.text = str(val)
        self.in_sell.text = str(val)
        self.update_price()
        if not getattr(self, "_silent", False):
            self.toast("تم تحديث السعر اللحظي: %.2f ريال/غرام (سبوت 24ق)" % val)

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
    def _sum_row(self, label, value, color=TEXT, big=False):
        r = BoxLayout(size_hint_y=None, height=dp(34) if not big else dp(40))
        vl = lbl(value, font_size="18sp" if big else "15sp", bold=big, color=color,
                 halign="left", valign="middle")
        ll = lbl(label, font_size="13sp", color=MUTE, halign="right", valign="middle")
        vl.bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
        ll.bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
        r.add_widget(vl)
        r.add_widget(ll)
        return r

    def refresh(self):
        grams = self.total_grams()
        cost = sum(l["grams"] * l["price"] for l in self.s["lots"])
        cur_val = grams * self.s["sell_price"]
        unreal = cur_val - cost
        realized = sum(e.get("profit", 0) for e in self.s["ledger"] if e["type"] == "sell")
        # بطاقة الملخص
        self.sum_card.clear_widgets()
        self.sum_card.add_widget(self._sum_row("الرصيد", "%.3f غرام" % grams,
                                               color=GOLD, big=True))
        self.sum_card.add_widget(self._sum_row("تكلفة الشراء", self.fmt(cost)))
        self.sum_card.add_widget(self._sum_row("القيمة الحالية (بيع)", self.fmt(cur_val)))
        self.sum_card.add_widget(self._sum_row("ربح/خسارة غير محقق", self.fmt(unreal),
                                               color=GREEN if unreal >= 0 else RED))
        self.sum_card.add_widget(self._sum_row("ربح محقق", self.fmt(realized),
                                               color=GREEN if realized >= 0 else RED))
        # الدفعات
        self.lots_box.clear_widgets()
        if not self.s["lots"]:
            empty = Card(bg=CARD, radius=14, size_hint_y=None, height=dp(44),
                         padding=dp(10))
            empty.add_widget(lbl("لا توجد دفعات", color=MUTE, halign="center",
                                 valign="middle"))
            self.lots_box.add_widget(empty)
        for i, l in enumerate(self.s["lots"]):
            c = Card(bg=CARD, radius=14, size_hint_y=None, height=dp(52),
                     padding=(dp(14), dp(6)))
            g = lbl("%.3f غرام" % l["grams"], font_size="15sp", bold=True,
                    color=GOLD, halign="left", valign="middle")
            d = lbl("%s  •  @ %.2f ريال" % (l.get("date", ""), l["price"]),
                    font_size="12sp", color=MUTE, halign="right", valign="middle")
            g.bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
            d.bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
            c.add_widget(g)
            c.add_widget(d)
            self.lots_box.add_widget(c)

    # ---------- شراء ----------
    def open_buy(self, *a):
        bx = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        bx.add_widget(lbl("الكمية (غرام):", halign="right", size_hint_y=None, height=dp(26)))
        g = styled_input(input_filter="float")
        bx.add_widget(g)
        bx.add_widget(lbl("سعر الشراء للغرام (ريال):", halign="right",
                          size_hint_y=None, height=dp(26)))
        pr = styled_input(text=str(self.s["buy_price"]), input_filter="float")
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
        g = styled_input(input_filter="float")
        bx.add_widget(g)
        bx.add_widget(lbl("سعر البيع للغرام (الراجحي - ريال):", halign="right",
                          size_hint_y=None, height=dp(26)))
        pr = styled_input(text=str(self.s["sell_price"]), input_filter="float")
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
        v = styled_input(text=str(self.s.get("alert_price", 0)), input_filter="float")
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
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        box.bind(minimum_height=box.setter("height"))
        if not self.s["ledger"]:
            box.add_widget(lbl("السجل فارغ", size_hint_y=None, height=dp(30), color=MUTE))
        for e in reversed(self.s["ledger"]):
            if e["type"] == "buy":
                t = "➕ شراء | %s | %.3fغ @ %.2f = %.2f" % (
                    e["date"], e["grams"], e["price"], e["value"])
                c = TEXT
                bg = CARD
            else:
                t = "➖ بيع | %s | %.3fغ @ %.2f | ربح: %.2f" % (
                    e["date"], e["grams"], e["price"], e.get("profit", 0))
                c = GREEN if e.get("profit", 0) >= 0 else RED
                bg = CARD2
            card = Card(bg=bg, radius=12, size_hint_y=None, height=dp(42),
                        padding=(dp(12), dp(4)))
            il = lbl(t, halign="right", valign="middle", font_size="12sp", color=c)
            il.bind(size=lambda x, *a: setattr(x, "text_size", (x.width, None)))
            card.add_widget(il)
            box.add_widget(card)
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
        bx = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        card = Card(bg=CARD2, radius=16, orientation="vertical", padding=dp(16))
        txt = (
            "الرصيد: %.3f غرام\n" % grams +
            "النصاب: %.0f غرام\n" % nisab_g +
            "القيمة الحالية: %s\n\n" % self.fmt(value) +
            ("بلغ النصاب ✓\nالزكاة (2.5%%): %s" % self.fmt(zakat)
             if grams >= nisab_g else
             "لم يبلغ النصاب — لا زكاة")
        )
        l = lbl(txt, halign="right", valign="top", font_size="16sp", color=TEXT)
        l.bind(size=lambda w, *x: setattr(w, "text_size", (w.width, None)))
        card.add_widget(l)
        bx.add_widget(card)
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

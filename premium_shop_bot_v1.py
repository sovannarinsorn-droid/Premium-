# -*- coding: utf-8 -*-
"""
Kairozen Premium Account Shop Bot
----------------------------------
លក់ account premium (ChatGPT, Netflix, Spotify, Office365, Canva ...) តាម Telegram
- Stock គ្រប់គ្រងតាមឯកសារ .txt (មួយបន្ទាត់ = account មួយ)
- ប្រព័ន្ធ Wallet (deposit លុយចូល -> ទិញអីវ៉ាន់ចេញ)
- KHQR deposit តាម CamRapidPay + auto-polling
- Admin panel: បន្ថែម product / បន្ថែម stock / មើលស្ថិតិ / broadcast

ត្រូវការ Environment Variables:
  BOT_TOKEN            - Telegram Bot Token
  ADMIN_ID             - Telegram user id របស់ admin (លេខ)
  CAMRAPIDPAY_API_KEY  - API key របស់ CamRapidPay
  CAMRAPIDPAY_BASE_URL - (default: https://api.camrapidpay.com) កែតាមឯកសារពិត
"""

import os
import re
import io
import json
import time
import hashlib
import threading
import requests
import telebot
from telebot import types
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    KH_TZ = ZoneInfo("Asia/Phnom_Penh")
except Exception:
    KH_TZ = None


def now_kh():
    """ម៉ោងបច្ចុប្បន្នតាមម៉ោងកម្ពុជា (ICT, UTC+7) ដោយមិនអាស្រ័យលើ timezone server (Render = UTC)"""
    if KH_TZ:
        return datetime.now(KH_TZ)
    return datetime.utcnow()  # fallback បើ zoneinfo មិនមាន (Python < 3.9)


def kh_time_str(fmt="%Y-%m-%d %H:%M"):
    return now_kh().strftime(fmt)

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CAMRAPIDPAY_API_KEY = os.environ.get("CAMRAPIDPAY_API_KEY", "")
CAMRAPID_CREATE = os.environ.get("CAMRAPID_CREATE_URL", "https://pay.camrapidpay.com/api/v1/khqr/create-payments")
CAMRAPID_CHECK = os.environ.get("CAMRAPID_CHECK_URL", "https://pay.camrapidpay.com/check-transaction-api")
STORE_NAME = os.environ.get("STORE_NAME", "Kairozen Premium Shop")

DATA_DIR = os.environ.get("DATA_DIR", "data")
STOCK_DIR = os.path.join(DATA_DIR, "stock")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
EMOJI_FILE = os.path.join(DATA_DIR, "premium_emoji.json")

os.makedirs(STOCK_DIR, exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ------------------------------------------------------------------
# PREMIUM EMOJI SYSTEM (Bot API 9.4+, ត្រូវការ Telegram Premium)
# ------------------------------------------------------------------
# admin ភ្ជាប់ custom_emoji_id មួយ ទៅនឹង glyph unicode មួយ (ឧ. ✅) ដងតែម្តង
# ចាប់ពីនោះ glyph នេះនៅត្រង់ណាក៏ដោយ (ប៊ូតុង ឬ អត្ថបទសារ) នឹងបង្ហាញ icon premium
# ដោយស្វ័យប្រវត្តិ — emoji ធម្មតានៅតែមាន មិនត្រូវជំនួសទេ។
EMOJI_CATEGORIES = [
    ("✅", "✅ ជោគជ័យ / ទិញ / បញ្ជាក់"),
    ("❌", "❌ បោះបង់ / លុប / អស់ស្តុក"),
    ("🔙", "🔙 ត្រឡប់ក្រោយ"),
    ("➕", "➕ បន្ថែម"),
    ("📦", "📦 ផលិតផល"),
    ("📊", "📊 ស្ថិតិ"),
    ("💰", "💰 កាបូបលុយ"),
    ("💳", "💳 ការទូទាត់"),
    ("🛒", "🛒 ទិញ Account"),
    ("📥", "📥 Stock"),
    ("🔑", "🔑 Account/Key"),
    ("⏳", "⏳ កំពុងរង់ចាំ"),
    ("⚠️", "⚠️ ប្រុងប្រយ័ត្ន"),
    ("🔔", "🔔 ជូនដំណឹង"),
    ("📢", "📢 Broadcast"),
    ("☎️", "☎️ ទំនាក់ទំនង"),
]


def get_emoji_map():
    return _load(EMOJI_FILE, {})


def save_emoji_map(m):
    _save(EMOJI_FILE, m)


def _html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def message_to_html(message):
    """បំលែង message.text + message.entities (Bold, Italic, Custom Emoji ។ល។)
    ទៅជា HTML ដើម្បីរក្សាទុក premium emoji ដែល admin វាយ/ផ្ញើផ្ទាល់ក្នុងសារ
    (offset/length របស់ entity គិតជា UTF-16 code units តាមស្តង់ដារ Telegram)។"""
    text = message.text or ""
    entities = message.entities or []
    if not entities:
        return _html_escape(text)

    units = text.encode("utf-16-le")

    def sl(a, b):
        return units[a * 2: b * 2].decode("utf-16-le")

    def wrap(e, inner):
        t = e.type
        if t == "bold":
            return f"<b>{inner}</b>"
        if t == "italic":
            return f"<i>{inner}</i>"
        if t == "underline":
            return f"<u>{inner}</u>"
        if t == "strikethrough":
            return f"<s>{inner}</s>"
        if t == "spoiler":
            return f"<tg-spoiler>{inner}</tg-spoiler>"
        if t == "code":
            return f"<code>{inner}</code>"
        if t == "pre":
            lang = getattr(e, "language", None)
            return f'<pre><code class="language-{lang}">{inner}</code></pre>' if lang else f"<pre>{inner}</pre>"
        if t == "text_link":
            return f'<a href="{e.url}">{inner}</a>'
        if t == "custom_emoji":
            return f'<tg-emoji emoji-id="{e.custom_emoji_id}">{inner}</tg-emoji>'
        return inner

    ents = sorted(entities, key=lambda e: (e.offset, -e.length))

    def build(start, end, pool):
        out = []
        pos = start
        i = 0
        while i < len(pool):
            e = pool[i]
            if e.offset < pos:
                i += 1
                continue
            if e.offset >= end:
                break
            if e.offset > pos:
                out.append(_html_escape(sl(pos, e.offset)))
            e_end = e.offset + e.length
            children = []
            j = i + 1
            while j < len(pool) and pool[j].offset < e_end:
                children.append(pool[j])
                j += 1
            inner = build(e.offset, e_end, children)
            out.append(wrap(e, inner))
            pos = e_end
            i = j
        if pos < end:
            out.append(_html_escape(sl(pos, end)))
        return "".join(out)

    total_units = len(units) // 2
    return build(0, total_units, ents)


def premium_text(text):
    """ជំនួស glyph ធម្មតា (ឧ. ✅) ដោយ HTML <tg-emoji> tag បើមាន custom_emoji_id
    កំណត់ទុករួច។ ត្រូវការសារផ្ញើជា parse_mode HTML (ជា default របស់ bot នេះរួចហើយ)។"""
    if not text:
        return text
    m = get_emoji_map()
    if not m:
        return text
    for glyph, info in m.items():
        icon_id = info.get("custom_emoji_id")
        if icon_id and glyph in text:
            text = text.replace(glyph, f'<tg-emoji emoji-id="{icon_id}">{glyph}</tg-emoji>')
    return text


def emoji_icon_for(text):
    """រកមើលថាតើ text (ជាធម្មតាជា label ប៊ូតុង) មាន glyph ណាមួយដែលកំណត់ icon រួច — return custom_emoji_id ដំបូងដែលរកឃើញ"""
    m = get_emoji_map()
    if not m:
        return None
    for glyph, _label in EMOJI_CATEGORIES:
        if glyph in text and glyph in m:
            icon_id = m[glyph].get("custom_emoji_id")
            if icon_id:
                return icon_id
    return None


def pbtn(text, callback_data=None, style=None, url=None, **kw):
    """InlineKeyboardButton ជាមួយ icon premium (បើមាន) + style ពណ៌ (success/danger)"""
    icon_id = emoji_icon_for(text)
    attempts = []
    if style and icon_id:
        attempts.append({"style": style, "icon_custom_emoji_id": icon_id})
    if icon_id:
        attempts.append({"icon_custom_emoji_id": icon_id})
    if style:
        attempts.append({"style": style})
    attempts.append({})
    for extra in attempts:
        try:
            return types.InlineKeyboardButton(text, callback_data=callback_data, url=url, **extra, **kw)
        except TypeError:
            continue
    return types.InlineKeyboardButton(text, callback_data=callback_data, url=url, **kw)


def preply_btn(text, **kw):
    """KeyboardButton (reply keyboard) ជាមួយ icon premium (បើមាន)"""
    icon_id = emoji_icon_for(text)
    if icon_id:
        try:
            return types.KeyboardButton(text, icon_custom_emoji_id=icon_id, **kw)
        except TypeError:
            pass
    return types.KeyboardButton(text, **kw)


# --- Auto-apply premium_text() លើសារគ្រប់ប្រភេទដែល bot ផ្ញើ ---
# Monkey-patch send_message / reply_to / edit_message_text / send_photo(caption)
# ដើម្បីកុំបំបែក code ចាស់ៗនៅកន្លែងផ្សេងទៀត — គ្រប់ bot.send_message(...) ដែលមានស្រាប់
# នៅតែដំណើរការធម្មតា ប៉ុន្តែ glyph ណាដែលកំណត់ icon premium រួច នឹងបង្ហាញស្វ័យប្រវត្តិ។
_orig_send_message = bot.send_message
_orig_reply_to = bot.reply_to
_orig_edit_message_text = bot.edit_message_text
_orig_send_photo = bot.send_photo


def _patched_send_message(chat_id, text=None, *args, **kwargs):
    return _orig_send_message(chat_id, premium_text(text), *args, **kwargs)


def _patched_reply_to(message, text=None, *args, **kwargs):
    return _orig_reply_to(message, premium_text(text), *args, **kwargs)


def _patched_edit_message_text(text=None, *args, **kwargs):
    return _orig_edit_message_text(premium_text(text), *args, **kwargs)


def _patched_send_photo(chat_id, photo, caption=None, *args, **kwargs):
    return _orig_send_photo(chat_id, photo, premium_text(caption), *args, **kwargs)


bot.send_message = _patched_send_message
bot.reply_to = _patched_reply_to
bot.edit_message_text = _patched_edit_message_text
bot.send_photo = _patched_send_photo

# ------------------------------------------------------------------
# STORAGE HELPERS
# ------------------------------------------------------------------
_lock = threading.Lock()


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_users():
    return _load(USERS_FILE, {})


def save_users(d):
    _save(USERS_FILE, d)


def load_products():
    # default product catalogue - admin អាចកែ/បន្ថែមតាម /addproduct
    default = {
        "chatgpt": {"name": "ChatGPT Plus 1 Month", "price": 8.0, "icon": "🤖"},
        "netflix": {"name": "Netflix Premium 1 Month", "price": 5.0, "icon": "🎬"},
        "spotify": {"name": "Spotify Premium 1 Month", "price": 3.0, "icon": "🎧"},
        "office365": {"name": "Office 365 1 Year", "price": 10.0, "icon": "📘"},
        "canva": {"name": "Canva Pro 1 Month", "price": 4.0, "icon": "🎨"},
    }
    return _load(PRODUCTS_FILE, default)


def save_products(d):
    _save(PRODUCTS_FILE, d)


def load_orders():
    return _load(ORDERS_FILE, [])


def save_orders(d):
    _save(ORDERS_FILE, d)


def get_user(uid):
    users = load_users()
    uid = str(uid)
    if uid not in users:
        users[uid] = {"balance": 0.0, "orders": 0}
        save_users(users)
    return users[uid]


def update_balance(uid, delta):
    with _lock:
        users = load_users()
        uid = str(uid)
        if uid not in users:
            users[uid] = {"balance": 0.0, "orders": 0}
        users[uid]["balance"] = round(users[uid]["balance"] + delta, 2)
        save_users(users)
        return users[uid]["balance"]


def stock_path(product_key):
    return os.path.join(STOCK_DIR, f"{product_key}.txt")


def stock_count(product_key):
    p = stock_path(product_key)
    if not os.path.exists(p):
        return 0
    with open(p, "r", encoding="utf-8") as f:
        return len([l for l in f if l.strip()])


def pop_stock_item(product_key):
    """យក account មួយចេញពី stock (FIFO), atomic-ish with lock."""
    with _lock:
        p = stock_path(product_key)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        if not lines:
            return None
        item = lines[0].strip()
        remaining = lines[1:]
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(remaining)
        return item


def push_stock_items(product_key, items):
    p = stock_path(product_key)
    with _lock:
        with open(p, "a", encoding="utf-8") as f:
            for it in items:
                it = it.strip()
                if it:
                    f.write(it + "\n")


# ------------------------------------------------------------------
# CAMRAPIDPAY (KHQR) INTEGRATION — endpoint/field ត្រឹមត្រូវ
# ------------------------------------------------------------------
_http = requests.Session()
_http.mount("https://", requests.adapters.HTTPAdapter(
    max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5)
))


def camrapid_create(amount, reference):
    """POST ទៅ CamRapidPay ដើម្បីបង្កើត KHQR → return dict ឬ None"""
    try:
        r = _http.post(
            CAMRAPID_CREATE,
            json={
                "api_key": CAMRAPIDPAY_API_KEY,
                "amount": round(float(amount), 2),
                "reference": reference,
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        data = r.json()
        if data.get("success"):
            return data  # keys: qr_code, payment_url, amount, expires_in
        print(f"[camrapid_create] failed: {data}")
    except Exception as e:
        print(f"[camrapid_create] error: {e}")
    return None


def camrapid_check(reference):
    """GET check → True ប្រសិនបើបានបង់"""
    try:
        r = _http.get(
            CAMRAPID_CHECK,
            params={"api_key": CAMRAPIDPAY_API_KEY, "reference": reference},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        data = r.json()
        return bool(data.get("success")) and data.get("status", "").lower() in ("success", "paid")
    except Exception as e:
        print(f"[camrapid_check] error: {e}")
    return False


# ------------------------------------------------------------------
# KHQR CARD GENERATOR (styled card, requires: pip install qrcode Pillow numpy)
# ------------------------------------------------------------------
_CARD_NAVY = (13, 18, 38)
_CARD_NAVY2 = (30, 27, 75)
_CARD_RED = (229, 29, 39)
_CARD_WHITE = (255, 255, 255)
_CARD_SUBTITLE = (191, 196, 234)
_CARD_GRAY = (104, 110, 128)
_CARD_MUTED = (139, 140, 144)
_CARD_GOLD = (245, 197, 66)
_CARD_VIOLET = (124, 92, 255)
_CARD_PANEL = (250, 250, 252)

_FONT_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/system/fonts/Roboto-Regular.ttf",
    "/data/data/com.termux/files/usr/share/fonts/DejaVuSans.ttf",
]
_FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/system/fonts/Roboto-Bold.ttf",
    "/data/data/com.termux/files/usr/share/fonts/DejaVuSans-Bold.ttf",
]


def _card_font(size, bold=False):
    from PIL import ImageFont
    for path in (_FONT_BOLD if bold else _FONT_REG):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _tw(draw, text, font):
    return draw.textbbox((0, 0), text, font=font)[2]


def _cx_text(draw, cx, y, text, font, fill):
    draw.text((cx - _tw(draw, text, font) / 2, y), text, font=font, fill=fill)


def _vgrad(draw, box, top_color, bottom_color):
    x0, y0, x1, y1 = box
    h = max(1, y1 - y0)
    for i in range(h):
        t = i / h
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.line([(x0, y0 + i), (x1, y0 + i)], fill=(r, g, b))


def _qr_matrix(data):
    import numpy as np
    import qrcode as _qrcode
    qr = _qrcode.QRCode(border=0, error_correction=_qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    m = qr.get_matrix()
    return np.array([[0 if c else 255 for c in row] for row in m], dtype=np.uint8)


def _qr_img(data, box_px):
    from PIL import Image, ImageDraw
    matrix = _qr_matrix(data)
    n = matrix.shape[0]
    mod = max(1, box_px // n)
    img = Image.new("RGB", (mod * n, mod * n), _CARD_PANEL)
    draw = ImageDraw.Draw(img)
    for ry in range(n):
        for rx in range(n):
            if matrix[ry, rx] == 0:
                x0, y0 = rx * mod, ry * mod
                draw.rectangle([x0, y0, x0 + mod - 1, y0 + mod - 1], fill=_CARD_NAVY)
    return img.resize((box_px, box_px), Image.LANCZOS)


def build_qr_image(qr_string, amount=None, ref=None, label=None, subtitle=None, expires_min=5, width=720):
    """បង្កើត branded KHQR card (Bakong-style) → BytesIO (PNG)។ Fallback ទៅ QR ធម្មតាបើមានបញ្ហា។"""
    from PIL import Image, ImageDraw
    try:
        W = width
        HEADER_H = int(W * 0.30)
        SIDE_PAD = int(W * 0.13)
        QR_BOX = W - 2 * SIDE_PAD
        QR_PAD = int(QR_BOX * 0.09)
        OVERLAP = int(W * 0.10)

        f_title = _card_font(int(W * 0.052), bold=True)
        f_sub = _card_font(int(W * 0.026))
        f_name = _card_font(int(W * 0.042), bold=True)
        f_label = _card_font(int(W * 0.024))
        f_amt = _card_font(int(W * 0.062), bold=True)
        f_small = _card_font(int(W * 0.0205))
        f_badge = _card_font(int(W * 0.0195), bold=True)

        qr_card_top = HEADER_H - OVERLAP
        qr_card_bottom = qr_card_top + QR_BOX
        content_top = qr_card_bottom + int(W * 0.05)

        amt_h = int(f_amt.size * 1.5)
        gap1, gap2 = int(W * 0.022), int(W * 0.035)
        bottom_pad = int(W * 0.05)

        H = (content_top + int(W * 0.065) + int(W * 0.04) + gap1 + amt_h + gap2
             + int(W * 0.03) + int(W * 0.03) + int(W * 0.03) + int(W * 0.03) + bottom_pad)

        img = Image.new("RGB", (W, H), _CARD_WHITE)
        draw = ImageDraw.Draw(img)
        cx = W // 2
        pad = int(W * 0.06)

        _vgrad(draw, [0, 0, W, HEADER_H], _CARD_NAVY, _CARD_NAVY2)

        ring_r = int(W * 0.32)
        ring_cx, ring_cy = W - int(W * 0.05), int(W * 0.02)
        draw.ellipse([ring_cx - ring_r, ring_cy - ring_r, ring_cx + ring_r, ring_cy + ring_r],
                     outline=(255, 255, 255), width=1)

        draw.text((pad, int(W * 0.045)), "KHQR", font=f_title, fill=_CARD_WHITE)
        draw.text((pad, int(W * 0.045) + f_title.size + int(W * 0.010)),
                  "Cambodian QR Payment · Bakong", font=f_sub, fill=_CARD_SUBTITLE)

        badge_txt = "★ PREMIUM"
        bw = _tw(draw, badge_txt, f_badge)
        bpad_x, bpad_y = int(W * 0.020), int(W * 0.011)
        bx1 = W - pad
        bx0 = bx1 - bw - bpad_x * 2
        by0 = int(W * 0.045)
        by1 = by0 + f_badge.size + bpad_y * 2
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=(by1 - by0) // 2, fill=_CARD_GOLD)
        draw.text((bx0 + bpad_x, by0 + bpad_y - int(W * 0.003)), badge_txt, font=f_badge, fill=_CARD_NAVY)

        r = int(W * 0.045)
        panel_box = [SIDE_PAD, qr_card_top, SIDE_PAD + QR_BOX, qr_card_bottom]
        shadow_off = int(W * 0.012)
        draw.rounded_rectangle(
            [panel_box[0] + shadow_off, panel_box[1] + shadow_off,
             panel_box[2] + shadow_off, panel_box[3] + shadow_off],
            radius=r, fill=(225, 227, 235))
        draw.rounded_rectangle(panel_box, radius=r, fill=_CARD_WHITE)

        qr_px = QR_BOX - 2 * QR_PAD
        qr_pil = _qr_img(qr_string, qr_px)
        img.paste(qr_pil, (SIDE_PAD + QR_PAD, qr_card_top + QR_PAD))

        bl = int(W * 0.055)
        bt = max(3, int(W * 0.007))
        bo = int(W * 0.018)
        x0, y0, x1, y1 = panel_box
        corners = [
            ((x0 + bo, y0 + bo + bl), (x0 + bo, y0 + bo), (x0 + bo + bl, y0 + bo)),
            ((x1 - bo - bl, y0 + bo), (x1 - bo, y0 + bo), (x1 - bo, y0 + bo + bl)),
            ((x0 + bo, y1 - bo - bl), (x0 + bo, y1 - bo), (x0 + bo + bl, y1 - bo)),
            ((x1 - bo - bl, y1 - bo), (x1 - bo, y1 - bo), (x1 - bo, y1 - bo - bl)),
        ]
        for pts in corners:
            draw.line(pts, fill=_CARD_VIOLET, width=bt, joint="curve")

        y = content_top
        store_label = label or STORE_NAME
        _cx_text(draw, cx, y, store_label, f_name, _CARD_NAVY)
        y += int(W * 0.065)
        _cx_text(draw, cx, y, subtitle or STORE_NAME, f_label, _CARD_GRAY)
        y += int(W * 0.04) + gap1

        if amount is not None:
            amt_str = f"${float(amount):.2f}"
            banner_box = [pad, y, W - pad, y + amt_h]
            draw.rounded_rectangle(banner_box, radius=int(W * 0.02), fill=(243, 241, 255))
            draw.rounded_rectangle(banner_box, radius=int(W * 0.02), outline=_CARD_VIOLET, width=2)
            _cx_text(draw, cx, y + (amt_h - f_amt.size) // 2 - int(W * 0.010), amt_str, f_amt, _CARD_NAVY2)
            y += amt_h + gap2

        if ref:
            _cx_text(draw, cx, y, f"Ref: {ref}", f_small, _CARD_MUTED)
            y += int(W * 0.03)
        if expires_min:
            _cx_text(draw, cx, y, f"Expires in {expires_min} minutes", f_small, _CARD_RED)
            y += int(W * 0.03)
        _cx_text(draw, cx, y, "Scan with any Bakong-member app", f_small, _CARD_MUTED)
        y += int(W * 0.03)
        _cx_text(draw, cx, y, "ABA · ACLEDA · Wing", f_small, _CARD_MUTED)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        buf.name = "khqr_card.png"
        return buf

    except Exception as e:
        print(f"[build_qr_image] {e}")
        try:
            import qrcode as _qrcode
            qr = _qrcode.QRCode(box_size=8, border=2, error_correction=_qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(qr_string)
            qr.make(fit=True)
            pil = qr.make_image(fill_color=(10, 34, 64), back_color="white").convert("RGB")
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            buf.seek(0)
            buf.name = "khqr.png"
            return buf
        except Exception:
            return None


_CARD_GREEN = (22, 163, 74)
_CARD_GREEN2 = (5, 105, 45)


def build_receipt_image(product_name, icon, price, order_id, width=720, buyer_note=None):
    """បង្កើត Receipt Card ស្អាតៗ (green gradient header) បញ្ជាក់ការទិញជោគជ័យ។
    Fallback ទៅ None បើមានបញ្ហា (caller គួរមានផែនការបម្រុងជាអត្ថបទវិញ)។"""
    from PIL import Image, ImageDraw
    try:
        W = width
        HEADER_H = int(W * 0.34)

        f_title = _card_font(int(W * 0.052), bold=True)
        f_sub = _card_font(int(W * 0.026))
        f_icon = _card_font(int(W * 0.13))
        f_name = _card_font(int(W * 0.044), bold=True)
        f_label = _card_font(int(W * 0.026))
        f_amt = _card_font(int(W * 0.075), bold=True)
        f_small = _card_font(int(W * 0.0215))

        pad = int(W * 0.07)
        icon_circle_r = int(W * 0.10)
        content_top = HEADER_H + icon_circle_r + int(W * 0.05)

        row_h = int(W * 0.055)
        H = content_top + int(W * 0.05) + int(W * 0.06) + int(W * 0.10) + row_h * 3 + int(W * 0.10)

        img = Image.new("RGB", (W, H), _CARD_WHITE)
        draw = ImageDraw.Draw(img)
        cx = W // 2

        _vgrad(draw, [0, 0, W, HEADER_H], _CARD_GREEN, _CARD_GREEN2)
        _cx_text(draw, cx, int(W * 0.06), "✅ PAYMENT SUCCESS", f_title, _CARD_WHITE)
        _cx_text(draw, cx, int(W * 0.06) + f_title.size + int(W * 0.012), STORE_NAME, f_sub, (222, 247, 232))

        icon_cy = HEADER_H
        draw.ellipse(
            [cx - icon_circle_r, icon_cy - icon_circle_r, cx + icon_circle_r, icon_cy + icon_circle_r],
            fill=_CARD_WHITE, outline=_CARD_GREEN, width=int(W * 0.008),
        )
        try:
            ib = draw.textbbox((0, 0), icon, font=f_icon)
            draw.text((cx - (ib[2] - ib[0]) / 2, icon_cy - (ib[3] - ib[1]) / 2 - ib[1]), icon, font=f_icon, fill=_CARD_NAVY)
        except Exception:
            pass

        y = content_top
        _cx_text(draw, cx, y, product_name, f_name, _CARD_NAVY)
        y += int(W * 0.06)

        amt_str = f"${float(price):.2f}"
        _cx_text(draw, cx, y, amt_str, f_amt, _CARD_GREEN)
        y += int(W * 0.10)

        draw.line([(pad, y), (W - pad, y)], fill=(230, 232, 238), width=2)
        y += int(W * 0.035)

        rows = [("🔖 Order ID", order_id), ("📅 Date", kh_time_str())]
        if buyer_note:
            rows.append(("👤 Buyer", str(buyer_note)))
        for label, val in rows:
            draw.text((pad, y), label, font=f_label, fill=_CARD_GRAY)
            vw = _tw(draw, val, f_label)
            draw.text((W - pad - vw, y), val, font=f_label, fill=_CARD_NAVY)
            y += row_h

        y += int(W * 0.02)
        _cx_text(draw, cx, y, "Thank you for your purchase 💚", f_small, _CARD_MUTED)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        buf.name = "receipt.png"
        return buf
    except Exception as e:
        print(f"[build_receipt_image] {e}")
        return None


def poll_deposit(uid, chat_id, amount, reference, max_minutes=5):
    """Background thread ដើម្បី poll ការទូទាត់ រហូតដល់ PAID ឬ timeout។"""
    deadline = time.time() + max_minutes * 60
    while time.time() < deadline:
        if camrapid_check(reference):
            new_balance = update_balance(uid, amount)
            try:
                bot.send_message(
                    chat_id,
                    f"✅ ការទូទាត់ជោគជ័យ! បញ្ចូល <b>${amount:.2f}</b> ចូល wallet។\n"
                    f"💰 សមតុល្យថ្មី: <b>${new_balance:.2f}</b>",
                )
            except Exception:
                pass
            return
        time.sleep(8)
    try:
        bot.send_message(chat_id, "⌛ QR ផុតកំណត់ ឬមិនទាន់ទូទាត់។ សូមព្យាយាមម្តងទៀត /deposit")
    except Exception:
        pass


# ------------------------------------------------------------------
# UI HELPERS
# ------------------------------------------------------------------
def main_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🛒 ទិញ Account", callback_data="menu_shop"),
        types.InlineKeyboardButton("💰 Wallet", callback_data="menu_wallet"),
    )
    kb.add(
        types.InlineKeyboardButton("📦 ការកម្មង់របស់ខ្ញុំ", callback_data="menu_orders"),
        types.InlineKeyboardButton("☎️ ទំនាក់ទំនង Admin", url="tg://user?id=%d" % ADMIN_ID),
    )
    return kb


def safe_button(label, callback_data, style=None):
    """បង្កើត InlineKeyboardButton ដោយសាកល្បង style (Bot API 9.4) មុន បើ library ចាស់មិនស្គាល់ style
    នឹង fallback ទៅប៊ូតុងធម្មតាវិញ ដើម្បីកុំឲ្យ bot crash។"""
    if style:
        try:
            return types.InlineKeyboardButton(label, callback_data=callback_data, style=style)
        except TypeError:
            pass
    return types.InlineKeyboardButton(label, callback_data=callback_data)


def products_kb():
    products = load_products()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, p in products.items():
        left = stock_count(key)
        icon = p.get("icon", "📦")
        if left > 0:
            label = f"{icon} {p['name'].upper()} - ${p['price']:.2f}"
            btn = safe_button(label, f"buy_{key}", style="success")
        else:
            label = f"× {icon} {p['name'].upper()} - អស់ស្តុក"
            btn = safe_button(label, f"nostock_{key}", style="danger")
        kb.add(btn)
    kb.add(types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back_main"))
    return kb


def deposit_amount_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    amounts = [2, 5, 10, 20, 50]
    kb.add(*[types.InlineKeyboardButton(f"${a}", callback_data=f"dep_{a}") for a in amounts])
    kb.add(types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back_main"))
    return kb


# --- Reply Keyboard (ប៊ូតុងខាងក្រោមអេក្រង់, នៅជាប់ជានិច្ច) ---
BTN_SHOP = "🛒 ទិញ Account"
BTN_WALLET = "💰 Wallet"
BTN_DEPOSIT = "➕ បញ្ចូលលុយ"
BTN_ORDERS = "📦 ការកម្មង់"
BTN_HELP = "☎️ ជួយខ្ញុំផង"

ADMIN_BTN_STATS = "📊 ស្ថិតិ"
ADMIN_BTN_ADDPRODUCT = "➕ Product ថ្មី"
ADMIN_BTN_EDITPRODUCT = "✏️ កែ Product"
ADMIN_BTN_ADDSTOCK = "📥 Stock ថ្មី"
ADMIN_BTN_EMOJI = "🎭 Setup Emoji"
ADMIN_BTN_MESSAGE = "✉️ ផ្ញើសារ"
ADMIN_BTN_BROADCAST = "📢 ផ្ញើទាំងអស់"


def main_reply_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(preply_btn(BTN_SHOP), preply_btn(BTN_WALLET))
    kb.add(preply_btn(BTN_DEPOSIT), preply_btn(BTN_ORDERS))
    kb.add(preply_btn(BTN_HELP))
    return kb


def admin_reply_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(preply_btn(BTN_SHOP), preply_btn(BTN_WALLET))
    kb.add(preply_btn(BTN_DEPOSIT), preply_btn(BTN_ORDERS))
    kb.add(preply_btn(ADMIN_BTN_STATS), preply_btn(ADMIN_BTN_ADDPRODUCT))
    kb.add(preply_btn(ADMIN_BTN_EDITPRODUCT), preply_btn(ADMIN_BTN_ADDSTOCK))
    kb.add(preply_btn(ADMIN_BTN_EMOJI), preply_btn(ADMIN_BTN_MESSAGE))
    kb.add(preply_btn(ADMIN_BTN_BROADCAST))
    return kb


def reply_kb_for(uid):
    return admin_reply_kb() if uid == ADMIN_ID else main_reply_kb()


# ------------------------------------------------------------------
# USER COMMANDS
# ------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    get_user(message.from_user.id)
    text = (
        "👋 សូមស្វាគមន៍មកកាន់ <b>Kairozen Premium Shop</b>!\n\n"
        "🛒 ជ្រើសរើស account premium ដែលអ្នកចង់បាន ហើយទូទាត់ដោយ KHQR។\n"
        "សូមប្រើប៊ូតុងខាងក្រោមដើម្បីចាប់ផ្តើម:"
    )
    # ផ្ញើ reply keyboard (ប៊ូតុងខាងក្រោមអេក្រង់) ជាមុនសិន
    bot.send_message(message.chat.id, "🏠 ម៉ឺនុយសំខាន់ៗនៅខាងក្រោម 👇", reply_markup=reply_kb_for(message.from_user.id))
    # បន្ទាប់មកផ្ញើ inline keyboard សម្រាប់សកម្មភាពលម្អិត
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())


@bot.message_handler(commands=["wallet"])
def cmd_wallet(message):
    u = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"💰 សមតុល្យបច្ចុប្បន្ន: <b>${u['balance']:.2f}</b>\n"
        f"ការកម្មង់សរុប: {u['orders']}\n\n"
        f"ចង់បញ្ចូលលុយ? ចុច /deposit",
    )


@bot.message_handler(commands=["deposit"])
def cmd_deposit(message):
    bot.send_message(
        message.chat.id,
        "សូមជ្រើសរើសចំនួនទឹកប្រាក់ដែលចង់បញ្ចូល (USD):",
        reply_markup=deposit_amount_kb(),
    )


@bot.message_handler(commands=["orders"])
def cmd_orders(message):
    orders = load_orders()
    mine = [o for o in orders if o["uid"] == message.from_user.id]
    if not mine:
        bot.send_message(message.chat.id, "អ្នកមិនទាន់មានការកម្មង់ណាមួយទេ។")
        return
    lines = []
    for o in mine[-10:]:
        lines.append(f"• {o['product']} - ${o['price']:.2f} - {o['time']}")
    bot.send_message(message.chat.id, "📦 ការកម្មង់ចុងក្រោយ:\n" + "\n".join(lines))


# ------------------------------------------------------------------
# REPLY KEYBOARD TEXT HANDLERS
# ------------------------------------------------------------------
@bot.message_handler(func=lambda m: m.text == BTN_SHOP)
def reply_shop(message):
    bot.send_message(message.chat.id, "🛒 ជ្រើសរើស account ដែលអ្នកចង់ទិញ:", reply_markup=products_kb())


@bot.message_handler(func=lambda m: m.text == BTN_WALLET)
def reply_wallet(message):
    u = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"💰 សមតុល្យបច្ចុប្បន្ន: <b>${u['balance']:.2f}</b>\nការកម្មង់សរុប: {u['orders']}",
    )


@bot.message_handler(func=lambda m: m.text == BTN_DEPOSIT)
def reply_deposit(message):
    bot.send_message(message.chat.id, "សូមជ្រើសរើសចំនួនទឹកប្រាក់ដែលចង់បញ្ចូល (USD):", reply_markup=deposit_amount_kb())


@bot.message_handler(func=lambda m: m.text == BTN_ORDERS)
def reply_orders(message):
    orders = load_orders()
    mine = [o for o in orders if o["uid"] == message.from_user.id]
    if not mine:
        bot.send_message(message.chat.id, "អ្នកមិនទាន់មានការកម្មង់ណាមួយទេ។")
        return
    lines = [f"• {o['product']} - ${o['price']:.2f} - {o['time']}" for o in mine[-10:]]
    bot.send_message(message.chat.id, "📦 ការកម្មង់ចុងក្រោយ:\n" + "\n".join(lines))


@bot.message_handler(func=lambda m: m.text == BTN_HELP)
def reply_help(message):
    bot.send_message(
        message.chat.id,
        "☎️ ទំនាក់ទំនង Admin បានផ្ទាល់ខាងក្រោម ឬចុច /start ដើម្បីមើលម៉ឺនុយម្តងទៀត:",
        reply_markup=main_menu_kb(),
    )


@bot.message_handler(func=lambda m: m.text == ADMIN_BTN_STATS)
def reply_admin_stats(message):
    if is_admin(message.from_user.id):
        cmd_stats(message)


@bot.message_handler(func=lambda m: m.text == ADMIN_BTN_ADDPRODUCT)
def reply_admin_addproduct(message):
    if is_admin(message.from_user.id):
        cmd_addproduct(message)


@bot.message_handler(func=lambda m: m.text == ADMIN_BTN_EDITPRODUCT)
def reply_admin_editproduct(message):
    if is_admin(message.from_user.id):
        cmd_editproduct(message)


@bot.message_handler(func=lambda m: m.text == ADMIN_BTN_ADDSTOCK)
def reply_admin_addstock(message):
    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "សូមវាយបញ្ជា:\n<code>/addstock key</code>\nឧ. <code>/addstock netflix</code>")


@bot.message_handler(func=lambda m: m.text == ADMIN_BTN_EMOJI)
def reply_admin_emoji(message):
    if is_admin(message.from_user.id):
        cmd_setupemoji(message)


@bot.message_handler(func=lambda m: m.text == ADMIN_BTN_MESSAGE)
def reply_admin_message(message):
    if is_admin(message.from_user.id):
        cmd_message(message)


@bot.message_handler(func=lambda m: m.text == ADMIN_BTN_BROADCAST)
def reply_admin_broadcast(message):
    if is_admin(message.from_user.id):
        cmd_broadcast(message)


# ------------------------------------------------------------------
# CALLBACK HANDLERS
# ------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: not (c.data.startswith("emoji_") or c.data.startswith("editp_")))
def callback_router(call):
    data = call.data
    uid = call.from_user.id
    chat_id = call.message.chat.id

    if data == "menu_shop":
        bot.edit_message_text(
            "🛒 ជ្រើសរើស account ដែលអ្នកចង់ទិញ:",
            chat_id, call.message.message_id, reply_markup=products_kb(),
        )

    elif data == "menu_wallet":
        u = get_user(uid)
        bot.edit_message_text(
            f"💰 សមតុល្យបច្ចុប្បន្ន: <b>${u['balance']:.2f}</b>\n\nចង់បញ្ចូលលុយ?",
            chat_id, call.message.message_id, reply_markup=deposit_amount_kb(),
        )

    elif data == "menu_orders":
        orders = load_orders()
        mine = [o for o in orders if o["uid"] == uid]
        if not mine:
            bot.answer_callback_query(call.id, "អ្នកមិនទាន់មានការកម្មង់ណាមួយទេ", show_alert=True)
            return
        lines = [f"• {o['product']} - ${o['price']:.2f} - {o['time']}" for o in mine[-10:]]
        bot.edit_message_text(
            "📦 ការកម្មង់ចុងក្រោយ:\n" + "\n".join(lines),
            chat_id, call.message.message_id, reply_markup=main_menu_kb(),
        )

    elif data == "back_main":
        bot.edit_message_text(
            "🏠 ម៉ឺនុយចម្បង:", chat_id, call.message.message_id, reply_markup=main_menu_kb(),
        )

    elif data.startswith("buy_"):
        product_key = data.split("_", 1)[1]
        handle_buy(call, product_key)

    elif data.startswith("nostock_"):
        product_key = data.split("_", 1)[1]
        products = load_products()
        name = products.get(product_key, {}).get("name", "Product")
        bot.answer_callback_query(call.id, f"❌ {name} អស់ស្តុកហើយ សូមទាក់ទង Admin", show_alert=True)
        return

    elif data.startswith("dep_"):
        amount = float(data.split("_", 1)[1])
        handle_deposit(call, amount)

    bot.answer_callback_query(call.id)


def handle_buy(call, product_key):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    products = load_products()
    if product_key not in products:
        bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
        return

    product = products[product_key]
    price = product["price"]

    if stock_count(product_key) <= 0:
        bot.answer_callback_query(call.id, "❌ ស្តុកអស់ហើយ សូមទាក់ទង Admin", show_alert=True)
        return

    user = get_user(uid)
    if user["balance"] < price:
        bot.answer_callback_query(
            call.id,
            f"❌ សមតុល្យមិនគ្រប់គ្រាន់ (${user['balance']:.2f}/${price:.2f}). សូម /deposit មុន",
            show_alert=True,
        )
        return

    item = pop_stock_item(product_key)
    if not item:
        bot.answer_callback_query(call.id, "❌ ស្តុកអស់ហើយ", show_alert=True)
        return

    update_balance(uid, -price)
    order_id = f"KZ{hashlib.md5(f'{uid}{product_key}{time.time()}'.encode()).hexdigest()[:8].upper()}"
    orders = load_orders()
    orders.append({
        "uid": uid,
        "product": product["name"],
        "price": price,
        "time": kh_time_str(),
        "order_id": order_id,
    })
    save_orders(orders)

    users = load_users()
    users[str(uid)]["orders"] = users[str(uid)].get("orders", 0) + 1
    save_users(users)

    caption = (
        f"✅ ការទិញជោគជ័យ!\n\n"
        f"🛍️ Product: <b>{product['name']}</b>\n"
        f"💵 តម្លៃ: ${price:.2f}\n"
        f"🔖 Order: <code>{order_id}</code>"
    )
    receipt_img = build_receipt_image(
        product["name"], product.get("icon", "📦"), price, order_id,
        buyer_note=call.from_user.first_name or str(uid),
    )
    if receipt_img:
        bot.send_photo(chat_id, receipt_img, caption=caption)
    else:
        bot.send_message(chat_id, caption)

    # ផ្ញើ account ជាសារអត្ថបទដាច់ដោយឡែក (មិនដាក់ក្នុង caption រូបភាព) ដើម្បីអោយ copy បានងាយ
    bot.send_message(chat_id, f"🔑 <b>Account របស់អ្នក:</b>\n<code>{item}</code>")

    # notify admin
    if ADMIN_ID:
        try:
            bot.send_message(
                ADMIN_ID,
                f"🔔 លក់ថ្មី: {product['name']} ($ {price:.2f}) ដល់ user {uid}\n"
                f"ស្តុកនៅសល់: {stock_count(product_key)}",
            )
            if stock_count(product_key) <= 2:
                bot.send_message(ADMIN_ID, f"⚠️ ស្តុក {product['name']} ជិតអស់! ({stock_count(product_key)} នៅសល់)")
        except Exception:
            pass


def handle_deposit(call, amount):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    ref = f"KZDEP{uid}{int(time.time())}"[:50]
    ref_disp = f"DEP-{hashlib.md5(ref.encode()).hexdigest()[:8].upper()}"

    resp = camrapid_create(amount, ref)
    if not resp:
        bot.answer_callback_query(call.id, "❌ មិនអាចបង្កើត QR បានទេ សូមព្យាយាមម្តងទៀត", show_alert=True)
        return

    qr_string = resp.get("qr_code", "")
    img_buf = build_qr_image(
        qr_string, amount=amount, ref=ref_disp,
        label="Wallet Top-Up", subtitle=f"{STORE_NAME} · Deposit",
    ) if qr_string else None

    caption = (
        f"💰 Deposit <b>${amount:.2f}</b>\n🔖 <code>{ref_disp}</code>\n\n"
        f"📱 សូម Scan QR ខាងក្រោម ដើម្បីបញ្ចូលលុយចូល Wallet\n"
        f"✅ ប្រព័ន្ធនឹង detect ស្វ័យប្រវត្តិ\n⏳ QR ផុតកំណត់ក្នុង ~5 នាទី"
    )

    if img_buf:
        bot.send_photo(chat_id, img_buf, caption=caption)
    elif qr_string:
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={qr_string}"
        bot.send_photo(chat_id, qr_url, caption=caption)
    else:
        bot.answer_callback_query(call.id, "❌ QR string ទទេ សូមព្យាយាមម្តងទៀត", show_alert=True)
        return

    t = threading.Thread(
        target=poll_deposit,
        args=(uid, chat_id, amount, ref),
        daemon=True,
    )
    t.start()


# ------------------------------------------------------------------
# ADMIN COMMANDS
# ------------------------------------------------------------------
def is_admin(uid):
    return uid == ADMIN_ID


def slugify_key(name):
    """បំលែងឈ្មោះទៅជា key (អក្សរតូច, គ្មានចន្លោះ, គ្មានសញ្ញាពិសេស)"""
    key = name.strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key or "product"


def unique_key(base_key, products):
    if base_key not in products:
        return base_key
    i = 2
    while f"{base_key}_{i}" in products:
        i += 1
    return f"{base_key}_{i}"


@bot.message_handler(commands=["addproduct"])
def cmd_addproduct(message):
    if not is_admin(message.from_user.id):
        return
    msg = bot.send_message(
        message.chat.id,
        "🆕 <b>បន្ថែម Product ថ្មី</b>\n\n1️⃣ សូមវាយ <b>ឈ្មោះ Product</b> ឧ. <code>Disney+ 1 Month</code>",
    )
    bot.register_next_step_handler(msg, addproduct_step_name)


def addproduct_step_name(message):
    if not is_admin(message.from_user.id):
        return
    name = message.text.strip()
    if not name:
        msg = bot.reply_to(message, "❌ ឈ្មោះមិនត្រឹមត្រូវ សូមវាយម្តងទៀត:")
        bot.register_next_step_handler(msg, addproduct_step_name)
        return
    products = load_products()
    key = unique_key(slugify_key(name), products)
    msg = bot.reply_to(
        message,
        f"🔑 key auto-generate: <code>{key}</code>\n\n"
        f"2️⃣ សូមវាយ <b>តម្លៃ</b> (ជាលេខ, USD) ឧ. <code>6</code>",
    )
    bot.register_next_step_handler(msg, addproduct_step_price, key, name)


def addproduct_step_price(message, key, name):
    if not is_admin(message.from_user.id):
        return
    try:
        price = float(message.text.strip())
    except ValueError:
        msg = bot.reply_to(message, "❌ តម្លៃត្រូវជាលេខ (ឧ. 6 ឬ 6.5) សូមវាយម្តងទៀត:")
        bot.register_next_step_handler(msg, addproduct_step_price, key, name)
        return
    msg = bot.reply_to(
        message,
        "3️⃣ សូមផ្ញើ <b>icon/emoji</b> សម្រាប់ app នេះ (ឧ. 🎬)\nឬវាយ <code>skip</code> ដើម្បីប្រើ 📦 លំនាំដើម",
    )
    bot.register_next_step_handler(msg, addproduct_step_icon, key, name, price)


def addproduct_step_icon(message, key, name, price):
    if not is_admin(message.from_user.id):
        return
    icon = message.text.strip()
    if icon.lower() == "skip" or not icon:
        icon = "📦"
    products = load_products()
    products[key] = {"name": name, "price": price, "icon": icon}
    save_products(products)
    if not os.path.exists(stock_path(key)):
        open(stock_path(key), "w").close()
    bot.reply_to(
        message,
        f"✅ <b>Product បន្ថែមរួចរាល់!</b>\n\n"
        f"{icon} {name}\n"
        f"🔑 key: <code>{key}</code>\n"
        f"💵 តម្លៃ: ${price:.2f}\n\n"
        f"👉 ឥឡូវប្រើ <code>/addstock {key}</code> ដើម្បីបញ្ចូល account ចូល stock",
    )


# ------------------------------------------------------------------
# EDIT PRODUCT (កែឈ្មោះ / តម្លៃ / icon)
# ------------------------------------------------------------------
def edit_products_kb():
    products = load_products()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, p in products.items():
        icon = p.get("icon", "📦")
        kb.add(types.InlineKeyboardButton(
            f"{icon} {p['name']} - ${p['price']:.2f}", callback_data=f"editp_pick_{key}",
        ))
    kb.add(types.InlineKeyboardButton("🔙 បិទ", callback_data="editp_close"))
    return kb


def edit_product_menu_kb(key):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("✏️ ប្តូរឈ្មោះ", callback_data=f"editp_name_{key}"))
    kb.add(types.InlineKeyboardButton("💵 ប្តូរតម្លៃ", callback_data=f"editp_price_{key}"))
    kb.add(types.InlineKeyboardButton("🎨 ប្តូរ Icon", callback_data=f"editp_icon_{key}"))
    kb.add(types.InlineKeyboardButton("🗑 លុប Product នេះ", callback_data=f"editp_delete_{key}"))
    kb.add(types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="editp_back"))
    return kb


@bot.message_handler(commands=["editproduct"])
def cmd_editproduct(message):
    if not is_admin(message.from_user.id):
        return
    products = load_products()
    if not products:
        bot.reply_to(message, "❌ មិនទាន់មាន product ណាមួយទេ សូម /addproduct ជាមុនសិន")
        return
    bot.send_message(
        message.chat.id,
        "✏️ <b>កែ Product</b>\n\nជ្រើសរើស product ដែលចង់កែ:",
        reply_markup=edit_products_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("editp_"))
def editproduct_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id)
        return
    data = call.data
    chat_id = call.message.chat.id
    products = load_products()

    if data == "editp_close":
        bot.edit_message_text("✏️ បិទកម្មវិធីកែ Product។ ប្រើ /editproduct ម្តងទៀតបើត្រូវការ។", chat_id, call.message.message_id)

    elif data == "editp_back":
        bot.edit_message_text("✏️ ជ្រើសរើស product ដែលចង់កែ:", chat_id, call.message.message_id, reply_markup=edit_products_kb())

    elif data.startswith("editp_pick_"):
        key = data.split("editp_pick_", 1)[1]
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        p = products[key]
        bot.edit_message_text(
            f"{p.get('icon','📦')} <b>{p['name']}</b>\n💵 តម្លៃ: ${p['price']:.2f}\n🔑 key: <code>{key}</code>\n📦 ស្តុក: {stock_count(key)}\n\nចង់កែអ្វី?",
            chat_id, call.message.message_id, reply_markup=edit_product_menu_kb(key),
        )

    elif data.startswith("editp_name_"):
        key = data.split("editp_name_", 1)[1]
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        msg = bot.send_message(chat_id, f"✏️ ឈ្មោះបច្ចុប្បន្ន: <b>{products[key]['name']}</b>\n\nសូមវាយ <b>ឈ្មោះថ្មី</b>:")
        bot.register_next_step_handler(msg, editproduct_step_name, key)

    elif data.startswith("editp_price_"):
        key = data.split("editp_price_", 1)[1]
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        msg = bot.send_message(chat_id, f"💵 តម្លៃបច្ចុប្បន្ន: <b>${products[key]['price']:.2f}</b>\n\nសូមវាយ <b>តម្លៃថ្មី</b> (ជាលេខ):")
        bot.register_next_step_handler(msg, editproduct_step_price, key)

    elif data.startswith("editp_icon_"):
        key = data.split("editp_icon_", 1)[1]
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        msg = bot.send_message(chat_id, f"🎨 Icon បច្ចុប្បន្ន: {products[key].get('icon','📦')}\n\nសូមផ្ញើ <b>icon/emoji ថ្មី</b>:")
        bot.register_next_step_handler(msg, editproduct_step_icon, key)

    elif data.startswith("editp_delete_"):
        key = data.split("editp_delete_", 1)[1]
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ បញ្ជាក់លុប", callback_data=f"editp_delconfirm_{key}"),
            types.InlineKeyboardButton("❌ បោះបង់", callback_data=f"editp_pick_{key}"),
        )
        bot.edit_message_text(
            f"⚠️ លុប <b>{products[key]['name']}</b> ចោលមែនទេ?\n(ស្តុកនៅសល់ {stock_count(key)} account នឹងបាត់ដែរ)",
            chat_id, call.message.message_id, reply_markup=kb,
        )

    elif data.startswith("editp_delconfirm_"):
        key = data.split("editp_delconfirm_", 1)[1]
        name = products.get(key, {}).get("name", key)
        products.pop(key, None)
        save_products(products)
        sp = stock_path(key)
        if os.path.exists(sp):
            os.remove(sp)
        bot.edit_message_text(f"🗑 លុប '{name}' រួចរាល់។", chat_id, call.message.message_id, reply_markup=edit_products_kb())

    bot.answer_callback_query(call.id)


def editproduct_step_name(message, key):
    if not is_admin(message.from_user.id):
        return
    new_name = message.text.strip()
    if not new_name:
        msg = bot.reply_to(message, "❌ ឈ្មោះមិនត្រឹមត្រូវ សូមវាយម្តងទៀត:")
        bot.register_next_step_handler(msg, editproduct_step_name, key)
        return
    products = load_products()
    if key not in products:
        bot.reply_to(message, "❌ Product នេះលែងមានហើយ")
        return
    old_name = products[key]["name"]
    products[key]["name"] = new_name
    save_products(products)
    bot.reply_to(message, f"✅ ប្តូរឈ្មោះពី '{old_name}' ទៅ '{new_name}' រួចរាល់!")


def editproduct_step_price(message, key):
    if not is_admin(message.from_user.id):
        return
    try:
        new_price = float(message.text.strip())
    except ValueError:
        msg = bot.reply_to(message, "❌ តម្លៃត្រូវជាលេខ (ឧ. 6 ឬ 6.5) សូមវាយម្តងទៀត:")
        bot.register_next_step_handler(msg, editproduct_step_price, key)
        return
    products = load_products()
    if key not in products:
        bot.reply_to(message, "❌ Product នេះលែងមានហើយ")
        return
    old_price = products[key]["price"]
    products[key]["price"] = new_price
    save_products(products)
    bot.reply_to(message, f"✅ ប្តូរតម្លៃពី ${old_price:.2f} ទៅ ${new_price:.2f} រួចរាល់!")


def editproduct_step_icon(message, key):
    if not is_admin(message.from_user.id):
        return
    icon = message.text.strip()
    if not icon:
        msg = bot.reply_to(message, "❌ សូមផ្ញើ icon/emoji ម្តងទៀត:")
        bot.register_next_step_handler(msg, editproduct_step_icon, key)
        return
    products = load_products()
    if key not in products:
        bot.reply_to(message, "❌ Product នេះលែងមានហើយ")
        return
    products[key]["icon"] = icon
    save_products(products)
    bot.reply_to(message, f"✅ ប្តូរ Icon ទៅ {icon} រួចរាល់!")


@bot.message_handler(commands=["addstock"])
def cmd_addstock(message):
    if not is_admin(message.from_user.id):
        return
    # ទំរង់: /addstock key
    # រួចផ្ញើ account list ជា reply ក្នុងសារបន្ទាប់ (មួយបន្ទាត់ = account មួយ)
    try:
        _, key = message.text.split(" ", 1)
        key = key.strip()
        products = load_products()
        if key not in products:
            bot.reply_to(message, "❌ Product key មិនត្រឹមត្រូវ")
            return
        msg = bot.reply_to(message, f"📥 សូមផ្ញើ account list សំរាប់ '{products[key]['name']}'\n(មួយបន្ទាត់ = account មួយ)")
        bot.register_next_step_handler(msg, process_addstock, key)
    except Exception:
        bot.reply_to(message, "ទំរង់ត្រូវជា: /addstock key")


def process_addstock(message, key):
    if not is_admin(message.from_user.id):
        return
    items = message.text.split("\n")
    push_stock_items(key, items)
    bot.reply_to(message, f"✅ បន្ថែម {len([i for i in items if i.strip()])} accounts ចូល stock '{key}'\n"
                           f"ស្តុករួម: {stock_count(key)}")


def emoji_setup_kb():
    m = get_emoji_map()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for idx, (glyph, label) in enumerate(EMOJI_CATEGORIES):
        mark = "✅" if glyph in m else "⬜"
        kb.add(types.InlineKeyboardButton(f"{mark} {label}", callback_data=f"emoji_pick_{idx}"))
    kb.add(types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="emoji_close"))
    return kb


@bot.message_handler(commands=["setupemoji"])
def cmd_setupemoji(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "🎭 <b>Setup Premium Emoji</b>\n\n"
        "ជ្រើសរើសប្រភេទខាងក្រោម រួចផ្ញើ Premium Emoji ពិត (ត្រូវការ Telegram Premium)\n"
        "ដើម្បីភ្ជាប់ icon នោះទៅគ្រប់ប៊ូតុង/សារដែលមាន glyph ធម្មតានេះ:",
        reply_markup=emoji_setup_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("emoji_"))
def emoji_setup_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id)
        return
    data = call.data
    chat_id = call.message.chat.id

    if data == "emoji_close":
        bot.edit_message_text("🎭 បិទ Setup Emoji។ ប្រើ /setupemoji ម្តងទៀតបើត្រូវការ។", chat_id, call.message.message_id)

    elif data.startswith("emoji_pick_"):
        idx = int(data.split("_")[-1])
        glyph, label = EMOJI_CATEGORIES[idx]
        msg = bot.send_message(
            chat_id,
            f"📨 សូមផ្ញើ <b>Premium Emoji ពិត</b> សម្រាប់ប្រភេទ:\n{label}\n\n"
            f"(ត្រូវជា custom emoji ពិតៗ ដែលអ្នកមាន Telegram Premium ចុចផ្ញើ មិនមែន emoji ធម្មតាទេ)",
        )
        bot.register_next_step_handler(msg, emoji_capture_step, idx)

    elif data.startswith("emoji_clear_"):
        idx = int(data.split("_")[-1])
        glyph, label = EMOJI_CATEGORIES[idx]
        m = get_emoji_map()
        m.pop(glyph, None)
        save_emoji_map(m)
        bot.edit_message_text(
            f"🗑 លុប icon premium សម្រាប់ {label} រួចហើយ។",
            chat_id, call.message.message_id, reply_markup=emoji_setup_kb(),
        )

    bot.answer_callback_query(call.id)


def emoji_capture_step(message, idx):
    if not is_admin(message.from_user.id):
        return
    glyph, label = EMOJI_CATEGORIES[idx]
    entities = message.entities or []
    ce = next((e for e in entities if e.type == "custom_emoji"), None)
    if not ce:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔁 ព្យាយាមម្តងទៀត", callback_data=f"emoji_pick_{idx}"))
        kb.add(types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="emoji_close"))
        bot.send_message(
            message.chat.id,
            "❌ រកមិនឃើញ Premium Emoji ក្នុងសារនេះទេ។\nសូមផ្ញើ Premium Emoji ពិត (មិនមែន emoji ធម្មតា) ម្តងទៀត:",
            reply_markup=kb,
        )
        return
    emoji_char = message.text[ce.offset: ce.offset + ce.length]
    m = get_emoji_map()
    m[glyph] = {"custom_emoji_id": ce.custom_emoji_id, "emoji": emoji_char}
    save_emoji_map(m)
    bot.send_message(
        message.chat.id,
        f"✅ <b>{label}</b>\n\nបានភ្ជាប់ Premium Emoji {emoji_char} ទៅ glyph <code>{glyph}</code> រួចហើយ។\n"
        f"ចាប់ពីនេះទៅ គ្រប់ប៊ូតុង/សារណាដែលមាន {glyph} នឹងបង្ហាញ icon premium ថែមទៀត។",
        reply_markup=emoji_setup_kb(),
    )


@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    if not is_admin(message.from_user.id):
        return
    users = load_users()
    orders = load_orders()
    products = load_products()
    total_balance = sum(u["balance"] for u in users.values())

    lines = [
        "📊 <b>ស្ថិតិទូទៅ</b>",
        f"👥 អ្នកប្រើប្រាស់: {len(users)}",
        f"🛒 ការកម្មង់សរុប: {len(orders)}",
        f"💰 សមតុល្យសរុបក្នុងប្រព័ន្ធ: ${total_balance:.2f}",
        "",
        "📦 ស្តុកបច្ចុប្បន្ន:",
    ]
    for key, p in products.items():
        lines.append(f"  • {p['name']}: {stock_count(key)} accounts")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["addbalance"])
def cmd_addbalance(message):
    """Admin ដាក់លុយចូល wallet ដោយដៃ (ករណីមិនប្រើ KHQR)"""
    if not is_admin(message.from_user.id):
        return
    try:
        _, payload = message.text.split(" ", 1)
        target_uid, amount = payload.split("|")
        new_balance = update_balance(int(target_uid.strip()), float(amount.strip()))
        bot.reply_to(message, f"✅ បន្ថែម ${amount.strip()} ចូល user {target_uid.strip()} (សមតុល្យថ្មី: ${new_balance:.2f})")
    except Exception:
        bot.reply_to(message, "ទំរង់ត្រូវជា:\n/addbalance user_id|amount\nឧ. /addbalance 123456789|10")


@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    if message.text.startswith("/broadcast") and " " in message.text:
        _, text = message.text.split(" ", 1)
        _do_broadcast(message, premium_text(_html_escape(text.strip())))
        return
    msg = bot.send_message(
        message.chat.id,
        "📢 <b>ផ្ញើសារទៅអ្នកប្រើទាំងអស់</b>\n\nសូមវាយ <b>អត្ថបទសារ</b> ដែលចង់ផ្ញើ:",
    )
    bot.register_next_step_handler(msg, broadcast_step_text)


def broadcast_step_text(message):
    if not is_admin(message.from_user.id):
        return
    if not (message.text or "").strip():
        msg = bot.reply_to(message, "❌ សារទទេ សូមវាយម្តងទៀត:")
        bot.register_next_step_handler(msg, broadcast_step_text)
        return
    html = message_to_html(message)
    _do_broadcast(message, html)


def _do_broadcast(message, html_text):
    users = load_users()
    sent, failed = 0, 0
    for uid in users:
        try:
            _orig_send_message(int(uid), f"📢 <b>សេចក្តីជូនដំណឹង</b>\n\n{html_text}")
            sent += 1
        except Exception:
            failed += 1
    bot.reply_to(message, f"✅ ផ្ញើជោគជ័យ {sent} នាក់ ({failed} បរាជ័យ)")


@bot.message_handler(commands=["message"])
def cmd_message(message):
    """Admin ផ្ញើសារទៅ user ណាម្នាក់ដោយផ្ទាល់ (wizard, ខុសពី /broadcast ដែលផ្ញើទៅគ្រប់គ្នា)"""
    if not is_admin(message.from_user.id):
        return
    # ក៏អាចប្រើផ្លូវកាត់: /message user_id|សារ (មិនចាំបាច់ឆ្លងកាត់ wizard, ប៉ុន្តែមិនរក្សា premium emoji ដែលវាយចូល)
    try:
        _, payload = message.text.split(" ", 1)
        target_uid, text = payload.split("|", 1)
        _send_dm_to_user(message, int(target_uid.strip()), premium_text(_html_escape(text.strip())))
        return
    except Exception:
        pass
    msg = bot.send_message(
        message.chat.id,
        "✉️ <b>ផ្ញើសារទៅ User</b>\n\n1️⃣ សូមវាយ <b>Telegram user_id</b> របស់អ្នកទទួល:",
    )
    bot.register_next_step_handler(msg, message_step_uid)


def message_step_uid(message):
    if not is_admin(message.from_user.id):
        return
    try:
        target_uid = int(message.text.strip())
    except ValueError:
        msg = bot.reply_to(message, "❌ user_id ត្រូវជាលេខ សូមវាយម្តងទៀត:")
        bot.register_next_step_handler(msg, message_step_uid)
        return
    users = load_users()
    if str(target_uid) not in users:
        bot.reply_to(message, f"⚠️ user_id {target_uid} មិនទាន់ធ្លាប់ប្រើ bot នេះទេ (មិនអាចផ្ញើបានទេ)")
        return
    msg = bot.reply_to(message, "2️⃣ សូមវាយ <b>អត្ថបទសារ</b> ដែលចង់ផ្ញើ (អាចមាន premium emoji ផ្ទាល់ខ្លួន):")
    bot.register_next_step_handler(msg, message_step_text, target_uid)


def message_step_text(message, target_uid):
    if not is_admin(message.from_user.id):
        return
    if not (message.text or "").strip():
        msg = bot.reply_to(message, "❌ សារទទេ សូមវាយម្តងទៀត:")
        bot.register_next_step_handler(msg, message_step_text, target_uid)
        return
    html = message_to_html(message)
    _send_dm_to_user(message, target_uid, html)


def _send_dm_to_user(admin_message, target_uid, html_text):
    try:
        _orig_send_message(target_uid, f"✉️ <b>សារពី Admin</b>\n\n{html_text}")
        bot.reply_to(admin_message, f"✅ ផ្ញើទៅ user {target_uid} ជោគជ័យ")
    except Exception as e:
        bot.reply_to(admin_message, f"❌ ផ្ញើមិនចេញ: user {target_uid} ប្រហែលបានទប់ស្កាត់ bot ឬ id មិនត្រឹមត្រូវ\n({e})")


# ------------------------------------------------------------------
# KEEP-ALIVE (Flask, សម្រាប់ deploy លើ Render)
# ------------------------------------------------------------------
def start_keep_alive():
    from flask import Flask
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Kairozen Premium Shop Bot is running ✅"

    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080))),
        daemon=True,
    ).start()


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("❌ សូម set environment variable BOT_TOKEN ជាមុនសិន")
    start_keep_alive()
    print("🤖 Bot កំពុងដំណើរការ...")
    bot.infinity_polling(skip_pending=True)

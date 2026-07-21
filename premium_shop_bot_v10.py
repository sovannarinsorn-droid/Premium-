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
  CAMRAPIDPAY_API_KEY  - API key របស់ CamRapidPay (ចាំបាច់សម្រាប់ deposit តាម Bakong KHQR)
  CAMRAPID_CREATE_URL / CAMRAPID_CHECK_URL / PUBLIC_BASE_URL - កំណត់ webhook_url សម្រាប់ CamRapidPay
  KHPAY_API_KEY         - API key របស់ https://khpay.site (ចាំបាច់សម្រាប់ deposit តាម ABA ប៉ុណ្ណោះ)
                          យកបាននៅ https://www.khpay.site/dashboard/settings

ចំណាំ (v11): Bakong KHQR deposit → CamRapidPay | ABA deposit → khpay.site
"""

import os
import re
import io
import html
import json
import time
import hashlib
import threading
import requests
import telebot
from telebot import types

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CAMRAPIDPAY_API_KEY = os.environ.get("CAMRAPIDPAY_API_KEY", "")
CAMRAPID_CREATE = os.environ.get("CAMRAPID_CREATE_URL", "https://pay.camrapidpay.com/api/v1/khqr/create-payments")
CAMRAPID_CHECK = os.environ.get("CAMRAPID_CHECK_URL", "https://pay.camrapidpay.com/check-transaction-api")
# KHPAY (https://khpay.site) — ប្រើសម្រាប់ deposit ជម្រើសទី ២/៣ ក្នុងម៉ឺនុយ Wallet
# ("ទូទាត់តាម ABA" និង "ទូទាត់តាម Bakong KHQR") ។ យក API key ពី
# https://www.khpay.site/dashboard/settings ដាក់ក្នុង Render Env Var ឈ្មោះ KHPAY_API_KEY
KHPAY_API_KEY = os.environ.get("KHPAY_API_KEY", "")
KHPAY_BASE_URL = os.environ.get("KHPAY_BASE_URL", "https://khpay.site/api/v1")
# Render ដាក់ RENDER_EXTERNAL_URL ស្វ័យប្រវត្តិ (ឧ. https://your-app.onrender.com)។
# បើគ្មាន អាចកំណត់ PUBLIC_BASE_URL ដោយដៃ។ ត្រូវការសម្រាប់ webhook_url ដែល CamRapidPay តម្រូវ។
PUBLIC_BASE_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_BASE_URL", "")
CAMRAPID_WEBHOOK_URL = os.environ.get(
    "CAMRAPID_WEBHOOK_URL",
    f"{PUBLIC_BASE_URL.rstrip('/')}/camrapid-webhook" if PUBLIC_BASE_URL else "",
)
STORE_NAME = "Kairozen Store"  # ឈ្មោះហាង — ដាក់ hardcode ត្រង់នេះ (មិនប្រើ env var ទៀតទេ)
# ភាគរយ commission ដែលអ្នកណែនាំ (referrer) ទទួលបាន រាល់ពេលអ្នកដែលខ្លួនណែនាំ (referred user)
# ដាក់លុយចូល wallet ជោគជ័យ (ឧ. 5 មានន័យថា ណែនាំគេដាក់ $10 → ខ្លួនឯងទទួល $0.50 ចូល wallet
# ស្វ័យប្រវត្តិ)។ អាចកែបានតាម Env Var REFERRAL_PERCENT
REFERRAL_PERCENT = float(os.environ.get("REFERRAL_PERCENT", "5"))
# ID របស់ channel/group ដែលចង់ឲ្យ bot ផ្ញើសារជូនដំណឹងស្វ័យប្រវត្តិ ពេលមាន deposit
# ឬ order ជោគជ័យ។ ដាក់ hardcode ត្រង់នេះផ្ទាល់ (negative number ឧ. -1001234567890
# សម្រាប់ channel/supergroup) — អាចដាក់ច្រើនក្នុងមួយ list បាន ១ សម្រាប់ channel ១ សម្រាប់ group។
# ចាំបាច់: bot ត្រូវជា admin (មាន permission ផ្ញើសារ) នៅក្នុង channel/group នោះជាមុនសិន។
NOTIFY_CHAT_IDS = [
    -1004440559295,   # <- Kairozen Store
    # -1002222222222,   # <- ដាក់ ID ទីពីរនៅទីនេះ បើមាន channel/group ថែមទៀត
]

# ពេលស្តុក product មួយធ្លាក់មកដល់ចំនួននេះ ឬតិចជាងនេះ (ប៉ុន្តែមិនទាន់អស់ស្រុង) bot នឹងផ្ញើសារ
# ជូនដំណឹងទៅ user គ្រប់គ្នា ដើម្បីជំរុញឲ្យទិញឲ្យឆាប់មុនអស់ស្តុក (មួយដងក្នុងមួយជុំស្តុក —
# reset ស្វ័យប្រវត្តិពេល admin បញ្ចូល stock ថ្មី)។ អាចកែបានតាម Env Var LOW_STOCK_THRESHOLD
LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "3"))

# ត្រូវការ Render Persistent Disk mount នៅ path នេះ (Render Dashboard -> service
# -> Disks -> Add Disk -> Mount Path = /var/data) បើមិនដូច្នេះទេ data នៅតែបាត់ពេល
# deploy ដដែល ព្រោះ local filesystem ធម្មតារបស់ Render ជា ephemeral (reset រាល់
# deploy)។ ប្រើ /var/data ជាមួយ /data ព្រោះ Render ណែនាំ standalone directory
# នេះជាផ្លូវការសម្រាប់ disk (mount /data ផ្ទាល់ធ្លាប់ជួប PermissionError លើ Render)។
# អាចប្តូរ path តាមចិត្តតាម env var DATA_DIR បើចង់ mount ត្រង់ផ្សេង។
DATA_DIR = os.environ.get("DATA_DIR", "/var/data")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except PermissionError:
    # គ្មាន persistent disk mount នៅ /var/data ទេ → fallback ទៅ local dir (data នឹងបាត់ពេល redeploy)
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STOCK_DIR = os.path.join(DATA_DIR, "stock")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
EMOJI_FILE = os.path.join(DATA_DIR, "premium_emoji.json")

os.makedirs(STOCK_DIR, exist_ok=True)

class _LoggingExceptionHandler(telebot.ExceptionHandler):
    """បើគ្មាន handler នេះ pyTelegramBotAPI នឹងលេប exception ចោលស្ងាត់ៗ ពេល handler
    ណាមួយ crash (ឧ. Telegram server បដិសេធ style/icon_custom_emoji_id នៅពេលផ្ញើពិត
    ដែលមិនមែនជា TypeError ដូច្នេះ pbtn()/preply_btn() ចាប់មិនបាន) — user ចុច button
    ហើយគ្មានអ្វីកើតឡើងសោះ គ្មាន log អោយឃើញមូលហេតុ។ handler នេះធ្វើឲ្យ error print
    ចេញ terminal/Render logs ជានិច្ច ហើយ bot បន្តដំណើរការធម្មតាសម្រាប់ update បន្ទាប់។"""
    def handle(self, exception):
        import traceback
        print("[UNHANDLED EXCEPTION]", flush=True)
        traceback.print_exc()
        return True  # បញ្ជាក់ថា handled រួច កុំឲ្យ polling ដួល


bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", exception_handler=_LoggingExceptionHandler())


def public_user_label(user):
    """label សម្រាប់បង្ហាញជាសាធារណៈក្នុង channel/group — ប្រើ @username បើមាន
    ឬ first_name បើគ្មាន username (កុំបង្ហាញ user id ពេញលេញជាសាធារណៈ)"""
    if not user:
        return "User"
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    return getattr(user, "first_name", None) or "User"


def notify_public(text):
    """ផ្ញើសារទៅ channel/group ទាំងអស់ក្នុង NOTIFY_CHAT_IDS (ឧ. deposit/order ជោគជ័យ)
    ដើម្បីបង្ហាញសកម្មភាពលក់ជាសាធារណៈ។ Bot ត្រូវបានបន្ថែមជា admin របស់ channel/group
    នោះជាមុនសិន (មាន permission ផ្ញើសារ) បើមិនដូច្នេះទេការផ្ញើនឹងបរាជ័យ — ខ្ញុំចាប់
    Exception ទុកនៅទីនេះ ដើម្បីកុំឲ្យប៉ះពាល់ដល់ flow ចម្បង (order/deposit) បើ channel
    មួយផ្ញើមិនចេញ។"""
    if not NOTIFY_CHAT_IDS:
        return
    for cid in NOTIFY_CHAT_IDS:
        try:
            bot.send_message(cid, text)
        except Exception as e:
            print(f"[notify_public] failed to send to {cid}: {e}", flush=True)


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
    ("➖", "➖ បន្ថយ (ចំនួន)"),
    ("📦", "📦 ផលិតផល"),
    ("📊", "📊 ស្ថិតិ"),
    ("💰", "💰 កាបូបលុយ"),
    ("💵", "💵 តម្លៃ/ប្រាក់"),
    ("💳", "💳 ការទូទាត់"),
    ("🛒", "🛒 ទិញ Account"),
    ("🛍", "🛍 ការទិញ"),
    ("📥", "📥 Stock"),
    ("🗑", "🗑 លុប"),
    ("🔑", "🔑 Account/Key"),
    ("🔖", "🔖 លេខយោង Ref"),
    ("⏳", "⏳ កំពុងរង់ចាំ"),
    ("⌛", "⌛ ផុតកំណត់"),
    ("⚠️", "⚠️ ប្រុងប្រយ័ត្ន"),
    ("🚨", "🚨 បន្ទាន់ (Admin alert)"),
    ("🚫", "🚫 បដិសេធ/បិទ"),
    ("🔔", "🔔 ជូនដំណឹង"),
    ("📢", "📢 Broadcast"),
    ("📨", "📨 សំណើ/សារ"),
    ("🔁", "🔁 ព្យាយាមម្តងទៀត"),
    ("☎️", "☎️ ទំនាក់ទំនង"),
    ("👉", "👉 ចង្អុលបង្ហាញ"),
    ("👋", "👋 សួស្តី"),
    ("👥", "👥 អ្នកប្រើប្រាស់"),
    ("🏠", "🏠 ម៉ឺនុយចម្បង"),
    ("⚡", "⚡ ទូទាត់ភ្លាមៗ (KHQR)"),
    ("📱", "📱 ស្កេន QR"),
    ("🎭", "🎭 Setup Emoji"),
    ("✏️", "✏️ កែ/បញ្ចូលព័ត៌មាន"),
    ("🔗", "🔗 ណែនាំមិត្ត (Referral)"),
    ("🎉", "🎉 អបអរ/Bonus"),
    ("👤", "👤 អ្នកប្រើប្រាស់ម្នាក់"),
    ("📈", "📈 ស្ថិតិលក់ដាច់ / តម្លៃឡើង"),
    ("📉", "📉 តម្លៃចុះ / បញ្ចុះតម្លៃ"),
    ("📭", "📭 អស់ស្តុក (empty)"),
    ("ℹ️", "ℹ️ ព័ត៌មាន"),
    ("🔎", "🔎 ស្វែងរក/Debug"),
    ("✨", "✨ ការណែនាំ/Tips"),
    ("🙏", "🙏 អរគុណ"),
]



def get_emoji_map():
    return _load(EMOJI_FILE, {})


def save_emoji_map(m):
    _save(EMOJI_FILE, m)


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
    """រកមើលថាតើ text (ជាធម្មតាជា label ប៊ូតុង) មាន glyph ណាមួយដែលកំណត់ icon រួច
    — return (glyph, custom_emoji_id) ដំបូងដែលរកឃើញ, ឬ (None, None) បើគ្មាន
    ពិនិត្យគ្រប់ glyph ដែលបានកំណត់ទាំងអស់ (មិនកំណត់ត្រឹមតែ EMOJI_CATEGORIES ទេ —
    ដូច្នេះ icon ផលិតផលនីមួយៗ ក៏អាចដាក់ premium emoji បានដែរ)"""
    m = get_emoji_map()
    if not m:
        return None, None
    # ត្រៀម glyph វែងបំផុតជាមុន ដើម្បីកុំឲ្យ glyph ខ្លីស៊ុតត្រូវនឹង substring របស់ glyph វែង
    for glyph in sorted(m.keys(), key=len, reverse=True):
        if glyph and glyph in text:
            icon_id = m[glyph].get("custom_emoji_id")
            if icon_id:
                return glyph, icon_id
    return None, None


def _strip_glyph(text, glyph):
    """លុប glyph ធម្មតាចេញពី label (ព្រោះ icon premium បង្ហាញជំនួសរួចហើយ —
    កុំឲ្យ emoji ចាស់លេចមកជាមួយ icon ថ្មីស្ទួនគ្នា)។
    ចំណាំ: បើ label ទាំងមូលគឺ glyph នោះឯង (ឧ. ប៊ូតុង "➕"/"➖" នៅក្នុងអ្នកជ្រើសចំនួន)
    ការលុបនឹងធ្វើឲ្យ label ទទេ — Telegram បដិសេធ button text ទទេ ដែលធ្វើឲ្យទាំង
    keyboard ខូចអស់ (ប៊ូតុងផ្សេងទៀតក៏ដំណើរការមិនកើតដែរ ព្រោះវាជា API call តែមួយ)។
    ដូច្នេះបើលុបហើយទទេ យើងរក្សា text ដើមទុក (មិនលុប) ជាជាងឲ្យ label ទទេ។"""
    cleaned = text.replace(glyph, "", 1)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else text


def pbtn(text, callback_data=None, style=None, url=None, **kw):
    """InlineKeyboardButton ជាមួយ icon premium (បើមាន) + style ពណ៌ (success/danger)
    បើ icon premium ភ្ជាប់បានជោគជ័យ នឹងលុប glyph ធម្មតាចេញពី label ដើម្បីកុំឲ្យបង្ហាញស្ទួន"""
    glyph, icon_id = emoji_icon_for(text)
    clean_text = _strip_glyph(text, glyph) if glyph else text
    attempts = []
    if style and icon_id:
        attempts.append({"style": style, "icon_custom_emoji_id": icon_id})
    if icon_id:
        attempts.append({"icon_custom_emoji_id": icon_id})
    if style:
        attempts.append({"style": style})
    for extra in attempts:
        use_text = clean_text if "icon_custom_emoji_id" in extra else text
        try:
            return types.InlineKeyboardButton(use_text, callback_data=callback_data, url=url, **extra, **kw)
        except TypeError:
            continue
    return types.InlineKeyboardButton(text, callback_data=callback_data, url=url, **kw)


def norm_label(text):
    """ត្រឡប់ text ដូចគ្នានឹងអ្វីដែល preply_btn()/pbtn() ពិតជាផ្ញើទៅ Telegram
    (បើ glyph មាន premium icon រួច នឹងលុប glyph ធម្មតាចេញ ដូច _strip_glyph ធ្វើ)។
    ត្រូវប្រើ function នេះទាំងសងខាង ពេលប្រៀបធៀប m.text == BTN_XXX ដើម្បីកុំឲ្យ
    button ដាច់ការងារពេលកំណត់ premium emoji ថ្មី។"""
    if not text:
        return text
    glyph, icon_id = emoji_icon_for(text)
    if glyph and icon_id:
        return _strip_glyph(text, glyph)
    return text


def preply_btn(text, style=None, **kw):
    """KeyboardButton (reply keyboard) ជាមួយ icon premium (បើមាន) + ពណ៌ (Bot API 9.4+ style)
    បើ icon premium ភ្ជាប់បានជោគជ័យ នឹងលុប glyph ធម្មតាចេញពី label ដើម្បីកុំឲ្យបង្ហាញស្ទួន"""
    glyph, icon_id = emoji_icon_for(text)
    clean_text = _strip_glyph(text, glyph) if glyph else text
    attempts = []
    if style and icon_id:
        attempts.append({"icon_custom_emoji_id": icon_id, "style": style})
    if icon_id:
        attempts.append({"icon_custom_emoji_id": icon_id})
    if style:
        attempts.append({"style": style})
    for extra in attempts:
        use_text = clean_text if "icon_custom_emoji_id" in extra else text
        try:
            return types.KeyboardButton(use_text, **extra, **kw)
        except TypeError:
            continue
    return types.KeyboardButton(text, **kw)


# --- Auto-apply premium_text() លើសារគ្រប់ប្រភេទដែល bot ផ្ញើ ---
# Monkey-patch send_message / reply_to / edit_message_text / send_photo(caption)
# ដើម្បីកុំបំបែក code ចាស់ៗនៅកន្លែងផ្សេងទៀត — គ្រប់ bot.send_message(...) ដែលមានស្រាប់
# នៅតែដំណើរការធម្មតា ប៉ុន្តែ glyph ណាដែលកំណត់ icon premium រួច នឹងបង្ហាញស្វ័យប្រវត្តិ។
_orig_send_message = bot.send_message
_orig_reply_to = bot.reply_to
_orig_edit_message_text = bot.edit_message_text
_orig_send_photo = bot.send_photo
_orig_send_video = bot.send_video
_orig_send_document = bot.send_document


def _patched_send_message(chat_id, text=None, *args, **kwargs):
    return _orig_send_message(chat_id, premium_text(text), *args, **kwargs)


def _patched_reply_to(message, text=None, *args, **kwargs):
    return _orig_reply_to(message, premium_text(text), *args, **kwargs)


def _patched_edit_message_text(text=None, *args, **kwargs):
    return _orig_edit_message_text(premium_text(text), *args, **kwargs)


def _patched_send_photo(chat_id, photo, caption=None, *args, **kwargs):
    return _orig_send_photo(chat_id, photo, premium_text(caption), *args, **kwargs)


def _patched_send_video(chat_id, video, caption=None, *args, **kwargs):
    return _orig_send_video(chat_id, video, premium_text(caption), *args, **kwargs)


def _patched_send_document(chat_id, document, caption=None, *args, **kwargs):
    return _orig_send_document(chat_id, document, premium_text(caption), *args, **kwargs)


bot.send_message = _patched_send_message
bot.reply_to = _patched_reply_to
bot.edit_message_text = _patched_edit_message_text
bot.send_photo = _patched_send_photo
bot.send_video = _patched_send_video
bot.send_document = _patched_send_document

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
        users[uid] = {
            "balance": 0.0,
            "orders": 0,
            "referred_by": None,   # uid (str) របស់អ្នកណែនាំ បើមាន
            "ref_count": 0,        # ចំនួនអ្នកដែលខ្លួនណែនាំបានចូលរួម
            "ref_earned": 0.0,     # commission សរុបដែលទទួលបានពី referral
        }
        save_users(users)
    return users[uid]


def credit_referral_commission(referred_uid, deposit_amount):
    """បើ user ដែលបានដាក់លុយនេះ ត្រូវបានណែនាំដោយអ្នកណា — បន្ថែម commission
    (REFERRAL_PERCENT%) ចូល wallet អ្នកណែនាំនោះ ស្វ័យប្រវត្តិ។ ហៅរាល់ពេល deposit
    ជោគជ័យ (មិនមែនតែលើកដំបូងទេ)។ Return (referrer_uid, bonus) ឬ (None, 0)។"""
    with _lock:
        users = load_users()
        u = users.get(str(referred_uid))
        ref_uid = u.get("referred_by") if u else None
        if not ref_uid or str(ref_uid) == str(referred_uid) or str(ref_uid) not in users:
            return None, 0.0
        bonus = round(deposit_amount * REFERRAL_PERCENT / 100.0, 2)
        if bonus <= 0:
            return None, 0.0
        users[str(ref_uid)]["balance"] = round(users[str(ref_uid)].get("balance", 0.0) + bonus, 2)
        users[str(ref_uid)]["ref_earned"] = round(users[str(ref_uid)].get("ref_earned", 0.0) + bonus, 2)
        save_users(users)
        return ref_uid, bonus


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


def pop_stock_items(product_key, qty):
    """យក account ច្រើនក្នុងពេលតែមួយ (FIFO) → return list (អាចតិចជាង qty បើស្តុកមិនគ្រប់)"""
    items = []
    for _ in range(qty):
        it = pop_stock_item(product_key)
        if not it:
            break
        items.append(it)
    return items


def peek_stock_items(product_key, limit=None):
    """អានមើល account ទាំងអស់ក្នុង stock (មិនលុបចេញទេ) → list តាមលំដាប់ FIFO
    (item ដំបូង = index 1 = ជាអ្នកដែលនឹងត្រូវលក់មុនគេ)។ ប្រើសម្រាប់បង្ហាញ preview
    មុនពេលលុប។ limit កំណត់ចំនួនអតិបរមាដែល return (None = យកទាំងអស់)"""
    p = stock_path(product_key)
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    if limit:
        return lines[:limit]
    return lines


def remove_stock_items_by_indices(product_key, indices):
    """លុប account ជាក់លាក់ចេញពី stock តាម index (1-based, តាមលំដាប់ FIFO ដូច preview)។
    indices: iterable នៃលេខ int។ Return (removed_items, remaining_count)។"""
    with _lock:
        p = stock_path(product_key)
        if not os.path.exists(p):
            return [], 0
        with open(p, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        idx_set = {i for i in indices if 1 <= i <= len(lines)}
        removed = [lines[i - 1] for i in sorted(idx_set)]
        kept = [lines[i] for i in range(len(lines)) if (i + 1) not in idx_set]
        with open(p, "w", encoding="utf-8") as f:
            for it in kept:
                f.write(it + "\n")
        return removed, len(kept)


def clear_stock_items(product_key):
    """លុប stock ទាំងអស់របស់ product មួយ (ចោលចោលទាំង account) → return ចំនួនដែលបានលុប"""
    with _lock:
        p = stock_path(product_key)
        count = stock_count(product_key)
        if os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write("")
        return count


# ------------------------------------------------------------------
# CAMRAPIDPAY (KHQR) INTEGRATION — endpoint/field ត្រឹមត្រូវ
# ------------------------------------------------------------------
_http = requests.Session()
_http.mount("https://", requests.adapters.HTTPAdapter(
    max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5)
))


_last_camrapid_error = ""  # debug: raw error/response ចុងក្រោយ ដើម្បីបង្ហាញអោយ admin ដោយមិនចាំបាច់មើល Render logs


def camrapid_create(amount, reference, _attempt=1):
    """POST ទៅ CamRapidPay ដើម្បីបង្កើត KHQR → return dict ឬ None
    _attempt: ព្យាយាមម្តងទៀតដោយស្វ័យប្រវត្តិ ១ដង (attempt 2) លុះត្រាតែជា error
    បណ្តោះអាសន្ន (timeout/connection/5xx) — មិន retry លើ 4xx ព្រោះ payload/reference
    ដដែល នឹងឲ្យលទ្ធផលដដែលៗ (ឧ. reference ស្ទួន)។"""
    global _last_camrapid_error
    if not CAMRAPIDPAY_API_KEY:
        _last_camrapid_error = "CAMRAPIDPAY_API_KEY មិនបានកំណត់ក្នុង Render environment variables"
        print(f"[camrapid_create] {_last_camrapid_error}", flush=True)
        return None
    if not CAMRAPID_WEBHOOK_URL:
        _last_camrapid_error = (
            "CAMRAPID_WEBHOOK_URL/PUBLIC_BASE_URL មិនបានកំណត់ — CamRapidPay តម្រូវ webhook_url"
        )
        print(f"[camrapid_create] {_last_camrapid_error}", flush=True)
        return None
    try:
        r = _http.post(
            CAMRAPID_CREATE,
            json={
                "api_key": CAMRAPIDPAY_API_KEY,
                "amount": round(float(amount), 2),
                "reference": reference,
                "webhook_url": CAMRAPID_WEBHOOK_URL,
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=20,
        )
        try:
            data = r.json()
        except Exception:
            _last_camrapid_error = f"HTTP {r.status_code} (non-JSON): {r.text[:300]}"
            print(f"[camrapid_create] {_last_camrapid_error}", flush=True)
            if r.status_code >= 500 and _attempt < 2:
                time.sleep(1.5)
                return camrapid_create(amount, reference, _attempt=2)
            return None
        if data.get("success"):
            return data  # keys: qr_code, payment_url, amount, expires_in
        _last_camrapid_error = f"HTTP {r.status_code}: {data}"
        print(f"[camrapid_create] failed: {_last_camrapid_error}", flush=True)
        if r.status_code >= 500 and _attempt < 2:
            time.sleep(1.5)
            return camrapid_create(amount, reference, _attempt=2)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        _last_camrapid_error = f"{type(e).__name__}: {e}"
        print(f"[camrapid_create] transient error: {_last_camrapid_error}", flush=True)
        if _attempt < 2:
            time.sleep(1.5)
            return camrapid_create(amount, reference, _attempt=2)
    except Exception as e:
        _last_camrapid_error = f"{type(e).__name__}: {e}"
        print(f"[camrapid_create] error: {_last_camrapid_error}", flush=True)
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
# KHPAY (https://khpay.site) — ABA PayWay QR + Bakong KHQR, ១ API key ជាមួយ
# gateway ទាំង២។ ប្រើសម្រាប់ deposit ជម្រើស "ទូទាត់តាម ABA" / "ទូទាត់តាម Bakong"
# ------------------------------------------------------------------
_last_khpay_error = ""  # debug: error/response ចុងក្រោយពី khpay.site


def khpay_create(amount, note, method="aba", _attempt=1):
    """POST ទៅ khpay.site ដើម្បីបង្កើត QR ទូទាត់។
    method: "aba" -> POST /qr/generate (ABA PayWay) | "bakong" -> POST /bakong/generate (Bakong KHQR)
    return dict (resp["data"]) ឬ None"""
    global _last_khpay_error
    if not KHPAY_API_KEY:
        _last_khpay_error = "KHPAY_API_KEY មិនបានកំណត់ក្នុង Render environment variables"
        print(f"[khpay_create] {_last_khpay_error}", flush=True)
        return None
    endpoint = "/bakong/generate" if method == "bakong" else "/qr/generate"
    try:
        r = _http.post(
            f"{KHPAY_BASE_URL}{endpoint}",
            json={"amount": round(float(amount), 2), "currency": "USD", "note": note},
            headers={
                "Authorization": f"Bearer {KHPAY_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=20,
        )
        try:
            data = r.json()
        except Exception:
            _last_khpay_error = f"HTTP {r.status_code} (non-JSON): {r.text[:300]}"
            print(f"[khpay_create] {_last_khpay_error}", flush=True)
            if r.status_code >= 500 and _attempt < 2:
                time.sleep(1.5)
                return khpay_create(amount, note, method, _attempt=2)
            return None
        if data.get("success"):
            return data.get("data") or {}
        _last_khpay_error = f"HTTP {r.status_code}: {data}"
        print(f"[khpay_create] failed: {_last_khpay_error}", flush=True)
        if r.status_code >= 500 and _attempt < 2:
            time.sleep(1.5)
            return khpay_create(amount, note, method, _attempt=2)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        _last_khpay_error = f"{type(e).__name__}: {e}"
        print(f"[khpay_create] transient error: {_last_khpay_error}", flush=True)
        if _attempt < 2:
            time.sleep(1.5)
            return khpay_create(amount, note, method, _attempt=2)
    except Exception as e:
        _last_khpay_error = f"{type(e).__name__}: {e}"
        print(f"[khpay_create] error: {_last_khpay_error}", flush=True)
    return None


def khpay_check(transaction_id):
    """GET /qr/check/{id} → True ប្រសិនបើបានបង់។ ដំណើរការទាំង txn_ (ABA) និង bk_ (Bakong)
    ដោយ khpay.site detect gateway ស្វ័យប្រវត្តិ។"""
    try:
        r = _http.get(
            f"{KHPAY_BASE_URL}/qr/check/{transaction_id}",
            headers={"Authorization": f"Bearer {KHPAY_API_KEY}", "Accept": "application/json"},
            timeout=10,
        )
        data = r.json()
        return bool(data.get("success")) and bool(data.get("data", {}).get("paid"))
    except Exception as e:
        print(f"[khpay_check] error: {e}")
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


def poll_deposit(uid, chat_id, amount, reference, user_label=None, max_minutes=5, checker=None):
    """Background thread ដើម្បី poll ការទូទាត់ រហូតដល់ PAID ឬ timeout។
    checker: function(reference) -> bool ។ default = camrapid_check (backward compatible) ។
    សម្រាប់ខ្សែ ABA/Bakong តាម khpay.site ត្រូវបញ្ជូន checker=khpay_check ។"""
    checker = checker or camrapid_check
    deadline = time.time() + max_minutes * 60
    while time.time() < deadline:
        if checker(reference):
            new_balance = update_balance(uid, amount)
            try:
                bot.send_message(
                    chat_id,
                    f"✅ ការទូទាត់ជោគជ័យ! បញ្ចូល <b>${amount:.2f}</b> ចូល wallet។\n"
                    f"💰 សមតុល្យថ្មី: <b>${new_balance:.2f}</b>",
                )
            except Exception:
                pass
            notify_public(
                f"💰 <b>Deposit ជោគជ័យ!</b>\n"
                f"👤 {user_label or 'User'}\n"
                f"💵 ${amount:.2f}"
            )
            ref_uid, bonus = credit_referral_commission(uid, amount)
            if ref_uid:
                try:
                    bot.send_message(
                        int(ref_uid),
                        f"🎉 <b>Referral Commission!</b>\n\n"
                        f"👤 {user_label or 'អ្នកដែលអ្នកណែនាំ'} បានដាក់លុយ ${amount:.2f}\n"
                        f"💵 អ្នកទទួលបាន <b>${bonus:.2f}</b> ({REFERRAL_PERCENT:.0f}%) ចូល wallet ស្វ័យប្រវត្តិ!",
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
_bot_username_cache = None


def get_bot_username():
    """ទាញ @username របស់ bot ខ្លួនឯង (cache ទុកកុំហៅ Telegram API រាល់ដង)
    ត្រូវការសម្រាប់បង្កើត referral link https://t.me/<username>?start=ref_<uid>"""
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache
    try:
        _bot_username_cache = bot.get_me().username
    except Exception:
        _bot_username_cache = None
    return _bot_username_cache


def referral_link_for(uid):
    uname = get_bot_username()
    if not uname:
        return None
    return f"https://t.me/{uname}?start=ref_{uid}"


def main_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        pbtn("🛒 ទិញ Account", callback_data="menu_shop"),
        pbtn("💰 Wallet", callback_data="menu_wallet"),
    )
    kb.add(
        pbtn("📦 ការកម្មង់របស់ខ្ញុំ", callback_data="menu_orders"),
        pbtn("🔗 ណែនាំមិត្ត (Referral)", callback_data="menu_referral"),
    )
    kb.add(
        pbtn("☎️ ទំនាក់ទំនង Admin", url="tg://user?id=%d" % ADMIN_ID),
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
            btn = pbtn(label, callback_data=f"buyopt_{key}", style="success")
        else:
            label = f"× {icon} {p['name'].upper()} - អស់ស្តុក"
            btn = pbtn(label, callback_data=f"nostock_{key}", style="danger")
        kb.add(btn)
    kb.add(pbtn("🔙 ត្រឡប់ក្រោយ", callback_data="back_main"))
    return kb


def qty_pick_kb(key, qty, max_qty, unit_price):
    """ប៊ូតុង ➖ / ➕ ដើម្បីជ្រើសរើសចំនួន account ដែលចង់ទិញ (1..stock នៅសល់)"""
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        pbtn("➖", callback_data=f"qtymin_{key}_{qty}"),
        pbtn(f"{qty} ដុំ", callback_data="noop"),
        pbtn("➕", callback_data=f"qtyplus_{key}_{qty}"),
    )
    kb.add(pbtn(f"✅ ទិញពី Wallet — សរុប ${unit_price * qty:.2f}", callback_data=f"qtyok_{key}_{qty}", style="success"))
    kb.add(pbtn("🔙 ត្រឡប់ក្រោយ", callback_data="menu_shop"))
    return kb


def show_qty_picker(call, product_key, qty):
    chat_id = call.message.chat.id
    products = load_products()
    if product_key not in products:
        bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
        return
    p = products[product_key]
    max_qty = stock_count(product_key)
    if max_qty <= 0:
        bot.answer_callback_query(call.id, f"❌ {p['name']} អស់ស្តុកហើយ សូមទាក់ទង Admin", show_alert=True)
        return
    qty = max(1, min(qty, max_qty))
    icon = p.get("icon", "📦")
    sold = p.get("sold", 0)
    bot.edit_message_text(
        f"{icon} <b>{p['name']}</b>\n💵 តម្លៃឯកតា: ${p['price']:.2f}\n📦 ស្តុកនៅសល់: {max_qty}\n📈 លក់រួច: {sold} accounts\n\n"
        f"សូមជ្រើសរើសចំនួនដែលចង់ទិញ:",
        chat_id, call.message.message_id, reply_markup=qty_pick_kb(product_key, qty, max_qty, p["price"]),
    )



def deposit_amount_kb():
    """V6: លុបប៊ូតុងចំនួនកំណត់ (preset $2/$5/$10...) ចេញ — ឲ្យ user វាយចំនួនលុយ
    ដោយខ្លួនឯងទាំងស្រុងតាមរយៈប៊ូតុង '✏️ បញ្ចូលចំនួនលុយ' ខាងក្រោម។"""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(pbtn("✏️ បញ្ចូលចំនួនលុយ", callback_data="dep_custom"))
    kb.add(pbtn("🔙 ត្រឡប់ក្រោយ", callback_data="back_main"))
    return kb


def pay_method_kb(amount):
    """ប៊ូតុងជ្រើសរើសវិធីទូទាត់ — ទី១ ABA ទី២ Bakong KHQR (ទាំង២ តាម khpay.site)"""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(pbtn("🏦 ទូទាត់តាម ABA", callback_data=f"paym_aba_{amount}"))
    kb.add(pbtn("📱 ទូទាត់តាម Bakong", callback_data=f"paym_bkq_{amount}"))
    kb.add(pbtn("🔙 ត្រឡប់ក្រោយ", callback_data="menu_wallet"))
    return kb


DEPOSIT_MIN_AMOUNT = 0.1  # ចំនួនអប្បបរមាដែលអនុញ្ញាតឲ្យបញ្ចូលដោយខ្លួនឯង (USD)


def _deposit_custom_amount_step(message, from_user):
    """ទទួល message បន្ទាប់ពី user ចុច '✏️ បញ្ចូលចំនួនផ្សេង' — validate ហើយសួរជ្រើសរើសវិធីទូទាត់។"""
    chat_id = message.chat.id
    raw = (message.text or "").strip().replace("$", "").replace(",", "")
    try:
        amount = round(float(raw), 2)
    except (TypeError, ValueError):
        bot.send_message(chat_id, "❌ សូមវាយបញ្ចូលជាលេខ (ឧ. 0.5 ឬ 3.25)។ ចុច /deposit ដើម្បីព្យាយាមម្តងទៀត")
        return
    if amount < DEPOSIT_MIN_AMOUNT:
        bot.send_message(
            chat_id,
            f"❌ ចំនួនតិចជាងអប្បបរមា (${DEPOSIT_MIN_AMOUNT:.2f})។ ចុច /deposit ដើម្បីព្យាយាមម្តងទៀត",
        )
        return
    bot.send_message(
        chat_id,
        f"💰 ចំនួន: <b>${amount:.2f}</b>\n\nសូមជ្រើសរើសវិធីទូទាត់:",
        reply_markup=pay_method_kb(amount),
    )


# --- Reply Keyboard (ប៊ូតុងខាងក្រោមអេក្រង់, នៅជាប់ជានិច្ច) ---
BTN_SHOP = "🛒 ទិញ Account"
BTN_WALLET = "💰 Wallet"
BTN_DEPOSIT = "➕ បញ្ចូលលុយ"
BTN_ORDERS = "📦 ការកម្មង់"
BTN_REFERRAL = "🔗 ណែនាំមិត្ត"
BTN_HELP = "☎️ ជួយខ្ញុំផង"

ADMIN_BTN_STATS = "📊 ស្ថិតិ"
ADMIN_BTN_ADDPRODUCT = "➕ Product ថ្មី"
ADMIN_BTN_ADDSTOCK = "📥 Stock ថ្មី"
ADMIN_BTN_DELSTOCK = "🗑 លុប Stock"
ADMIN_BTN_DELPRODUCT = "🗑 លុប Product"
ADMIN_BTN_EDITPRODUCT = "✏️ កែ Product"
ADMIN_BTN_MSGUSER = "📨 ផ្ញើសារទៅ User"
ADMIN_BTN_BROADCAST = "📢 ផ្ញើសារទៅគ្រប់គ្នា"
ADMIN_BTN_EMOJI = "🎭 Setup Emoji"


def main_reply_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(preply_btn(BTN_SHOP, style="primary"), preply_btn(BTN_WALLET, style="primary"))
    kb.add(preply_btn(BTN_DEPOSIT, style="primary"), preply_btn(BTN_ORDERS, style="primary"))
    kb.add(preply_btn(BTN_REFERRAL, style="primary"), preply_btn(BTN_HELP, style="primary"))
    return kb


def admin_reply_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(preply_btn(BTN_SHOP, style="primary"), preply_btn(BTN_WALLET, style="primary"))
    kb.add(preply_btn(BTN_DEPOSIT, style="primary"), preply_btn(BTN_ORDERS, style="primary"))
    kb.add(preply_btn(BTN_REFERRAL, style="primary"), preply_btn(BTN_HELP, style="primary"))
    kb.add(preply_btn(ADMIN_BTN_STATS, style="primary"), preply_btn(ADMIN_BTN_ADDPRODUCT, style="primary"))
    kb.add(preply_btn(ADMIN_BTN_ADDSTOCK, style="primary"), preply_btn(ADMIN_BTN_DELSTOCK, style="danger"))
    kb.add(preply_btn(ADMIN_BTN_DELPRODUCT, style="danger"), preply_btn(ADMIN_BTN_EDITPRODUCT, style="primary"))
    kb.add(preply_btn(ADMIN_BTN_MSGUSER, style="primary"))
    kb.add(preply_btn(ADMIN_BTN_BROADCAST, style="primary"))
    kb.add(preply_btn(ADMIN_BTN_EMOJI, style="primary"))
    return kb


def reply_kb_for(uid):
    return admin_reply_kb() if uid == ADMIN_ID else main_reply_kb()


# ------------------------------------------------------------------
# USER COMMANDS
# ------------------------------------------------------------------
def _link_referral_if_new(message):
    """បើនេះជា userថ្មីទាំងស្រុង (មិនទាន់ធ្លាប់ចូល bot ពីមុន) ហើយ /start មាន payload
    ជា 'ref_<uid>' — ចងទំនាក់ទំនង referred_by + បន្ថែម ref_count ឲ្យអ្នកណែនាំ។
    ត្រូវហៅមុន get_user() ព្រោះ get_user() នឹងបង្កើត record ថ្មីភ្លាមៗ។"""
    uid = message.from_user.id
    users = load_users()
    is_new = str(uid) not in users
    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else ""
    if is_new and payload.startswith("ref_"):
        try:
            ref_uid = int(payload[len("ref_"):])
        except ValueError:
            ref_uid = None
        if ref_uid and ref_uid != uid and str(ref_uid) in users:
            with _lock:
                users = load_users()
                users[str(uid)] = {
                    "balance": 0.0, "orders": 0,
                    "referred_by": str(ref_uid), "ref_count": 0, "ref_earned": 0.0,
                }
                users[str(ref_uid)]["ref_count"] = users[str(ref_uid)].get("ref_count", 0) + 1
                save_users(users)
            try:
                bot.send_message(ref_uid, f"👥 មានមិត្តភ័ក្តិម្នាក់ចូលរួមតាមរយៈ referral link របស់អ្នក!")
            except Exception:
                pass


@bot.message_handler(commands=["start"])
def cmd_start(message):
    _link_referral_if_new(message)
    get_user(message.from_user.id)
    first_name = message.from_user.first_name or "មិត្ត"
    text = (
        f"👋 <b>សួស្តី {first_name}, សូមស្វាគមន៍មកកាន់ {STORE_NAME}!</b> 🏠\n\n"
        f"យើងខ្ញុំជាកន្លែងទិញ account premium ដូចជា ChatGPT, Netflix, Spotify, "
        f"Office 365, Canva... <b>ដឹកជញ្ជូនភ្លាមៗ</b> ក្រោយទូទាត់ដោយ KHQR ០សុវត្ថិភាព។\n\n"
        f"👉 <b>របៀបប្រើ Bot:</b>\n"
        f"🛒 <b>ទិញ Account</b> — មើល stock ទាំងអស់ដែលមានឥឡូវនេះ\n"
        f"➕ <b>បញ្ចូលលុយ</b> — ស្កេន KHQR បញ្ចូល Wallet ក្នុងប៉ុន្មានវិនាទី\n"
        f"💰 <b>Wallet</b> — មើលសមតុល្យ និងប្រវត្តិកម្មង់\n"
        f"📦 <b>ការកម្មង់</b> — មើល account ដែលធ្លាប់ទិញរួច\n"
        f"🔗 <b>ណែនាំមិត្ត</b> — ចែក link ថែមចំណូល {REFERRAL_PERCENT:.0f}% រៀងរហូត\n"
        f"☎️ <b>ជួយខ្ញុំផង</b> — ជជែកផ្ទាល់ជាមួយ Admin\n\n"
        f"✨ <i>ព័ត៌មានជំនួយ:</i> ត្រូវបញ្ចូលលុយចូល Wallet សិន រួចជ្រើសរើសទិញបាន — account ផ្ញើមកភ្លាមៗដោយស្វ័យប្រវត្តិ!\n"
        f"🙏 អរគុណដែលទុកចិត្ត {STORE_NAME}"
    )
    # ផ្ញើសារតែមួយប៉ុណ្ណោះ (reply keyboard ភ្ជាប់ជាមួយសារនេះតែម្តង) — កុំឲ្យម៉ឺនុយបង្ហាញស្ទួនគ្នា ២ ដង
    bot.send_message(message.chat.id, text, reply_markup=reply_kb_for(message.from_user.id))


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
@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(BTN_SHOP))
def reply_shop(message):
    bot.send_message(message.chat.id, "🛒 ជ្រើសរើស account ដែលអ្នកចង់ទិញ:", reply_markup=products_kb())


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(BTN_WALLET))
def reply_wallet(message):
    u = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"💰 សមតុល្យបច្ចុប្បន្ន: <b>${u['balance']:.2f}</b>\nការកម្មង់សរុប: {u['orders']}",
    )


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(BTN_DEPOSIT))
def reply_deposit(message):
    bot.send_message(message.chat.id, "សូមជ្រើសរើសចំនួនទឹកប្រាក់ដែលចង់បញ្ចូល (USD):", reply_markup=deposit_amount_kb())


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(BTN_ORDERS))
def reply_orders(message):
    orders = load_orders()
    mine = [o for o in orders if o["uid"] == message.from_user.id]
    if not mine:
        bot.send_message(message.chat.id, "អ្នកមិនទាន់មានការកម្មង់ណាមួយទេ។")
        return
    lines = [f"• {o['product']} - ${o['price']:.2f} - {o['time']}" for o in mine[-10:]]
    bot.send_message(message.chat.id, "📦 ការកម្មង់ចុងក្រោយ:\n" + "\n".join(lines))


def referral_info_text(uid):
    u = get_user(uid)
    link = referral_link_for(uid)
    link_line = f"🔗 <code>{link}</code>" if link else "🔗 (Bot username មិនទាន់ត្រៀមរួច សូមព្យាយាមម្តងទៀត)"
    return (
        f"🔗 <b>ណែនាំមិត្ត — ទទួល {REFERRAL_PERCENT:.0f}% ជារៀងរហូត!</b>\n\n"
        f"ចែក link ខាងក្រោមទៅមិត្តភ័ក្តិ។ រាល់ពេលគេដាក់លុយចូល wallet "
        f"(មិនកំណត់ចំនួនដង) អ្នកទទួលបាន {REFERRAL_PERCENT:.0f}% ចូល wallet ស្វ័យប្រវត្តិ!\n\n"
        f"{link_line}\n\n"
        f"👥 អ្នកបានណែនាំ: <b>{u.get('ref_count', 0)} នាក់</b>\n"
        f"💵 Commission ទទួលបានសរុប: <b>${u.get('ref_earned', 0.0):.2f}</b>"
    )


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(BTN_REFERRAL))
def reply_referral(message):
    bot.send_message(message.chat.id, referral_info_text(message.from_user.id))


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(BTN_HELP))
def reply_help(message):
    bot.send_message(
        message.chat.id,
        "☎️ ទំនាក់ទំនង Admin បានផ្ទាល់ខាងក្រោម ឬចុច /start ដើម្បីមើលម៉ឺនុយម្តងទៀត:",
        reply_markup=main_menu_kb(),
    )


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_STATS))
def reply_admin_stats(message):
    if is_admin(message.from_user.id):
        cmd_stats(message)


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_ADDPRODUCT))
def reply_admin_addproduct(message):
    if is_admin(message.from_user.id):
        cmd_addproduct(message)


def admin_product_pick_kb(prefix, empty_stock_only=False):
    """Inline keyboard ជ្រើសរើស product មួយ សម្រាប់ admin action (add stock / delete)។
    prefix: ដូចជា 'admaddstock' ឬ 'admdel' → callback_data = f'{prefix}_{key}'"""
    products = load_products()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, p in products.items():
        icon = p.get("icon", "📦")
        left = stock_count(key)
        sold = p.get("sold", 0)
        label = f"{icon} {p['name']} ({left} នៅសល់ / លក់ {sold})"
        kb.add(pbtn(label, callback_data=f"{prefix}_{key}"))
    if not products:
        kb.add(pbtn("(មិនទាន់មាន product ណាមួយ)", callback_data="noop"))
    kb.add(pbtn("🔙 បោះបង់", callback_data="admcancel"))
    return kb


def admin_delete_confirm_kb(key):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        pbtn("✅ បាទ/ចាស លុប", callback_data=f"admdelyes_{key}", style="danger"),
        pbtn("🔙 បោះបង់", callback_data="admcancel"),
    )
    return kb


def admin_edit_field_kb(key):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        pbtn("✏️ កែ ឈ្មោះ", callback_data=f"admeditname_{key}"),
        pbtn("💵 កែ តម្លៃ", callback_data=f"admeditprice_{key}"),
        pbtn("🔙 បោះបង់", callback_data="admcancel"),
    )
    return kb


def editproduct_step_name(message, key):
    if not is_admin(message.from_user.id):
        return
    new_name = (message.text or "").strip()
    if not new_name:
        msg = bot.send_message(message.chat.id, "❌ ឈ្មោះមិនអាចទទេបានទេ។ សូមផ្ញើម្តងទៀត:")
        bot.register_next_step_handler(msg, editproduct_step_name, key)
        return
    products = load_products()
    if key not in products:
        bot.reply_to(message, "❌ Product មិនត្រឹមត្រូវ (ប្រហែលជាត្រូវបានលុបទៅហើយ)")
        return
    old_name = products[key]["name"]
    products[key]["name"] = new_name
    save_products(products)
    bot.reply_to(message, f"✅ បានប្តូរឈ្មោះពី '{old_name}' ទៅ '{new_name}' រួចហើយ")


def editproduct_step_price(message, key):
    if not is_admin(message.from_user.id):
        return
    try:
        new_price = float((message.text or "").strip())
        if new_price <= 0:
            raise ValueError
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ តម្លៃត្រូវជាលេខវិជ្ជមាន (ឧ. 5.5)។ សូមផ្ញើម្តងទៀត:")
        bot.register_next_step_handler(msg, editproduct_step_price, key)
        return
    products = load_products()
    if key not in products:
        bot.reply_to(message, "❌ Product មិនត្រឹមត្រូវ (ប្រហែលជាត្រូវបានលុបទៅហើយ)")
        return
    old_price = products[key]["price"]
    products[key]["price"] = new_price
    save_products(products)
    bot.reply_to(message, f"✅ បានប្តូរតម្លៃពី ${old_price:.2f} ទៅ ${new_price:.2f} រួចហើយ")
    if new_price != old_price:
        sent, failed = broadcast_price_change(key, old_price, new_price)
        bot.send_message(message.chat.id, f"📢 ជូនដំណឹងតម្លៃថ្មីទៅ user {sent} នាក់ ({failed} បរាជ័យ)")


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_ADDSTOCK))
def reply_admin_addstock(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "📥 <b>Stock ថ្មី</b>\n\nជ្រើសរើស product ដែលចង់បញ្ចូល stock:",
        reply_markup=admin_product_pick_kb("admaddstock"),
    )


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_DELSTOCK))
def reply_admin_delstock(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "🗑 <b>លុប Stock</b>\n\nជ្រើសរើស product ដែលចង់លុប stock ចេញ:",
        reply_markup=admin_product_pick_kb("admdelstock"),
    )


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_DELPRODUCT))
def reply_admin_delproduct(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "🗑 <b>លុប Product</b>\n\nជ្រើសរើស product ដែលចង់លុប (នឹងលុបទាំង stock ដែលនៅសល់ផងដែរ):",
        reply_markup=admin_product_pick_kb("admdel"),
    )



@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_EDITPRODUCT))
def reply_admin_editproduct(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "✏️ <b>កែ Product</b>\n\nជ្រើសរើស product ដែលចង់កែ ឈ្មោះ/តម្លៃ:",
        reply_markup=admin_product_pick_kb("admedit"),
    )


@bot.message_handler(commands=["msguser"])
def cmd_msguser(message):
    if not is_admin(message.from_user.id):
        return
    msg = bot.send_message(
        message.chat.id,
        "📨 <b>ផ្ញើសារទៅ User</b>\n\nសូមផ្ញើ user_id ដែលចង់ផ្ញើសារទៅ (លេខ):",
    )
    bot.register_next_step_handler(msg, msguser_step_id)


def msguser_step_id(message):
    if not is_admin(message.from_user.id):
        return
    try:
        target_uid = int(message.text.strip())
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ user_id ត្រូវជាលេខ។ សូមផ្ញើម្តងទៀត:")
        bot.register_next_step_handler(msg, msguser_step_id)
        return
    msg = bot.send_message(
        message.chat.id,
        f"📨 សូមផ្ញើមាតិកាសារដែលចង់ផ្ញើទៅ user <code>{target_uid}</code>:",
    )
    bot.register_next_step_handler(msg, msguser_step_text, target_uid)


def msguser_step_text(message, target_uid):
    if not is_admin(message.from_user.id):
        return
    text = message.text
    try:
        bot.send_message(target_uid, f"📨 <b>សារពី Admin</b>\n\n{text}")
        bot.reply_to(message, f"✅ បានផ្ញើសារទៅ user {target_uid} ជោគជ័យ")
    except Exception as e:
        bot.reply_to(message, f"❌ បរាជ័យ ផ្ញើមិនចេញ: {e}")


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_MSGUSER))
def reply_admin_msguser(message):
    if is_admin(message.from_user.id):
        cmd_msguser(message)


def broadcast_step_content(message):
    if not is_admin(message.from_user.id):
        return
    users = load_users()
    uids = list(users.keys())
    total = len(uids)
    status = bot.send_message(message.chat.id, f"⏳ កំពុងផ្ញើ... 0/{total}")

    sent, failed = 0, 0
    for i, uid_str in enumerate(uids, start=1):
        try:
            target_uid = int(uid_str)
        except Exception:
            failed += 1
            continue
        try:
            if message.content_type == "text":
                bot.send_message(target_uid, f"📢 <b>សារពី Admin</b>\n\n{message.text}")
            elif message.content_type == "photo":
                bot.send_photo(target_uid, message.photo[-1].file_id, caption=message.caption or "")
            elif message.content_type == "video":
                bot.send_video(target_uid, message.video.file_id, caption=message.caption or "")
            elif message.content_type == "document":
                bot.send_document(target_uid, message.document.file_id, caption=message.caption or "")
            else:
                bot.forward_message(target_uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
        time.sleep(0.05)  # ជៀសវាង Telegram rate limit
        if i % 20 == 0 or i == total:
            try:
                bot.edit_message_text(
                    f"⏳ កំពុងផ្ញើ... {i}/{total} (✅ {sent} / ❌ {failed})",
                    message.chat.id,
                    status.message_id,
                )
            except Exception:
                pass

    bot.send_message(
        message.chat.id,
        f"✅ <b>ផ្ញើសារបញ្ចប់</b>\n\nសរុប: {total}\nជោគជ័យ: {sent}\nបរាជ័យ: {failed}",
    )


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_BROADCAST))
def reply_admin_broadcast(message):
    if is_admin(message.from_user.id):
        cmd_broadcast(message)


@bot.message_handler(func=lambda m: norm_label(m.text) == norm_label(ADMIN_BTN_EMOJI))
def reply_admin_emoji(message):
    if is_admin(message.from_user.id):
        cmd_setupemoji(message)


# ------------------------------------------------------------------
# CALLBACK HANDLERS
# ------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: not c.data.startswith("emoji_"))
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

    elif data == "menu_referral":
        bot.edit_message_text(
            referral_info_text(uid),
            chat_id, call.message.message_id, reply_markup=main_menu_kb(),
        )

    elif data == "back_main":
        bot.edit_message_text(
            "🏠 ម៉ឺនុយចម្បង:", chat_id, call.message.message_id, reply_markup=main_menu_kb(),
        )

    elif data.startswith("buyopt_"):
        product_key = data.split("_", 1)[1]
        show_qty_picker(call, product_key, 1)

    elif data.startswith("qtymin_"):
        key, qty_s = data[len("qtymin_"):].rsplit("_", 1)
        show_qty_picker(call, key, int(qty_s) - 1)

    elif data.startswith("qtyplus_"):
        key, qty_s = data[len("qtyplus_"):].rsplit("_", 1)
        show_qty_picker(call, key, int(qty_s) + 1)

    elif data.startswith("qtyok_"):
        key, qty_s = data[len("qtyok_"):].rsplit("_", 1)
        handle_buy_wallet(call, key, int(qty_s))

    elif data.startswith("nostock_"):
        product_key = data.split("_", 1)[1]
        products = load_products()
        name = products.get(product_key, {}).get("name", "Product")
        bot.answer_callback_query(call.id, f"❌ {name} អស់ស្តុកហើយ សូមទាក់ទង Admin", show_alert=True)
        return

    elif data == "dep_custom":
        msg = bot.send_message(
            chat_id,
            "✏️ សូមវាយបញ្ចូលចំនួនទឹកប្រាក់ដែលអ្នកចង់ដាក់ (USD)\n"
            "អប្បបរមា <b>$0.1</b> — ឧទាហរណ៍: 0.5 ឬ 3.25",
        )
        bot.register_next_step_handler(msg, _deposit_custom_amount_step, call.from_user)

    elif data.startswith("paym_aba_"):
        amount = float(data[len("paym_aba_"):])
        handle_deposit(uid, chat_id, amount, call.from_user, method="aba", call=call)

    elif data.startswith("paym_bkq_"):
        amount = float(data[len("paym_bkq_"):])
        handle_deposit(uid, chat_id, amount, call.from_user, method="bakong", call=call)

    elif data.startswith("dep_"):
        amount = float(data.split("_", 1)[1])
        bot.edit_message_text(
            f"💰 ចំនួន: <b>${amount:.2f}</b>\n\nសូមជ្រើសរើសវិធីទូទាត់:",
            chat_id, call.message.message_id, reply_markup=pay_method_kb(amount),
        )

    elif data == "admcancel":
        bot.edit_message_text("🚫 បានបោះបង់។", chat_id, call.message.message_id)

    elif data == "noop":
        pass

    elif data.startswith("admaddstock_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        bot.edit_message_text(
            f"📥 សូមផ្ញើ account list សំរាប់ '{products[key]['name']}'\n(មួយបន្ទាត់ = account មួយ)",
            chat_id, call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_addstock, key)

    elif data.startswith("admdelstock_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        total = stock_count(key)
        if total == 0:
            bot.edit_message_text(
                f"📭 '{products[key]['name']}' គ្មាន stock សល់ទេ។",
                chat_id, call.message.message_id,
            )
            bot.answer_callback_query(call.id)
            return
        preview = peek_stock_items(key, limit=30)
        lines = [f"{i+1}. <code>{html.escape(it)}</code>" for i, it in enumerate(preview)]
        more_note = f"\n… និងមាន {total - len(preview)} ទៀត (មិនបានបង្ហាញ)" if total > len(preview) else ""
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(pbtn("🗑 លុបទាំងអស់ (Clear All)", callback_data=f"admclearstockconfirm_{key}", style="danger"))
        kb.add(pbtn("🔙 បោះបង់", callback_data="admcancel"))
        msg = bot.edit_message_text(
            f"🗑 <b>លុប Stock — {products[key]['name']}</b> (សរុប {total})\n\n"
            + "\n".join(lines) + more_note +
            "\n\nសូមវាយបញ្ចូល <b>លេខ</b> ដែលចង់លុប (ឧ. <code>1,3,5</code>) រួចផ្ញើមក "
            "ឬចុច 🗑 លុបទាំងអស់ខាងក្រោម:",
            chat_id, call.message.message_id,
            reply_markup=kb,
        )
        bot.register_next_step_handler(msg, process_delstock_indices, key)

    elif data.startswith("admclearstockconfirm_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            pbtn("✅ បាទ/ចាស លុបទាំងអស់", callback_data=f"admclearstockyes_{key}", style="danger"),
            pbtn("🔙 បោះបង់", callback_data="admcancel"),
        )
        bot.edit_message_text(
            f"⚠️ តើអ្នកប្រាកដថាចង់លុប stock ទាំង {stock_count(key)} account "
            f"របស់ '{products[key]['name']}' ចោលទាំងអស់មែនទេ? (មិនអាចដកមកវិញបានទេ)",
            chat_id, call.message.message_id,
            reply_markup=kb,
        )

    elif data.startswith("admclearstockyes_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        removed = clear_stock_items(key)
        bot.edit_message_text(
            f"✅ បានលុប stock ទាំង {removed} account របស់ '{products[key]['name']}' រួចហើយ\n"
            f"📊 ស្តុកសល់: {stock_count(key)}",
            chat_id, call.message.message_id,
        )

    elif data.startswith("admdelyes_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        name = products[key]["name"]
        left = stock_count(key)
        del products[key]
        save_products(products)
        sp = stock_path(key)
        if os.path.exists(sp):
            os.remove(sp)
        bot.edit_message_text(
            f"✅ បានលុប product '{name}' (key: <code>{key}</code>) រួចហើយ\n"
            f"🗑 Stock ដែលបានលុបទាំង {left} account",
            chat_id, call.message.message_id,
        )

    elif data.startswith("admedit_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        p = products[key]
        bot.edit_message_text(
            f"✏️ <b>{p.get('icon','📦')} {p['name']}</b> (តម្លៃបច្ចុប្បន្ន: ${p['price']:.2f})\n\n"
            f"ជ្រើសរើសអ្វីដែលចង់កែ:",
            chat_id, call.message.message_id,
            reply_markup=admin_edit_field_kb(key),
        )

    elif data.startswith("admeditname_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        bot.edit_message_text(
            f"✏️ ឈ្មោះបច្ចុប្បន្ន: <b>{products[key]['name']}</b>\n\nសូមផ្ញើឈ្មោះថ្មី:",
            chat_id, call.message.message_id,
        )
        bot.register_next_step_handler(call.message, editproduct_step_name, key)

    elif data.startswith("admeditprice_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        bot.edit_message_text(
            f"✏️ តម្លៃបច្ចុប្បន្ន: <b>${products[key]['price']:.2f}</b>\n\nសូមផ្ញើតម្លៃថ្មី (ឧ. 5.5):",
            chat_id, call.message.message_id,
        )
        bot.register_next_step_handler(call.message, editproduct_step_price, key)

    elif data.startswith("admdel_"):
        if not is_admin(uid):
            return
        key = data.split("_", 1)[1]
        products = load_products()
        if key not in products:
            bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
            return
        p = products[key]
        bot.edit_message_text(
            f"⚠️ តើអ្នកប្រាកដថាចង់លុប <b>{p.get('icon','📦')} {p['name']}</b> (key: <code>{key}</code>)?\n"
            f"ស្តុកនៅសល់ {stock_count(key)} account នឹងត្រូវលុបចោលផងដែរ។",
            chat_id, call.message.message_id,
            reply_markup=admin_delete_confirm_kb(key),
        )

    bot.answer_callback_query(call.id)


def handle_buy_wallet(call, product_key, qty=1):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    products = load_products()
    if product_key not in products:
        bot.answer_callback_query(call.id, "❌ Product មិនត្រឹមត្រូវ", show_alert=True)
        return

    product = products[product_key]
    unit_price = product["price"]
    qty = max(1, qty)
    total_price = round(unit_price * qty, 2)

    if stock_count(product_key) < qty:
        bot.answer_callback_query(call.id, f"❌ ស្តុកមានតែ {stock_count(product_key)} មិនគ្រប់ {qty}", show_alert=True)
        return

    user = get_user(uid)
    if user["balance"] < total_price:
        bot.answer_callback_query(
            call.id,
            f"❌ សមតុល្យមិនគ្រប់គ្រាន់ (${user['balance']:.2f}/${total_price:.2f}). សូម /deposit មុន",
            show_alert=True,
        )
        return

    items = pop_stock_items(product_key, qty)
    if len(items) < qty:
        push_stock_items(product_key, items)  # ដាក់ត្រឡប់វិញ បើយកមិនគ្រប់ (race condition)
        bot.answer_callback_query(call.id, "❌ ស្តុកអស់ភ្លាមៗ សូមព្យាយាមម្តងទៀត", show_alert=True)
        return

    update_balance(uid, -total_price)
    orders = load_orders()
    orders.append({
        "uid": uid,
        "product": product["name"],
        "price": total_price,
        "qty": qty,
        "time": time.strftime("%Y-%m-%d %H:%M"),
    })
    save_orders(orders)

    # ធ្វើបច្ចុប្បន្នភាព "sold" (ចំនួនលក់រួច) សម្រាប់ product នេះ
    products[product_key]["sold"] = products[product_key].get("sold", 0) + qty
    save_products(products)

    users = load_users()
    users[str(uid)]["orders"] = users[str(uid)].get("orders", 0) + qty
    save_users(users)

    accounts_text = "\n".join(f"{i+1}. <code>{html.escape(it)}</code>" for i, it in enumerate(items))
    bot.send_message(
        chat_id,
        f"✅ ការទិញជោគជ័យ!\n\n"
        f"🛍️ Product: <b>{product['name']}</b> × {qty}\n"
        f"💵 សរុប: ${total_price:.2f}\n\n"
        f"🔑 <b>Account របស់អ្នក:</b>\n{accounts_text}",
    )

    # notify admin
    if ADMIN_ID:
        try:
            bot.send_message(
                ADMIN_ID,
                f"🔔 លក់ថ្មី: {product['name']} × {qty} (${total_price:.2f}) ដល់ user {uid}\n"
                f"ស្តុកនៅសល់: {stock_count(product_key)}",
            )
            if stock_count(product_key) <= 2:
                bot.send_message(ADMIN_ID, f"⚠️ ស្តុក {product['name']} ជិតអស់! ({stock_count(product_key)} នៅសល់)")
        except Exception:
            pass

    # notify public channel/group (NOTIFY_CHAT_IDS)
    notify_public(
        f"🛍️ <b>ការកម្មង់ថ្មី!</b>\n"
        f"{product.get('icon', '📦')} {product['name']} × {qty}\n"
        f"💵 ${total_price:.2f}\n"
        f"👤 {public_user_label(call.from_user)}"
    )

    # ជិតអស់ស្តុក? ជូនដំណឹងទៅ user ទាំងអស់ឲ្យទិញឲ្យឆាប់ (ផ្ញើតែម្តងក្នុងមួយជុំស្តុក
    # ដោយប្រើ flag low_stock_alerted — reset ស្វ័យប្រវត្តិពេល admin បញ្ចូល stock ថ្មី)
    left_after = stock_count(product_key)
    if 0 < left_after <= LOW_STOCK_THRESHOLD:
        products2 = load_products()
        if product_key in products2 and not products2[product_key].get("low_stock_alerted"):
            products2[product_key]["low_stock_alerted"] = True
            save_products(products2)
            try:
                broadcast_low_stock(product_key, left_after)
            except Exception as e:
                print(f"[broadcast_low_stock] failed: {e}", flush=True)


def handle_deposit(uid, chat_id, amount, user_obj, method="aba", call=None):
    """method: "aba"    -> ABA PayWay QR (khpay.site /qr/generate)
               "bakong" -> Bakong KHQR (CamRapidPay) — តាមការកំណត់ថ្មី៖
               Bakong ប្រើ CamRapidPay, ឯ ABA នៅតែប្រើ khpay.site ដដែល។"""
    def _fail(err_text):
        if call:
            bot.answer_callback_query(call.id, err_text, show_alert=True)
        else:
            bot.send_message(chat_id, err_text)

    ref = f"KZDEP{uid}{int(time.time())}"[:50]
    ref_disp = f"DEP-{hashlib.md5(ref.encode()).hexdigest()[:8].upper()}"
    method_label = "ABA" if method == "aba" else "Bakong KHQR"

    caption = (
        f"💰 Deposit <b>${amount:.2f}</b>\n💳 វិធីទូទាត់: <b>{method_label}</b>\n🔖 <code>{ref_disp}</code>\n\n"
        f"📱 សូម Scan QR ខាងក្រោម (ឬចុចប៊ូតុងទំព័រទូទាត់) ដើម្បីបញ្ចូលលុយចូល Wallet\n"
        f"✅ ប្រព័ន្ធនឹង detect ស្វ័យប្រវត្តិ\n⏳ QR ផុតកំណត់ក្នុង ~5-10 នាទី"
    )

    # ---------- BAKONG → CamRapidPay ----------
    if method == "bakong":
        data = camrapid_create(amount, ref)
        if not data:
            _fail(f"❌ មិនអាចបង្កើត QR បានទេ ({method_label})\n\nមូលហេតុ:\n{_last_camrapid_error[:180]}")
            return

        qr_string = data.get("qr_code", "")
        payment_url = data.get("payment_url", "")

        kb = None
        if payment_url:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔗 បើកទំព័រទូទាត់", url=payment_url))

        img_buf = build_qr_image(
            qr_string, amount=amount, ref=ref_disp,
            label="Wallet Top-Up", subtitle=f"{STORE_NAME} · Bakong KHQR",
        ) if qr_string else None
        photo = img_buf or None

        if photo:
            bot.send_photo(chat_id, photo, caption=caption, reply_markup=kb)
        elif payment_url:
            bot.send_message(chat_id, caption, reply_markup=kb)
        else:
            _fail("❌ គ្មានទិន្នន័យ QR ត្រឡប់មកទេ សូមព្យាយាមម្តងទៀត")
            return

        t = threading.Thread(
            target=poll_deposit,
            args=(uid, chat_id, amount, ref, public_user_label(user_obj)),
            kwargs={"checker": camrapid_check},
            daemon=True,
        )
        t.start()
        return

    # ---------- ABA → khpay.site ----------
    data = khpay_create(amount, ref_disp, method=method)
    if not data:
        _fail(f"❌ មិនអាចបង្កើត QR បានទេ ({method_label})\n\nមូលហេតុ:\n{_last_khpay_error[:180]}")
        return

    txn_id = data.get("transaction_id", "")
    payment_url = data.get("payment_url", "")
    download_qr = data.get("download_qr", "")

    kb = None
    if payment_url:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔗 បើកទំព័រទូទាត់", url=payment_url))

    photo = download_qr or None

    if photo:
        bot.send_photo(chat_id, photo, caption=caption, reply_markup=kb)
    elif payment_url:
        bot.send_message(chat_id, caption, reply_markup=kb)
    else:
        _fail("❌ គ្មានទិន្នន័យ QR ត្រឡប់មកទេ សូមព្យាយាមម្តងទៀត")
        return

    if not txn_id:
        return

    t = threading.Thread(
        target=poll_deposit,
        args=(uid, chat_id, amount, txn_id, public_user_label(user_obj)),
        kwargs={"checker": khpay_check},
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
        f"👉 ឥឡូវចុចប៊ូតុង 📥 Stock ថ្មី ដើម្បីបញ្ចូល account ចូល stock",
    )


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


@bot.message_handler(commands=["delstock"])
def cmd_delstock(message):
    if not is_admin(message.from_user.id):
        return
    # ទំរង់: /delstock key
    try:
        _, key = message.text.split(" ", 1)
        key = key.strip()
        products = load_products()
        if key not in products:
            bot.reply_to(message, "❌ Product key មិនត្រឹមត្រូវ")
            return
        total = stock_count(key)
        if total == 0:
            bot.reply_to(message, f"📭 '{products[key]['name']}' គ្មាន stock សល់ទេ។")
            return
        preview = peek_stock_items(key, limit=30)
        lines = [f"{i+1}. <code>{html.escape(it)}</code>" for i, it in enumerate(preview)]
        more_note = f"\n… និងមាន {total - len(preview)} ទៀត (មិនបានបង្ហាញ)" if total > len(preview) else ""
        msg = bot.reply_to(
            message,
            f"🗑 <b>លុប Stock — {products[key]['name']}</b> (សរុប {total})\n\n"
            + "\n".join(lines) + more_note +
            "\n\nសូមវាយបញ្ចូល <b>លេខ</b> ដែលចង់លុប (ឧ. <code>1,3,5</code>):",
        )
        bot.register_next_step_handler(msg, process_delstock_indices, key)
    except Exception:
        bot.reply_to(message, "ទំរង់ត្រូវជា: /delstock key")


def broadcast_new_stock(key, added_count):
    """ជូនដំណឹងទៅ user ទាំងអស់ពេល stock ថ្មីត្រូវបានបន្ថែម (ដូចរូបគំរូ)"""
    products = load_products()
    p = products.get(key)
    if not p or added_count <= 0:
        return 0, 0
    icon = p.get("icon", "📦")
    text = (
        f"➕ <b>ស្តុកថ្មីត្រូវបានបន្ថែមសម្រាប់ {p['name']}!</b>\n\n"
        f"📦 ថ្មីបន្ថែម: <b>{added_count} items</b>\n"
        f"📊 សរុបនៅសល់: <b>{stock_count(key)} items</b>\n"
        f"💰 តម្លៃ: <b>${p['price']:.2f}</b>"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(pbtn(f"{icon} {p['name'].upper()}", callback_data=f"buyopt_{key}", style="success"))
    users = load_users()
    sent, failed = 0, 0
    for uid in users:
        try:
            bot.send_message(int(uid), text, reply_markup=kb)
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


def broadcast_price_change(key, old_price, new_price):
    """ជូនដំណឹងទៅ user ទាំងអស់ (និង channel/group) ពេល admin កែតម្លៃ product មួយ —
    សារខុសគ្នាបើឡើងថ្លៃ (📈) ធៀបនឹងចុះថោក (📉, ជំរុញឲ្យទិញព្រោះកម្រៃថោក)"""
    products = load_products()
    p = products.get(key)
    if not p or new_price == old_price:
        return 0, 0
    icon = p.get("icon", "📦")
    if new_price < old_price:
        pct = round((old_price - new_price) / old_price * 100) if old_price else 0
        header = f"📉 <b>បញ្ចុះតម្លៃ! {p['name']} ថោកជាងមុន{f' {pct}%' if pct else ''}!</b>"
        cta = "🎉 ចាប់ឱកាសទិញឥឡូវ មុនតម្លៃឡើងវិញ!"
    else:
        header = f"📈 <b>តម្លៃថ្មី — {p['name']}</b>"
        cta = "ℹ️ តម្លៃត្រូវបានធ្វើបច្ចុប្បន្នភាព។"
    text = (
        f"{header}\n\n"
        f"💵 តម្លៃចាស់: <s>${old_price:.2f}</s>\n"
        f"💰 តម្លៃថ្មី: <b>${new_price:.2f}</b>\n\n"
        f"{cta}"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(pbtn(f"{icon} {p['name'].upper()} — ${new_price:.2f}", callback_data=f"buyopt_{key}", style="success"))
    users = load_users()
    sent, failed = 0, 0
    for uid in users:
        try:
            bot.send_message(int(uid), text, reply_markup=kb)
            sent += 1
        except Exception:
            failed += 1
    notify_public(
        f"{header}\n💵 <s>${old_price:.2f}</s> → 💰 <b>${new_price:.2f}</b>"
    )
    return sent, failed


def broadcast_low_stock(key, left):
    """ជូនដំណឹង 'ជិតអស់ស្តុក' ទៅ user ទាំងអស់ (និង channel/group ក្នុង NOTIFY_CHAT_IDS)
    ដើម្បីជំរុញឲ្យទិញឲ្យឆាប់មុនអស់ស្តុក។ ហៅត្រឹមតែម្តងក្នុងមួយជុំស្តុក (មើល low_stock_alerted
    flag ក្នុង handle_buy_wallet) — មិនផ្ញើឡើងវិញរាល់ការទិញនីមួយៗទេ។"""
    products = load_products()
    p = products.get(key)
    if not p:
        return 0, 0
    icon = p.get("icon", "📦")
    text = (
        f"🚨 <b>ស្តុកជិតអស់ហើយ — {p['name']}!</b>\n\n"
        f"📦 សល់តែ <b>{left} accounts</b> ប៉ុណ្ណោះ\n"
        f"💰 តម្លៃ: <b>${p['price']:.2f}</b>\n\n"
        f"⏳ សូមទិញឲ្យឆាប់មុនអស់ស្តុក!"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(pbtn(f"{icon} ទិញឥឡូវ — {p['name'].upper()}", callback_data=f"buyopt_{key}", style="success"))
    users = load_users()
    sent, failed = 0, 0
    for uid in users:
        try:
            bot.send_message(int(uid), text, reply_markup=kb)
            sent += 1
        except Exception:
            failed += 1
    notify_public(
        f"🚨 <b>ស្តុកជិតអស់ — {icon} {p['name']}!</b>\nសល់តែ {left} accounts ទៀតប៉ុណ្ណោះ 💵 ${p['price']:.2f}\n⏳ ទិញឲ្យឆាប់!"
    )
    return sent, failed


def process_addstock(message, key):
    if not is_admin(message.from_user.id):
        return
    items = message.text.split("\n")
    added = len([i for i in items if i.strip()])
    push_stock_items(key, items)
    # reset ការជូនដំណឹង "ជិតអស់ស្តុក" ព្រោះទើបតែបញ្ចូល stock ថ្មី — ជុំក្រោយបើធ្លាក់ទាប
    # ដល់ LOW_STOCK_THRESHOLD ទៀត bot នឹងផ្ញើសារជូនដំណឹងម្តងទៀត
    products = load_products()
    if key in products and products[key].get("low_stock_alerted"):
        products[key]["low_stock_alerted"] = False
        save_products(products)
    bot.reply_to(message, f"✅ បន្ថែម {added} accounts ចូល stock '{key}'\n"
                           f"ស្តុករួម: {stock_count(key)}")
    sent, failed = broadcast_new_stock(key, added)
    bot.send_message(message.chat.id, f"📢 ជូនដំណឹងទៅ user {sent} នាក់ ({failed} បរាជ័យ)")


def process_delstock_indices(message, key):
    """ទទួល message ដែល admin វាយបញ្ចូលលេខ (ឧ. '1,3,5') បន្ទាប់ពីជ្រើសរើស product
    ក្នុងម៉ឺនុយ 🗑 លុប Stock — លុប account ទាំងនោះចេញពី stock តាម index (1-based)"""
    if not is_admin(message.from_user.id):
        return
    products = load_products()
    if key not in products:
        bot.reply_to(message, "❌ Product មិនត្រឹមត្រូវ (ប្រហែលជាត្រូវបានលុបទៅហើយ)")
        return
    raw = (message.text or "").strip()
    if not raw:
        bot.reply_to(message, "❌ សូមវាយបញ្ចូលលេខ (ឧ. 1,3,5)")
        return
    try:
        indices = [int(x.strip()) for x in raw.replace(" ", "").split(",") if x.strip()]
        if not indices:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ ទំរង់មិនត្រឹមត្រូវ។ សូមវាយជាលេខ ខណ្ឌដោយ , (ឧ. 1,3,5)")
        return
    removed, remaining = remove_stock_items_by_indices(key, indices)
    if not removed:
        bot.reply_to(message, "❌ គ្មាន item ត្រូវនឹងលេខដែលអ្នកបញ្ចូលទេ (ប្រហែលជាលេខហួសព្រំដែន)")
        return
    lines = "\n".join(f"• <code>{html.escape(it)}</code>" for it in removed)
    bot.reply_to(
        message,
        f"✅ បានលុប {len(removed)} account ចេញពី stock '{products[key]['name']}':\n{lines}\n\n"
        f"📊 ស្តុកសល់: {remaining}",
    )


def all_emoji_categories():
    """បញ្ជីពេញលេញសម្រាប់ setup: category base (✅❌🔙...) បូក icon របស់ផលិតផលនីមួយៗ
    ដែលមានក្នុងហាង — ដូច្នេះ admin អាចដាក់ Premium Emoji ទៅ icon ផលិតផលនីមួយៗបានដែរ
    (ដូចឧទាហរណ៍ shop ដទៃ ដែល icon ក្នុង inline keyboard ជា premium emoji ស្អាតៗ)"""
    cats = list(EMOJI_CATEGORIES)
    seen = {g for g, _ in cats}
    for key, p in load_products().items():
        icon = p.get("icon", "📦")
        if icon and icon not in seen:
            cats.append((icon, f"{icon} Icon ផលិតផល: {p.get('name', key)}"))
            seen.add(icon)
    return cats


def _encode_glyph(glyph):
    return glyph.encode("utf-8").hex()


def _decode_glyph(hex_str):
    return bytes.fromhex(hex_str).decode("utf-8")


def emoji_setup_kb():
    m = get_emoji_map()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for glyph, label in all_emoji_categories():
        mark = "✅" if glyph in m else "⬜"
        kb.add(types.InlineKeyboardButton(f"{mark} {label}", callback_data=f"emoji_pick_{_encode_glyph(glyph)}"))
    kb.add(pbtn("🔙 ត្រឡប់ក្រោយ", callback_data="emoji_close"))
    return kb


@bot.message_handler(commands=["setupemoji"])
def cmd_setupemoji(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "🎭 <b>Setup Premium Emoji</b>\n\n"
        "ជ្រើសរើសប្រភេទខាងក្រោម (រួមទាំង icon ផលិតផលនីមួយៗ) រួចផ្ញើ Premium Emoji ពិត "
        "(ត្រូវការ Telegram Premium)\nដើម្បីភ្ជាប់ icon នោះទៅគ្រប់ប៊ូតុង/សារដែលមាន glyph ធម្មតានេះ "
        "— ស្តុកមានទើបប៊ូតុងបង្ហាញ icon premium ដូចក្នុងឧទាហរណ៍:",
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
        glyph = _decode_glyph(data[len("emoji_pick_"):])
        label = next((l for g, l in all_emoji_categories() if g == glyph), f"Icon {glyph}")
        msg = bot.send_message(
            chat_id,
            f"📨 សូមផ្ញើ <b>Premium Emoji ពិត</b> សម្រាប់ប្រភេទ:\n{label}\n\n"
            f"(ត្រូវជា custom emoji ពិតៗ ដែលអ្នកមាន Telegram Premium ចុចផ្ញើ មិនមែន emoji ធម្មតាទេ)",
        )
        bot.register_next_step_handler(msg, emoji_capture_step, glyph, label)

    elif data.startswith("emoji_clear_"):
        glyph = _decode_glyph(data[len("emoji_clear_"):])
        label = next((l for g, l in all_emoji_categories() if g == glyph), f"Icon {glyph}")
        m = get_emoji_map()
        m.pop(glyph, None)
        save_emoji_map(m)
        bot.edit_message_text(
            f"🗑 លុប icon premium សម្រាប់ {label} រួចហើយ។",
            chat_id, call.message.message_id, reply_markup=emoji_setup_kb(),
        )

    bot.answer_callback_query(call.id)


def emoji_capture_step(message, glyph, label):
    if not is_admin(message.from_user.id):
        return
    entities = message.entities or []
    ce = next((e for e in entities if e.type == "custom_emoji"), None)
    if not ce:
        kb = types.InlineKeyboardMarkup()
        kb.add(pbtn("🔁 ព្យាយាមម្តងទៀត", callback_data=f"emoji_pick_{_encode_glyph(glyph)}"))
        kb.add(pbtn("🔙 ត្រឡប់ក្រោយ", callback_data="emoji_close"))
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
        f"ចាប់ពីនេះទៅ គ្រប់ប៊ូតុង/សារណាដែលមាន {glyph} នឹងបង្ហាញ icon premium ថែមទៀត "
        f"(ឧ. ប៊ូតុងផលិតផលក្នុង 🛒 ទិញ Account ពេលមានស្តុក)។",
        reply_markup=emoji_setup_kb(),
    )


@bot.message_handler(commands=["lastqrerror"])
def cmd_lastqrerror(message):
    if not is_admin(message.from_user.id):
        return
    lines = []
    if _last_khpay_error:
        lines.append(f"🔎 <b>KHPAY (ABA/Bakong) error ចុងក្រោយ:</b>\n<code>{html.escape(_last_khpay_error)}</code>")
    if _last_camrapid_error:
        lines.append(f"🔎 <b>CamRapidPay error ចុងក្រោយ:</b>\n<code>{html.escape(_last_camrapid_error)}</code>")
    bot.reply_to(message, "\n\n".join(lines) if lines else "✅ មិនទាន់មាន error QR ណាមួយកត់ត្រាទុកនៅឡើយទេ")


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
        lines.append(f"  • {p['name']}: {stock_count(key)} នៅសល់ / លក់រួច {p.get('sold', 0)} accounts")
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
    try:
        _, text = message.text.split(" ", 1)
    except Exception:
        bot.reply_to(message, "ទំរង់ត្រូវជា: /broadcast សារដែលចង់ផ្ញើ")
        return
    users = load_users()
    sent, failed = 0, 0
    for uid in users:
        try:
            bot.send_message(int(uid), f"📢 <b>សេចក្តីជូនដំណឹង</b>\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
    bot.reply_to(message, f"✅ ផ្ញើជោគជ័យ {sent} នាក់ ({failed} បរាជ័យ)")


# ------------------------------------------------------------------
# KEEP-ALIVE (Flask, សម្រាប់ deploy លើ Render)
# ------------------------------------------------------------------
def start_keep_alive():
    from flask import Flask, request as flask_request
    app = Flask(__name__)

    @app.route("/")
    def home():
        return f"{STORE_NAME} Bot is running ✅"

    @app.route("/camrapid-webhook", methods=["POST", "GET"])
    def camrapid_webhook():
        # CamRapidPay ហៅ endpoint នេះពេលទូទាត់ជោគជ័យ។ bot ប្រើ polling (camrapid_check)
        # ជាចម្បងរួចហើយ ដូច្នេះទីនេះគ្រាន់តែ log ចោល និង return 200 ដើម្បីបំពេញលក្ខខណ្ឌ webhook_url។
        try:
            print(f"[camrapid_webhook] {flask_request.get_json(silent=True) or flask_request.args}", flush=True)
        except Exception:
            pass
        return {"success": True}, 200

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

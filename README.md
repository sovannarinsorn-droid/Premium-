# Kairozen Premium Account Shop Bot

## មុខងារ
- លក់ account premium (ChatGPT, Netflix, Spotify, Office365, Canva...) តាម Telegram
- Stock គ្រប់គ្រងតាមឯកសារ `.txt` (មួយបន្ទាត់ = account មួយ)
- ប្រព័ន្ធ Wallet — deposit លុយចូលមុន រួចទិញអីវ៉ាន់ចេញពី balance
- KHQR deposit តាម CamRapidPay + auto-polling ការទូទាត់
- Admin panel: `/addproduct`, `/addstock`, `/addbalance`, `/stats`, `/broadcast`

## ការដំឡើង (Termux / Local)
```bash
pip install -r requirements.txt
export BOT_TOKEN="xxxxx:yyyyyyyyy"
export ADMIN_ID="8266854899"
export CAMRAPIDPAY_API_KEY="your_camrapidpay_key"
python3 premium_shop_bot.py
```

## Deploy លើ Render
1. Push code ទៅ GitHub repo
2. បង្កើត **Background Worker** (ឬ Web Service) លើ Render
3. Set Environment Variables: `BOT_TOKEN`, `ADMIN_ID`, `CAMRAPIDPAY_API_KEY`, `CAMRAPIDPAY_BASE_URL`
4. Start command: `python3 premium_shop_bot.py`

## ចំណាំសំខាន់ៗ
- **CamRapidPay** ប្រើ endpoint ពិត (`https://pay.camrapidpay.com/api/v1/khqr/create-payments` និង `/check-transaction-api`) — ដកចេញពី template ដែលកំពុងដំណើរការស្រាប់ (phanna_premium_bot)។ បើ CamRapidPay ផ្លាស់ប្តូរ endpoint អាចប្តូរតាម env var `CAMRAPID_CREATE_URL` / `CAMRAPID_CHECK_URL`។
- **KHQR Card**: ពេល `/deposit` bot នឹង generate QR card ស្អាតបែប Bakong (gradient header + violet corner brackets) ជំនួសឲ្យ QR ធម្មតា។ ត្រូវការ `qrcode`, `Pillow`, `numpy` (មាននៅក្នុង `requirements.txt` រួចហើយ)។
- Bot Token និង API Key មិនត្រូវ hardcode ក្នុងកូដទេ សូមប្រើ environment variables ជានិច្ច។
- ឯកសារ stock នៅ `data/stock/<key>.txt` — Admin បន្ថែមតាម `/addstock <key>` រួចផ្ញើ list account ជាសារបន្ទាប់។

## ពាក្យបញ្ជា Admin
| ពាក្យបញ្ជា | ការប្រើប្រាស់ |
|---|---|
| `/addproduct` | បន្ថែម product ថ្មី (សួរម្តងមួយៗ៖ ឈ្មោះ → តម្លៃ → icon, key auto-generate ពីឈ្មោះ) |
| `/addstock key` | បន្ថែម stock account (ផ្ញើ list ជាសារបន្ទាប់) |
| `/addbalance user_id\|amount` | បន្ថែមលុយចូល wallet អ្នកប្រើដោយដៃ |
| `/stats` | មើលស្ថិតិទូទៅ + ស្តុកនីមួយៗ |
| `/setupemoji` | ភ្ជាប់ Premium Emoji (custom_emoji_id) ទៅនឹង glyph (✅, 📦, 💰...) — មានលើទាំងប៊ូតុង និងអត្ថបទសារ |
| `/broadcast សារ` | ផ្ញើសារទៅអ្នកប្រើទាំងអស់ |

## Premium Emoji
- ត្រូវការគណនី **Telegram Premium** (ដែលអ្នកមានស្រាប់) ដើម្បីផ្ញើ custom emoji ពិត
- `/setupemoji` → ជ្រើសប្រភេទ (ឧ. ✅, 📦, 💰...) → ផ្ញើ Premium Emoji ពិត → bot ចាប់ `custom_emoji_id` រក្សាទុក
- ចាប់ពីនោះ glyph នោះនៅកន្លែងណាក៏ដោយ (ប៊ូតុង inline/reply ឬ **អត្ថបទសារធម្មតា** ដូច "✅ ជោគជ័យ!") នឹងបង្ហាញ icon premium ស្វ័យប្រវត្តិ តាម HTML `<tg-emoji>` — emoji ធម្មតានៅតែមាន មិនត្រូវជំនួសទេ
- Fallback ស្វ័យប្រវត្តិ៖ បើ pyTelegramBotAPI ចាស់មិនស្គាល់ `icon_custom_emoji_id`/`style`, ប៊ូតុងនឹងបង្ហាញធម្មតាដោយមិន crash

## ពាក្យបញ្ជា User
| ពាក្យបញ្ជា | ការប្រើប្រាស់ |
|---|---|
| `/start` | បើកម៉ឺនុយចម្បង |
| `/wallet` | មើលសមតុល្យ |
| `/deposit` | បញ្ចូលលុយតាម KHQR |
| `/orders` | មើលការកម្មង់ចាស់ៗ |

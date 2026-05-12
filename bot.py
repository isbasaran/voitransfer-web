import os
import json
import datetime
import threading
import requests
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)
CORS(app)

SCRIPT_URL    = 'https://script.google.com/macros/s/AKfycbzK8JePbJKk87aryoAvuOWvH7nrrA_6HMnvrZpzaE8zCNexE9ndrCyO2V_gKILAbl2iaA/exec'
TELEGRAM_TOKEN= '8654282740:AAGSXtoXAMtbTmfJiWJI1C_VpM1Oq-4XvGI'
ADMIN_CHAT_ID = '5833736265'
TG            = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}'

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# ── In-memory state ───────────────────────────────────────────────────
# {chat_id: [{'role':..,'content':..}, ...]}
tg_sessions = {}
# {chat_id: 'awaiting_price_VOUCHER' | 'awaiting_price_confirm_VOUCHER'}
tg_pending  = {}
# {voucher: {'drv_tgid':str, 'drv_name':str, 'res_data':dict, 'timer': Timer}}
pending_driver_sends = {}
# {voucher: str}  — fiyat girildi ama henüz gönderilmedi
pending_prices = {}

PRICE_TIMEOUT = 15 * 60  # 15 dakika (saniye)

# ── System prompt ────────────────────────────────────────────────────
SYSTEM_PROMPT = """Sen BRIX TRAVEL / Voitrip şirketinin profesyonel transfer rezervasyon asistanısın. Türkçe konuşuyorsun.

Kullanıcıdan sırayla şu bilgileri topla (her seferinde 1-2 soru sor, kısa ve net ol):
1. Transfer tipi: ARRIVAL mi DEPARTURE mi?
2. Nereden → Nereye (havalimanı kodu veya adres kısa olsun, ör: AYT, BJV, GNY → BELEK, KEMER, SIDE)
3. Tarih (GG.AA.YYYY)
4. Uçuş numarası ve uçuş saati (SS:DD)
5. Otel/adres adı (tam isim)
6. Yolcu adı (tam ad) ve telefon numarası (+90 formatı)
7. Yetişkin / çocuk / bebek sayısı
8. Satış fiyatı ve döviz (EUR/USD/TRY)

PICKUP TIME hesaplama:
- ARRIVAL → Pickup = Uçuş saati (aynı)
- DEPARTURE → Pickup = Uçuş saati - 3.5 saat

Eğer kullanıcı belirsiz bir şey sorarsa veya rezervasyonla ilgisi yoksa, bilgi uydurmadan şunu söyle:
"Bu konuda emin değilim, sizi operatörümüze bağlıyorum. Lütfen bekleyin."
Ardından mesajın sonuna şunu ekle: FALLBACK_TO_ADMIN

Tüm bilgiler tamamlandığında şu formatta ÖZET göster:
✅ Rezervasyon özeti:
📍 Transfer: [JOB] | [FROM] → [TO]
📅 Tarih: [TARİH]
✈️ Uçuş: [UCUS] saat [SAAT]
🕐 Pickup: [PICKUP]
🏨 Otel: [HOTEL]
👤 Yolcu: [YOLCU] | [TELEFON]
👥 [YETİŞKİN] yetişkin / [ÇOCUK] çocuk / [BEBEK] bebek
💰 Fiyat: [FİYAT] [DÖVİZ]

Onaylıyor musunuz? (Evet / Hayır)

Kullanıcı onayladığında (evet/onayla/tamam/ok) sadece şunu yaz: REZERVASYON_ONAYLANDI
Düzeltme isterse düzelt ve özeti tekrar göster.
Asla bilgi uydurma. Kullanıcının yazdığı değerleri aynen kullan."""

# ── Tool definition for structured field extraction ───────────────────
EXTRACT_TOOL = [{
    "type": "function",
    "function": {
        "name": "update_fields",
        "description": "Kullanıcının konuşmasından doğrulanan rezervasyon alanlarını güncelle.",
        "parameters": {
            "type": "object",
            "properties": {
                "job":      {"type": "string"},
                "from":     {"type": "string"},
                "to":       {"type": "string"},
                "tarih":    {"type": "string"},
                "ucus":     {"type": "string"},
                "saat":     {"type": "string"},
                "pickup":   {"type": "string"},
                "hotel":    {"type": "string"},
                "yolcu":    {"type": "string"},
                "telefon":  {"type": "string"},
                "yetiskin": {"type": "string"},
                "cocuk":    {"type": "string"},
                "bebek":    {"type": "string"},
                "fiyat":    {"type": "string"},
                "doviz":    {"type": "string"},
                "not":      {"type": "string"}
            },
            "required": []
        }
    }
}]

# ── Telegram helpers ──────────────────────────────────────────────────
def tg_send(chat_id, text, markup=None, reply_markup=None):
    payload = {'chat_id': str(chat_id), 'text': text, 'parse_mode': 'HTML'}
    m = markup or reply_markup
    if m:
        payload['reply_markup'] = json.dumps(m)
    try:
        requests.post(f'{TG}/sendMessage', json=payload, timeout=10)
    except Exception:
        pass

def tg_answer(callback_id, text='', alert=False):
    try:
        requests.post(f'{TG}/answerCallbackQuery',
                      json={'callback_query_id': callback_id, 'text': text, 'show_alert': alert},
                      timeout=5)
    except Exception:
        pass

def tg_edit(chat_id, message_id, text, markup=None):
    payload = {'chat_id': str(chat_id), 'message_id': message_id,
               'text': text, 'parse_mode': 'HTML'}
    if markup:
        payload['reply_markup'] = json.dumps(markup)
    else:
        payload['reply_markup'] = json.dumps({})
    try:
        requests.post(f'{TG}/editMessageText', json=payload, timeout=5)
    except Exception:
        pass

def tg_force_reply(chat_id, text):
    tg_send(chat_id, text, markup={'force_reply': True, 'selective': True})

# ── Google Sheets helpers ─────────────────────────────────────────────
def get_drivers():
    try:
        resp = requests.get(SCRIPT_URL, params={'action': 'get_drivers'}, timeout=15)
        result = resp.json()
        return result if isinstance(result, list) else result.get('drivers', [])
    except Exception:
        return []

def sheets_update(payload):
    try:
        requests.post(SCRIPT_URL, json={**payload, 'action': 'update_status'}, timeout=15)
    except Exception:
        pass

def sheets_reserve(payload):
    try:
        r = requests.post(SCRIPT_URL, json={**payload, 'action': 'reserve'}, timeout=20)
        return r.status_code == 200
    except Exception:
        return False

def sheets_check(voucher):
    try:
        resp = requests.get(SCRIPT_URL, params={'action': 'check', 'voucher': voucher}, timeout=15)
        return resp.json()
    except Exception:
        return {}

# ── Voucher generator ─────────────────────────────────────────────────
COUNTER_FILE = '/tmp/voi_counter.json'

def generate_voucher():
    now = datetime.datetime.now()
    date_key = now.strftime('%d%m%y')
    try:
        with open(COUNTER_FILE, 'r') as f:
            data = json.load(f)
    except Exception:
        data = {}
    seq = data.get(date_key, 0) + 1
    data[date_key] = seq
    try:
        with open(COUNTER_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass
    return f"BRX{date_key}{seq:03d}"

# ── Pickup time calculator ────────────────────────────────────────────
def calc_pickup(saat, job):
    if not saat:
        return ''
    if job.upper() == 'ARRIVAL':
        return saat
    try:
        h, m = map(int, saat.replace('.', ':').split(':'))
        total = h * 60 + m - 210
        if total < 0:
            total += 1440
        return f'{total//60:02d}:{total%60:02d}'
    except Exception:
        return saat

# ── Admin reservation notification (NO price button here) ─────────────
def notify_admin(data, voucher, source='WEB'):
    job_emoji = '🛬' if data.get('job', '').upper() == 'ARRIVAL' else '🛫'
    msg = (
        f"🆕 <b>YENİ REZERVASYON</b> — {source}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n"
        f"{job_emoji} <b>Transfer:</b> {data.get('job', '')}\n"
        f"📍 <b>Güzergah:</b> {data.get('from', '')} → {data.get('to', '')}\n"
        f"📅 <b>Tarih:</b> {data.get('tarih', '')}\n"
        f"✈️ <b>Uçuş:</b> {data.get('ucus', '')} saat {data.get('saat', '')}\n"
        f"🕐 <b>Pickup:</b> {data.get('pickup', '')}\n"
        f"🏨 <b>Otel:</b> {data.get('hotel', '')}\n"
        f"👤 <b>Yolcu:</b> {data.get('yolcu', '')} | {data.get('telefon', '')}\n"
        f"👥 <b>Kişi:</b> {data.get('yetiskin', '1')}Y / {data.get('cocuk', '0')}Ç / {data.get('bebek', '0')}B\n"
        f"💰 <b>Fiyat:</b> {data.get('fiyat', '')} {data.get('doviz', 'EUR')}\n"
        f"📝 <b>Not:</b> {data.get('not', '-') or '-'}\n"
        f"━━━━━━━━━━━━━━━━"
    )
    kb = {'inline_keyboard': [[
        {'text': '✅ ONAYLA', 'callback_data': f'approve_{voucher}'},
        {'text': '❌ RED ET', 'callback_data': f'reject_{voucher}'}
    ]]}
    tg_send(ADMIN_CHAT_ID, msg, markup=kb)

# ── Driver notification ───────────────────────────────────────────────
def notify_driver(drv_tgid, drv_name, voucher, res_data, price_text=''):
    job_emoji = '🛬' if res_data.get('JOB', '').upper() == 'ARRIVAL' else '🛫'
    price_line = f"\n💰 <b>Tedarikçi Fiyatı:</b> {price_text}" if price_text else ''
    msg = (
        f"🚌 <b>YENİ TRANSFER GÖREVİ</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n"
        f"{job_emoji} <b>Transfer:</b> {res_data.get('JOB', '')}\n"
        f"📍 <b>Güzergah:</b> {res_data.get('FROM', '')} → {res_data.get('TO', '')}\n"
        f"📅 <b>Tarih:</b> {res_data.get('DATE', '')}\n"
        f"✈️ <b>Uçuş:</b> {res_data.get('FLIGHT COD', res_data.get('FLIGHT_COD', ''))} "
        f"saat {res_data.get('FLIGHT TIME', res_data.get('FLIGHT_TIME', ''))}\n"
        f"🕐 <b>Pickup:</b> {res_data.get('PICKUP TIME', res_data.get('PICKUP_TIME', ''))}\n"
        f"🏨 <b>Otel/Adres:</b> {res_data.get('HOTEL/ADRESS', res_data.get('HOTEL_ADRESS', ''))}\n"
        f"👤 <b>Yolcu:</b> {res_data.get('PASSANGER NAME', res_data.get('PASSANGER_NAME', ''))}\n"
        f"📞 <b>Yolcu Tel:</b> {res_data.get('PASSANGER PHONE', res_data.get('PASSANGER_PHONE', ''))}\n"
        f"👥 <b>Kişi:</b> {res_data.get('ADULT', '1')}Y / "
        f"{res_data.get('CHILD', '0')}Ç / {res_data.get('INF', '0')}B"
        f"{price_line}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👷 <b>Şoför:</b> {drv_name}"
    )
    kb = {'inline_keyboard': [[
        {'text': '✅ KABUL ET', 'callback_data': f'drv_accept_{voucher}'},
        {'text': '❌ RED ET',   'callback_data': f'drv_reject_{voucher}'}
    ]]}
    tg_send(drv_tgid, msg, markup=kb)

# ── Auto-send driver notification after timeout ───────────────────────
def _auto_send_driver(voucher):
    """15 dk geçti, admin fiyat girmedi → fiyatsız gönder."""
    info = pending_driver_sends.pop(voucher, None)
    pending_prices.pop(voucher, None)
    # Clear any admin pending state
    for cid, val in list(tg_pending.items()):
        if voucher in val:
            tg_pending.pop(cid, None)
    if not info:
        return
    drv_tgid  = info['drv_tgid']
    drv_name  = info['drv_name']
    res_data  = info['res_data']
    if drv_tgid and drv_tgid != 'nan':
        notify_driver(drv_tgid, drv_name, voucher, res_data, price_text='')
    tg_send(ADMIN_CHAT_ID,
            f"⏰ <b>Süre doldu</b> — <code>{voucher}</code>\n"
            f"Fiyat girilmediği için şoföre <b>fiyatsız</b> gönderildi.")

def _start_price_timer(voucher):
    """15 dakikalık zamanlayıcı başlat."""
    info = pending_driver_sends.get(voucher, {})
    old_timer = info.get('timer')
    if old_timer:
        old_timer.cancel()
    t = threading.Timer(PRICE_TIMEOUT, _auto_send_driver, args=[voucher])
    t.daemon = True
    t.start()
    if voucher in pending_driver_sends:
        pending_driver_sends[voucher]['timer'] = t

def _cancel_timer(voucher):
    info = pending_driver_sends.get(voucher, {})
    t = info.get('timer')
    if t:
        t.cancel()

# ── AI chat fields extractor ──────────────────────────────────────────
def extract_fields_from_history(messages):
    user_lines = []
    for m in messages:
        if m.get('role') == 'user':
            user_lines.append(m['content'])
    if not user_lines:
        return {}
    user_text = '\n'.join(f'- {line}' for line in user_lines)
    extraction_messages = [
        {
            'role': 'system',
            'content': (
                'Sen bir transfer rezervasyon veri çıkarma asistanısın. '
                'Kullanıcının yazdığı mesajlardan rezervasyon bilgilerini çıkar. '
                'KURAL: Sadece kullanıcının açıkça yazdığı gerçek değerleri kaydet. '
                'Soru cümlesi, açıklama veya AI metni asla değer olarak kaydetme. '
                'Kullanıcı bir bilgiyi vermemişse o alanı boş bırak.'
            )
        },
        {
            'role': 'user',
            'content': f'Aşağıdaki kullanıcı mesajlarından rezervasyon bilgilerini çıkar:\n\n{user_text}'
        }
    ]
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=extraction_messages,
            tools=EXTRACT_TOOL,
            tool_choice={'type': 'function', 'function': {'name': 'update_fields'}},
            max_tokens=300
        )
        tc = resp.choices[0].message.tool_calls
        if tc:
            fields = json.loads(tc[0].function.arguments)
            return {k: v for k, v in fields.items() if v and str(v).strip()}
    except Exception:
        pass
    return {}

# ── Static routes ─────────────────────────────────────────────────────
MOCKUP_PORT = 23636

@app.route('/__mockup/', defaults={'path': ''})
@app.route('/__mockup/<path:path>')
def proxy_mockup(path):
    target = f'http://localhost:{MOCKUP_PORT}/__mockup/{path}'
    qs = request.query_string.decode()
    if qs:
        target += '?' + qs
    try:
        resp = requests.get(target, timeout=10, stream=True,
                            headers={k: v for k, v in request.headers if k.lower() != 'host'})
        excluded = {'transfer-encoding', 'content-encoding', 'content-length'}
        headers  = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded]
        return Response(resp.content, status=resp.status_code, headers=headers)
    except Exception as e:
        return str(e), 502

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/logo.png')
def logo():
    return send_from_directory('.', 'logo.png')

@app.route('/logo-nobg.png')
def logo_nobg():
    return send_from_directory('.', 'logo-nobg.png')

# ── Web: AI Chat ──────────────────────────────────────────────────────
@app.route('/api/chat', methods=['POST'])
def api_chat():
    data     = request.get_json(force=True)
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'error': 'Mesaj gerekli'}), 400

    full_messages = [{'role': 'system', 'content': SYSTEM_PROMPT}] + messages

    try:
        reply_resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=full_messages,
            max_tokens=600
        )
        reply     = reply_resp.choices[0].message.content
        confirmed = 'REZERVASYON_ONAYLANDI' in reply
        fallback  = 'FALLBACK_TO_ADMIN' in reply

        if fallback:
            last_user = next((m['content'] for m in reversed(messages)
                              if m['role'] == 'user'), '')
            tg_send(ADMIN_CHAT_ID,
                    f"❓ <b>MÜŞTERİ SORUSU (Web)</b>\n\n<i>{last_user}</i>\n\n"
                    f"Müşteri cevap bekliyor. Lütfen web arayüzünden manuel olarak yanıtlayın.")

        fields = extract_fields_from_history(
            full_messages + [{'role': 'assistant', 'content': reply}]
        )
        return jsonify({'reply': reply, 'confirmed': confirmed, 'fields': fields})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Web: Reserve ──────────────────────────────────────────────────────
@app.route('/api/reserve', methods=['POST'])
def api_reserve():
    data    = request.get_json(force=True)
    voucher = data.get('voucher') or generate_voucher()
    data['voucher'] = voucher

    job    = data.get('job', 'ARRIVAL').upper()
    saat   = data.get('saat', '')
    pickup = data.get('pickup', '') or calc_pickup(saat, job)
    now_str= datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    sheets_payload = {
        'VOUCHER':          voucher,
        'DATE':             data.get('tarih', ''),
        'OPERATOR':         'BRIX TRAVEL',
        'JOB':              job,
        'FROM':             data.get('from', ''),
        'TO':               data.get('to', ''),
        'HOTEL_ADRESS':     data.get('hotel', ''),
        'FLIGHT_COD':       data.get('ucus', ''),
        'FLIGHT_TIME':      saat,
        'PICKUP_TIME':      pickup,
        'PASSANGER_NAME':   data.get('yolcu', ''),
        'PASSANGER_PHONE':  data.get('telefon', ''),
        'ADULT':            data.get('yetiskin', '1'),
        'CHILD':            data.get('cocuk', '0'),
        'INF':              data.get('bebek', '0'),
        'SALE_PRICE':       data.get('fiyat', ''),
        'SALE_CURE':        data.get('doviz', 'EUR'),
        'NOTE_1':           data.get('not', ''),
        'RESERVATION_STATUS': 'NEW',
        'RESERVATION_STAFF':  'WEB',
        'RESERVATION_DATE':   now_str,
    }
    sheets_reserve(sheets_payload)
    notify_admin(data, voucher, source='🌐 WEB')
    return jsonify({'status': 'ok', 'voucher': voucher}), 200


# ── Web: Check ────────────────────────────────────────────────────────
@app.route('/api/check', methods=['GET'])
def api_check():
    voucher = request.args.get('voucher', '').upper().strip()
    if not voucher:
        return jsonify({'error': 'Voucher gerekli'}), 400
    result = sheets_check(voucher)
    return jsonify(result)


# ── Web: Edit ─────────────────────────────────────────────────────────
@app.route('/api/edit', methods=['POST'])
def api_edit():
    data = request.get_json(force=True)
    if not data or not data.get('voucher'):
        return jsonify({'error': 'Voucher gerekli'}), 400
    try:
        requests.post(SCRIPT_URL, json={**data, 'action': 'edit'}, timeout=15)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Web: Cancel ───────────────────────────────────────────────────────
@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    data = request.get_json(force=True)
    if not data or not data.get('voucher'):
        return jsonify({'error': 'Voucher gerekli'}), 400
    voucher = data.get('voucher', '').upper()
    kb = {'inline_keyboard': [[
        {'text': '✅ İptali Onayla', 'callback_data': f'cancel_ok_{voucher}'},
        {'text': '❌ Reddet',        'callback_data': f'cancel_no_{voucher}'}
    ]]}
    tg_send(ADMIN_CHAT_ID,
            f"❌ <b>İPTAL TALEBİ</b>\n🎫 Voucher: <code>{voucher}</code>\n🌐 Web arayüzünden",
            markup=kb)
    try:
        requests.post(SCRIPT_URL,
                      json={**data, 'action': 'cancel', 'voucher': voucher},
                      timeout=15)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Telegram Webhook ──────────────────────────────────────────────────
@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = request.get_json(force=True, silent=True) or {}

    cq = update.get('callback_query')
    if cq:
        _handle_callback(cq)
        return jsonify({'ok': True})

    msg = update.get('message', {})
    if msg:
        _handle_message(msg)

    return jsonify({'ok': True})


def _handle_message(msg):
    chat_id  = msg.get('chat', {}).get('id')
    text     = (msg.get('text') or '').strip()
    username = msg.get('from', {}).get('first_name', 'Misafir')

    if not text or not chat_id:
        return

    # ── Bekleyen durum: fiyat girişi ─────────────────────────────────
    pending = tg_pending.get(str(chat_id))
    if pending and pending.startswith('awaiting_price_'):
        voucher = pending[len('awaiting_price_'):]
        price_text = text.strip()

        # Fiyatı geçici olarak sakla
        pending_prices[voucher] = price_text
        tg_pending.pop(str(chat_id), None)

        # Admin'e onay butonu gönder
        kb = {'inline_keyboard': [[
            {'text': '✅ EVET, GÖNDER', 'callback_data': f'pricesend_{voucher}'},
            {'text': '⏭️ GEÇ (fiyatsız gönder)', 'callback_data': f'priceskip_{voucher}'}
        ]]}
        tg_send(chat_id,
                f"💰 <b>Fiyat:</b> {price_text}\n\n"
                f"Taşımacıya bu fiyatla göndereyim mi?\n"
                f"(Cevap vermezseniz 15 dk sonra otomatik gönderilir)",
                markup=kb)
        return

    # ── Commands ──────────────────────────────────────────────────────
    if text.startswith('/start'):
        tg_sessions[str(chat_id)] = []
        tg_pending.pop(str(chat_id), None)
        tg_send(chat_id,
                f"👋 Merhaba <b>{username}</b>! Ben Voitrip AI Asistanı.\n\n"
                f"Transfer rezervasyonu yapmak için transfer tipini söyleyin:\n\n"
                f"🛬 <b>ARRIVAL</b> → Havalimanından otele\n"
                f"🛫 <b>DEPARTURE</b> → Otelden havalimanına\n\n"
                f"Diğer komutlar:\n"
                f"/check VOUCHER — Rezervasyon sorgula\n"
                f"/cancel VOUCHER — İptal talebi\n"
                f"/driver — Şoför kaydı")
        return

    if text.startswith('/check'):
        parts = text.split()
        if len(parts) < 2:
            tg_send(chat_id, "❓ Kullanım: /check VOUCHER\nÖrnek: /check BRX1305261001")
            return
        voucher = parts[1].upper()
        tg_send(chat_id, f"🔍 <code>{voucher}</code> sorgulanıyor...")
        data = sheets_check(voucher)
        if data.get('found'):
            d = data.get('data', {})
            job_emoji = '🛬' if str(d.get('JOB', '')).upper() == 'ARRIVAL' else '🛫'
            tg_send(chat_id,
                    f"✅ <b>Rezervasyon Bulundu</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🎫 <code>{voucher}</code>\n"
                    f"{job_emoji} {d.get('JOB', '')} | {d.get('FROM', '')} → {d.get('TO', '')}\n"
                    f"📅 {d.get('DATE', '')}\n"
                    f"✈️ {d.get('FLIGHT COD', '')} {d.get('FLIGHT TIME', '')}\n"
                    f"🕐 Pickup: {d.get('PICKUP TIME', '')}\n"
                    f"🏨 {d.get('HOTEL/ADRESS', '')}\n"
                    f"👤 {d.get('PASSANGER NAME', '')} | {d.get('PASSANGER PHONE', '')}\n"
                    f"📋 Durum: <b>{d.get('RESERVATION STATUS', '')}</b>")
        else:
            tg_send(chat_id, f"❌ <code>{voucher}</code> numaralı rezervasyon bulunamadı.")
        return

    if text.startswith('/cancel'):
        parts = text.split()
        if len(parts) < 2:
            tg_send(chat_id, "❓ Kullanım: /cancel VOUCHER\nÖrnek: /cancel BRX1305261001")
            return
        voucher = parts[1].upper()
        kb = {'inline_keyboard': [[
            {'text': '✅ İptali Onayla', 'callback_data': f'cancel_ok_{voucher}'},
            {'text': '❌ Reddet',        'callback_data': f'cancel_no_{voucher}'}
        ]]}
        tg_send(ADMIN_CHAT_ID,
                f"❌ <b>İPTAL TALEBİ</b>\n"
                f"🎫 Voucher: <code>{voucher}</code>\n"
                f"👤 Talep eden: {username} ({chat_id})",
                markup=kb)
        tg_send(chat_id, f"✅ <code>{voucher}</code> için iptal talebiniz admin'e gönderildi.")
        return

    if text.startswith('/driver'):
        tg_send(chat_id,
                f"🚗 <b>Şoför Kaydı</b>\n\n"
                f"Sisteme kaydolmak için lütfen yöneticinizle iletişime geçin.\n"
                f"Telegram ID'niz: <code>{chat_id}</code>\n"
                f"Bu ID'yi yöneticinize bildirin.")
        tg_send(ADMIN_CHAT_ID,
                f"🚗 <b>Şoför Kaydı Talebi</b>\n"
                f"👤 Ad: {username}\n"
                f"🆔 Telegram ID: <code>{chat_id}</code>\n\n"
                f"DRIVERS sayfasına ekleyebilirsiniz.")
        return

    # ── AI Conversational mode ────────────────────────────────────────
    session = tg_sessions.setdefault(str(chat_id), [])
    session.append({'role': 'user', 'content': text})

    full_msgs = [{'role': 'system', 'content': SYSTEM_PROMPT}] + session

    try:
        resp  = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=full_msgs,
            max_tokens=600
        )
        reply = resp.choices[0].message.content
        session.append({'role': 'assistant', 'content': reply})

        if 'FALLBACK_TO_ADMIN' in reply:
            clean_reply = reply.replace('FALLBACK_TO_ADMIN', '').strip()
            tg_send(chat_id, clean_reply)
            tg_send(ADMIN_CHAT_ID,
                    f"❓ <b>MÜŞTERİ SORUSU (Telegram)</b>\n"
                    f"👤 {username} ({chat_id})\n\n"
                    f"<i>{text}</i>")
            return

        if 'REZERVASYON_ONAYLANDI' in reply:
            fields  = extract_fields_from_history(full_msgs)
            voucher = generate_voucher()
            job     = fields.get('job', 'ARRIVAL').upper()
            saat    = fields.get('saat', '')
            pickup  = fields.get('pickup', '') or calc_pickup(saat, job)
            now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

            sheets_payload = {
                'VOUCHER':          voucher,
                'DATE':             fields.get('tarih', ''),
                'OPERATOR':         'BRIX TRAVEL',
                'JOB':              job,
                'FROM':             fields.get('from', ''),
                'TO':               fields.get('to', ''),
                'HOTEL_ADRESS':     fields.get('hotel', ''),
                'FLIGHT_COD':       fields.get('ucus', ''),
                'FLIGHT_TIME':      saat,
                'PICKUP_TIME':      pickup,
                'PASSANGER_NAME':   fields.get('yolcu', ''),
                'PASSANGER_PHONE':  fields.get('telefon', ''),
                'ADULT':            fields.get('yetiskin', '1'),
                'CHILD':            fields.get('cocuk', '0'),
                'INF':              fields.get('bebek', '0'),
                'SALE_PRICE':       fields.get('fiyat', ''),
                'SALE_CURE':        fields.get('doviz', 'EUR'),
                'NOTE_1':           fields.get('not', ''),
                'RESERVATION_STATUS': 'NEW',
                'RESERVATION_STAFF':  'TG',
                'RESERVATION_DATE':   now_str,
            }
            sheets_reserve(sheets_payload)
            notify_admin(fields, voucher, source='📱 TELEGRAM')
            tg_sessions.pop(str(chat_id), None)
            tg_send(chat_id,
                    f"✅ <b>Rezervasyon Kaydedildi!</b>\n\n"
                    f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n\n"
                    f"Admin onayından sonra size bilgi verilecektir.\n"
                    f"Sorgu için: /check {voucher}")
            return

        tg_send(chat_id, reply)

    except Exception as e:
        tg_send(chat_id, f"❌ Bir hata oluştu: {str(e)}\nLütfen tekrar deneyin.")


def _handle_callback(cq):
    cq_id   = cq.get('id')
    chat_id = cq.get('message', {}).get('chat', {}).get('id')
    msg_id  = cq.get('message', {}).get('message_id')
    cbd     = cq.get('data', '')
    tg_answer(cq_id)

    # ── ADMIN: Rezervasyon onayla ─────────────────────────────────────
    if cbd.startswith('approve_'):
        voucher = cbd[len('approve_'):]
        sheets_update({'voucher': voucher,
                       'RESERVATION_STATUS': 'APPROVED',
                       'TRANSFER_STATUS': 'WAITING_CAR'})

        drivers = get_drivers()
        if not drivers:
            tg_edit(chat_id, msg_id,
                    f"✅ <b>ONAYLANDI</b> — <code>{voucher}</code>\n\n"
                    f"⚠️ DRIVERS sayfasında aktif şoför bulunamadı.")
        else:
            buttons = []
            for d in drivers:
                drv_id   = str(d.get('DRIVER_ID', ''))
                drv_name = d.get('DRIVER_NAME', 'İsimsiz')
                supplier = d.get('SUPPLIER_NAME', '')
                buttons.append([{
                    'text': f"🚗 {drv_name} ({supplier})",
                    'callback_data': f"drv_{drv_id}_{voucher}"
                }])
            tg_edit(chat_id, msg_id,
                    f"✅ <b>ONAYLANDI</b> — <code>{voucher}</code>\n\n👇 Şoför seçin:")
            tg_send(chat_id,
                    f"🚌 <b>{voucher}</b> için şoför atayın:",
                    markup={'inline_keyboard': buttons})

    # ── ADMIN: Şoför seç → fiyat sor, timer başlat ───────────────────
    elif cbd.startswith('drv_'):
        parts   = cbd.split('_', 2)
        drv_id  = parts[1] if len(parts) > 1 else ''
        voucher = parts[2] if len(parts) > 2 else ''

        drivers = get_drivers()
        driver  = next((d for d in drivers
                        if str(d.get('DRIVER_ID', '')) == drv_id), None)
        if not driver:
            tg_edit(chat_id, msg_id, f"❌ Şoför bulunamadı (ID: {drv_id})")
            return

        drv_name  = driver.get('DRIVER_NAME', '')
        drv_phone = driver.get('DRIVER_PHONE', '')
        supplier  = driver.get('SUPPLIER_NAME', '')
        drv_tgid  = str(driver.get('TELEGRAM_ID', ''))

        # Sheets güncelle
        sheets_update({
            'voucher':         voucher,
            'TRANSFER_STATUS': 'WAITING_DRIVER',
            'SUPPLIER_NAME':   supplier,
            'DRIVER_NAME':     drv_name,
            'DRIVER_PHONE':    drv_phone,
        })

        # Şoför bilgilerini ve rezervasyon datasını sakla (henüz bildirim yok)
        res_data = sheets_check(voucher).get('data', {})
        pending_driver_sends[voucher] = {
            'drv_tgid': drv_tgid,
            'drv_name': drv_name,
            'res_data': res_data,
            'timer':    None
        }

        # 15 dk timer başlat
        _start_price_timer(voucher)

        # Admin'e şoför atandı mesajı + fiyat iste
        tg_edit(chat_id, msg_id,
                f"✅ <b>ŞOFÖR ATANDI</b> — <code>{voucher}</code>\n"
                f"🚗 <b>{drv_name}</b> ({supplier})\n"
                f"📞 {drv_phone}\n\n"
                f"⏳ Şoföre gönderilmeden önce tedarikçi fiyatını girin.")

        # Fiyat bekleme durumuna al
        tg_pending[str(chat_id)] = f'awaiting_price_{voucher}'
        tg_send(chat_id,
                f"💰 <b>{voucher}</b> için tedarikçi fiyatını girin\n"
                f"Örnek: <code>45 EUR</code> veya <code>50</code>\n\n"
                f"⏰ 15 dakika içinde girilmezse şoföre <b>fiyatsız</b> gönderilir.")

    # ── ADMIN: Fiyatla gönder ─────────────────────────────────────────
    elif cbd.startswith('pricesend_'):
        voucher    = cbd[len('pricesend_'):]
        price_text = pending_prices.pop(voucher, '')

        # Timer iptal
        _cancel_timer(voucher)
        info = pending_driver_sends.pop(voucher, None)

        if info:
            drv_tgid = info['drv_tgid']
            drv_name = info['drv_name']
            res_data = info['res_data']

            # Fiyatı Sheets'e kaydet
            if price_text:
                parts = price_text.split()
                price_val = parts[0]
                currency  = parts[1].upper() if len(parts) > 1 else 'EUR'
                sheets_update({
                    'voucher':          voucher,
                    'SUPPLIER_PRICE':   price_val,
                    'SUPPLIER_CURRENCY': currency
                })

            # Şoföre bildir
            if drv_tgid and drv_tgid != 'nan':
                notify_driver(drv_tgid, drv_name, voucher, res_data, price_text=price_text)

        tg_edit(chat_id, msg_id,
                f"✅ <b>Şoföre gönderildi</b> — <code>{voucher}</code>\n"
                f"💰 Fiyat: {price_text or '—'}\n"
                f"📋 Durum: WAITING_DRIVER")

    # ── ADMIN: Fiyatsız gönder ────────────────────────────────────────
    elif cbd.startswith('priceskip_'):
        voucher = cbd[len('priceskip_'):]
        pending_prices.pop(voucher, None)
        tg_pending.pop(str(chat_id), None)

        _cancel_timer(voucher)
        info = pending_driver_sends.pop(voucher, None)

        if info:
            drv_tgid = info['drv_tgid']
            drv_name = info['drv_name']
            res_data = info['res_data']
            if drv_tgid and drv_tgid != 'nan':
                notify_driver(drv_tgid, drv_name, voucher, res_data, price_text='')

        tg_edit(chat_id, msg_id,
                f"✅ <b>Şoföre fiyatsız gönderildi</b> — <code>{voucher}</code>\n"
                f"📋 Durum: WAITING_DRIVER")

    # ── ADMIN: Red et ─────────────────────────────────────────────────
    elif cbd.startswith('reject_'):
        voucher = cbd[len('reject_'):]
        sheets_update({'voucher': voucher, 'RESERVATION_STATUS': 'REJECTED'})
        tg_edit(chat_id, msg_id,
                f"❌ <b>REDDEDİLDİ</b>\n🎫 <code>{voucher}</code>")

    # ── ADMIN: İptal onayla ───────────────────────────────────────────
    elif cbd.startswith('cancel_ok_'):
        voucher = cbd[len('cancel_ok_'):]
        sheets_update({'voucher': voucher, 'RESERVATION_STATUS': 'CANCELLED'})
        tg_edit(chat_id, msg_id,
                f"✅ <b>İPTAL EDİLDİ</b>\n🎫 <code>{voucher}</code>")

    # ── ADMIN: İptal reddet ───────────────────────────────────────────
    elif cbd.startswith('cancel_no_'):
        voucher = cbd[len('cancel_no_'):]
        tg_edit(chat_id, msg_id,
                f"↩️ <b>İptal reddedildi</b>\n🎫 <code>{voucher}</code> aktif.")

    # ── ŞOFÖR: Kabul et ───────────────────────────────────────────────
    elif cbd.startswith('drv_accept_'):
        voucher = cbd[len('drv_accept_'):]
        sheets_update({'voucher': voucher, 'TRANSFER_STATUS': 'DRIVER_CONFIRMED'})
        tg_edit(chat_id, msg_id,
                f"✅ <b>GÖREVİ KABUL ETTİNİZ</b>\n"
                f"🎫 <code>{voucher}</code>\n\n"
                f"Transferiniz onaylandı. İyi yolculuklar!")
        tg_send(ADMIN_CHAT_ID,
                f"✅ <b>ŞOFÖR KABUL ETTİ</b>\n"
                f"🎫 <code>{voucher}</code>\n"
                f"📋 Durum: DRIVER_CONFIRMED")

    # ── ŞOFÖR: Reddet ─────────────────────────────────────────────────
    elif cbd.startswith('drv_reject_'):
        voucher = cbd[len('drv_reject_'):]
        sheets_update({'voucher': voucher, 'TRANSFER_STATUS': 'WAITING_CAR'})
        tg_edit(chat_id, msg_id,
                f"❌ <b>GÖREVİ REDDETTİNİZ</b>\n"
                f"🎫 <code>{voucher}</code>")
        tg_send(ADMIN_CHAT_ID,
                f"⚠️ <b>ŞOFÖR REDDETTİ</b>\n"
                f"🎫 <code>{voucher}</code>\n\n"
                f"Lütfen başka şoför atayın.",
                markup={'inline_keyboard': [[
                    {'text': '🔄 Yeniden Şoför Seç', 'callback_data': f'approve_{voucher}'}
                ]]})


# ── Webhook registration ──────────────────────────────────────────────
def register_webhook():
    domain = os.environ.get('REPLIT_DEV_DOMAIN', '')
    if domain:
        url = f'https://{domain}/telegram'
        try:
            r = requests.post(f'{TG}/setWebhook',
                              json={'url': url,
                                    'allowed_updates': ['message', 'callback_query']},
                              timeout=10)
            print(f'Telegram webhook → {url} : {r.json()}')
        except Exception as e:
            print(f'Webhook failed: {e}')


if __name__ == '__main__':
    register_webhook()
    app.run(host='0.0.0.0', port=5000, debug=False)

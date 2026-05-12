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
tg_sessions      = {}   # {chat_id: [{role,content},...]}
tg_pending       = {}   # {chat_id: 'state_VOUCHER'}
pending_driver_sends = {}  # {voucher: {drv_tgid,drv_name,res_data,timer}}
pending_prices   = {}   # {voucher: price_text}
pending_return_data = {}   # {voucher: {fields for return transfer}}

PRICE_TIMEOUT = 15 * 60   # 15 dakika

# ── System prompt ────────────────────────────────────────────────────
SYSTEM_PROMPT = """Sen BRIX TRAVEL / Voitrip şirketinin profesyonel transfer rezervasyon asistanısın. Türkçe konuşuyorsun.

━━ TRANSFER TİPLERİ ━━━━━━━━━━━━━━━━━━━━━━━

🛬 ARRIVAL (Varış Transferi):
   → Havalimanından → Otel / Adres
   → Yolcu uçaktan iniyor, havalimanından alınıyor
   → FROM: Havalimanı kodu (AYT, BJV, GNY, SAW, ESB, ADB...)
   → TO: Otel adı veya tam adres
   → UÇUŞ SAATİ: Uçağın VARIŞ (iniş) saati
   → PICKUP TIME: Varış saatiyle AYNI → AYRIYETEN SORMA!

🛫 DEPARTURE (Gidiş Transferi):
   → Otel / Adresten → Havalimanına
   → Yolcu uçağa binecek, otelden alınıyor
   → FROM: Otel adı veya tam adres
   → TO: Havalimanı kodu
   → UÇUŞ SAATİ: Uçağın KALKIŞ saati
   → PICKUP TIME: Otelden alınış saati — bilmiyorsa boş bırak

━━ SORU SIRASI ━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Transfer tipi: ARRIVAL mı DEPARTURE mı?
2. FROM ve TO (tipe göre — otel/havalimanı)
3. Tarih (GG.AA.YYYY)
4. Uçuş numarası ve uçuş saati
5. SADECE DEPARTURE ise: Otelden alınış saati (pickup) — bilmiyorsa boş bırak
6. Yolcu tam adı ve telefon numarası
7. Kişi sayısı: yetişkin / çocuk / bebek
8. Satış fiyatı ve döviz (EUR / USD / TRY)

NOT: Ayrıca "otel/adres" diye tekrar SORMA — TO (ARRIVAL) veya FROM (DEPARTURE) zaten otel/adres bilgisini içeriyor.

━━ KRİTİK KURALLAR ━━━━━━━━━━━━━━━━━━━━━━━

• JOB alanını KESINLIKLE doğru belirle: ARRIVAL veya DEPARTURE
• Kullanıcı "varış / geliş / arrival" diyorsa → ARRIVAL
• Kullanıcı "gidiş / kalkış / departure" diyorsa → DEPARTURE
• ARRIVAL'da pickup time SORMA — uçuş saatiyle aynıdır
• Bilgi uydurmadan, kullanıcının yazdığı değerleri aynen kullan

━━ ONAY VE DÖNÜŞ AKIŞI ━━━━━━━━━━━━━━━━━━━

1) Tüm bilgiler tamam → özet göster:

✅ Rezervasyon Özeti:
━━━━━━━━━━━━━━━━
📍 [ARRIVAL/DEPARTURE] | [FROM] → [TO]
📅 Tarih: [TARİH]
✈️ Uçuş: [UCUS NO] [UÇUŞ SAATİ]
🕐 Pickup: [PICKUP veya —]
👤 [YOLCU] | [TELEFON]
👥 [Y]Y / [Ç]Ç / [B]B
💰 [FİYAT] [DÖVİZ]
━━━━━━━━━━━━━━━━
Onaylıyor musunuz?

2) Kullanıcı onayladığında (evet/onayla/tamam/ok) → HEMEN kaydetme!
   Önce şunu sor:
   "🔄 Dönüş transferi de oluşturmak ister misiniz?"

3a) Kullanıcı dönüş İSTEMİYORSA (hayır/istemiyorum/yok) → sadece şunu yaz:
    REZERVASYON_ONAYLANDI

3b) Kullanıcı dönüş İSTİYORSA:
    - Dönüş transfer tipi otomatik tersine döner (ARRIVAL↔DEPARTURE)
    - Dönüş tarihini sor (GG.AA.YYYY)
    - Dönüş uçuş no ve saatini sor
    - Eğer dönüş DEPARTURE ise: alınış saatini sor (bilmiyorsa boş bırak)
    - Kısa dönüş özeti göster
    - Sonra şunu yaz: REZERVASYON_ONAYLANDI

Düzeltme isterse düzelt ve özeti tekrar göster."""

# ── Tool definition for structured field extraction ───────────────────
EXTRACT_TOOL = [{
    "type": "function",
    "function": {
        "name": "update_fields",
        "description": "Rezervasyon bilgilerini ve varsa dönüş transfer bilgilerini çıkar.",
        "parameters": {
            "type": "object",
            "properties": {
                "job":      {"type": "string", "description": "ARRIVAL veya DEPARTURE"},
                "from":     {"type": "string"},
                "to":       {"type": "string"},
                "tarih":    {"type": "string"},
                "ucus":     {"type": "string"},
                "saat":     {"type": "string"},
                "pickup":   {"type": "string"},
                "yolcu":    {"type": "string"},
                "telefon":  {"type": "string"},
                "yetiskin": {"type": "string"},
                "cocuk":    {"type": "string"},
                "bebek":    {"type": "string"},
                "fiyat":    {"type": "string"},
                "doviz":    {"type": "string"},
                "not":      {"type": "string"},
                "has_return":     {"type": "string", "description": "Dönüş transferi var mı? 'evet' veya 'hayir'"},
                "return_tarih":   {"type": "string", "description": "Dönüş transfer tarihi GG.AA.YYYY"},
                "return_ucus":    {"type": "string", "description": "Dönüş uçuş numarası"},
                "return_saat":    {"type": "string", "description": "Dönüş uçuş saati"},
                "return_pickup":  {"type": "string", "description": "Dönüş için pickup saati (sadece DEPARTURE dönüş ise)"}
            },
            "required": []
        }
    }
}]

# ── Telegram helpers ──────────────────────────────────────────────────
def tg_send(chat_id, text, markup=None):
    payload = {'chat_id': str(chat_id), 'text': text, 'parse_mode': 'HTML'}
    if markup:
        payload['reply_markup'] = json.dumps(markup)
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
               'text': text, 'parse_mode': 'HTML',
               'reply_markup': json.dumps(markup or {})}
    try:
        requests.post(f'{TG}/editMessageText', json=payload, timeout=5)
    except Exception:
        pass

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
    now      = datetime.datetime.now()
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

# ── Pickup time logic ─────────────────────────────────────────────────
def calc_pickup(saat, job):
    """
    ARRIVAL  → pickup = flight arrival time (same)
    DEPARTURE → pickup = '' (user provides or admin fills later)
    """
    if job.upper() == 'ARRIVAL':
        return saat   # pickup is when the plane lands
    return ''          # departure pickup is NOT auto-calculated

# ── Admin reservation notification ───────────────────────────────────
def notify_admin(data, voucher, source='WEB'):
    job      = data.get('job', '').upper()
    job_emoji= '🛬' if job == 'ARRIVAL' else '🛫'
    job_label= 'ARRIVAL (Havalimanı→Otel)' if job == 'ARRIVAL' else 'DEPARTURE (Otel→Havalimanı)'
    pickup   = data.get('pickup', '')
    pickup_line = pickup if pickup else '— (admin girecek)'
    msg = (
        f"🆕 <b>YENİ REZERVASYON</b> — {source}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n"
        f"{job_emoji} <b>Transfer:</b> {job_label}\n"
        f"📍 <b>Güzergah:</b> {data.get('from','')} → {data.get('to','')}\n"
        f"📅 <b>Tarih:</b> {data.get('tarih','')}\n"
        f"✈️ <b>Uçuş:</b> {data.get('ucus','')} saat {data.get('saat','')}\n"
        f"🕐 <b>Pickup:</b> {pickup_line}\n"
        f"🏨 <b>Otel/Adres:</b> {data.get('hotel','')}\n"
        f"👤 <b>Yolcu:</b> {data.get('yolcu','')} | {data.get('telefon','')}\n"
        f"👥 <b>Kişi:</b> {data.get('yetiskin','1')}Y / {data.get('cocuk','0')}Ç / {data.get('bebek','0')}B\n"
        f"💰 <b>Satış:</b> {data.get('fiyat','')} {data.get('doviz','EUR')}\n"
        f"📝 <b>Not:</b> {data.get('not','-') or '-'}\n"
        f"━━━━━━━━━━━━━━━━"
    )
    kb = {'inline_keyboard': [[
        {'text': '✅ ONAYLA', 'callback_data': f'approve_{voucher}'},
        {'text': '❌ RED ET', 'callback_data': f'reject_{voucher}'}
    ]]}
    tg_send(ADMIN_CHAT_ID, msg, markup=kb)

# ── Driver notification ───────────────────────────────────────────────
def notify_driver(drv_tgid, drv_name, voucher, res_data, price_text=''):
    job      = str(res_data.get('JOB', res_data.get('job', ''))).upper()
    job_emoji= '🛬' if job == 'ARRIVAL' else '🛫'
    flight_cod  = res_data.get('FLIGHT COD', res_data.get('FLIGHT_COD', ''))
    flight_time = res_data.get('FLIGHT TIME', res_data.get('FLIGHT_TIME', ''))
    pickup_time = res_data.get('PICKUP TIME', res_data.get('PICKUP_TIME', ''))
    hotel       = res_data.get('HOTEL/ADRESS', res_data.get('HOTEL_ADRESS', ''))
    pax_name    = res_data.get('PASSANGER NAME', res_data.get('PASSANGER_NAME', ''))
    pax_phone   = res_data.get('PASSANGER PHONE', res_data.get('PASSANGER_PHONE', ''))
    price_line  = f"\n💰 <b>Tedarikçi Fiyatı:</b> {price_text}" if price_text else ''
    pickup_line = f"\n🕐 <b>Pickup:</b> {pickup_time}" if pickup_time else ''
    msg = (
        f"🚌 <b>YENİ TRANSFER GÖREVİ</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n"
        f"{job_emoji} <b>Transfer:</b> {res_data.get('JOB', job)}\n"
        f"📍 <b>Güzergah:</b> {res_data.get('FROM','')} → {res_data.get('TO','')}\n"
        f"📅 <b>Tarih:</b> {res_data.get('DATE','')}\n"
        f"✈️ <b>Uçuş:</b> {flight_cod} saat {flight_time}"
        f"{pickup_line}\n"
        f"🏨 <b>Otel/Adres:</b> {hotel}\n"
        f"👤 <b>Yolcu:</b> {pax_name}\n"
        f"📞 <b>Yolcu Tel:</b> {pax_phone}\n"
        f"👥 <b>Kişi:</b> {res_data.get('ADULT','1')}Y / "
        f"{res_data.get('CHILD','0')}Ç / {res_data.get('INF','0')}B"
        f"{price_line}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👷 <b>Şoför:</b> {drv_name}"
    )
    kb = {'inline_keyboard': [[
        {'text': '✅ KABUL ET', 'callback_data': f'drv_accept_{voucher}'},
        {'text': '❌ RED ET',   'callback_data': f'drv_reject_{voucher}'}
    ]]}
    tg_send(drv_tgid, msg, markup=kb)

# ── Auto-send driver after price timeout ──────────────────────────────
def _auto_send_driver(voucher):
    info = pending_driver_sends.pop(voucher, None)
    pending_prices.pop(voucher, None)
    for cid, val in list(tg_pending.items()):
        if voucher in val:
            tg_pending.pop(cid, None)
    if not info:
        return
    drv_tgid = info['drv_tgid']
    drv_name = info['drv_name']
    res_data = info['res_data']
    if drv_tgid and drv_tgid != 'nan':
        notify_driver(drv_tgid, drv_name, voucher, res_data, price_text='')
    tg_send(ADMIN_CHAT_ID,
            f"⏰ <b>Süre doldu (15 dk)</b> — <code>{voucher}</code>\n"
            f"Fiyat girilmediği için şoföre <b>fiyatsız</b> gönderildi.")

def _start_price_timer(voucher):
    info      = pending_driver_sends.get(voucher, {})
    old_timer = info.get('timer')
    if old_timer:
        old_timer.cancel()
    t = threading.Timer(PRICE_TIMEOUT, _auto_send_driver, args=[voucher])
    t.daemon = True
    t.start()
    if voucher in pending_driver_sends:
        pending_driver_sends[voucher]['timer'] = t

def _cancel_timer(voucher):
    t = pending_driver_sends.get(voucher, {}).get('timer')
    if t:
        t.cancel()

# ── Save return transfer (from Telegram state machine) ────────────────
def _save_return_transfer(chat_id, voucher):
    data    = pending_return_data.pop(voucher, {})
    tg_pending.pop(str(chat_id), None)

    orig_job   = data.get('original_job', 'ARRIVAL').upper()
    return_job = 'DEPARTURE' if orig_job == 'ARRIVAL' else 'ARRIVAL'

    # Swap FROM/TO
    orig_from = data.get('from', '')
    orig_to   = data.get('to', '')

    ret_date   = data.get('return_date', '')
    ret_flight = data.get('return_flight', '')
    ret_saat   = data.get('return_flight_time', '')
    ret_pickup = data.get('return_pickup', '')

    # ARRIVAL return pickup = flight time; DEPARTURE return = what user said
    if return_job == 'ARRIVAL':
        ret_pickup = ret_saat

    ret_voucher = generate_voucher()
    now_str     = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    sheets_payload = {
        'VOUCHER':          ret_voucher,
        'DATE':             ret_date,
        'OPERATOR':         'BRIX TRAVEL',
        'JOB':              return_job,
        'FROM':             orig_to,    # swapped
        'TO':               orig_from,  # swapped
        'HOTEL_ADRESS':     data.get('hotel', ''),
        'FLIGHT_COD':       ret_flight,
        'FLIGHT_TIME':      ret_saat,
        'PICKUP_TIME':      ret_pickup,
        'PASSANGER_NAME':   data.get('yolcu', ''),
        'PASSANGER_PHONE':  data.get('telefon', ''),
        'ADULT':            data.get('yetiskin', '1'),
        'CHILD':            data.get('cocuk', '0'),
        'INF':              data.get('bebek', '0'),
        'SALE_PRICE':       data.get('fiyat', ''),
        'SALE_CURE':        data.get('doviz', 'EUR'),
        'RESERVATION_STATUS': 'NEW',
        'RESERVATION_STAFF':  'TG',
        'RESERVATION_DATE':   now_str,
    }
    sheets_reserve(sheets_payload)

    return_fields = {
        'job': return_job, 'from': orig_to, 'to': orig_from,
        'tarih': ret_date, 'ucus': ret_flight, 'saat': ret_saat,
        'pickup': ret_pickup, 'hotel': data.get('hotel', ''),
        'yolcu': data.get('yolcu', ''), 'telefon': data.get('telefon', ''),
        'yetiskin': data.get('yetiskin', '1'), 'cocuk': data.get('cocuk', '0'),
        'bebek': data.get('bebek', '0'), 'fiyat': data.get('fiyat', ''),
        'doviz': data.get('doviz', 'EUR'),
    }
    notify_admin(return_fields, ret_voucher, source='🔄 DÖNÜŞ TRANSFERİ')

    job_emoji = '🛬' if return_job == 'ARRIVAL' else '🛫'
    pickup_info = f"\n🕐 Pickup: {ret_pickup}" if ret_pickup else ''
    tg_send(chat_id,
            f"✅ <b>Dönüş Transferi Oluşturuldu!</b>\n\n"
            f"🎫 <b>Voucher:</b> <code>{ret_voucher}</code>\n"
            f"{job_emoji} <b>{return_job}</b> | {orig_to} → {orig_from}\n"
            f"📅 {ret_date} | ✈️ {ret_flight} {ret_saat}"
            f"{pickup_info}\n"
            f"👤 {data.get('yolcu','')}\n\n"
            f"Admin onayı bekleniyor. /check {ret_voucher}")

# ── AI chat fields extractor ──────────────────────────────────────────
def extract_fields_from_history(messages):
    """
    Tüm konuşmadan hem orijinal hem dönüş transfer bilgilerini çıkar.
    JOB alanı için onaylanan özeti (assistant) de kullan.
    Returns: (original_fields, return_fields_or_None)
    """
    user_lines    = []
    asst_summaries= []

    for m in messages:
        role    = m.get('role', '')
        content = m.get('content', '')
        if role == 'user':
            user_lines.append(content)
        elif role == 'assistant' and content:
            asst_summaries.append(content)

    if not user_lines:
        return {}, None

    user_text = '\n'.join(f'U: {line}' for line in user_lines)
    asst_text = '\n'.join(f'A: {s}' for s in asst_summaries[-4:])  # son 4 asst mesajı yeterli

    context = (
        f'Tam konuşma (U=kullanıcı, A=asistan):\n{asst_text}\n{user_text}\n\n'
        f'Görev: Orijinal transfer bilgilerini VE eğer kullanıcı dönüş transferi istediyse '
        f'dönüş bilgilerini çıkar. has_return="evet" ise return_tarih, return_ucus, return_saat doldur.'
    )

    extraction_messages = [
        {
            'role': 'system',
            'content': (
                'Transfer rezervasyon bilgilerini çıkar. '
                'JOB kesinlikle "ARRIVAL" veya "DEPARTURE" olmalı — asistan özetinden al. '
                'Dönüş transferi istenip istenmediğini tespit et: '
                'Kullanıcı "evet dönüş/istiyorum/dönüş oluştur" dediyse has_return="evet". '
                'has_return="evet" ise return_tarih, return_ucus, return_saat alanlarını doldur. '
                'Soru cümlelerini veya AI metin parçalarını değer olarak KAYDETME.'
            )
        },
        {'role': 'user', 'content': context}
    ]

    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=extraction_messages,
            tools=EXTRACT_TOOL,
            tool_choice={'type': 'function', 'function': {'name': 'update_fields'}},
            max_tokens=400
        )
        tc = resp.choices[0].message.tool_calls
        if not tc:
            return {}, None

        all_fields = json.loads(tc[0].function.arguments)
        all_fields = {k: v for k, v in all_fields.items() if v and str(v).strip()}

        # Split original vs return
        return_keys = {'has_return', 'return_tarih', 'return_ucus', 'return_saat', 'return_pickup'}
        orig = {k: v for k, v in all_fields.items() if k not in return_keys}
        ret  = {k: v for k, v in all_fields.items() if k in return_keys}

        # Auto-derive hotel from to/from (no separate hotel question)
        job = orig.get('job', 'ARRIVAL').upper()
        if job == 'ARRIVAL':
            orig['hotel'] = orig.get('to', '')
        else:
            orig['hotel'] = orig.get('from', '')

        has_return = ret.get('has_return', 'hayir').lower() == 'evet'
        return_fields = None
        if has_return and ret.get('return_tarih'):
            orig_job    = orig.get('job', 'ARRIVAL').upper()
            return_job  = 'DEPARTURE' if orig_job == 'ARRIVAL' else 'ARRIVAL'
            ret_saat    = ret.get('return_saat', '')
            ret_pickup  = ret.get('return_pickup', '')
            if return_job == 'ARRIVAL':
                ret_pickup = ret_saat  # ARRIVAL → pickup = flight time
            return_fields = {
                'job':      return_job,
                'from':     orig.get('to', ''),    # swapped
                'to':       orig.get('from', ''),  # swapped
                'hotel':    orig.get('hotel', ''),
                'tarih':    ret.get('return_tarih', ''),
                'ucus':     ret.get('return_ucus', ''),
                'saat':     ret_saat,
                'pickup':   ret_pickup,
                'yolcu':    orig.get('yolcu', ''),
                'telefon':  orig.get('telefon', ''),
                'yetiskin': orig.get('yetiskin', '1'),
                'cocuk':    orig.get('cocuk', '0'),
                'bebek':    orig.get('bebek', '0'),
                'fiyat':    orig.get('fiyat', ''),
                'doviz':    orig.get('doviz', 'EUR'),
            }

        return orig, return_fields

    except Exception:
        pass
    return {}, None

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
                    f"Müşteri cevap bekliyor.")

        all_msgs = full_messages + [{'role': 'assistant', 'content': reply}]
        orig_fields, return_fields = extract_fields_from_history(all_msgs)
        resp_data = {'reply': reply, 'confirmed': confirmed, 'fields': orig_fields}
        if return_fields:
            resp_data['return_fields'] = return_fields
            resp_data['has_return'] = True
        return jsonify(resp_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Web: Reserve ──────────────────────────────────────────────────────
def _build_sheets_payload(fields, voucher, staff='WEB', now_str=''):
    """Build sheets dict from normalized fields dict."""
    if not now_str:
        now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    job    = (fields.get('job') or 'ARRIVAL').upper()
    saat   = fields.get('saat', '')
    pickup = fields.get('pickup', '') or calc_pickup(saat, job)
    # Auto-derive hotel: ARRIVAL → TO is the hotel; DEPARTURE → FROM is the hotel
    hotel  = fields.get('hotel', '') or (fields.get('to','') if job == 'ARRIVAL' else fields.get('from',''))
    return {
        'VOUCHER':          voucher,
        'DATE':             fields.get('tarih', ''),
        'OPERATOR':         'BRIX TRAVEL',
        'JOB':              job,
        'FROM':             fields.get('from', ''),
        'TO':               fields.get('to', ''),
        'HOTEL_ADRESS':     hotel,
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
        'RESERVATION_STAFF':  staff,
        'RESERVATION_DATE':   now_str,
    }

@app.route('/api/reserve', methods=['POST'])
def api_reserve():
    data    = request.get_json(force=True)
    now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    voucher = data.get('voucher') or generate_voucher()

    # Auto-derive hotel field if not provided
    job = (data.get('job') or 'ARRIVAL').upper()
    if not data.get('hotel'):
        data['hotel'] = data.get('to','') if job == 'ARRIVAL' else data.get('from','')

    sheets_reserve(_build_sheets_payload(data, voucher, staff='WEB', now_str=now_str))
    notify_admin(data, voucher, source='🌐 WEB')

    ret_voucher = None
    # Save return transfer if provided in the same request
    return_fields = data.get('return_fields')
    if return_fields and return_fields.get('tarih'):
        ret_voucher = generate_voucher()
        sheets_reserve(_build_sheets_payload(return_fields, ret_voucher, staff='WEB', now_str=now_str))
        notify_admin(return_fields, ret_voucher, source='🔄 DÖNÜŞ (WEB)')

    resp = {'status': 'ok', 'voucher': voucher}
    if ret_voucher:
        resp['return_voucher'] = ret_voucher

    return jsonify(resp), 200


# ── Web: Check ────────────────────────────────────────────────────────
@app.route('/api/check', methods=['GET'])
def api_check():
    voucher = request.args.get('voucher', '').upper().strip()
    if not voucher:
        return jsonify({'error': 'Voucher gerekli'}), 400
    return jsonify(sheets_check(voucher))


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
    data    = request.get_json(force=True)
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

    pending = tg_pending.get(str(chat_id), '')

    # ── Return transfer state machine ─────────────────────────────────
    if pending.startswith('return_date_'):
        voucher = pending[len('return_date_'):]
        pending_return_data[voucher]['return_date'] = text
        tg_pending[str(chat_id)] = f'return_flight_{voucher}'
        orig_job   = pending_return_data[voucher].get('original_job', 'ARRIVAL')
        return_job = 'DEPARTURE' if orig_job == 'ARRIVAL' else 'ARRIVAL'
        job_emoji  = '🛫' if return_job == 'DEPARTURE' else '🛬'
        tg_send(chat_id,
                f"✅ Tarih: {text}\n\n"
                f"{job_emoji} Dönüş uçuş numarası ve saatini girin:\n"
                f"Örnek: <code>PC1802 17:45</code>")
        return

    if pending.startswith('return_flight_'):
        voucher = pending[len('return_flight_'):]
        parts   = text.strip().split()
        flight_no   = parts[0] if parts else ''
        flight_time = parts[1] if len(parts) > 1 else ''
        pending_return_data[voucher]['return_flight']      = flight_no
        pending_return_data[voucher]['return_flight_time'] = flight_time

        orig_job   = pending_return_data[voucher].get('original_job', 'ARRIVAL')
        return_job = 'DEPARTURE' if orig_job == 'ARRIVAL' else 'ARRIVAL'

        if return_job == 'DEPARTURE':
            # Need pickup time for departure
            tg_pending[str(chat_id)] = f'return_pickup_{voucher}'
            tg_send(chat_id,
                    f"✅ Uçuş: {flight_no} saat {flight_time}\n\n"
                    f"🕐 Otelden alınış saatini girin:\n"
                    f"Örnek: <code>14:30</code>\n"
                    f"(Bilmiyorsanız <code>boş</code> yazın, admin doldurur)")
        else:
            # ARRIVAL return — no pickup needed
            _save_return_transfer(chat_id, voucher)
        return

    if pending.startswith('return_pickup_'):
        voucher = pending[len('return_pickup_'):]
        pickup  = '' if text.lower() in ['boş', 'bos', '-', 'bilmiyorum', 'yok'] else text
        pending_return_data[voucher]['return_pickup'] = pickup
        _save_return_transfer(chat_id, voucher)
        return

    # ── Price input ───────────────────────────────────────────────────
    if pending.startswith('awaiting_price_'):
        voucher    = pending[len('awaiting_price_'):]
        price_text = text.strip()
        pending_prices[voucher] = price_text
        tg_pending.pop(str(chat_id), None)
        kb = {'inline_keyboard': [[
            {'text': '✅ EVET, GÖNDER',         'callback_data': f'pricesend_{voucher}'},
            {'text': '⏭️ GEÇ (fiyatsız gönder)', 'callback_data': f'priceskip_{voucher}'}
        ]]}
        tg_send(chat_id,
                f"💰 <b>Fiyat:</b> {price_text}\n\n"
                f"Taşımacıya bu fiyatla göndereyim mi?",
                markup=kb)
        return

    # ── Commands ──────────────────────────────────────────────────────
    if text.startswith('/start'):
        tg_sessions[str(chat_id)] = []
        tg_pending.pop(str(chat_id), None)
        tg_send(chat_id,
                f"👋 Merhaba <b>{username}</b>! Ben Voitrip AI Asistanı.\n\n"
                f"Transfer rezervasyonu yapmak için transfer tipini söyleyin:\n\n"
                f"🛬 <b>ARRIVAL</b> — Havalimanı → Otel\n"
                f"🛫 <b>DEPARTURE</b> — Otel → Havalimanı\n\n"
                f"Komutlar:\n"
                f"/check VOUCHER — Rezervasyon sorgula\n"
                f"/cancel VOUCHER — İptal talebi\n"
                f"/driver — Şoför kaydı")
        return

    if text.startswith('/check'):
        parts = text.split()
        if len(parts) < 2:
            tg_send(chat_id, "❓ Kullanım: /check VOUCHER")
            return
        voucher = parts[1].upper()
        data    = sheets_check(voucher)
        if data.get('found'):
            d         = data.get('data', {})
            job       = str(d.get('JOB', '')).upper()
            job_emoji = '🛬' if job == 'ARRIVAL' else '🛫'
            tg_send(chat_id,
                    f"✅ <b>Rezervasyon Bulundu</b>\n━━━━━━━━━━━━━━━\n"
                    f"🎫 <code>{voucher}</code>\n"
                    f"{job_emoji} {d.get('JOB','')} | {d.get('FROM','')} → {d.get('TO','')}\n"
                    f"📅 {d.get('DATE','')}\n"
                    f"✈️ {d.get('FLIGHT COD','')} {d.get('FLIGHT TIME','')}\n"
                    f"🕐 Pickup: {d.get('PICKUP TIME','') or '—'}\n"
                    f"🏨 {d.get('HOTEL/ADRESS','')}\n"
                    f"👤 {d.get('PASSANGER NAME','')} | {d.get('PASSANGER PHONE','')}\n"
                    f"📋 Durum: <b>{d.get('RESERVATION STATUS','')}</b>")
        else:
            tg_send(chat_id, f"❌ <code>{voucher}</code> bulunamadı.")
        return

    if text.startswith('/cancel'):
        parts = text.split()
        if len(parts) < 2:
            tg_send(chat_id, "❓ Kullanım: /cancel VOUCHER")
            return
        voucher = parts[1].upper()
        kb = {'inline_keyboard': [[
            {'text': '✅ İptali Onayla', 'callback_data': f'cancel_ok_{voucher}'},
            {'text': '❌ Reddet',        'callback_data': f'cancel_no_{voucher}'}
        ]]}
        tg_send(ADMIN_CHAT_ID,
                f"❌ <b>İPTAL TALEBİ</b>\n🎫 <code>{voucher}</code>\n👤 {username} ({chat_id})",
                markup=kb)
        tg_send(chat_id, f"✅ <code>{voucher}</code> için iptal talebi admin'e gönderildi.")
        return

    if text.startswith('/driver'):
        tg_send(chat_id,
                f"🚗 <b>Şoför Kaydı</b>\n\n"
                f"Telegram ID'niz: <code>{chat_id}</code>\n"
                f"Bu ID'yi yöneticinize bildirin.")
        tg_send(ADMIN_CHAT_ID,
                f"🚗 <b>Şoför Kaydı Talebi</b>\n"
                f"👤 {username}\n🆔 <code>{chat_id}</code>")
        return

    # ── AI conversation ───────────────────────────────────────────────
    session = tg_sessions.setdefault(str(chat_id), [])
    session.append({'role': 'user', 'content': text})

    full_msgs = [{'role': 'system', 'content': SYSTEM_PROMPT}] + session

    try:
        resp  = client.chat.completions.create(
            model='gpt-4o-mini', messages=full_msgs, max_tokens=600)
        reply = resp.choices[0].message.content
        session.append({'role': 'assistant', 'content': reply})

        if 'FALLBACK_TO_ADMIN' in reply:
            tg_send(chat_id, reply.replace('FALLBACK_TO_ADMIN', '').strip())
            tg_send(ADMIN_CHAT_ID,
                    f"❓ <b>MÜŞTERİ SORUSU (Telegram)</b>\n👤 {username} ({chat_id})\n\n<i>{text}</i>")
            return

        if 'REZERVASYON_ONAYLANDI' in reply:
            orig_fields, return_fields = extract_fields_from_history(full_msgs)
            now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
            voucher = generate_voucher()

            # Save original
            sheets_reserve(_build_sheets_payload(orig_fields, voucher, staff='TG', now_str=now_str))
            notify_admin(orig_fields, voucher, source='📱 TELEGRAM')
            tg_sessions.pop(str(chat_id), None)

            job = (orig_fields.get('job') or 'ARRIVAL').upper()

            # Save return transfer if user requested it in conversation
            if return_fields and return_fields.get('tarih'):
                ret_voucher = generate_voucher()
                sheets_reserve(_build_sheets_payload(return_fields, ret_voucher, staff='TG', now_str=now_str))
                notify_admin(return_fields, ret_voucher, source='🔄 DÖNÜŞ (TG)')
                ret_job   = return_fields.get('job', '')
                ret_emoji = '🛫' if ret_job == 'DEPARTURE' else '🛬'
                tg_send(chat_id,
                        f"✅ <b>İki Rezervasyon Kaydedildi!</b>\n\n"
                        f"🎫 <b>Gidiş:</b> <code>{voucher}</code>\n"
                        f"🎫 <b>Dönüş:</b> <code>{ret_voucher}</code>\n\n"
                        f"{ret_emoji} {ret_job} | {return_fields.get('from','')} → {return_fields.get('to','')}\n"
                        f"📅 {return_fields.get('tarih','')} | ✈️ {return_fields.get('ucus','')} {return_fields.get('saat','')}\n\n"
                        f"Admin'e bildirimler gönderildi.")
            else:
                tg_send(chat_id,
                        f"✅ <b>Rezervasyon Kaydedildi!</b>\n\n"
                        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n\n"
                        f"Admin'e bildirim gönderildi.")
            return

        tg_send(chat_id, reply)

    except Exception as e:
        tg_send(chat_id, f"❌ Bir hata oluştu: {str(e)}")


def _handle_callback(cq):
    cq_id   = cq.get('id')
    chat_id = cq.get('message', {}).get('chat', {}).get('id')
    msg_id  = cq.get('message', {}).get('message_id')
    cbd     = cq.get('data', '')
    tg_answer(cq_id)

    # ── ADMIN: Onayla ─────────────────────────────────────────────────
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
            buttons = [[{
                'text': f"🚗 {d.get('DRIVER_NAME','İsimsiz')} ({d.get('SUPPLIER_NAME','')})",
                'callback_data': f"drv_{d.get('DRIVER_ID','')}_{voucher}"
            }] for d in drivers]
            tg_edit(chat_id, msg_id,
                    f"✅ <b>ONAYLANDI</b> — <code>{voucher}</code>\n\n👇 Şoför seçin:")
            tg_send(chat_id,
                    f"🚌 <b>{voucher}</b> için şoför atayın:",
                    markup={'inline_keyboard': buttons})

    # ── ADMIN: Şoför seç → fiyat sor ─────────────────────────────────
    elif cbd.startswith('drv_'):
        parts   = cbd.split('_', 2)
        drv_id  = parts[1] if len(parts) > 1 else ''
        voucher = parts[2] if len(parts) > 2 else ''

        drivers = get_drivers()
        driver  = next((d for d in drivers
                        if str(d.get('DRIVER_ID','')) == drv_id), None)
        if not driver:
            tg_edit(chat_id, msg_id, f"❌ Şoför bulunamadı (ID: {drv_id})")
            return

        drv_name  = driver.get('DRIVER_NAME', '')
        drv_phone = driver.get('DRIVER_PHONE', '')
        supplier  = driver.get('SUPPLIER_NAME', '')
        drv_tgid  = str(driver.get('TELEGRAM_ID', ''))

        sheets_update({
            'voucher': voucher, 'TRANSFER_STATUS': 'WAITING_DRIVER',
            'SUPPLIER_NAME': supplier, 'DRIVER_NAME': drv_name,
            'DRIVER_PHONE': drv_phone,
        })

        res_data = sheets_check(voucher).get('data', {})
        pending_driver_sends[voucher] = {
            'drv_tgid': drv_tgid, 'drv_name': drv_name,
            'res_data': res_data, 'timer': None
        }
        _start_price_timer(voucher)

        tg_edit(chat_id, msg_id,
                f"✅ <b>ŞOFÖR ATANDI</b> — <code>{voucher}</code>\n"
                f"🚗 <b>{drv_name}</b> ({supplier})\n"
                f"📞 {drv_phone}\n\n"
                f"⏳ Şoföre gönderilmeden önce tedarikçi fiyatını girin.")

        tg_pending[str(chat_id)] = f'awaiting_price_{voucher}'
        tg_send(chat_id,
                f"💰 <b>{voucher}</b> tedarikçi fiyatı:\n"
                f"Örnek: <code>45 EUR</code>\n\n"
                f"⏰ 15 dk içinde girilmezse şoföre fiyatsız gönderilir.")

    # ── ADMIN: Fiyatla gönder ─────────────────────────────────────────
    elif cbd.startswith('pricesend_'):
        voucher    = cbd[len('pricesend_'):]
        price_text = pending_prices.pop(voucher, '')
        _cancel_timer(voucher)
        info = pending_driver_sends.pop(voucher, None)
        if info:
            if price_text:
                pts = price_text.split()
                sheets_update({'voucher': voucher,
                               'SUPPLIER_PRICE':    pts[0],
                               'SUPPLIER_CURRENCY': pts[1].upper() if len(pts)>1 else 'EUR'})
            if info['drv_tgid'] and info['drv_tgid'] != 'nan':
                notify_driver(info['drv_tgid'], info['drv_name'], voucher,
                              info['res_data'], price_text=price_text)
        tg_edit(chat_id, msg_id,
                f"✅ <b>Şoföre gönderildi</b> — <code>{voucher}</code>\n"
                f"💰 Fiyat: {price_text or '—'}")

    # ── ADMIN: Fiyatsız gönder ────────────────────────────────────────
    elif cbd.startswith('priceskip_'):
        voucher = cbd[len('priceskip_'):]
        pending_prices.pop(voucher, None)
        tg_pending.pop(str(chat_id), None)
        _cancel_timer(voucher)
        info = pending_driver_sends.pop(voucher, None)
        if info and info['drv_tgid'] and info['drv_tgid'] != 'nan':
            notify_driver(info['drv_tgid'], info['drv_name'], voucher,
                          info['res_data'], price_text='')
        tg_edit(chat_id, msg_id,
                f"✅ <b>Şoföre fiyatsız gönderildi</b> — <code>{voucher}</code>")

    # ── ADMIN: Red et ─────────────────────────────────────────────────
    elif cbd.startswith('reject_'):
        voucher = cbd[len('reject_'):]
        sheets_update({'voucher': voucher, 'RESERVATION_STATUS': 'REJECTED'})
        tg_edit(chat_id, msg_id, f"❌ <b>REDDEDİLDİ</b>\n🎫 <code>{voucher}</code>")

    # ── ADMIN: İptal onayla ───────────────────────────────────────────
    elif cbd.startswith('cancel_ok_'):
        voucher = cbd[len('cancel_ok_'):]
        sheets_update({'voucher': voucher, 'RESERVATION_STATUS': 'CANCELLED'})
        tg_edit(chat_id, msg_id, f"✅ <b>İPTAL EDİLDİ</b>\n🎫 <code>{voucher}</code>")

    # ── ADMIN: İptal reddet ───────────────────────────────────────────
    elif cbd.startswith('cancel_no_'):
        voucher = cbd[len('cancel_no_'):]
        tg_edit(chat_id, msg_id,
                f"↩️ <b>İptal reddedildi</b>\n🎫 <code>{voucher}</code> aktif.")

    # ── DÖNÜŞ: Evet ──────────────────────────────────────────────────
    elif cbd.startswith('retyes_'):
        voucher  = cbd[len('retyes_'):]
        orig     = pending_return_data.get(voucher)
        if not orig:
            tg_edit(chat_id, msg_id, f"❌ Dönüş verisi bulunamadı.")
            return
        orig_job   = orig.get('original_job', 'ARRIVAL')
        return_job = 'DEPARTURE' if orig_job == 'ARRIVAL' else 'ARRIVAL'
        return_emoji = '🛫' if return_job == 'DEPARTURE' else '🛬'
        return_from  = orig.get('to', '')
        return_to    = orig.get('from', '')
        tg_edit(chat_id, msg_id,
                f"🔄 <b>Dönüş Transferi</b>\n"
                f"{return_emoji} {return_job}: {return_from} → {return_to}\n"
                f"👤 {orig.get('yolcu','')}\n\n📅 Dönüş tarihi bekleniyor...")
        tg_pending[str(chat_id)] = f'return_date_{voucher}'
        tg_send(chat_id, f"📅 Dönüş transferi başlatıldı!\n\n"
                         f"{return_emoji} <b>{return_job}</b>: {return_from} → {return_to}\n\n"
                         f"Dönüş tarihini girin (GG.AA.YYYY):")

    # ── DÖNÜŞ: Hayır ─────────────────────────────────────────────────
    elif cbd.startswith('retno_'):
        voucher = cbd[len('retno_'):]
        pending_return_data.pop(voucher, None)
        tg_edit(chat_id, msg_id,
                f"✅ <b>Rezervasyon tamamlandı.</b>\n"
                f"🎫 <code>{voucher}</code>\n\nDönüş transferi oluşturulmadı.")

    # ── ŞOFÖR: Kabul et ───────────────────────────────────────────────
    elif cbd.startswith('drv_accept_'):
        voucher = cbd[len('drv_accept_'):]
        sheets_update({'voucher': voucher, 'TRANSFER_STATUS': 'DRIVER_CONFIRMED'})
        tg_edit(chat_id, msg_id,
                f"✅ <b>GÖREVİ KABUL ETTİNİZ</b>\n🎫 <code>{voucher}</code>\nİyi yolculuklar!")
        tg_send(ADMIN_CHAT_ID,
                f"✅ <b>ŞOFÖR KABUL ETTİ</b>\n🎫 <code>{voucher}</code>\n📋 DRIVER_CONFIRMED")

    # ── ŞOFÖR: Red et ─────────────────────────────────────────────────
    elif cbd.startswith('drv_reject_'):
        voucher = cbd[len('drv_reject_'):]
        sheets_update({'voucher': voucher, 'TRANSFER_STATUS': 'WAITING_CAR'})
        tg_edit(chat_id, msg_id,
                f"❌ <b>GÖREVİ REDDETTİNİZ</b>\n🎫 <code>{voucher}</code>")
        tg_send(ADMIN_CHAT_ID,
                f"⚠️ <b>ŞOFÖR REDDETTİ</b>\n🎫 <code>{voucher}</code>\n\nBaşka şoför atayın.",
                markup={'inline_keyboard': [[
                    {'text': '🔄 Yeniden Şoför Seç',
                     'callback_data': f'approve_{voucher}'}
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

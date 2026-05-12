import os
import json
import datetime
import requests
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)
CORS(app)

SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxvqcAXLNyIU0DPrNQQDB3ZcfIsy9pT5STCkZTe-9yQIkED_au6B_ciF_aop_jyTP7ulQ/exec'
TELEGRAM_TOKEN = '8654282740:AAGSXtoXAMtbTmfJiWJI1C_VpM1Oq-4XvGI'
ADMIN_CHAT_ID = '5833736265'
TG = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}'

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# ── System prompt ────────────────────────────────────────────────────
SYSTEM_PROMPT = """Sen BRIX TRAVEL / Voitrip şirketinin profesyonel transfer rezervasyon asistanısın. Türkçe konuşuyorsun.

Kullanıcıdan sırayla şu bilgileri topla (her seferinde 1-2 soru sor, kısa ve net ol):
1. Transfer tipi: ARRIVAL mi DEPARTURE mi?
2. Nereden → Nereye (havalimanı kodu veya adres kısa olsun)
3. Tarih (GG.AA.YYYY)
4. Uçuş numarası ve uçuş saati (SS:DD)
5. Otel/adres adı
6. Yolcu adı (tam ad) ve telefon numarası
7. Yetişkin / çocuk / bebek sayısı
8. Satış fiyatı ve döviz (EUR/USD/TRY)

PICKUP TIME:
- ARRIVAL → Pickup = Uçuş saati (aynı)
- DEPARTURE → Pickup = Uçuş saati - 3.5 saat

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

# ── Tool definition for structured field extraction ──────────────────
EXTRACT_TOOL = [{
    "type": "function",
    "function": {
        "name": "update_fields",
        "description": "Kullanıcının konuşmasından doğrulanan rezervasyon alanlarını güncelle. Sadece kullanıcının açıkça belirttiği değerleri doldur, AI prompt metnini asla yazma.",
        "parameters": {
            "type": "object",
            "properties": {
                "job":      {"type": "string", "description": "ARRIVAL veya DEPARTURE"},
                "from":     {"type": "string", "description": "Kalkış noktası (kısa, ör: AYT, Antalya Havalimanı)"},
                "to":       {"type": "string", "description": "Varış noktası (kısa, ör: BELEK, Sueno Hotel)"},
                "tarih":    {"type": "string", "description": "Tarih GG.AA.YYYY formatında"},
                "ucus":     {"type": "string", "description": "Uçuş numarası"},
                "saat":     {"type": "string", "description": "Uçuş saati SS:DD"},
                "pickup":   {"type": "string", "description": "Pickup saati SS:DD"},
                "hotel":    {"type": "string", "description": "Otel veya adres adı"},
                "yolcu":    {"type": "string", "description": "Yolcu tam adı"},
                "telefon":  {"type": "string", "description": "Telefon numarası"},
                "yetiskin": {"type": "string", "description": "Yetişkin sayısı (rakam)"},
                "cocuk":    {"type": "string", "description": "Çocuk sayısı (rakam)"},
                "bebek":    {"type": "string", "description": "Bebek sayısı (rakam)"},
                "fiyat":    {"type": "string", "description": "Satış fiyatı (rakam)"},
                "doviz":    {"type": "string", "description": "Döviz: EUR, USD veya TRY"},
                "not":      {"type": "string", "description": "Varsa özel not"}
            },
            "required": []
        }
    }
}]

# ── Helpers ──────────────────────────────────────────────────────────
def tg_send(chat_id, text, markup=None):
    payload = {'chat_id': str(chat_id), 'text': text, 'parse_mode': 'HTML'}
    if markup:
        payload['reply_markup'] = json.dumps(markup)
    try:
        requests.post(f'{TG}/sendMessage', json=payload, timeout=10)
    except Exception:
        pass

def tg_answer(callback_id, text=''):
    try:
        requests.post(f'{TG}/answerCallbackQuery',
                      json={'callback_query_id': callback_id, 'text': text},
                      timeout=5)
    except Exception:
        pass

def tg_edit(chat_id, message_id, text):
    try:
        requests.post(f'{TG}/editMessageText',
                      json={'chat_id': str(chat_id), 'message_id': message_id,
                            'text': text, 'parse_mode': 'HTML'},
                      timeout=5)
    except Exception:
        pass

def get_drivers():
    """DRIVERS sheet'ten aktif şoför listesini çek."""
    try:
        resp = requests.get(SCRIPT_URL,
                            params={'action': 'get_drivers'},
                            timeout=15)
        result = resp.json()
        if isinstance(result, list):
            return result
        return result.get('drivers', [])
    except Exception:
        return []

def notify_admin(data, voucher):
    job_emoji = '🛬' if data.get('job','').upper() == 'ARRIVAL' else '🛫'
    msg = (
        f"🆕 <b>YENİ REZERVASYON</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n"
        f"{job_emoji} <b>Transfer:</b> {data.get('job','')}\n"
        f"📍 <b>Güzergah:</b> {data.get('from','')} → {data.get('to','')}\n"
        f"📅 <b>Tarih:</b> {data.get('tarih','')}\n"
        f"✈️ <b>Uçuş:</b> {data.get('ucus','')} saat {data.get('saat','')}\n"
        f"🕐 <b>Pickup:</b> {data.get('pickup','')}\n"
        f"🏨 <b>Otel:</b> {data.get('hotel','')}\n"
        f"👤 <b>Yolcu:</b> {data.get('yolcu','')} | {data.get('telefon','')}\n"
        f"👥 <b>Kişi:</b> {data.get('yetiskin','0')}Y / {data.get('cocuk','0')}Ç / {data.get('bebek','0')}B\n"
        f"💰 <b>Fiyat:</b> {data.get('fiyat','')} {data.get('doviz','EUR')}\n"
        f"📝 <b>Not:</b> {data.get('not','-')}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🌐 Web arayüzünden girildi"
    )
    kb = {'inline_keyboard': [[
        {'text': '✅ ONAYLA', 'callback_data': f'approve_{voucher}'},
        {'text': '❌ RED ET', 'callback_data': f'reject_{voucher}'}
    ]]}
    tg_send(ADMIN_CHAT_ID, msg, kb)

def generate_voucher():
    now = datetime.datetime.now()
    return f"BRX{now.strftime('%d%m%y%H%M')}"

def calc_pickup(saat, job):
    if not saat:
        return ''
    if job.upper() == 'ARRIVAL':
        return saat
    try:
        h, m = map(int, saat.split(':'))
        total = h * 60 + m - 210
        if total < 0:
            total += 1440
        return f'{total//60:02d}:{total%60:02d}'
    except Exception:
        return saat

# ── Static files ─────────────────────────────────────────────────────
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
        headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded]
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

# ── AI Chat — with tool calling for field extraction ─────────────────
@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json(force=True)
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'error': 'Mesaj gerekli'}), 400

    full_messages = [{'role': 'system', 'content': SYSTEM_PROMPT}] + messages

    try:
        # Step 1: Get conversational reply
        reply_resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=full_messages,
            max_tokens=600
        )
        reply = reply_resp.choices[0].message.content

        confirmed = 'REZERVASYON_ONAYLANDI' in reply

        # Step 2: Extract structured fields from conversation (parallel tool call)
        extract_messages = full_messages + [{'role': 'assistant', 'content': reply}]
        extract_resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=extract_messages + [{
                'role': 'user',
                'content': 'Şimdiye kadar kullanıcının kesin olarak belirttiği rezervasyon bilgilerini update_fields fonksiyonuyla kaydet. Sadece kullanıcının söylediği gerçek değerleri yaz, soru metni veya açıklama yazma.'
            }],
            tools=EXTRACT_TOOL,
            tool_choice={'type': 'function', 'function': {'name': 'update_fields'}},
            max_tokens=300
        )

        fields = {}
        tool_calls = extract_resp.choices[0].message.tool_calls
        if tool_calls:
            try:
                fields = json.loads(tool_calls[0].function.arguments)
                # Remove empty strings
                fields = {k: v for k, v in fields.items() if v and str(v).strip()}
            except Exception:
                fields = {}

        return jsonify({'reply': reply, 'confirmed': confirmed, 'fields': fields})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Reserve — save to Google Sheets + notify Telegram ────────────────
@app.route('/api/reserve', methods=['POST'])
def api_reserve():
    data = request.get_json(force=True)

    voucher = data.get('voucher') or generate_voucher()
    data['voucher'] = voucher

    job = data.get('job', 'ARRIVAL').upper()
    saat = data.get('saat', '')
    pickup = data.get('pickup', '') or calc_pickup(saat, job)
    now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    # Map exactly to Google Sheets column order:
    # VOUCHER | DATE | OPERATOR | JOB | FROM | TO | HOTEL/ADRESS |
    # FLIGHT COD | FLIGHT TIME | PICKUP TIME | PASSANGER NAME | PASSANGER PHONE |
    # ADULT | CHILD | INF | SALE PRICE | SALE CURE | NOTE 1 |
    # RESERVATION STATUS | RESERVATION STAFF | RESERVATION DATE
    sheets_payload = {
        'action': 'reserve',
        'VOUCHER':             voucher,
        'DATE':                data.get('tarih', ''),
        'OPERATOR':            data.get('operator', 'BRIX TRAVEL'),
        'JOB':                 job,
        'FROM':                data.get('from', ''),
        'TO':                  data.get('to', ''),
        'HOTEL_ADRESS':        data.get('hotel', ''),
        'FLIGHT_COD':          data.get('ucus', ''),
        'FLIGHT_TIME':         saat,
        'PICKUP_TIME':         pickup,
        'PASSANGER_NAME':      data.get('yolcu', ''),
        'PASSANGER_PHONE':     data.get('telefon', ''),
        'ADULT':               data.get('yetiskin', '1'),
        'CHILD':               data.get('cocuk', '0'),
        'INF':                 data.get('bebek', '0'),
        'SALE_PRICE':          data.get('fiyat', ''),
        'SALE_CURE':           data.get('doviz', 'EUR'),
        'NOTE_1':              data.get('not', ''),
        'RESERVATION_STATUS':  'NEW',
        'RESERVATION_STAFF':   'WEB',
        'RESERVATION_DATE':    now_str,
    }

    try:
        requests.post(SCRIPT_URL, json=sheets_payload, timeout=20)
    except Exception as e:
        return jsonify({'error': f'Sheets hatası: {str(e)}'}), 500

    # Telegram admin notification
    notify_admin(data, voucher)

    return jsonify({'status': 'ok', 'voucher': voucher}), 200


# ── Check ─────────────────────────────────────────────────────────────
@app.route('/api/check', methods=['GET'])
def api_check():
    voucher = request.args.get('voucher', '').upper().strip()
    if not voucher:
        return jsonify({'error': 'Voucher gerekli'}), 400
    try:
        resp = requests.get(SCRIPT_URL, params={'action': 'check', 'voucher': voucher}, timeout=15)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Edit ──────────────────────────────────────────────────────────────
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


# ── Cancel ────────────────────────────────────────────────────────────
@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    data = request.get_json(force=True)
    if not data or not data.get('voucher'):
        return jsonify({'error': 'Voucher gerekli'}), 400
    voucher = data.get('voucher', '').upper()
    msg = (f"❌ <b>İPTAL TALEBİ</b>\n"
           f"🎫 Voucher: <code>{voucher}</code>\n"
           f"🌐 Web arayüzünden gönderildi")
    kb = {'inline_keyboard': [[
        {'text': '✅ İptali Onayla', 'callback_data': f'cancel_ok_{voucher}'},
        {'text': '❌ Reddet', 'callback_data': f'cancel_no_{voucher}'}
    ]]}
    tg_send(ADMIN_CHAT_ID, msg, kb)
    try:
        requests.post(SCRIPT_URL, json={**data, 'action': 'cancel', 'voucher': voucher}, timeout=15)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Telegram Webhook — handle callback_query ──────────────────────────
@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = request.get_json(force=True, silent=True) or {}

    # Handle callback queries (inline keyboard button presses)
    cq = update.get('callback_query')
    if cq:
        cq_id   = cq.get('id')
        chat_id = cq.get('message', {}).get('chat', {}).get('id')
        msg_id  = cq.get('message', {}).get('message_id')
        cbd     = cq.get('data', '')

        tg_answer(cq_id)  # remove loading spinner

        if cbd.startswith('approve_'):
            # ── Rezervasyonu onayla → DRIVERS listesini getir ──────────
            voucher = cbd[len('approve_'):]
            try:
                requests.post(SCRIPT_URL, json={
                    'action': 'update_status',
                    'voucher': voucher,
                    'RESERVATION_STATUS': 'APPROVED',
                    'TRANSFER_STATUS': 'WAITING_CAR'
                }, timeout=15)
            except Exception:
                pass

            drivers = get_drivers()
            if not drivers:
                tg_edit(chat_id, msg_id,
                        f"✅ <b>ONAYLANDI</b> — <code>{voucher}</code>\n\n"
                        f"⚠️ DRIVERS sayfasında aktif şoför bulunamadı. "
                        f"Lütfen Sheets'te manuel atama yapın.")
            else:
                # Şoför butonu: callback_data max 64 byte → DRV_ID kısa tutuyoruz
                buttons = []
                for d in drivers:
                    drv_id   = str(d.get('DRIVER_ID', ''))
                    drv_name = d.get('DRIVER_NAME', 'İsimsiz')
                    supplier = d.get('SUPPLIER_NAME', '')
                    label    = f"🚗 {drv_name} ({supplier})"
                    # Format: drv_DRIVERID_VOUCHER  (voucher max 13 char → safe)
                    cb       = f"drv_{drv_id}_{voucher}"
                    buttons.append([{'text': label, 'callback_data': cb}])

                tg_edit(chat_id, msg_id,
                        f"✅ <b>ONAYLANDI</b> — <code>{voucher}</code>\n\n"
                        f"👇 Şoför seçin:")
                tg_send(chat_id,
                        f"🚌 <b>{voucher}</b> için şoför atayın:",
                        markup={'inline_keyboard': buttons})

        elif cbd.startswith('drv_'):
            # ── Şoför seçildi → Sheets güncelle + şoföre bildir ────────
            parts   = cbd.split('_', 2)   # ['drv', DRIVER_ID, VOUCHER]
            drv_id  = parts[1] if len(parts) > 1 else ''
            voucher = parts[2] if len(parts) > 2 else ''

            # Şoför bilgilerini DRIVERS listesinden bul
            drivers = get_drivers()
            driver  = next((d for d in drivers
                            if str(d.get('DRIVER_ID','')) == drv_id), None)

            if not driver:
                tg_edit(chat_id, msg_id, f"❌ Şoför bulunamadı (ID: {drv_id})")
            else:
                drv_name  = driver.get('DRIVER_NAME', '')
                drv_phone = driver.get('DRIVER_PHONE', '')
                supplier  = driver.get('SUPPLIER_NAME', '')
                drv_tgid  = driver.get('TELEGRAM_ID', '')

                # Google Sheets güncelle
                try:
                    requests.post(SCRIPT_URL, json={
                        'action':            'update_status',
                        'voucher':           voucher,
                        'TRANSFER_STATUS':   'ASSIGNED',
                        'SUPPLIER_NAME':     supplier,
                        'DRIVER_NAME':       drv_name,
                        'DRIVER_PHONE':      drv_phone,
                    }, timeout=15)
                except Exception:
                    pass

                # Admin mesajını güncelle
                tg_edit(chat_id, msg_id,
                        f"✅ <b>ŞOFÖR ATANDI</b>\n"
                        f"🎫 Voucher: <code>{voucher}</code>\n"
                        f"🚗 Şoför: <b>{drv_name}</b>\n"
                        f"📞 Telefon: {drv_phone}\n"
                        f"🏢 Firma: {supplier}")

                # Şoföre Telegram bildirimi (TELEGRAM_ID varsa)
                if drv_tgid:
                    drv_msg = (
                        f"🚌 <b>YENİ TRANSFER GÖREVİ</b>\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n"
                        f"👤 <b>Şoför:</b> {drv_name}\n\n"
                        f"Lütfen rezervasyon detayları için yöneticinizle iletişime geçin."
                    )
                    tg_send(drv_tgid, drv_msg)

        elif cbd.startswith('reject_'):
            voucher = cbd[len('reject_'):]
            try:
                requests.post(SCRIPT_URL, json={
                    'action': 'update_status',
                    'voucher': voucher,
                    'RESERVATION_STATUS': 'REJECTED'
                }, timeout=15)
            except Exception:
                pass
            tg_edit(chat_id, msg_id,
                    f"❌ <b>REDDEDİLDİ</b>\n🎫 Voucher: <code>{voucher}</code>")

        elif cbd.startswith('cancel_ok_'):
            voucher = cbd[len('cancel_ok_'):]
            try:
                requests.post(SCRIPT_URL, json={
                    'action': 'update_status',
                    'voucher': voucher,
                    'RESERVATION_STATUS': 'CANCELLED'
                }, timeout=15)
            except Exception:
                pass
            tg_edit(chat_id, msg_id,
                    f"✅ <b>İPTAL EDİLDİ</b>\n🎫 Voucher: <code>{voucher}</code>")

        elif cbd.startswith('cancel_no_'):
            voucher = cbd[len('cancel_no_'):]
            tg_edit(chat_id, msg_id,
                    f"↩️ <b>İptal reddedildi</b>\n🎫 Voucher: <code>{voucher}</code> aktif kalmaya devam ediyor.")

    return jsonify({'ok': True})


# ── Register Telegram webhook on startup ──────────────────────────────
def register_webhook():
    replit_domain = os.environ.get('REPLIT_DEV_DOMAIN', '')
    if replit_domain:
        url = f'https://{replit_domain}/telegram'
        try:
            r = requests.post(f'{TG}/setWebhook', json={'url': url}, timeout=10)
            print(f'Telegram webhook set: {url} → {r.json()}')
        except Exception as e:
            print(f'Webhook registration failed: {e}')


if __name__ == '__main__':
    register_webhook()
    app.run(host='0.0.0.0', port=5000, debug=False)

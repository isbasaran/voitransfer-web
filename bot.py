import os
import re
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
TELEGRAM_API = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}'

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

SYSTEM_PROMPT = """Sen BRIX TRAVEL / Voitrip şirketinin profesyonel transfer rezervasyon asistanısın. Türkçe konuşuyorsun.

Kullanıcıdan sırayla şu bilgileri topla (her seferinde 1-2 soru sor, kısa ve net ol):
1. Transfer tipi: ARRIVAL mi DEPARTURE mi?
2. Nereden → Nereye (havalimanı kodu veya şehir → otel/adres)
3. Tarih (GG.AA.YYYY formatında)
4. Uçuş numarası ve uçuş saati
5. Otel adı
6. Yolcu adı ve telefon numarası
7. Yetişkin / çocuk / bebek sayısı
8. Satış fiyatı ve döviz cinsi (EUR/USD/TRY)

PICKUP TIME HESABI:
- ARRIVAL: Pickup saati = Uçuş saati (aynı)
- DEPARTURE: Pickup saati = Uçuş saati - 3.5 saat
- Kullanıcı farklı pickup saati belirtirse onu kullan

Tüm bilgiler tamamlandığında şu formatta özet göster ve onay iste:
"✅ Rezervasyon özeti hazır! Onaylıyor musunuz?

🛫 Transfer: [JOB]
📍 Güzergah: [FROM] → [TO]
📅 Tarih: [TARİH]
✈️ Uçuş: [UCUS] saat [SAAT]
🕐 Pickup: [PICKUP]
🏨 Otel: [HOTEL]
👤 Yolcu: [YOLCU] - [TELEFON]
👥 Yetişkin: [YETİŞKİN] / Çocuk: [ÇOCUK] / Bebek: [BEBEK]
💰 Fiyat: [FİYAT] [DÖVİZ]

Onaylamak için 'Evet' yazın veya sağ taraftaki butonu kullanın."

Kullanıcı 'evet', 'onayla', 'tamam', 'ok', 'kaydet' gibi bir şey yazarsa sadece şunu yaz (başka hiçbir şey ekleme):
REZERVASYON_ONAYLANDI

Eğer düzeltme isterse düzelt ve tekrar özet göster.
Asla bilgi uydurmа. Emin olmadığında sor."""


MOCKUP_PORT = 23636


def send_telegram(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(f'{TELEGRAM_API}/sendMessage', json=payload, timeout=10)
    except Exception:
        pass


def notify_admin_new_reservation(data, voucher):
    job_emoji = '🛬' if data.get('job', '').upper() == 'ARRIVAL' else '🛫'
    msg = (
        f"🆕 <b>YENİ REZERVASYON</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎫 <b>Voucher:</b> <code>{voucher}</code>\n"
        f"{job_emoji} <b>Transfer:</b> {data.get('job','')}\n"
        f"📍 <b>Güzergah:</b> {data.get('from','')} → {data.get('to','')}\n"
        f"📅 <b>Tarih:</b> {data.get('tarih','')}\n"
        f"✈️ <b>Uçuş:</b> {data.get('ucus','')} saat {data.get('saat','')}\n"
        f"🕐 <b>Pickup:</b> {data.get('pickup','')}\n"
        f"🏨 <b>Otel:</b> {data.get('hotel','')}\n"
        f"👤 <b>Yolcu:</b> {data.get('yolcu','')} | {data.get('telefon','')}\n"
        f"👥 <b>Kişi:</b> {data.get('yetiskin','0')} yetişkin / {data.get('cocuk','0')} çocuk / {data.get('bebek','0')} bebek\n"
        f"💰 <b>Fiyat:</b> {data.get('fiyat','')} {data.get('doviz','EUR')}\n"
        f"📝 <b>Not:</b> {data.get('not','-')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌐 Web arayüzünden girildi"
    )
    keyboard = {
        'inline_keyboard': [[
            {'text': '✅ ONAYLA', 'callback_data': f'approve_{voucher}'},
            {'text': '❌ RED ET', 'callback_data': f'reject_{voucher}'}
        ]]
    }
    send_telegram(ADMIN_CHAT_ID, msg, keyboard)


def generate_voucher():
    now = datetime.datetime.now()
    date_str = now.strftime('%d%m%y')
    seq = now.strftime('%H%M')
    return f'BRX{date_str}{seq}'


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


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json(force=True)
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'error': 'Mesaj gerekli'}), 400
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'system', 'content': SYSTEM_PROMPT}] + messages,
            max_tokens=600
        )
        reply = response.choices[0].message.content
        confirmed = 'REZERVASYON_ONAYLANDI' in reply
        return jsonify({'reply': reply, 'confirmed': confirmed})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reserve', methods=['POST'])
def api_reserve():
    data = request.get_json(force=True)

    # Generate voucher if not provided
    voucher = data.get('voucher') or generate_voucher()
    data['voucher'] = voucher

    # Build Google Sheets row in correct column order (1-21)
    # 1.VOUCHER 2.DATE 3.OPERATOR 4.JOB 5.FROM 6.TO 7.HOTEL 8.FLIGHT_CODE
    # 9.FLIGHT_TIME 10.PICKUP_TIME 11.PASSENGER_NAME 12.PASSENGER_PHONE
    # 13.ADULT 14.CHILD 15.INFANT 16.SALE_PRICE 17.SALE_CURRENCY
    # 18.NOTE1 19.RESERVATION_STATUS 20.RESERVATION_STAFF 21.RESERVATION_DATE
    now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    # Pickup time calculation
    flight_time = data.get('saat', '')
    pickup_time = data.get('pickup', '')
    job = data.get('job', 'ARRIVAL').upper()
    if not pickup_time and flight_time:
        if job == 'ARRIVAL':
            pickup_time = flight_time
        else:
            try:
                h, m = map(int, flight_time.split(':'))
                total = h * 60 + m - 210  # -3.5 hours
                if total < 0:
                    total += 1440
                pickup_time = f'{total//60:02d}:{total%60:02d}'
            except Exception:
                pickup_time = flight_time

    sheets_row = {
        'action': 'reserve',
        'voucher': voucher,
        'date': data.get('tarih', ''),
        'operator': data.get('operator', 'BRIX TRAVEL'),
        'job': job,
        'from': data.get('from', ''),
        'to': data.get('to', ''),
        'hotel': data.get('hotel', ''),
        'flight_code': data.get('ucus', ''),
        'flight_time': flight_time,
        'pickup_time': pickup_time,
        'passenger_name': data.get('yolcu', ''),
        'passenger_phone': data.get('telefon', ''),
        'adult': data.get('yetiskin', '0'),
        'child': data.get('cocuk', '0'),
        'infant': data.get('bebek', '0'),
        'sale_price': data.get('fiyat', ''),
        'sale_currency': data.get('doviz', data.get('döviz', 'EUR')),
        'note1': data.get('not', ''),
        'status': 'WAITING_CAR',
        'staff': 'WEB',
        'reservation_date': now_str,
    }

    try:
        requests.post(SCRIPT_URL, json=sheets_row, timeout=20)
    except Exception as e:
        return jsonify({'error': f'Sheets hatası: {str(e)}'}), 500

    # Telegram admin notification
    notify_admin_new_reservation(data, voucher)

    return jsonify({'status': 'ok', 'voucher': voucher}), 200


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


@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    data = request.get_json(force=True)
    if not data or not data.get('voucher'):
        return jsonify({'error': 'Voucher gerekli'}), 400
    voucher = data.get('voucher', '').upper()
    # Notify admin
    msg = f"❌ <b>İPTAL TALEBİ</b>\n🎫 Voucher: <code>{voucher}</code>\n🌐 Web arayüzünden gönderildi"
    keyboard = {
        'inline_keyboard': [[
            {'text': '✅ İptali Onayla', 'callback_data': f'cancel_confirm_{voucher}'},
            {'text': '❌ Reddet', 'callback_data': f'cancel_reject_{voucher}'}
        ]]
    }
    send_telegram(ADMIN_CHAT_ID, msg, keyboard)
    try:
        requests.post(SCRIPT_URL, json={**data, 'action': 'cancel', 'voucher': voucher}, timeout=15)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

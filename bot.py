import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)
CORS(app)

SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxvqcAXLNyIU0DPrNQQDB3ZcfIsy9pT5STCkZTe-9yQIkED_au6B_ciF_aop_jyTP7ulQ/exec'

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

SYSTEM_PROMPT = """Sen bir transfer rezervasyon asistanısın. Türkçe konuşuyorsun.
Kullanıcıdan şu bilgileri sırayla topla:
1. Nereden nereye (from → to)
2. Tarih (GG.AA.YYYY)
3. Uçuş numarası ve saat
4. Otel adı
5. Yolcu adı ve telefonu
6. Yetişkin/çocuk/bebek sayısı
7. Fiyat ve döviz

Her seferde 1-2 soru sor, kısa ve net ol. Tüm bilgiler toplandığında özet göster."""


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


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
            max_tokens=400
        )
        reply = response.choices[0].message.content
        return jsonify({'reply': reply})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    try:
        resp = requests.post(SCRIPT_URL, json=data, timeout=15)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webhook/check', methods=['GET'])
def webhook_check():
    voucher = request.args.get('voucher', '').upper().strip()
    if not voucher:
        return jsonify({'error': 'Voucher gerekli'}), 400
    try:
        resp = requests.get(SCRIPT_URL, params={'action': 'check', 'voucher': voucher}, timeout=15)
        data = resp.json()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webhook/edit', methods=['POST'])
def webhook_edit():
    data = request.get_json(force=True)
    if not data or not data.get('voucher'):
        return jsonify({'error': 'Voucher gerekli'}), 400
    try:
        payload = {**data, 'action': 'edit'}
        requests.post(SCRIPT_URL, json=payload, timeout=15)
        return jsonify({'status': 'ok', 'message': 'Düzenleme gönderildi'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webhook/cancel', methods=['POST'])
def webhook_cancel():
    data = request.get_json(force=True)
    if not data or not data.get('voucher'):
        return jsonify({'error': 'Voucher gerekli'}), 400
    try:
        payload = {**data, 'action': 'cancel'}
        requests.post(SCRIPT_URL, json=payload, timeout=15)
        return jsonify({'status': 'ok', 'message': 'İptal talebi gönderildi'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

import os
import requests
from flask import Flask, request, jsonify, send_from_directory, Response
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


@app.route('/api/reserve', methods=['POST'])
def api_reserve():
    data = request.get_json(force=True)
    try:
        requests.post(SCRIPT_URL, json=data, timeout=15)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'status': 'ok', 'message': 'Düzenleme gönderildi'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    data = request.get_json(force=True)
    if not data or not data.get('voucher'):
        return jsonify({'error': 'Voucher gerekli'}), 400
    try:
        requests.post(SCRIPT_URL, json={**data, 'action': 'cancel'}, timeout=15)
        return jsonify({'status': 'ok', 'message': 'İptal talebi gönderildi'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

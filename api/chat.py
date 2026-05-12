from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request

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


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            messages = body.get('messages', [])

            api_key = os.environ.get('OPENAI_API_KEY', '')
            if not api_key:
                self._respond(500, {'error': 'OPENAI_API_KEY ayarlanmamış'})
                return

            payload = json.dumps({
                'model': 'gpt-4o-mini',
                'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}] + messages,
                'max_tokens': 400
            }).encode()

            req = urllib.request.Request(
                'https://api.openai.com/v1/chat/completions',
                data=payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                reply = data['choices'][0]['message']['content']
                self._respond(200, {'reply': reply})

        except Exception as e:
            self._respond(500, {'error': str(e)})

    def _respond(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass

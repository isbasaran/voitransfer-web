from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse

SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxvqcAXLNyIU0DPrNQQDB3ZcfIsy9pT5STCkZTe-9yQIkED_au6B_ciF_aop_jyTP7ulQ/exec'


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            voucher = params.get('voucher', [''])[0].upper().strip()

            if not voucher:
                self._respond(400, {'error': 'Voucher gerekli'})
                return

            url = SCRIPT_URL + '?' + urllib.parse.urlencode({'action': 'check', 'voucher': voucher})
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                self._respond(200, data)

        except Exception as e:
            self._respond(500, {'error': str(e)})

    def _respond(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

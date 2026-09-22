#!/usr/bin/env python3
"""Loopback-only, authenticated bridge for the existing Boca server.

Run cloudflared against this port, never against the unauthenticated local UI.
This process does not start Codex, resume runs, or open the operational DB.
"""
import argparse
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
ROUTES = json.loads((ROOT / 'deploy/routes.json').read_text())
MAX_BODY = 2_000_000
MAX_UPLOAD = 14_000_000


def allowed(method, path):
    return not ('..' in path or re.search(r'[%\\\x00-\x20]', path)) and any(
        re.fullmatch(pattern, path) for pattern in ROUTES.get(method, []))


def scrub(value):
    """Cloud clients never receive the local mutation/worker credentials."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k.lower() not in {
            'token', 'lease_token', 'completed_token', 'api_key', 'access_token', 'refresh_token', 'authorization'}}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class Bridge:
    def __init__(self, root, secret, local_port=8765):
        if len(secret) < 32 or secret.startswith('replace-with-'):
            raise ValueError('BOCA_BRIDGE_SECRET must contain at least 32 characters')
        self.root, self.secret, self.local_port = Path(root), secret, local_port
        self.directory = self.root / '.runtime/remote-bridge'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.uploads = self.directory / 'uploads'
        self.uploads.mkdir(mode=0o700, exist_ok=True)
        self.lock = threading.Lock()
        self.journal = self.directory / 'requests.sqlite3'
        with sqlite3.connect(str(self.journal)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT NOT NULL, status TEXT NOT NULL, code INTEGER, response BLOB, created REAL NOT NULL)')
        os.chmod(self.journal, 0o600)

    def authenticate(self, method, target, headers, body):
        stamp, request_id, actual = (headers.get(name, '') for name in
            ['X-BOCA-Bridge-Time', 'X-BOCA-Request-ID', 'X-BOCA-Bridge-Signature'])
        if not re.fullmatch(r'[A-Za-z0-9-]{16,80}', request_id) or not stamp.isdigit() or abs(time.time() - int(stamp)) > 60:
            return False
        message = '\n'.join([method, target, stamp, request_id, hashlib.sha256(body).hexdigest()])
        expected = hmac.new(self.secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return secrets.compare_digest(expected, actual)

    def begin(self, request_id, digest):
        with sqlite3.connect(str(self.journal), timeout=30) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT digest,status,code,response FROM requests WHERE id=?', (request_id,)).fetchone()
            if row:
                if row[0] != digest:
                    return 409, {'error': '같은 요청 ID에 다른 내용이 전달됐습니다.'}
                if row[1] != 'completed':
                    return 409, {'error': '기존 요청의 결과가 불확실합니다. 대시보드의 기록을 먼저 확인해 주세요.', 'code': 'OUTCOME_UNCERTAIN'}
                return row[2], json.loads(row[3])
            db.execute('INSERT INTO requests (id,digest,status,created) VALUES (?,?,?,?)', (request_id, digest, 'pending', time.time()))
        return None

    def finish(self, request_id, code, response):
        data = json.dumps(response, ensure_ascii=False).encode()
        with sqlite3.connect(str(self.journal)) as db:
            db.execute('UPDATE requests SET status=?,code=?,response=? WHERE id=?', ('completed', code, data, request_id))

    def connect(self, method, target, body=b'', range_header=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.local_port, timeout=240)
        headers = {}
        if method == 'POST':
            headers = {'Content-Type': 'application/json', 'X-BOCA-Token': (self.root / '.runtime/access-token').read_text().strip()}
        if range_header:
            headers['Range'] = range_header
        try:
            connection.request(method, target, body=body if method == 'POST' else None, headers=headers)
            return connection, connection.getresponse()
        except Exception:
            connection.close()
            raise

    def upload(self, path, body):
        match = re.fullmatch(r'/api/remote/uploads/([a-f0-9-]{36})/([0-9]+|complete)', path)
        upload_id, part = match.groups()
        folder = self.uploads / upload_id
        with self.lock:
            # Only abandoned temporary upload chunks are collected; content files are untouched.
            for old in self.uploads.iterdir():
                if old.is_dir() and old.stat().st_mtime < time.time() - 3600:
                    shutil.rmtree(old)
            active = [item for item in self.uploads.iterdir() if item.is_dir() and not (item / 'result.json').exists()]
            if not folder.exists() and len(active) >= 8:
                return 429, {'error': '진행 중인 이미지 업로드가 너무 많습니다.'}
            folder.mkdir(mode=0o700, exist_ok=True)
            os.utime(folder, None)
            if part != 'complete':
                if (folder / 'result.json').exists():
                    return 409, {'error': '이미 완료된 업로드입니다. 새 이미지에는 새 업로드 ID를 사용해 주세요.'}
                index, data = int(part), body.get('data')
                if not 0 <= index < 14 or not isinstance(data, str) or not 0 < len(data) <= 1_000_000 or not re.fullmatch(r'[A-Za-z0-9+/]*={0,2}', data):
                    return 400, {'error': '이미지 조각의 형식 또는 크기를 확인해 주세요.'}
                file = folder / ('%02d.part' % index)
                if file.exists() and file.read_text() != data:
                    return 409, {'error': '이미지 조각 내용이 이전 요청과 다릅니다.'}
                file.write_text(data)
                return 200, {'part': index, 'saved': True}
            cached = folder / 'result.json'
            if cached.exists():
                result = json.loads(cached.read_text())
                if result['parts'] != body.get('parts') or result['sha256'] != body.get('sha256'):
                    return 409, {'error': '완료된 업로드와 다른 내용입니다.'}
                return result['code'], result['response']
            count = body.get('parts')
            if type(count) is not int or not 1 <= count <= 14:
                return 400, {'error': '이미지 조각 수를 확인해 주세요.'}
            files = [folder / ('%02d.part' % index) for index in range(count)]
            if not all(file.is_file() for file in files):
                return 409, {'error': '아직 도착하지 않은 이미지 조각이 있습니다.'}
            encoded = ''.join(file.read_text() for file in files)
            if len(encoded) > MAX_UPLOAD or hashlib.sha256(encoded.encode()).hexdigest() != body.get('sha256'):
                return 400, {'error': '이미지 전체 크기 또는 해시가 일치하지 않습니다.'}
            payload = json.dumps({'data': encoded}).encode()
            connection, response = self.connect('POST', '/api/video/reference', payload)
            try:
                result = scrub(json.loads(response.read()))
                code = response.status
                cached.write_text(json.dumps({'code': code, 'response': result, 'parts': count, 'sha256': body['sha256']}, ensure_ascii=False))
                for file in files:
                    file.unlink()
                return code, result
            finally:
                connection.close()


def handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def end_headers(self):
            self.send_header('Cache-Control', 'private, no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            super().end_headers()
            self.response_started = True

        def send_json(self, code, value):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            connection = None
            self.response_started = False
            claimed = False
            try:
                parts = urlsplit(self.path)
                if parts.scheme or parts.netloc or parts.fragment or len(self.path) > 8192 or not allowed(self.command, parts.path):
                    return self.send_json(403, {'error': '원격 접근이 허용되지 않은 경로입니다.'})
                if self.headers.get('Transfer-Encoding'):
                    return self.send_json(400, {'error': '고정 길이 요청이 필요합니다.'})
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= MAX_BODY:
                    return self.send_json(413, {'error': '요청이 너무 큽니다. 이미지 분할 업로드를 사용해 주세요.'})
                self.connection.settimeout(30)
                data = self.rfile.read(length)
                if len(data) != length or not bridge.authenticate(self.command, self.path, self.headers, data):
                    return self.send_json(401, {'error': '중계 서버 인증이 필요합니다.'})
                if self.command == 'POST':
                    body = json.loads(data)
                    if not isinstance(body, dict):
                        return self.send_json(400, {'error': 'JSON 객체가 필요합니다.'})
                    request_id = self.headers['X-BOCA-Request-ID']
                    digest = hashlib.sha256(self.path.encode() + b'\n' + data).hexdigest()
                    previous = bridge.begin(request_id, digest)
                    if previous:
                        return self.send_json(*previous)
                    claimed = True
                    if parts.path.startswith('/api/remote/uploads/'):
                        code, value = bridge.upload(parts.path, body)
                    else:
                        connection, response = bridge.connect('POST', self.path, data)
                        code, value = response.status, scrub(json.loads(response.read()))
                    bridge.finish(request_id, code, value)
                    return self.send_json(code, value)
                connection, response = bridge.connect('GET', self.path, range_header=self.headers.get('Range'))
                mime = response.getheader('Content-Type', '')
                if 'application/json' in mime:
                    return self.send_json(response.status, scrub(json.loads(response.read())))
                self.send_response(response.status)
                for key in ['Content-Type', 'Content-Length', 'Content-Disposition', 'Accept-Ranges', 'Content-Range']:
                    value = response.getheader(key)
                    if value:
                        self.send_header(key, value)
                self.end_headers()
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (ValueError, TypeError):
                if not self.response_started:
                    self.send_json(503 if claimed else 400, {'error': '기존 요청의 결과를 확인해 주세요.' if claimed else '요청 형식을 확인해 주세요.',
                        'code': 'OUTCOME_UNCERTAIN' if claimed else 'INVALID_REQUEST'})
            except (OSError, http.client.HTTPException):
                if not self.response_started:
                    self.send_json(503, {'error': 'Mac의 로컬 서버 응답을 확인하지 못했습니다. 기록을 확인한 뒤 다시 요청해 주세요.', 'code': 'OUTCOME_UNCERTAIN' if self.command == 'POST' else 'WORKER_UNAVAILABLE'})
                else:
                    self.close_connection = True
            finally:
                if connection:
                    connection.close()

        def log_message(self, fmt, *args):
            # No secrets, request bodies or signed headers in public logs.
            return
    return Handler


def load_env(path):
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--local-port', type=int, default=8765)
    args = parser.parse_args()
    if args.env_file:
        load_env(args.env_file)
    bridge = Bridge(args.root, os.environ.get('BOCA_BRIDGE_SECRET', ''), args.local_port)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(bridge))
    print('Boca authenticated bridge: http://127.0.0.1:%d -> local port %d' % (args.port, args.local_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

"""Isolated real API + bridge fixture. Never launches AI or video workers."""
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/backend'))
from server import Store, handler as local_handler, DISCLOSURE
from remote_bridge import Bridge, handler as bridge_handler


def main():
    temporary = tempfile.TemporaryDirectory(prefix='boca-remote-test-')
    root = Path(os.environ.get('BOCA_REMOTE_TEST_ROOT', temporary.name))
    root.mkdir(parents=True, exist_ok=True)
    if not (root / 'config').exists():
        shutil.copytree(ROOT / 'config', root / 'config')
    (root / 'apps').mkdir(exist_ok=True)
    if not (root / 'apps/dashboard').exists():
        shutil.copytree(ROOT / 'apps/dashboard', root / 'apps/dashboard')
    image = root / 'fixture.png'
    image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII='))
    (root / 'large.mp4').write_bytes(b'ISOLATED_RANGE_FIXTURE' + b'x' * 6_000_000)
    store = Store(root)
    # Reproduce the oversized state seen after a long production run.
    with store.db() as db:
        db.execute('INSERT INTO jobs (id,stage,status,input_json,result_json,updated_at) VALUES (?,?,?,?,?,?)',
                   ('large-history-job', 'copy', 'completed', json.dumps({'previous_results': 'x' * 6_000_000}),
                    json.dumps({'caption': 'stored original evidence'}), '2026-09-22T00:00:00+00:00'))
    persona = store.persona()
    for cid, media in [('remote-image', 'fixture.png'), ('remote-large', 'large.mp4')]:
        store.ingest({'id': cid, 'title': '원격 검증 ' + cid, 'topic_key': cid, 'persona_id': persona['id'],
            'persona_version': persona['version'], 'caption': '운영과 분리된 검증용 콘텐츠.\n' + DISCLOSURE,
            'hashtags': [], 'cards': [{'media': media, 'alt': '검증용 미디어'}], 'sources': [], 'review_notes': ['합성 기능 검증용; 실제 생성 결과로 계산하지 않음']})
    sample = os.environ.get('BOCA_TEST_VIDEO_PATH')
    if sample:
        shutil.copy2(sample, root / 'sample.mp4')
        store.ingest({'id': 'remote-video', 'title': '원격 재생 검증 영상', 'topic_key': 'remote-playback',
            'persona_id': persona['id'], 'persona_version': persona['version'], 'caption': '기존 영상 사본을 이용한 전송 검증.\n' + DISCLOSURE,
            'hashtags': [], 'cards': [{'media': 'sample.mp4', 'alt': '기존 영상의 격리 검증 사본'}], 'sources': [], 'review_notes': ['새로운 AI 생성이 아님']})
    local = ThreadingHTTPServer(('127.0.0.1', 0), local_handler(store))
    secret = os.environ.get('BOCA_TEST_BRIDGE_SECRET', 'test-bridge-secret-' + 'x' * 32)
    bridge = ThreadingHTTPServer(('127.0.0.1', 0), bridge_handler(Bridge(root, secret, local.server_port)))
    threading.Thread(target=local.serve_forever, daemon=True).start()
    threading.Thread(target=bridge.serve_forever, daemon=True).start()
    print(json.dumps({'local_port': local.server_port, 'bridge_port': bridge.server_port, 'root': str(root), 'ai_workers_started': False}), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        local.shutdown(); bridge.shutdown(); temporary.cleanup()


if __name__ == '__main__':
    main()

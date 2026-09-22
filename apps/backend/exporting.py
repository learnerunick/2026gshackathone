"""Export the exact current review revision without publishing it."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def export_bundle(store, content_id):
    with store.db() as db:
        content = store._content(db, content_id)
        payload = json.loads(json.dumps(content["payload"], ensure_ascii=False))
        approval = db.execute(
            "SELECT * FROM approvals WHERE content_id=? AND version=? AND fingerprint=?",
            (content_id, content["current_version"], content["fingerprint"]),
        ).fetchone()
        files = []
        for index, card in enumerate(payload["cards"], start=1):
            store._verify_media(card)
            original = store.media / card["media"]
            data = original.read_bytes()
            if hashlib.sha256(data).hexdigest() != card["sha256"]:
                raise store.problem("미디어가 변경되어 다운로드를 중지했습니다.", 409)
            name = "media/card-%02d%s" % (index, Path(card["media"]).suffix.lower())
            files.append((name, data))
            card["media"] = name
        manifest = {
            "content": payload,
            "version": content["current_version"],
            "status": content["status"],
            "fingerprint": content["fingerprint"],
            "human_approved": bool(approval) and content["status"] in
                              ["approved", "posting", "published", "uncertain"],
            "published_url": (content.get("publication") or {}).get("permalink"),
            "note": "내부 검토용 다운로드입니다. 다운로드는 게시나 승인이 아닙니다.",
        }
    caption = payload["caption"].rstrip()
    if payload.get("hashtags"):
        caption += "\n\n" + " ".join(payload["hashtags"])
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
        archive.writestr("caption.txt", caption + "\n")
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "현재 버전의 이미지·문안과 내부 출처를 담은 검토용 묶음입니다.\n"
                         "이 다운로드는 Instagram에 게시하지 않습니다.\n"
                         "manifest.json에는 내부 검토 메모와 출처가 있으므로 공개 게시 자료와 구분하세요.\n")
    return output.getvalue(), "%s-v%d.zip" % (content_id, content["current_version"])

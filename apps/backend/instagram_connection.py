"""Read-only Instagram verification. Credentials never enter dashboard state."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://graph.instagram.com/v26.0/"


class ConnectionError(Exception):
    pass


def paths(root):
    folder = Path(root) / ".runtime/secrets"
    return folder / "instagram-token", folder / "instagram-connection.json"


def write_private(path, data):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def get(token, route):
    request = Request(API + route, headers={"Authorization": "Bearer " + token})
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        # Do not propagate response bodies, URLs, tokens, or provider exceptions.
        raise ConnectionError("Instagram 인증 또는 권한 확인에 실패했습니다 (HTTP %s)." % error.code) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ConnectionError("Instagram에 연결할 수 없습니다. 잠시 후 다시 확인해 주세요.") from None


def verify(root, expected_account):
    token_path, status_path = paths(root)
    if not expected_account:
        raise ConnectionError("게시 대상 계정을 먼저 저장해 주세요.")
    try:
        token = token_path.read_text().strip()
    except OSError:
        raise ConnectionError("서버에 Instagram 인증 토큰이 없습니다.") from None
    if not token:
        raise ConnectionError("서버에 Instagram 인증 토큰이 없습니다.")
    try:
        profile = get(token, "me?fields=id,user_id,username,account_type")
        username = profile.get("username", "")
        if username.lower() != expected_account.lstrip("@").lower():
            raise ConnectionError("토큰 계정이 게시 대상 계정과 다릅니다.")
        if profile.get("account_type") not in ("MEDIA_CREATOR", "BUSINESS"):
            raise ConnectionError("Instagram 프로페셔널 계정이 필요합니다.")
        user_id = str(profile.get("user_id") or profile.get("id") or "")
        if not user_id.isdigit():
            raise ConnectionError("Instagram 계정 ID를 확인하지 못했습니다.")
        quota = get(token, user_id + "/content_publishing_limit?fields=config,quota_usage")
        rows = quota.get("data", [])
        if not rows or not isinstance(rows[0], dict) or "quota_usage" not in rows[0]:
            raise ConnectionError("게시 권한 확인 응답이 올바르지 않습니다.")
        status = {"connection": "verified", "account": username, "user_id": user_id,
                  "account_type": profile["account_type"], "publishing_permission_verified": True,
                  "verified_at": datetime.now(timezone.utc).isoformat(),
                  "quota_usage": rows[0]["quota_usage"],
                  "quota_total": rows[0].get("config", {}).get("quota_total"),
                  "publisher_ready": False,
                  "token_fingerprint": hashlib.sha256(token.encode()).hexdigest()}
        write_private(status_path, status)
        return public_status(root, username)
    except ConnectionError:
        # A failed recheck must not leave a previous success visible.
        write_private(status_path, {"connection": "not-connected"})
        raise


def public_status(root, account):
    token_path, status_path = paths(root)
    if not status_path.exists():
        return {}
    disconnected = {"connection": "not-connected", "publisher_ready": False}
    try:
        saved = json.loads(status_path.read_text())
        token = token_path.read_text().strip()
        if (saved.get("connection") != "verified" or not token or
                saved.get("account", "").lower() != (account or "").lstrip("@").lower() or
                saved.get("token_fingerprint") != hashlib.sha256(token.encode()).hexdigest()):
            return disconnected
        checked = datetime.fromisoformat(saved["verified_at"])
        age = datetime.now(timezone.utc) - checked
        if age < timedelta(0) or age > timedelta(hours=24):
            return dict(disconnected, connection="recheck-required")
        # Explicit allowlist: never serialize credentials or their fingerprint.
        fields = ("connection", "account", "user_id", "account_type", "verified_at",
                  "publishing_permission_verified", "quota_usage", "quota_total")
        return dict({key: saved[key] for key in fields if key in saved}, publisher_ready=False)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return disconnected

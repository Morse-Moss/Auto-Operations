from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.services import huitun_live_note_source as source
from backend.app.services import huitun_account_service as account_source
from backend.app.services.huitun_live_note_source import _rows_from_response, search_notes


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.cookies = FakeCookieJar()

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        return FakeResponse(self.payload)


class FakeCookieJar:
    def __init__(self):
        self.values = {}

    def set(self, key, value, domain=None, path=None):
        self.values[str(key)] = str(value)

    def __iter__(self):
        for name, value in self.values.items():
            yield type("Cookie", (), {"name": name, "value": value})()


class FakeQrSession:
    def __init__(self):
        self.cookies = FakeCookieJar()

    def get(self, url, params=None, timeout=None):
        return FakeResponse({"status": 0, "extData": {"userId": "from-check-only"}})


class FakePasswordLoginSession:
    def __init__(self, post_payload=None):
        self.cookies = FakeCookieJar()
        self.calls = []
        self.post_payload = post_payload or {"status": 0, "message": "ok"}

    def post(self, url, params=None, data=None, headers=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": dict(params or {}),
                "data": dict(data or {}),
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        self.cookies.set("xhsapiToken", "password-token", domain=".huitun.com", path="/")
        return FakeResponse(self.post_payload)

    def get(self, url, params=None, timeout=None):
        assert url == account_source.HUITUN_CURRENT_USER_URL
        return FakeResponse({"status": 0, "extData": {"userId": "web-user-1", "nickName": "数据账号"}})


def test_note_search_rows_map_verified_fields_to_candidates():
    rows = _rows_from_response(
        {
            "status": 0,
            "extData": {
                "list": [
                    {
                        "noteId": "note-1",
                        "title": "硬控npc10秒",
                        "desc": "硬控npc10秒 #秦文玚",
                        "imageUrl": "http://sns-img-hw.xhscdn.com/cover.jpg",
                        "videoUrl": "http://sns-video-v6.xhscdn.com/video.mp4",
                        "nick": "作者A",
                        "like": "1.2w",
                        "coll": 500,
                        "comm": 80,
                        "share": 20,
                        "read": 10000,
                        "topic": "秦文玚,硬控npc10秒",
                        "ts": 1710000000,
                    }
                ]
            },
        },
        10,
    )

    assert rows == [
        {
            "external_id": "note-1",
            "platform_note_id": "note-1",
            "original_url": "https://www.xiaohongshu.com/explore/note-1",
            "title": "硬控npc10秒",
            "content_excerpt": "硬控npc10秒 #秦文玚",
            "author_name": "作者A",
            "cover_url": "http://sns-img-hw.xhscdn.com/cover.jpg",
            "asset_urls": ["http://sns-img-hw.xhscdn.com/cover.jpg"],
            "video_url": "http://sns-video-v6.xhscdn.com/video.mp4",
            "publish_time": "1710000000",
            "update_time": "",
            "rank_index": 1,
            "category": "",
            "tags": ["秦文玚", "硬控npc10秒"],
            "metrics": {
                "like_count": 12000,
                "collect_count": 500,
                "comment_count": 80,
                "share_count": 20,
                "estimated_read_count": 10000,
                "interaction_count": 12600,
            },
            "raw": {
                "noteId": "note-1",
                "title": "硬控npc10秒",
                "desc": "硬控npc10秒 #秦文玚",
                "imageUrl": "http://sns-img-hw.xhscdn.com/cover.jpg",
                "videoUrl": "http://sns-video-v6.xhscdn.com/video.mp4",
                "nick": "作者A",
                "like": "1.2w",
                "coll": 500,
                "comm": 80,
                "share": 20,
                "read": 10000,
                "topic": "秦文玚,硬控npc10秒",
                "ts": 1710000000,
            },
        }
    ]


def test_search_notes_uses_verified_browser_query_shape(monkeypatch):
    fake_session = FakeSession(
        {
            "status": 0,
            "extData": {
                "list": [
                    {
                        "noteId": "note-1",
                        "title": "bathtub storage",
                        "desc": "small bathroom idea",
                    }
                ]
            },
        }
    )
    monkeypatch.setattr(source, "_session_from_cookie_text", lambda _cookie_text: fake_session)
    monkeypatch.setattr(source, "shanghai_now", lambda: datetime(2026, 7, 6, 12, 0, 0), raising=False)
    monkeypatch.setattr(source, "_now_ms", lambda: 1234567890)

    rows = search_notes("session=ok", " 浴缸 ", 3, sort="interaction", note_type="all")

    assert [row["platform_note_id"] for row in rows] == ["note-1"]
    assert fake_session.calls == [
        {
            "url": source.HUITUN_NOTE_SEARCH_URL,
            "params": {
                "_t": 1234567890,
                "vs": "16101520.52.102",
                "Source": "web",
                "keyword": "浴缸",
                "page": 1,
                "pageSize": 3,
                "sort": 5,
                "rangeList": "1,2,3,5",
                "dateStart": "2026-06-07",
                "dateEnd": "2026-07-06",
                "days": 30,
                "del": True,
            },
            "timeout": 20,
        }
    ]


def test_search_notes_treats_expired_token_status_as_login_expired(monkeypatch):
    fake_session = FakeSession({"status": 1000, "message": "login expired"})
    monkeypatch.setattr(source, "_session_from_cookie_text", lambda _cookie_text: fake_session)

    with pytest.raises(RuntimeError, match=source.NOTE_SEARCH_LOGIN_EXPIRED_MESSAGE):
        search_notes("session=expired", "浴缸", 3)


def test_account_login_validation_rejects_expired_status_even_with_ext_data(monkeypatch):
    fake_session = FakeSession({"status": 1000, "extData": {"userId": "stale-user"}})
    monkeypatch.setattr(account_source, "_session_from_cookie_text", lambda _cookie_text: fake_session)

    with pytest.raises(RuntimeError, match=account_source.HUITUN_INVALID_LOGIN_MESSAGE):
        account_source.validate_huitun_login_state('{"xhsapiToken":"expired"}')


def test_data_account_user_facing_messages_do_not_expose_internal_provider_name():
    from backend.app.api import huitun_login_sessions

    messages = [
        account_source.HUITUN_INVALID_LOGIN_MESSAGE,
        account_source.HUITUN_QR_FAILED_MESSAGE,
        huitun_login_sessions.HUITUN_LOGIN_STATUS_CHECK_FAILED_MESSAGE,
        huitun_login_sessions.HUITUN_ACCOUNT_INFO_FAILED_MESSAGE,
    ]

    for message in messages:
        assert "数据账号" in message
        assert "灰豚" not in message
        assert "huitun" not in message.lower()


def test_qrcode_status_does_not_confirm_when_current_user_validation_fails(monkeypatch):
    monkeypatch.setattr(account_source.requests, "Session", FakeQrSession)
    monkeypatch.setattr(
        account_source,
        "validate_huitun_login_state",
        lambda _cookies_text: (_ for _ in ()).throw(RuntimeError("invalid login")),
    )

    result = account_source.check_huitun_qrcode_status(
        {"ticket": "ticket-1", "cookies": {"xhsapiToken": "temp-token"}}
    )

    assert result["status"] == "pending"
    assert result["user_info"] is None


def test_password_login_uses_official_captcha_ticket_and_returns_cookie(monkeypatch):
    fake_session = FakePasswordLoginSession()
    monkeypatch.setattr(account_source.requests, "Session", lambda: fake_session)
    monkeypatch.setattr(account_source, "_now_ms", lambda: 1234567890)

    result = account_source.login_huitun_with_password(
        "13800138000",
        "company-pass-123",
        "captcha-ticket",
        "captcha-rand",
    )

    assert result["status"] == "confirmed"
    assert result["cookies_text"] == '{"xhsapiToken":"password-token"}'
    assert result["user_info"]["external_user_id"] == "web-user-1"
    assert fake_session.calls == [
        {
            "url": account_source.HUITUN_PHONE_LOGIN_URL,
            "params": {"_t": 1234567890},
            "data": {
                "mobile": "13800138000",
                "password": "company-pass-123",
                "ticket": "captcha-ticket",
                "randStr": "captcha-rand",
                "vs": account_source.HUITUN_WEB_VERSION,
                "Source": "web",
            },
            "headers": {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://xhs.huitun.com",
                "Referer": "https://xhs.huitun.com/",
                "Source": "web",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            },
            "timeout": 20,
        }
    ]


def test_password_login_treats_string_status_as_sms_verification_required(monkeypatch):
    fake_session = FakePasswordLoginSession({"status": "1006", "message": "ok"})
    monkeypatch.setattr(account_source.requests, "Session", lambda: fake_session)

    result = account_source.login_huitun_with_password(
        "13800138000",
        "company-pass-123",
        "captcha-ticket",
        "captcha-rand",
    )

    assert result["status"] == "verification_required"

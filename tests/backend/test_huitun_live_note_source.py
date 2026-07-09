from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.services import huitun_live_note_source as source
from backend.app.services import huitun_account_service as account_source
from backend.app.services.huitun_live_note_source import _rows_from_response, fetch_note_comments, search_notes


class FakeResponse:
    status_code = 200

    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} error")
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


class SequentialFakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []
        self.cookies = FakeCookieJar()

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        if not self.payloads:
            raise AssertionError("unexpected extra request")
        return FakeResponse(self.payloads.pop(0))


class HeaderAwareSequentialFakeSession(SequentialFakeSession):
    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout})
        if not self.payloads:
            raise AssertionError("unexpected extra request")
        return FakeResponse(self.payloads.pop(0))


class FakeCookieJar:
    def __init__(self):
        self.values = {}

    def set(self, key, value, domain=None, path=None):
        self.values[str(key)] = str(value)

    def __iter__(self):
        for name, value in self.values.items():
            yield type("Cookie", (), {"name": name, "value": value})()


def test_note_search_rows_do_not_fabricate_original_url_from_internal_note_id():
    rows = _rows_from_response(
        {
            "status": 0,
            "extData": {
                "list": [
                    {
                        "noteId": "11548571364",
                        "title": "bathtub craft",
                        "imageUrl": "http://sns-img-hw.xhscdn.com/cover.jpg",
                    }
                ]
            },
        },
        10,
    )

    assert rows[0]["platform_note_id"] == "11548571364"
    assert rows[0]["original_url"] == ""


def test_note_search_rows_preserve_real_note_url_when_source_returns_one():
    rows = _rows_from_response(
        {
            "status": 0,
            "extData": {
                "list": [
                    {
                        "noteId": "11548571364",
                        "noteUrl": (
                            "https://www.xiaohongshu.com/discovery/item/6a4a223c0000000006022abe"
                            "?xsec_token=token&xsec_source=pc_feed"
                        ),
                        "title": "bathtub craft",
                    }
                ]
            },
        },
        10,
    )

    assert rows[0]["original_url"] == (
        "https://www.xiaohongshu.com/discovery/item/6a4a223c0000000006022abe"
        "?xsec_token=token&xsec_source=pc_feed"
    )


class FakeQrSession:
    def __init__(self):
        self.cookies = FakeCookieJar()

    def get(self, url, params=None, timeout=None):
        return FakeResponse({"status": 0, "extData": {"userId": "from-check-only"}})


class FakePasswordLoginSession:
    def __init__(self, post_payload=None, post_status_code=200):
        self.cookies = FakeCookieJar()
        self.calls = []
        self.post_payload = post_payload or {"status": 0, "message": "ok"}
        self.post_status_code = post_status_code

    def post(self, url, params=None, data=None, headers=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": dict(params or {}),
                "data": dict(data or {}),
                "headers": dict(headers or {}),
                "cookies": dict(self.cookies.values),
                "timeout": timeout,
            }
        )
        self.cookies.set("xhsapiToken", "password-token", domain=".huitun.com", path="/")
        return FakeResponse(self.post_payload, status_code=self.post_status_code)

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
                "original_url": "",
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
                "rangeList": "1,3",
                "dateStart": "2026-06-07",
                "dateEnd": "2026-07-06",
                "days": 30,
                "del": True,
            },
            "timeout": 20,
        }
    ]


def test_search_notes_maps_frontend_note_type_values_to_live_source_params(monkeypatch):
    fake_session = FakeSession(
        {
            "status": 0,
            "extData": {
                "list": [
                    {
                        "noteId": "note-1",
                        "title": "image note",
                        "type": "normal",
                    }
                ]
            },
        }
    )
    monkeypatch.setattr(source, "_session_from_cookie_text", lambda _cookie_text: fake_session)
    monkeypatch.setattr(source, "shanghai_now", lambda: datetime(2026, 7, 6, 12, 0, 0), raising=False)
    monkeypatch.setattr(source, "_now_ms", lambda: 1234567890)

    rows = search_notes("session=ok", "浴缸", 10, sort="interaction", note_type="2")

    assert [row["platform_note_id"] for row in rows] == ["note-1"]
    assert fake_session.calls[0]["params"]["noteType"] == "normal"


def test_search_notes_paginates_when_requested_limit_exceeds_live_page_size(monkeypatch):
    first_page = {
        "status": 0,
        "extData": {
            "list": [
                {
                    "noteId": f"note-{index}",
                    "title": f"page one {index}",
                    "type": "normal",
                }
                for index in range(20)
            ]
        },
    }
    second_page = {
        "status": 0,
        "extData": {
            "list": [
                {
                    "noteId": f"note-{index}",
                    "title": f"page two {index}",
                    "type": "normal",
                }
                for index in range(20, 30)
            ]
        },
    }
    fake_session = SequentialFakeSession([first_page, second_page])
    monkeypatch.setattr(source, "_session_from_cookie_text", lambda _cookie_text: fake_session)
    monkeypatch.setattr(source, "shanghai_now", lambda: datetime(2026, 7, 6, 12, 0, 0), raising=False)
    monkeypatch.setattr(source, "_now_ms", lambda: 1234567890)

    rows = search_notes("session=ok", "浴缸", 30, sort="interaction", note_type="normal")

    assert len(rows) == 30
    assert rows[0]["platform_note_id"] == "note-0"
    assert rows[-1]["platform_note_id"] == "note-29"
    assert [call["params"]["page"] for call in fake_session.calls] == [1, 2]
    assert [call["params"]["pageSize"] for call in fake_session.calls] == [20, 10]
    assert all(call["params"]["noteType"] == "normal" for call in fake_session.calls)


def test_fetch_note_comments_uses_verified_comment_shape_and_paginates(monkeypatch):
    first_page = {
        "status": 0,
        "extData": {
            "list": [
                {
                    "commentId": "comment-1",
                    "nick": "用户A",
                    "anchorId": "user-a",
                    "content": "同问",
                    "likeCount": 12,
                    "postTime": "2026-07-09",
                    "sentiment": 6000,
                },
                {
                    "commentId": "comment-2",
                    "nick": "用户B",
                    "content": "想看尺寸",
                    "likeCount": "3",
                    "postTime": "2026-07-08",
                },
            ],
            "hasNextPage": True,
            "total": 3,
        },
    }
    second_page = {
        "status": 0,
        "extData": {
            "list": [
                {
                    "commentId": "comment-3",
                    "nick": "用户C",
                    "content": "收藏了",
                    "likeCount": 1,
                    "postTime": "2026-07-07",
                }
            ],
            "hasNextPage": False,
            "total": 3,
        },
    }
    fake_session = HeaderAwareSequentialFakeSession([first_page, second_page])
    monkeypatch.setattr(source, "_session_from_cookie_text", lambda _cookie_text: fake_session)
    monkeypatch.setattr(source, "_now_ms", lambda: 1234567890)

    comments = fetch_note_comments("session=ok", " note-1 ", limit=3, page_size=2)

    assert comments == [
        {
            "comment_id": "comment-1",
            "user_name": "用户A",
            "user_id": "user-a",
            "content": "同问",
            "like_count": 12,
            "parent_comment_id": None,
            "created_at_remote": "2026-07-09",
            "raw_json": {
                "commentId": "comment-1",
                "nick": "用户A",
                "anchorId": "user-a",
                "content": "同问",
                "likeCount": 12,
                "postTime": "2026-07-09",
                "sentiment": 6000,
            },
        },
        {
            "comment_id": "comment-2",
            "user_name": "用户B",
            "user_id": None,
            "content": "想看尺寸",
            "like_count": 3,
            "parent_comment_id": None,
            "created_at_remote": "2026-07-08",
            "raw_json": {
                "commentId": "comment-2",
                "nick": "用户B",
                "content": "想看尺寸",
                "likeCount": "3",
                "postTime": "2026-07-08",
            },
        },
        {
            "comment_id": "comment-3",
            "user_name": "用户C",
            "user_id": None,
            "content": "收藏了",
            "like_count": 1,
            "parent_comment_id": None,
            "created_at_remote": "2026-07-07",
            "raw_json": {
                "commentId": "comment-3",
                "nick": "用户C",
                "content": "收藏了",
                "likeCount": 1,
                "postTime": "2026-07-07",
            },
        },
    ]
    assert fake_session.calls == [
        {
            "url": source.HUITUN_NOTE_COMMENT_URL,
            "params": {
                "_t": 1234567890,
                "vs": "16101520.52.102",
                "Source": "web",
                "noteId": "note-1",
                "keyword": "",
                "emotion": "",
                "pageSize": 2,
                "page": 1,
            },
            "headers": source._huitun_headers(),
            "timeout": 20,
        },
        {
            "url": source.HUITUN_NOTE_COMMENT_URL,
            "params": {
                "_t": 1234567890,
                "vs": "16101520.52.102",
                "Source": "web",
                "noteId": "note-1",
                "keyword": "",
                "emotion": "",
                "pageSize": 1,
                "page": 2,
            },
            "headers": source._huitun_headers(),
            "timeout": 20,
        },
    ]


def test_fetch_note_comments_stops_with_permission_message(monkeypatch):
    fake_session = HeaderAwareSequentialFakeSession(
        [{"status": 2001, "message": "当前版本无请求权限，请升级会员版本查看更多~"}]
    )
    monkeypatch.setattr(source, "_session_from_cookie_text", lambda _cookie_text: fake_session)

    with pytest.raises(RuntimeError, match="当前版本无请求权限"):
        fetch_note_comments("session=free", "note-1", limit=5)


def test_rows_from_response_uses_later_non_empty_bucket_when_first_bucket_is_empty():
    rows = _rows_from_response(
        {
            "status": 0,
            "extData": [
                {"list": []},
                {
                    "list": [
                        {
                            "noteId": "note-later",
                            "title": "later bucket",
                            "type": "normal",
                        }
                    ]
                },
            ],
        },
        10,
    )

    assert [row["platform_note_id"] for row in rows] == ["note-later"]


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
            "cookies": {},
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


def test_password_login_reads_sms_required_payload_before_http_error(monkeypatch):
    fake_session = FakePasswordLoginSession(
        {
            "code": 403,
            "message": "企业版账号当前设备需要短信验证码",
        },
        post_status_code=403,
    )
    monkeypatch.setattr(account_source.requests, "Session", lambda: fake_session)

    result = account_source.login_huitun_with_password(
        "13800138000",
        "company-pass-123",
        "captcha-ticket",
        "captcha-rand",
    )

    assert result["status"] == "verification_required"
    assert result["message"] == account_source.HUITUN_PASSWORD_SMS_REQUIRED_MESSAGE


def test_password_login_reuses_sms_challenge_cookie_when_confirming_code(monkeypatch):
    fake_session = FakePasswordLoginSession()
    monkeypatch.setattr(account_source.requests, "Session", lambda: fake_session)
    monkeypatch.setattr(account_source, "_now_ms", lambda: 1234567890)

    result = account_source.login_huitun_with_password(
        "13800138000",
        "company-pass-123",
        "captcha-ticket",
        "captcha-rand",
        captcha="654321",
        initial_cookies_text='{"smsChallenge":"challenge-cookie"}',
    )

    assert result["status"] == "confirmed"
    assert fake_session.calls[0]["url"] == account_source.HUITUN_DEVICE_PHONE_LOGIN_URL
    assert fake_session.calls[0]["data"]["captcha"] == "654321"
    assert fake_session.calls[0]["cookies"] == {"smsChallenge": "challenge-cookie"}

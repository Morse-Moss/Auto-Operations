from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from backend.app.adapters.xhs.creator_api_adapter import XhsCreatorApiAdapter


class FakeCreatorApi:
    edith_url = "https://edith.xiaohongshu.com"
    published_notes: list[dict] = []
    published_notes_calls = 0

    def get_topic(self, keyword, cookies):
        return True, "", {"data": {"topic_info_dtos": [{"id": "topic-1", "name": keyword, "link": ""}]}}

    def get_location_info(self, keyword, cookies):
        return True, "", {"data": {"poi_list": []}}

    def get_all_publish_note_info(self, cookies_str):
        type(self).published_notes_calls += 1
        return True, "", list(self.published_notes)


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


@contextmanager
def no_proxy_env():
    yield


def _patch_creator_publish_dependencies(monkeypatch, response_payload, *, published_notes=None):
    captured: dict = {}
    FakeCreatorApi.published_notes = published_notes or []
    FakeCreatorApi.published_notes_calls = 0

    monkeypatch.setattr("backend.app.adapters.xhs.creator_api_adapter.direct_xhs_request_env", no_proxy_env)
    monkeypatch.setattr("apis.xhs_creator_apis.XHS_Creator_Apis", FakeCreatorApi)
    monkeypatch.setattr(
        "xhs_utils.xhs_creator_util.generate_xs_xs_common",
        lambda a1, api, data: ("xs-value", 1234567890, "xs-common-value"),
    )
    monkeypatch.setattr("xhs_utils.xhs_util.generate_x_rap_param", lambda api, data: "rap-value")

    def fake_post(url, *, headers, data, cookies, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["raw_data"] = data.decode("utf-8")
        captured["data"] = json.loads(captured["raw_data"])
        captured["cookies"] = cookies
        captured["timeout"] = timeout
        return FakeResponse(response_payload)

    monkeypatch.setattr("requests.post", fake_post)
    return captured


def _image_note_info() -> dict:
    return {
        "media_type": "image",
        "title": "Creator publish test",
        "desc": "body",
        "type": 1,
        "topics": ["topic"],
        "image_file_infos": [
            {
                "fileIds": "uploaded-file-id",
                "width": 800,
                "height": 600,
                "mime_type": "image/jpeg",
                "file_size": 2048,
            }
        ],
    }


def test_post_uploaded_image_note_uses_creator_web_publish_shape(monkeypatch):
    captured = _patch_creator_publish_dependencies(monkeypatch, {"success": True, "data": {"id": "note-1"}})

    payload = XhsCreatorApiAdapter("a1=test-a1; web_session=session").post_note(_image_note_info())

    assert payload["success"] is True
    assert captured["url"] == "https://edith.xiaohongshu.com/web_api/sns/v2/note"
    assert captured["headers"]["origin"] == "https://creator.xiaohongshu.com"
    assert captured["headers"]["referer"] == "https://creator.xiaohongshu.com/"
    assert captured["headers"]["authorization"] == ""
    assert captured["headers"]["sec-fetch-site"] == "same-site"
    assert captured["headers"]["content-type"] == "application/json;charset=UTF-8"
    assert captured["headers"]["x-s"] == "xs-value"
    assert captured["headers"]["x-t"] == "1234567890"
    assert captured["headers"]["x-s-common"] == "xs-common-value"
    assert captured["headers"]["x-rap-param"] == "rap-value"
    assert captured["cookies"]["a1"] == "test-a1"

    common = captured["data"]["common"]
    source = json.loads(common["source"])
    business_binds = json.loads(common["business_binds"])
    assert source == {
        "type": "web",
        "ids": "",
        "extraInfo": "{\"subType\":\"official\",\"systemId\":\"web\"}",
    }
    assert business_binds["version"] == 1
    assert business_binds["noteCopyBind"]["copyable"] is True
    assert business_binds["coProduceBind"]["enable"] is True
    assert common["privacy_info"] == {"op_type": 1, "type": 1, "user_ids": []}
    assert common["hash_tag"] == [{"id": "topic-1", "link": "", "name": "topic", "type": "topic"}]
    assert " #topic[" in common["desc"]
    assert captured["data"]["image_info"]["images"][0]["file_id"] == "spectrum/uploaded-file-id"


def test_post_uploaded_image_note_treats_creator_signature_error_as_failure(monkeypatch):
    _patch_creator_publish_dependencies(
        monkeypatch,
        {"success": True, "code": -1, "msg": "publishFailedSignatureError"},
    )

    with pytest.raises(RuntimeError, match="publishFailedSignatureError"):
        XhsCreatorApiAdapter("a1=test-a1; web_session=session").post_note(_image_note_info())


def test_post_uploaded_image_note_accepts_result_zero_and_rejects_nonzero_result(monkeypatch):
    _patch_creator_publish_dependencies(monkeypatch, {"result": 0, "data": {"id": "note-1"}})

    payload = XhsCreatorApiAdapter("a1=test-a1; web_session=session").post_note(_image_note_info())

    assert payload["result"] == 0

    _patch_creator_publish_dependencies(monkeypatch, {"result": 1001, "msg": "creator rejected"})

    with pytest.raises(RuntimeError, match="creator rejected"):
        XhsCreatorApiAdapter("a1=test-a1; web_session=session").post_note(_image_note_info())


def test_post_uploaded_image_note_enriches_work_link_from_creator_works(monkeypatch):
    _patch_creator_publish_dependencies(
        monkeypatch,
        {"success": True, "data": {"id": "note-1"}},
        published_notes=[
            {"id": "other-note", "xsec_token": "other-token", "xsec_source": "pc_publish"},
            {"id": "note-1", "xsec_token": "token-1", "xsec_source": "pc_publish"},
        ],
    )

    payload = XhsCreatorApiAdapter("a1=test-a1; web_session=session").post_note(_image_note_info())

    assert payload["note_id"] == "note-1"
    assert payload["workId"] == "note-1"
    assert payload["shareLink"] == "https://www.xiaohongshu.com/explore/note-1?xsec_token=token-1&xsec_source=pc_publish"


def test_post_uploaded_image_note_prefers_publish_response_share_link(monkeypatch):
    _patch_creator_publish_dependencies(
        monkeypatch,
        {
            "success": True,
            "data": {"id": "note-1"},
            "share_link": "https://www.xiaohongshu.com/discovery/item/note-1?xsec_token=direct",
        },
        published_notes=[{"id": "note-1", "xsec_token": "token-1", "xsec_source": "pc_publish"}],
    )

    payload = XhsCreatorApiAdapter("a1=test-a1; web_session=session").post_note(_image_note_info())

    assert payload["note_id"] == "note-1"
    assert payload["workId"] == "note-1"
    assert payload["shareLink"] == "https://www.xiaohongshu.com/discovery/item/note-1?xsec_token=direct"
    assert FakeCreatorApi.published_notes_calls == 0


def test_post_uploaded_image_note_prefers_nested_publish_response_share_link(monkeypatch):
    _patch_creator_publish_dependencies(
        monkeypatch,
        {
            "success": True,
            "data": {
                "id": "note-1",
                "share_link": "https://www.xiaohongshu.com/discovery/item/note-1?xsec_token=nested",
            },
        },
        published_notes=[{"id": "note-1", "xsec_token": "token-1", "xsec_source": "pc_publish"}],
    )

    payload = XhsCreatorApiAdapter("a1=test-a1; web_session=session").post_note(_image_note_info())

    assert payload["note_id"] == "note-1"
    assert payload["workId"] == "note-1"
    assert payload["shareLink"] == "https://www.xiaohongshu.com/discovery/item/note-1?xsec_token=nested"
    assert FakeCreatorApi.published_notes_calls == 0

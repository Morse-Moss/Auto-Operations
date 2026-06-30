from __future__ import annotations

from datetime import datetime

import backend.app.api.notes as notes_api
from backend.app.api.notes import _note_engagement_metrics, _serialize_note
from backend.app.models import Note, NoteAsset


class _FakeDb:
    def scalars(self, statement):
        return _FakeScalarResult([])

    def scalar(self, statement):
        return None


class _FakeAssetDb(_FakeDb):
    def __init__(self, assets: list[NoteAsset]) -> None:
        self.assets = assets

    def scalars(self, statement):
        return _FakeScalarResult(self.assets)


class _FakeScalarResult:
    def __init__(self, items: list) -> None:
        self.items = items

    def all(self):
        return self.items


def _note(*, platform: str = "xhs", raw_json: dict | None = None) -> Note:
    note = Note(
        id=101,
        user_id=1,
        platform_account_id=10,
        platform=platform,
        note_id="serializer-note-001",
        title="Serializer note",
        content="Body",
        author_name="Author",
        raw_json=raw_json,
        created_at=datetime(2026, 6, 30, 9, 0, 0),
    )
    return note


def test_xhs_note_engagement_metrics_use_mapper_for_nested_note_card_shape():
    note = _note(raw_json={
        "data": {
            "items": [
                {
                    "note_card": {
                        "interact_info": {
                            "liked_count": "3,000",
                            "comment_count": "12",
                            "collected_count": "1.2w",
                            "share_count": "7",
                        }
                    }
                }
            ]
        }
    })

    assert _note_engagement_metrics(note) == {
        "likes": 3000,
        "comments": 12,
        "collects": 12000,
        "shares": 7,
    }


def test_xhs_note_serializer_uses_mapper_asset_fallback_when_db_assets_are_missing():
    note = _note(raw_json={
        "cover_url": "https://images.example/raw-cover.jpg",
        "image_url": "https://images.example/raw-image.jpg",
        "video_url": "https://videos.example/raw-video.mp4",
    })

    payload = _serialize_note(_FakeDb(), note)

    assert payload["cover_url"] == "https://images.example/raw-cover.jpg"
    assert payload["video_url"] == "https://videos.example/raw-video.mp4"
    assert payload["video_addr"] == "https://videos.example/raw-video.mp4"
    assert payload["asset_urls"] == [
        "https://images.example/raw-cover.jpg",
        "https://images.example/raw-image.jpg",
        "https://videos.example/raw-video.mp4",
    ]
    assert set(payload.keys()) == {
        "id",
        "platform",
        "platform_account_id",
        "note_id",
        "title",
        "content",
        "author_name",
        "raw_json",
        "asset_urls",
        "cover_url",
        "video_url",
        "video_addr",
        "created_at",
        "engagement_metrics",
        "analysis_marks",
        "is_analysis_focus",
        "feishu_sync",
        "analysis_result",
    }


def test_xhs_note_serializer_preserves_db_asset_priority_over_mapper_fallback():
    note = _note(raw_json={
        "cover_url": "https://images.example/raw-cover.jpg",
        "image_url": "https://images.example/raw-image.jpg",
        "video_url": "https://videos.example/raw-video.mp4",
    })
    image = NoteAsset(
        id=201,
        note_id=note.id,
        asset_type="image",
        url="https://images.example/db-image.jpg",
        local_path="xhs-asset-u1-local-image.jpg",
        sort_order=0,
    )
    video = NoteAsset(
        id=202,
        note_id=note.id,
        asset_type="video",
        url="https://videos.example/db-video.mp4",
        local_path="xhs-asset-u1-local-video.mp4",
        sort_order=1,
    )

    payload = _serialize_note(_FakeAssetDb([image, video]), note)

    assert payload["cover_url"] == "/api/files/media/xhs-asset-u1-local-image.jpg"
    assert payload["video_url"] == "/api/files/media/xhs-asset-u1-local-video.mp4"
    assert payload["video_addr"] == "/api/files/media/xhs-asset-u1-local-video.mp4"
    assert payload["asset_urls"] == [
        "/api/files/media/xhs-asset-u1-local-image.jpg",
        "/api/files/media/xhs-asset-u1-local-video.mp4",
    ]


def test_non_xhs_note_serializer_does_not_require_xhs_raw_shape():
    note = _note(platform="wechat_official", raw_json={"unexpected": {"shape": True}})

    payload = _serialize_note(_FakeDb(), note)

    assert payload["platform"] == "wechat_official"
    assert payload["cover_url"] == ""
    assert payload["video_url"] == ""
    assert payload["video_addr"] == ""
    assert payload["asset_urls"] == []
    assert payload["engagement_metrics"] == {
        "likes": 0,
        "collects": 0,
        "comments": 0,
        "shares": 0,
    }


def test_xhs_note_mapping_cache_reuses_mapper_result(monkeypatch):
    calls: list[str] = []

    def fake_map_xhs_content(note_id, raw):
        calls.append(note_id)
        return notes_api.XhsContentMapping(
            note_type="normal",
            note_url="https://www.xiaohongshu.com/explore/serializer-note-001",
            author_profile_url="",
            tags=[],
            engagement_metrics={"likes": 1, "comments": 2, "collects": 3, "shares": 4},
            cover_url="https://images.example/cached-cover.jpg",
            video_url="https://videos.example/cached-video.mp4",
            asset_urls=["https://images.example/cached-cover.jpg", "https://videos.example/cached-video.mp4"],
            publish_timestamp_ms=None,
        )

    monkeypatch.setattr(notes_api, "map_xhs_content", fake_map_xhs_content)
    note = _note(raw_json={"liked_count": "999"})
    mapping_cache = {}

    assert notes_api._note_engagement_metrics(note, mapping_cache) == {
        "likes": 1,
        "collects": 3,
        "comments": 2,
        "shares": 4,
    }
    payload = notes_api._serialize_note(_FakeDb(), note, mapping_cache=mapping_cache)

    assert payload["cover_url"] == "https://images.example/cached-cover.jpg"
    assert payload["video_url"] == "https://videos.example/cached-video.mp4"
    assert calls == ["serializer-note-001"]

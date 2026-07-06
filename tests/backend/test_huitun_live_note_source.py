from __future__ import annotations

from backend.app.services.huitun_live_note_source import _rows_from_response


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

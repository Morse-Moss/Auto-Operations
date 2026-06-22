from backend.app.adapters.xhs.mappers import map_xhs_content


def test_maps_direct_raw_metrics_and_numeric_string_variants():
    mapping = map_xhs_content(
        note_id="direct-metrics-note",
        raw={
            "liked_count": "1,234",
            "comment_count": "2.5w",
            "collected_count": "8w",
            "share_count": "99",
        },
    )

    assert mapping.engagement_metrics == {
        "likes": 1234,
        "comments": 25000,
        "collects": 80000,
        "shares": 99,
    }


def test_maps_nested_note_card_interact_info_metrics():
    mapping = map_xhs_content(
        note_id="nested-metrics-note",
        raw={
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
        },
    )

    assert mapping.engagement_metrics == {
        "likes": 3000,
        "comments": 12,
        "collects": 12000,
        "shares": 7,
    }


def test_builds_canonical_note_url_with_direct_xsec_and_fallback_priority():
    direct = map_xhs_content(
        note_id="direct-url-note",
        raw={
            "note_url": "https://www.xiaohongshu.com/explore/direct-url-note?xsec_token=already-present",
            "xsec_token": "ignored-token",
            "xsec_source": "pc_search",
        },
    )
    direct_share = map_xhs_content(
        note_id="direct-share-note",
        raw={"share_url": "https://www.xiaohongshu.com/discovery/item/direct-share-note"},
    )
    with_xsec = map_xhs_content(
        note_id="xsec-url-note",
        raw={"xsec_token": "safe-url-token", "xsec_source": "pc_search"},
    )
    nested_xsec_default_source = map_xhs_content(
        note_id="nested-xsec-note",
        raw={"data": {"items": [{"note_card": {"xsec_token": "nested-token"}}]}},
    )
    fallback = map_xhs_content(note_id="fallback-url-note", raw={})

    assert direct.note_url == "https://www.xiaohongshu.com/explore/direct-url-note?xsec_token=already-present"
    assert direct_share.note_url == "https://www.xiaohongshu.com/discovery/item/direct-share-note"
    assert with_xsec.note_url == "https://www.xiaohongshu.com/explore/xsec-url-note?xsec_token=safe-url-token&xsec_source=pc_search"
    assert nested_xsec_default_source.note_url == "https://www.xiaohongshu.com/explore/nested-xsec-note?xsec_token=nested-token&xsec_source=pc_feed"
    assert fallback.note_url == "https://www.xiaohongshu.com/explore/fallback-url-note"


def test_builds_author_profile_url_from_direct_or_nested_user_ids():
    direct = map_xhs_content(note_id="note-1", raw={"author_id": "author-direct"})
    nested_user_id = map_xhs_content(
        note_id="note-2",
        raw={"data": {"items": [{"note_card": {"user": {"user_id": "author-user-id"}}}]}},
    )
    nested_id = map_xhs_content(
        note_id="note-3",
        raw={"data": {"items": [{"note_card": {"user": {"id": "author-id"}}}]}},
    )
    missing = map_xhs_content(note_id="note-4", raw={})

    assert direct.author_profile_url == "https://www.xiaohongshu.com/user/profile/author-direct"
    assert nested_user_id.author_profile_url == "https://www.xiaohongshu.com/user/profile/author-user-id"
    assert nested_id.author_profile_url == "https://www.xiaohongshu.com/user/profile/author-id"
    assert missing.author_profile_url == ""


def test_extracts_tags_from_direct_and_nested_shapes():
    direct_tag_list = map_xhs_content(
        note_id="note-tags-1",
        raw={"tag_list": [{"name": "穿搭"}, {"tag_name": "通勤"}, "夏季"]},
    )
    direct_tags = map_xhs_content(note_id="note-tags-2", raw={"tags": ["家居", {"name": "收纳"}]})
    nested = map_xhs_content(
        note_id="note-tags-3",
        raw={"data": {"items": [{"note_card": {"tag_list": [{"name": "护肤"}, "测评"]}}]}},
    )

    assert direct_tag_list.tags == ["穿搭", "通勤", "夏季"]
    assert direct_tags.tags == ["家居", "收纳"]
    assert nested.tags == ["护肤", "测评"]


def test_extracts_cover_video_and_assets_from_direct_and_explicit_shapes():
    direct = map_xhs_content(
        note_id="asset-note-1",
        raw={
            "cover_url": "https://images.example/cover.jpg",
            "image_url": "https://images.example/image.jpg",
            "asset_urls": ["https://images.example/a.jpg", "https://images.example/b.jpg"],
            "video_url": "https://videos.example/video.mp4",
        },
    )
    explicit = map_xhs_content(
        note_id="asset-note-2",
        raw={"video_addr": "https://videos.example/raw-video.mp4"},
        cover_url="https://images.example/explicit-cover.jpg",
        image_urls=["https://images.example/explicit-image.jpg"],
        asset_urls=["https://images.example/explicit-asset.jpg"],
    )

    assert direct.cover_url == "https://images.example/cover.jpg"
    assert direct.video_url == "https://videos.example/video.mp4"
    assert direct.asset_urls == [
        "https://images.example/cover.jpg",
        "https://images.example/image.jpg",
        "https://images.example/a.jpg",
        "https://images.example/b.jpg",
        "https://videos.example/video.mp4",
    ]
    assert explicit.cover_url == "https://images.example/explicit-cover.jpg"
    assert explicit.video_url == "https://videos.example/raw-video.mp4"
    assert explicit.asset_urls == [
        "https://images.example/explicit-cover.jpg",
        "https://images.example/explicit-image.jpg",
        "https://images.example/explicit-asset.jpg",
        "https://videos.example/raw-video.mp4",
    ]


def test_extracts_raw_note_type_and_publish_timestamp():
    mapping = map_xhs_content(
        note_id="typed-note",
        raw={
            "type": "video",
            "time": "1710000000000",
            "data": {"items": [{"note_card": {"type": "normal", "last_update_time": 1700000000000}}]},
        },
    )

    assert mapping.note_type == "video"
    assert mapping.publish_timestamp_ms == 1710000000000

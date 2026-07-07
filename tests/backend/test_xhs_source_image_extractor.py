from __future__ import annotations

import json

from backend.app.services.xhs_source_image_extractor import (
    canonical_xhs_image_key,
    extract_xhs_note_image_urls_from_html,
    is_xhs_note_image_url,
)


def test_extracts_multi_image_urls_from_pc_initial_state():
    note = {
        "note": {
            "noteDetailMap": {
                "6a45e1250000000022014470": {
                    "note": {
                        "type": "normal",
                        "imageList": [
                            {"urlDefault": "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/a!nd_whgt34_webp_3"},
                            {"url": "https://sns-img-hw.xhscdn.com/notes_pre_post/b?imageView2/2/w/360/format/webp"},
                            {"traceId": "notes_pre_post/c"},
                            {"urlDefault": "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/a!nd_whgt34_webp_3"},
                        ],
                    }
                }
            }
        }
    }
    html = f"<html><script>window.__INITIAL_STATE__={json.dumps(note, ensure_ascii=False)}</script></html>"

    urls = extract_xhs_note_image_urls_from_html(html)

    assert urls == [
        "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/a",
        "https://sns-img-hw.xhscdn.com/notes_pre_post/b?imageView2/2/w/360/format/webp",
        "https://sns-img-bd.xhscdn.com/notes_pre_post/c",
    ]


def test_canonical_image_key_ignores_transform_suffixes():
    assert canonical_xhs_image_key("https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/a!nd_whgt34_webp_3") == (
        "notes_pre_post/a"
    )


def test_canonical_image_key_dedupes_xhs_cdn_variants_by_note_image_token():
    webpic_url = "http://sns-webpic-qc.xhscdn.com/202607072141/4232985492d7b89d33117e50add0bba2/notes_pre_post/1040g3k03223tv026na005nv0648g80tc8psra6o!nd_dft_wlteh_webp_3"
    raw_url = "https://sns-img-bd.xhscdn.com/notes_pre_post/1040g3k03223tv026na005nv0648g80tc8psra6o"
    older_webpic_url = "http://sns-webpic-qc.xhscdn.com/202607071002/aa80cd42a6966525ecb4501eec9c72ae/notes_pre_post/1040g3k03223tv026na005nv0648g80tc8psra6o!nd_dft_wlteh_webp_3"

    assert canonical_xhs_image_key(webpic_url) == canonical_xhs_image_key(raw_url)
    assert canonical_xhs_image_key(older_webpic_url) == canonical_xhs_image_key(raw_url)


def test_extracts_initial_state_with_spaced_assignment_and_url_list_objects():
    note = {
        "noteData": {
            "data": {
                "noteData": {
                    "imageList": [
                        {"urlList": [{"url": "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/a!nd_whgt34_webp_3"}]},
                        {"urlList": [{"urlDefault": "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/b!nd_whgt34_webp_3"}]},
                    ]
                }
            }
        }
    }
    html = f"<html><script>window.__INITIAL_STATE__ = {json.dumps(note, ensure_ascii=False)};</script></html>"

    urls = extract_xhs_note_image_urls_from_html(html)

    assert urls == [
        "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/a",
        "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/b",
    ]


def test_identifies_note_image_urls_without_accepting_avatars():
    assert is_xhs_note_image_url("https://sns-img-hw.xhscdn.com/1040g2sg321eiis80n2904a1d81iemm1iipppog0")
    assert is_xhs_note_image_url("https://sns-img-hw.xhscdn.com/note_pre_post_uhdr/1040g3r83225ng7")
    assert not is_xhs_note_image_url("https://sns-avatar-qc.xhscdn.com/avatar/1040g2jo31r0l7l4n0a005")

from __future__ import annotations

import json

from backend.app.services.xhs_source_image_extractor import (
    canonical_xhs_image_key,
    extract_xhs_note_image_urls_from_html,
    extract_xhs_note_image_urls_from_payload,
    is_xhs_note_image_url,
)


def test_extracts_detail_payload_image_schema_variants_in_stable_order():
    payload = {
        "data": {
            "items": [
                {
                    "note_card": {
                        "image_list": [
                            {
                                "info_list": [
                                    {
                                        "image_scene": "WB_DFT",
                                        "url": "https://sns-img-bd.xhscdn.com/notes_pre_post/first",
                                    }
                                ]
                            },
                            {
                                "infoList": [
                                    {
                                        "imageScene": "WB_DFT",
                                        "url": "https://sns-img-bd.xhscdn.com/notes_pre_post/second",
                                    }
                                ]
                            },
                            {"url_default": "https://sns-img-bd.xhscdn.com/notes_pre_post/third"},
                            {"urlDefault": "https://sns-img-bd.xhscdn.com/notes_pre_post/fourth"},
                        ]
                    }
                }
            ]
        }
    }

    assert extract_xhs_note_image_urls_from_payload(payload) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/first",
        "https://sns-img-bd.xhscdn.com/notes_pre_post/second",
        "https://sns-img-bd.xhscdn.com/notes_pre_post/third",
        "https://sns-img-bd.xhscdn.com/notes_pre_post/fourth",
    ]


def test_extract_payload_rejects_avatars_and_dedupes_cdn_variants():
    payload = {
        "images": [
            {"url": "https://sns-avatar-qc.xhscdn.com/avatar/1040g2jo31r0l7l4n0a005"},
            {
                "url_pre": (
                    "https://sns-webpic-qc.xhscdn.com/202607/notes_pre_post/"
                    "1040g3k03223tv026na005nv0648g80tc8psra6o!nd_dft_wlteh_webp_3"
                )
            },
            {
                "urlPre": (
                    "https://sns-img-bd.xhscdn.com/notes_pre_post/"
                    "1040g3k03223tv026na005nv0648g80tc8psra6o"
                )
            },
        ]
    }

    assert extract_xhs_note_image_urls_from_payload(payload) == [
        (
            "https://sns-webpic-qc.xhscdn.com/202607/notes_pre_post/"
            "1040g3k03223tv026na005nv0648g80tc8psra6o"
        )
    ]


def test_extract_payload_supports_master_url_variants():
    payload = {
        "images": [
            {"master_url": "https://sns-img-bd.xhscdn.com/notes_pre_post/master-snake"},
            {"masterUrl": "https://sns-img-bd.xhscdn.com/notes_pre_post/master-camel"},
        ]
    }

    assert extract_xhs_note_image_urls_from_payload(payload) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/master-snake",
        "https://sns-img-bd.xhscdn.com/notes_pre_post/master-camel",
    ]


def test_extract_payload_supports_independent_info_lists_without_scanning_arbitrary_strings():
    payload = {
        "unrelated": "https://sns-img-bd.xhscdn.com/notes_pre_post/not-an-image-field",
        "info_list": [
            {
                "image_scene": "WB_DFT",
                "url": "https://sns-img-bd.xhscdn.com/notes_pre_post/info-snake",
            }
        ],
        "data": {
            "nested": {
                "infoList": [
                    {
                        "imageScene": "WB_DFT",
                        "url": "https://sns-img-bd.xhscdn.com/notes_pre_post/info-camel",
                    }
                ]
            },
        },
    }

    assert extract_xhs_note_image_urls_from_payload(payload) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/info-snake",
        "https://sns-img-bd.xhscdn.com/notes_pre_post/info-camel",
    ]


def test_extract_payload_honors_max_payload_depth_boundary():
    boundary_payload = {
        "image_list": [{"url": "https://sns-img-bd.xhscdn.com/notes_pre_post/at-boundary"}]
    }
    for _ in range(8):
        boundary_payload = {"wrapper": boundary_payload}
    too_deep_payload = {"wrapper": boundary_payload}

    assert extract_xhs_note_image_urls_from_payload(boundary_payload) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/at-boundary"
    ]
    assert extract_xhs_note_image_urls_from_payload(too_deep_payload) == []


def test_extract_payload_stops_scanning_after_two_hundred_raw_candidates():
    class MustNotBeScanned(dict):
        def items(self):
            raise AssertionError("payload traversal continued past the candidate guard")

    payload = {
        "images": [
            {"url": f"https://sns-img-bd.xhscdn.com/notes_pre_post/candidate-{index}"}
            for index in range(200)
        ],
        "after_candidate_guard": MustNotBeScanned(),
    }

    urls = extract_xhs_note_image_urls_from_payload(payload)

    assert len(urls) == 50


def test_extract_payload_counts_invalid_raw_candidates_toward_scan_guard():
    class MustNotBeScanned(dict):
        def items(self):
            raise AssertionError("invalid candidates did not stop payload traversal")

    payload = {
        "images": [{"url": f"not-an-xhs-image-{index}"} for index in range(200)],
        "after_candidate_guard": MustNotBeScanned(),
    }

    assert extract_xhs_note_image_urls_from_payload(payload) == []


def test_extract_payload_uses_one_depth_budget_across_wrappers_and_image_context():
    boundary_payload = {
        "image_list": [
            {
                "info_list": [
                    "https://sns-img-bd.xhscdn.com/notes_pre_post/combined-depth-boundary"
                ]
            }
        ]
    }
    for _ in range(6):
        boundary_payload = {"wrapper": boundary_payload}
    too_deep_payload = {"wrapper": boundary_payload}

    assert extract_xhs_note_image_urls_from_payload(boundary_payload) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/combined-depth-boundary"
    ]
    assert extract_xhs_note_image_urls_from_payload(too_deep_payload) == []


def test_extracts_raw_html_image_url_without_initial_state():
    html = (
        '<html><img src="https://sns-img-bd.xhscdn.com/notes_pre_post/raw-fallback">'
        '<img src="https://sns-avatar-qc.xhscdn.com/avatar/not-a-note-image"></html>'
    )

    assert extract_xhs_note_image_urls_from_html(html) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/raw-fallback"
    ]


def test_extracts_escaped_raw_html_image_url_when_initial_state_is_malformed():
    html = (
        '<script>window.__INITIAL_STATE__ = {broken json: true, '
        '"url":"https:\\/\\/sns-img-bd.xhscdn.com\\/notes_pre_post\\/escaped-fallback"};'
        "</script>"
    )

    assert extract_xhs_note_image_urls_from_html(html) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/escaped-fallback"
    ]


def test_initial_state_extracts_target_note_without_recommendation_images():
    state = {
        "recommendations": {
            "imageList": [
                {"url": "https://sns-img-bd.xhscdn.com/notes_pre_post/recommendation"}
            ]
        },
        "note": {
            "noteDetailMap": {
                "target-note": {
                    "note": {
                        "imageList": [
                            {"url": "https://sns-img-bd.xhscdn.com/notes_pre_post/target"}
                        ]
                    }
                }
            }
        },
    }
    html = f"<script>window.__INITIAL_STATE__={json.dumps(state)}</script>"

    assert extract_xhs_note_image_urls_from_html(html) == [
        "https://sns-img-bd.xhscdn.com/notes_pre_post/target"
    ]


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


def test_canonical_image_key_keeps_note_pre_post_uhdr_tokens_distinct():
    first = "http://sns-webpic-qc.xhscdn.com/202607091612/a/note_pre_post_uhdr/1040g3r8321khfii9n0805n3cklqkba4lsql93j8!nd_dft_wlteh_webp_3"
    second = "http://sns-webpic-qc.xhscdn.com/202607091612/b/note_pre_post_uhdr/1040g3r8321khfii9n0b05n3cklqkba4l5f2camo!nd_dft_wlteh_webp_3"

    assert canonical_xhs_image_key(first) == "note_pre_post_uhdr/1040g3r8321khfii9n0805n3cklqkba4lsql93j8"
    assert canonical_xhs_image_key(second) == "note_pre_post_uhdr/1040g3r8321khfii9n0b05n3cklqkba4l5f2camo"
    assert canonical_xhs_image_key(first) != canonical_xhs_image_key(second)


def test_extract_does_not_promote_plain_state_ids_to_image_urls():
    note = {
        "note": {
            "noteDetailMap": {
                "6a361fc400000000110175cd": {
                    "note": {
                        "id": "6a361fc400000000110175cd",
                        "imageList": [
                            {"id": "6a361fc400000000110175cd"},
                            {"traceId": "notes_pre_post/real-image-token"},
                        ],
                    }
                }
            }
        }
    }
    html = f"<html><script>window.__INITIAL_STATE__={json.dumps(note, ensure_ascii=False)}</script></html>"

    urls = extract_xhs_note_image_urls_from_html(html)

    assert urls == ["https://sns-img-bd.xhscdn.com/notes_pre_post/real-image-token"]


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

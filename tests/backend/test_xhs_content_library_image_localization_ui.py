from __future__ import annotations

from pathlib import Path


FORBIDDEN_USER_COPY = ("灰豚", "huitun", "extData", "connector", "第三方数据源")


def test_xhs_content_library_exposes_plain_image_save_action():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")
    api_source = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
    type_source = Path("frontend/src/types/index.ts").read_text(encoding="utf-8")

    assert "localizeSavedNoteImages" in adapter_source
    assert "renderSaveImagesButton" in adapter_source
    assert "保存图片" in adapter_source
    assert "图片已保存" in adapter_source
    assert "/notes/${noteId}/assets/localize-images" in api_source
    assert "NoteImageLocalizationResult" in type_source

    save_button_section = adapter_source[
        adapter_source.index("function renderSaveImagesButton"):
        adapter_source.index("function renderFeishuToolbar")
    ]
    assert all(term not in save_button_section for term in FORBIDDEN_USER_COPY)


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


def test_xhs_source_image_completion_prepares_page_import_when_server_cannot_see_images():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")

    import_button_section = adapter_source[
        adapter_source.index("function renderImportSourceImagesButton"):
        adapter_source.index("function renderSystemAnalysisButton")
    ]

    assert "createSavedNoteSourceImageImportScript" in import_button_section
    assert "copyPageImportScript" not in import_button_section
    assert "自动补全未识别到新增图片" in import_button_section
    assert "已复制原文导入脚本" in import_button_section
    assert "需要打开原文导入" not in import_button_section
    assert all(term not in import_button_section for term in FORBIDDEN_USER_COPY)


def test_xhs_content_library_does_not_fabricate_source_url_from_note_id():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")
    get_note_url_section = adapter_source[
        adapter_source.index("function getNoteUrl"):
        adapter_source.index("function getAuthorProfileUrl")
    ]

    assert "note.source_url" in get_note_url_section
    assert "return \"\";" in get_note_url_section
    assert "return `https://www.xiaohongshu.com/explore/${note.note_id}`" not in get_note_url_section
    assert all(term not in get_note_url_section for term in FORBIDDEN_USER_COPY)


def test_xhs_content_library_does_not_open_legacy_data_acquisition_short_links():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")

    assert "function isOpenableNoteUrl" in adapter_source
    assert "legacy data-acquisition short links are resolver inputs" in adapter_source
    assert "const canOpenSource = isOpenableNoteUrl(noteUrl);" in adapter_source
    assert "const canImport = noteUrl.startsWith(\"http\");" in adapter_source

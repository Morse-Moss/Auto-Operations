from __future__ import annotations

from pathlib import Path


FORBIDDEN_USER_COPY = ("灰豚", "huitun", "extData", "connector", "第三方数据源")


def test_xhs_content_library_exposes_plain_image_save_action():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")
    api_source = Path("frontend/src/lib/api/shared.ts").read_text(encoding="utf-8")
    type_source = Path("frontend/src/types/shared.ts").read_text(encoding="utf-8")

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


def test_xhs_source_image_completion_does_not_implicitly_copy_page_script():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")

    import_button_section = adapter_source[
        adapter_source.index("function renderImportSourceImagesButton"):
        adapter_source.index("function renderSystemAnalysisButton")
    ]

    assert "preparePageImportScript" not in import_button_section
    assert "createSavedNoteSourceImageImportScript" not in import_button_section
    assert "sendBeacon" not in import_button_section
    assert "clipboard" not in import_button_section
    assert "已复制原文导入脚本" not in import_button_section
    assert "await runXhsSourceImageImportAction" in import_button_section
    assert "importImages:" in import_button_section
    assert "refreshSelectedItem:" in import_button_section
    assert "setBusy:" in import_button_section
    assert "setDetailError:" in import_button_section
    assert "setDetailActionMessage:" in import_button_section
    assert "notify:" in import_button_section
    assert all(term not in import_button_section for term in FORBIDDEN_USER_COPY)


def test_xhs_manual_page_import_remains_separate_from_automatic_action():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")
    manual_button_start = adapter_source.index("function renderPageImageImportAssistButton")
    automatic_button_start = adapter_source.index("function renderImportSourceImagesButton")
    automatic_button_end = adapter_source.index("function renderSystemAnalysisButton")
    automatic_button_section = adapter_source[automatic_button_start:automatic_button_end]

    assert manual_button_start < automatic_button_start
    assert "renderPageImageImportAssistButton" not in automatic_button_section
    assert "renderImportSourceImagesButton(controller, selectedNote, noteUrl)" in adapter_source
    assert "renderPageImageImportAssistButton(controller, selectedNote, noteUrl)" in adapter_source


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

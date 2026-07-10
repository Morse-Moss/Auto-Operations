from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend" / "src" / path).read_text(encoding="utf-8")


def test_xhs_content_library_system_analysis_shows_credit_cost():
    adapter_source = read_frontend("pages/platforms/xhs/xhs-content-library-adapter.ts")

    assert "SYSTEM_ANALYSIS_CREDIT_COST" in adapter_source
    assert "消耗 10 积分" in adapter_source
    assert "selectedCount * SYSTEM_ANALYSIS_CREDIT_COST" in adapter_source
    assert "消耗 10 积分/条" in adapter_source


def test_xhs_content_library_exposes_system_analysis_action():
    api_source = read_frontend("lib/api.ts")
    adapter_source = read_frontend("pages/platforms/xhs/xhs-content-library-adapter.ts")

    assert "export async function analyzeSavedNote" in api_source
    assert 'http.post<NoteAnalysisResult>(`/notes/${noteId}/analysis`' in api_source
    assert "analyzeSavedNote" in adapter_source
    assert "系统分析" in adapter_source
    assert "重新系统分析" in adapter_source


def test_xhs_content_library_exposes_batch_system_analysis_action():
    shell_source = read_frontend("components/content-library/content-library-shell.tsx")
    adapter_source = read_frontend("pages/platforms/xhs/xhs-content-library-adapter.ts")

    assert "adapter.renderBatchActions?.({ controller })" in shell_source
    assert "renderBatchActions: renderBatchSystemAnalysisAction" in adapter_source
    assert "BatchSystemAnalysisButton" in adapter_source
    assert "controller.selectedItemIds" in adapter_source
    assert "await analyzeSavedNote(noteId)" in adapter_source


def test_xhs_analysis_display_uses_system_analysis_copy():
    shell_source = read_frontend("components/content-library/content-library-shell.tsx")
    hook_source = read_frontend("components/content-library/use-content-library.ts")
    adapter_source = read_frontend("pages/platforms/xhs/xhs-content-library-adapter.ts")

    assert "系统分析筛选" in shell_source
    assert "系统分析筛选项加载失败" in hook_source
    assert "系统分析结果" in adapter_source
    assert "飞书同步状态" in adapter_source
    assert "分析备注" not in adapter_source

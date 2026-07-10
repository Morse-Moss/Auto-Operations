from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "pages" / "platforms" / "xhs" / "data-acquisition-page.tsx"


def test_candidate_table_preserves_metric_column_readability():
    source = PAGE.read_text(encoding="utf-8")

    assert 'style={{ whiteSpace: "nowrap" }}' in source
    assert 'scroll={{ x: 1000 }}' in source

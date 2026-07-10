from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAWER = ROOT / "frontend" / "src" / "components" / "account" / "add-account-drawer.tsx"
QR_PANEL = ROOT / "frontend" / "src" / "components" / "account" / "qr-login-panel.tsx"
ACCOUNTS_PAGE = ROOT / "frontend" / "src" / "pages" / "platforms" / "xhs" / "accounts-page.tsx"


def test_qr_panel_is_isolated_by_current_auth_selection():
    source = DRAWER.read_text(encoding="utf-8")

    assert "const qrPanelKey =" in source
    assert "schema.platform" in source
    assert "effectiveAccountType" in source
    assert "effectiveMethod" in source
    assert "key={qrPanelKey}" in source


def test_qr_panel_only_applies_latest_generation_request():
    source = QR_PANEL.read_text(encoding="utf-8")

    assert "requestSequenceRef" in source
    assert "const requestSequence = ++requestSequenceRef.current" in source
    assert "requestSequence !== requestSequenceRef.current" in source
    assert "正在生成 Creator 二维码，请稍候" in source


def test_qr_panel_ignores_stale_poll_results():
    source = QR_PANEL.read_text(encoding="utf-8")

    assert "const pollingRequestSequence = requestSequenceRef.current" in source
    assert "let pollingCancelled = false" in source
    assert "pollingRequestSequence !== requestSequenceRef.current" in source
    assert "pollingCancelled = true" in source


def test_pending_profile_sync_is_not_presented_as_fully_normal():
    source = ACCOUNTS_PAGE.read_text(encoding="utf-8")

    assert 'profileValue(account, "profile_sync_status") === "pending"' in source
    assert '"资料待同步"' in source

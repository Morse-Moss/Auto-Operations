from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAWER = ROOT / "frontend" / "src" / "components" / "account" / "add-account-drawer.tsx"
QR_PANEL = ROOT / "frontend" / "src" / "components" / "account" / "qr-login-panel.tsx"
ACCOUNTS_PAGE = ROOT / "frontend" / "src" / "pages" / "platforms" / "xhs" / "accounts-page.tsx"
ACCOUNTS_SHELL = ROOT / "frontend" / "src" / "platform-core" / "accounts" / "platform-accounts-shell.tsx"


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


def test_qr_panel_does_not_overlap_poll_requests():
    source = QR_PANEL.read_text(encoding="utf-8")

    assert "window.setInterval" not in source
    assert "window.setTimeout" in source


def test_pending_profile_sync_is_not_presented_as_fully_normal():
    source = ACCOUNTS_PAGE.read_text(encoding="utf-8")

    assert 'profileValue(account, "profile_sync_status") === "pending"' in source
    assert '"资料待同步"' in source


def test_pc_account_card_displays_red_id_with_profile_metrics():
    source = ACCOUNTS_PAGE.read_text(encoding="utf-8")
    shell_source = ACCOUNTS_SHELL.read_text(encoding="utf-8")
    pc_metrics_start = source.index('{ key: "type", title: "类型", value: "PC" }')
    pc_metrics_end = source.index("];", pc_metrics_start)
    pc_metrics = source[pc_metrics_start:pc_metrics_end]

    assert 'key: "red_id"' in pc_metrics
    assert 'title: "小红书号"' in pc_metrics
    assert 'groupSeparator: ""' in pc_metrics
    assert "span: 16" in pc_metrics
    assert "groupSeparator={metric.groupSeparator}" in shell_source
    assert "span={metric.span ?? 8}" in shell_source

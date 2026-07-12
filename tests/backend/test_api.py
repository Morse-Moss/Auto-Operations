import base64
import os
import re
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import Note, NoteAnalysisResult
from test_support.beta_invites import create_test_invite_code


client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "spider-xhs"}


def test_platforms_endpoint_exposes_product_registry():
    response = client.get("/api/platforms")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 9
    assert payload["items"][0]["id"] == "xhs"
    assert payload["items"][0]["enabled"] is True
    assert payload["items"][1]["status"] == "coming_soon"


def test_xhs_analytics_overview_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.get("/api/xhs/analytics/overview")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_backend_foundation_modules_import():
    from backend.app.core.config import get_settings
    from backend.app.core.database import Base
    from backend.app.models import PlatformAccount, Note, Task, User

    settings = get_settings()
    assert settings.app_name == "Spider_XHS"
    assert Base is not None
    assert User.__tablename__ == "users"
    assert PlatformAccount.__tablename__ == "platform_accounts"
    assert Note.__tablename__ == "notes"
    assert Task.__tablename__ == "tasks"


def test_accounts_page_does_not_auto_check_accounts_on_load():
    source = open("frontend/src/pages/platforms/xhs/accounts-page.tsx", encoding="utf-8").read()

    assert "refreshMissingProfiles" not in source
    assert "void refreshMissingProfiles(loadedAccounts)" not in source


def test_accounts_page_uses_antd_components_and_shows_check_state():
    source = open("frontend/src/pages/platforms/xhs/accounts-page.tsx", encoding="utf-8").read()

    assert "antd" in source
    assert "checkingAccountIds" in source or "checkingId" in source or "isChecking" in source
    assert "检查" in source


def test_xhs_direct_request_env_temporarily_removes_proxy_variables(monkeypatch):
    from backend.app.adapters.xhs.request_env import PROXY_ENV_KEYS, direct_xhs_request_env

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:10809")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:10809")

    with direct_xhs_request_env():
        assert all(key not in os.environ for key in PROXY_ENV_KEYS)

    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:10809"
    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:10809"


def test_xhs_pc_login_sdk_preserves_qrcode_identity_metadata(monkeypatch):
    from apis import xhs_pc_login_apis

    response = SimpleNamespace(
        cookies={},
        json=lambda: {
            "success": True,
            "msg": "success",
            "data": {"codeStatus": 1, "userId": "qr-user-1", "result": {}},
        },
    )
    monkeypatch.setattr(xhs_pc_login_apis, "generate_headers", lambda *_args, **_kwargs: ({}, "{}"))
    monkeypatch.setattr(xhs_pc_login_apis.requests, "post", lambda *_args, **_kwargs: response)

    api = xhs_pc_login_apis.XHSLoginApi()
    success, _message, _cookies = api.check_qrcode_status("qr-123", "code-123", {"a1": "temp-a1"})

    assert success is False
    assert api.last_qrcode_status_data == {"codeStatus": 1, "userId": "qr-user-1", "result": {}}


@pytest.mark.parametrize(
    ("response_cookies", "payload", "expected"),
    [
        ({"web_session": "cookie-session"}, {}, "cookie-session"),
        ({}, {"data": {"login_info": {"session": "legacy-session"}}}, "legacy-session"),
        ({}, {"data": {"loginInfo": {"session": "camel-session"}}}, "camel-session"),
        ({}, {"data": {"web_session": "snake-session"}}, "snake-session"),
        ({}, {"data": {"webSession": "camel-web-session"}}, "camel-web-session"),
        ({}, {"data": {"session": "direct-session"}}, "direct-session"),
        ({}, {"data": {"result": {"session": "result-session"}}}, "result-session"),
    ],
)
def test_xhs_pc_login_extracts_web_session_from_supported_response_shapes(
    response_cookies,
    payload,
    expected,
):
    from apis.xhs_pc_login_apis import _extract_web_session

    assert _extract_web_session(response_cookies, payload) == expected


def test_xhs_pc_login_adapter_maps_qrcode_user_id(monkeypatch):
    from apis.xhs_pc_login_apis import XHSLoginApi
    from backend.app.adapters.xhs.pc_login_adapter import XhsPcLoginAdapter

    def fake_check_qrcode_status(self, qr_id, code, cookies):
        assert qr_id == "qr-123"
        assert code == "code-123"
        self.last_qrcode_status_data = {"codeStatus": 2, "userId": "qr-user-1"}
        return True, "success", {**cookies, "web_session": "session-123"}

    monkeypatch.setattr(XHSLoginApi, "check_qrcode_status", fake_check_qrcode_status)

    result = XhsPcLoginAdapter().check_qrcode_status("qr-123", "code-123", {"a1": "temp-a1"})

    assert result["status"] == "confirmed"
    assert result["user_info"] == {"external_user_id": "qr-user-1"}


def test_xhs_pc_login_adapter_requires_web_session_for_confirmation(monkeypatch):
    from apis.xhs_pc_login_apis import XHSLoginApi
    from backend.app.adapters.xhs.pc_login_adapter import XhsPcLoginAdapter

    def fake_check_qrcode_status(self, qr_id, code, cookies):
        self.last_qrcode_status_data = {"codeStatus": 2, "userId": "qr-user-1"}
        return True, "success", dict(cookies)

    monkeypatch.setattr(XHSLoginApi, "check_qrcode_status", fake_check_qrcode_status)

    result = XhsPcLoginAdapter().check_qrcode_status("qr-123", "code-123", {"a1": "temp-a1"})

    assert result["status"] == "scanned"
    assert result["cookies"] == {"a1": "temp-a1"}
    assert result["user_info"] == {"external_user_id": "qr-user-1"}


def test_xhs_adapters_isolate_sdk_calls_from_broken_system_proxy():
    adapter_paths = [
        "backend/app/adapters/xhs/creator_login_adapter.py",
        "backend/app/adapters/xhs/creator_api_adapter.py",
        "backend/app/adapters/xhs/pc_login_adapter.py",
        "backend/app/adapters/xhs/pc_api_adapter.py",
    ]

    for path in adapter_paths:
        source = open(path, encoding="utf-8").read()
        assert "direct_xhs_request_env" in source


def test_crawler_page_exports_spider_style_excel():
    source = open("frontend/src/pages/platforms/xhs/crawler-page.tsx", encoding="utf-8").read()

    assert "noteExcelHeaders" in source
    assert "笔记id" in source
    assert "图片地址url列表" in source
    assert "application/vnd.ms-excel;charset=utf-8" in source


def test_crawler_page_uses_antd_table():
    source = open("frontend/src/pages/platforms/xhs/crawler-page.tsx", encoding="utf-8").read()

    assert "antd" in source
    assert "Table" in source


def test_xhs_data_acquisition_page_hides_internal_source_terms_and_keeps_high_risk_direct_area():
    source = open("frontend/src/pages/platforms/xhs/data-acquisition-page.tsx", encoding="utf-8").read()
    crawler_source = open("frontend/src/pages/platforms/xhs/crawler-page.tsx", encoding="utf-8").read()
    router_source = open("frontend/src/app/router.tsx", encoding="utf-8").read()
    registry_source = open("frontend/src/platform-core/registry/platform-sections.tsx", encoding="utf-8").read()

    assert 'path="/platforms/xhs/crawler" element={<XhsDataAcquisitionPage />}' in router_source
    assert "小红书数据获取" in registry_source
    assert "获取笔记数据" in source
    assert "待确认候选" in source
    assert "小红书账号直连" in source
    assert "高风险" in source
    assert "taskCards" not in source
    for hidden_status in ("获取热词趋势", "获取榜单笔记", "补全笔记详情", "关键词分析", "导入数据文件", "验证中", "后续"):
        assert hidden_status not in source
    assert '<XhsCrawlerPage visibleSource="xhs" />' in source
    assert 'visibleSource?: "all" | "xhs"' in crawler_source
    assert "account.nickname" not in source
    for forbidden in ("灰豚", "huitun", "extData", "connector", "第三方数据源"):
        assert forbidden not in source


def test_xhs_data_acquisition_keyword_group_links_open_data_account_workbench():
    source = open("frontend/src/pages/platforms/xhs/data-acquisition-page.tsx", encoding="utf-8").read()
    keywords_page_source = open("frontend/src/pages/platforms/xhs/keywords-page.tsx", encoding="utf-8").read()

    assert "navigate(`/platforms/xhs/crawler?keyword_group_id=${group.id}&keyword_limit=${Math.min(20, group.keywords.length)}`)" in keywords_page_source
    assert "handleCreateKeywordGroupRuns" in source
    assert "关键词组获取笔记数据" in source
    assert "预计消耗" in source
    assert 'searchParams.get("keyword_group_id")' in source
    assert "createDataAcquisitionRun" in source
    assert "run_ids" in source
    assert "setSelectedRunIds" in source
    assert "candidateSortOptions" in source
    assert "candidateSortBy" in source
    assert "sort_by: nextSortBy" in source
    assert "shouldShowKeywordGroupCrawler" not in source


def test_model_config_page_defaults_to_doubao_seed_main_model():
    source = open("frontend/src/pages/models/model-config-page.tsx", encoding="utf-8").read()
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()

    assert 'const DOUBAO_MAIN_MODEL = "doubao-seed-2-0-mini-260428"' in source
    assert 'const VOLCENGINE_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"' in source
    assert 'provider: "volcengine-ark"' in source
    assert "同一个 Doubao 配置可以分别保存为文本模型和图片分析模型" in source
    assert "豆包主力模型" in source
    assert "保存为主力模型" in source
    assert "configureDoubaoMainModels" in source
    assert '"/model-configs/doubao-main"' in api_source
    assert "DoubaoMainModelConfigResult" in types_source
    assert "runninghub-image-g" not in source


def test_task_center_links_data_acquisition_tasks_back_to_candidate_workbench():
    source = open("frontend/src/pages/tasks/task-center-page.tsx", encoding="utf-8").read()

    assert "data_acquisition_note_search" in source
    assert "数据获取" in source
    assert "data_acquisition_url" in source
    assert "查看候选" in source
    assert "重新获取" in source
    assert "安全点停止" in source
    assert "retryDataAcquisitionRun" in source
    for forbidden in ("灰豚", "huitun", "extData", "connector", "第三方数据源"):
        assert forbidden not in source


def test_frontend_exposes_huitun_discovery_and_crawl_diagnostics_clients():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()
    keywords_page_source = open("frontend/src/pages/platforms/xhs/keywords-page.tsx", encoding="utf-8").read()
    crawler_page_source = open("frontend/src/pages/platforms/xhs/crawler-page.tsx", encoding="utf-8").read()

    assert "createHuitunKeywordDiscoveryRun" in api_source
    assert "createHuitunQrLoginSession" in api_source
    assert "pollHuitunLoginSession" in api_source
    assert "importHuitunCookieAccount" in api_source
    assert "fetchHuitunKeywordDiscoveryRun" in api_source
    assert "importKeywordCandidatesToGroup" in api_source
    assert "importKeywordCandidates" in api_source
    assert "fetchXhsCrawlDiagnostics" in api_source
    assert "crawlXhsKeywordGroupStream" in api_source
    assert '"/keyword-groups/huitun/discovery-runs"' in api_source
    assert '"/xhs/crawl/diagnostics"' in api_source
    assert '"/api/xhs/crawl/keyword-group"' in api_source
    assert "export type KeywordDiscoveryItem" in types_source
    assert "export type KeywordDiscoveryRun" in types_source
    assert "export type HuitunDiscoveryRunPayload" in types_source
    assert "export type CrawlDiagnostic" in types_source
    assert '"huitun"' in types_source
    assert "live_account" in types_source
    assert "account_id?: number" in types_source
    assert "XhsKeywordGroupCrawlPayload" in types_source
    assert "quality_status" in types_source
    assert "diagnostic_kind" in types_source
    assert "热词候选" in keywords_page_source
    assert "获取候选词" in keywords_page_source
    assert "手工导入热词" in keywords_page_source
    assert "灰豚" not in keywords_page_source
    assert "live_account" in keywords_page_source
    assert "fetchHuitunHotwordsFromAccount" in keywords_page_source
    assert "parseHuitunHotwords" in keywords_page_source
    assert "importSelectedCandidates" in keywords_page_source
    assert "keyword_group_id" in keywords_page_source
    assert "开始采集" in keywords_page_source
    assert "quality_status" in crawler_page_source
    assert "diagnostic_kind" in crawler_page_source
    assert "是否已入库" in crawler_page_source
    assert "关键词组一键采集" in crawler_page_source
    assert "傻瓜模式" not in crawler_page_source
    assert "高级设置" in crawler_page_source
    assert "crawlXhsKeywordGroupStream" in crawler_page_source
    assert "summary_message" in crawler_page_source
    assert "采集完成" in crawler_page_source


def test_image_studio_draft_asset_url_resolver_contract():
    source = open("frontend/src/components/image-studio/draft-image-studio-context.ts", encoding="utf-8").read()
    xhs_source = open("frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts", encoding="utf-8").read()
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()

    assert "export function draftAssetImageUrl(asset: DraftAsset): string" in source
    assert "if (isUsableImageUrl(asset.url)) return asset.url;" in source
    assert "const rawLocalPath: unknown = asset.local_path;" in source
    assert "if (isUsableImageUrl(rawLocalPath)) return rawLocalPath;" in source
    assert r"replace(/^\/api\/files\/media\//" in source
    assert "`/api/files/media/${fileName}`" in source
    assert 'asset.asset_type !== "image"' in source
    assert re.search(
        r"draftAssetToImageStudioCandidate[\s\S]*?draftAssetImageUrl\(asset\)",
        source,
    )
    assert "draftAssetImageUrl" in xhs_source
    assert "export async function localizeDraftAsset" in api_source
    assert "`/drafts/${draftId}/assets/${assetId}/localize`" in api_source


def test_frontend_exposes_task_10_to_14_api_and_type_contracts():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()

    assert "fetchHuitunKeywordDiscoveryRuns" in api_source
    assert "duplicateDraft" in api_source
    assert "export type KeywordDiscoveryRun" in types_source
    keyword_discovery_run_match = re.search(
        r"export\s+type\s+KeywordDiscoveryRun\s*=\s*\{(?P<body>.*?)\n\};",
        types_source,
        re.DOTALL,
    )
    assert keyword_discovery_run_match, "KeywordDiscoveryRun type block is required"
    keyword_discovery_run_body = keyword_discovery_run_match.group("body")
    assert re.search(r"\bseed_results\b", keyword_discovery_run_body)
    assert re.search(r"\bsummary\b", keyword_discovery_run_body)
    assert (
        "export type HuitunKeywordDiscoverySeedResult" in types_source
        or "export type HuitunSeedResult" in types_source
    )
    assert (
        "export type HuitunKeywordDiscoverySummary" in types_source
        or "export type HuitunDiscoverySummary" in types_source
    )


def _matching_brace_index(source, open_brace_index, max_length=None):
    depth = 0
    limit = len(source) if max_length is None else min(len(source), open_brace_index + max_length)
    for index in range(open_brace_index, limit):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _extract_named_helper_bodies(source, names):
    bodies = []
    name_pattern = "|".join(re.escape(name) for name in names)
    for match in re.finditer(rf"\bfunction\s+(?:{name_pattern})\s*\(", source):
        open_brace_index = source.find("{", match.end())
        if open_brace_index == -1:
            continue
        close_brace_index = _matching_brace_index(source, open_brace_index)
        if close_brace_index is not None:
            bodies.append(source[open_brace_index + 1 : close_brace_index])

    for match in re.finditer(rf"\bconst\s+(?:{name_pattern})\s*=", source):
        arrow_index = source.find("=>", match.end())
        if arrow_index == -1:
            continue
        body_start = arrow_index + 2
        while body_start < len(source) and source[body_start].isspace():
            body_start += 1
        if body_start < len(source) and source[body_start] == "{":
            close_brace_index = _matching_brace_index(source, body_start)
            if close_brace_index is not None:
                bodies.append(source[body_start + 1 : close_brace_index])
        else:
            body_end = source.find(";", body_start)
            if body_end != -1:
                bodies.append(source[body_start:body_end])
    return bodies


def test_keywords_page_supports_batch_huitun_discovery_runs_and_seed_diagnostics():
    source = open("frontend/src/pages/platforms/xhs/keywords-page.tsx", encoding="utf-8").read()

    seed_splitter_bodies = _extract_named_helper_bodies(source, ["splitSeedKeywords", "parseSeedKeywords"])
    assert seed_splitter_bodies, "Batch discovery needs a dedicated seed splitter"
    assert any(
        re.search(r"\.split\s*\(", body)
        and re.search(r"(?:\\r|\\n|\\r\?\\n|\\s)", body)
        and re.search(r"(?:,|，|\\uFF0C)", body)
        for body in seed_splitter_bodies
    ), "Seed splitter must split on newline and comma/Chinese comma separators"
    assert "TextArea" in source
    assert "fetchHuitunKeywordDiscoveryRuns" in source
    assert "huitunRuns" in source or "discoveryRuns" in source
    assert "seed_results" in source
    assert "partial_failed" in source
    assert re.search(r"失败[^`'\"}]{0,80}(种子词|种子|seed)|(?:种子词|种子|seed)[^`'\"}]{0,80}失败", source, re.IGNORECASE)
    assert "数据账号" not in source
    for forbidden in ("灰豚", "extData", "connector", "第三方数据源"):
        assert forbidden not in source


def test_real_drafts_route_exposes_duplicate_draft_action():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    router_source = open("frontend/src/app/router.tsx", encoding="utf-8").read()
    workbench_source = open("frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx", encoding="utf-8").read()
    hook_source = open("frontend/src/components/draft-workbench/use-draft-workbench.ts", encoding="utf-8").read()

    assert 'path="/platforms/xhs/drafts"' in router_source
    assert "rewrite-page" in router_source
    assert "duplicateDraft" in api_source
    assert "duplicateSelectedDraft" in hook_source
    assert "createXhsDraftWorkbenchAdapter" in workbench_source
    shell_source = open("frontend/src/components/draft-workbench/draft-workbench-shell.tsx", encoding="utf-8").read()
    assert re.search(r"duplicateSelectedDraft[\s\S]*?adapter\.duplicateDraft\s*\(", hook_source)
    assert re.search(r"selectDraft[\s\S]*?setError\s*\(\s*null\s*\)[\s\S]*?setMessage\s*\(\s*null\s*\)", hook_source)
    assert "复制" in shell_source
    assert "CopyOutlined" in shell_source


def _object_slices_containing(source, text, max_length=2500):
    for match in re.finditer(re.escape(text), source):
        object_start = source.rfind("{", 0, match.start())
        while object_start != -1:
            object_end = _matching_brace_index(source, object_start, max_length=max_length)
            if object_end is not None and object_start <= match.start() <= object_end:
                yield source[object_start : object_end + 1]
            object_start = source.rfind("{", 0, object_start)


def test_publish_page_shows_visibility_labels_and_unsupported_mutual_friends_copy():
    source = open("frontend/src/pages/platforms/xhs/publish-page.tsx", encoding="utf-8").read()

    assert "公开可见" in source
    assert "仅自己可见" in source
    mutual_friends_option_slices = list(_object_slices_containing(source, "仅互关好友可见"))
    assert any(
        re.search(r"不支持|unsupported", option_slice, re.IGNORECASE)
        and re.search(r"\bdisabled\s*:\s*true\b", option_slice)
        for option_slice in mutual_friends_option_slices
    ), "Mutual-friends visibility must be visibly unsupported and disabled in the same option vicinity"


def test_rewrite_page_splits_generate_reference_inputs_before_combining():
    source = open("frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx", encoding="utf-8").read()

    assert "systemPrompt" in source
    assert "instruction" in source
    assert "rewriteDraftWithAi" in source


def test_frontend_exposes_feishu_integration_contracts():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()

    assert "FeishuIntegrationConfig" in types_source
    assert "FeishuIntegrationConfigPayload" in types_source
    assert "FeishuCreateAnalysisBasePayload" in types_source
    assert "FeishuCreateAnalysisBaseResponse" in types_source
    assert "NoteAnalysisResult" in types_source
    assert "FeishuSyncState" in types_source
    assert "FeishuPushNotesPayload" in types_source
    assert "FeishuPullNotesPayload" in types_source
    assert "FeishuSyncResponse" in types_source
    assert "feishu_sync?: FeishuSyncState" in types_source
    assert "analysis_result?: NoteAnalysisResult | null" in types_source
    assert "score?: number | null" in types_source
    assert "rating?: string | null" in types_source
    assert "cover_type?: string | null" in types_source
    assert "title_type?: string | null" in types_source
    assert "fetchFeishuConfig" in api_source
    assert "saveFeishuConfig" in api_source
    assert "ensureFeishuFields" in api_source
    assert "testFeishuConnection" in api_source
    assert "createFeishuAnalysisBase" in api_source
    assert "pushXhsNotesToFeishu" in api_source
    assert "pullXhsNotesFromFeishu" in api_source
    assert '"/integrations/feishu/config"' in api_source
    assert '"/integrations/feishu/create-analysis-base"' in api_source
    assert '"/integrations/feishu/xhs-notes/push"' in api_source
    assert '"/integrations/feishu/xhs-notes/pull"' in api_source
    assert "feishu_push_status" in api_source
    assert "analysis_status" in api_source
    assert "content_type" in api_source
    assert "reuse_value" in api_source
    assert "reusable_model" in api_source


def test_settings_page_exposes_feishu_integration_card():
    source = open("frontend/src/pages/settings/settings-page.tsx", encoding="utf-8").read()

    assert "飞书集成" in source
    assert "飞书 App ID" in source
    assert "飞书 App Secret" in source
    assert "飞书多维表格地址" in source
    assert "目标数据表" in source
    assert "启用状态" in source
    assert "保存飞书配置" in source
    assert "创建飞书分析表" in source
    assert "测试连接" in source
    assert "自动补字段" in source
    assert "fetchFeishuConfig" in source
    assert "saveFeishuConfig" in source
    assert "createFeishuAnalysisBase" in source
    assert "ensureFeishuFields" in source


def test_xhs_content_library_exposes_feishu_filters_and_actions():
    adapter_source = open("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts", encoding="utf-8").read()
    shell_source = open("frontend/src/components/content-library/content-library-shell.tsx", encoding="utf-8").read()
    types_source = open("frontend/src/components/content-library/content-library-types.ts", encoding="utf-8").read()
    hook_source = open("frontend/src/components/content-library/use-content-library.ts", encoding="utf-8").read()

    assert "系统分析筛选" in shell_source
    assert "飞书同步状态" in shell_source
    assert "分析状态" in shell_source
    assert "核心产品/服务" in shell_source
    assert "内容类型" in shell_source
    assert "可复用模型" in shell_source
    assert "内容利用方式" in shell_source
    assert "搜索属性" in shell_source
    assert shell_source.count("renderMultiSelect({") >= 5
    assert shell_source.count('mode="multiple"') >= 1
    assert "controller.coreProductServiceFilter" in shell_source
    assert "controller.contentTypeFilter" in shell_source
    assert "controller.reusableModelFilter" in shell_source
    assert "controller.contentUsageFilter" in shell_source
    assert "controller.searchAttributeFilter" in shell_source
    assert "controller.setCoreProductServiceFilter" in shell_source
    assert "controller.setContentTypeFilter" in shell_source
    assert "controller.setReusableModelFilter" in shell_source
    assert "controller.setContentUsageFilter" in shell_source
    assert "controller.setSearchAttributeFilter" in shell_source
    assert "feishuPushStatusFilter" in types_source
    assert "feishu_push_status: feishuPushStatusFilter || undefined" in hook_source
    assert "canFilterFeishuAnalysis" in types_source
    assert "pushXhsNotesToFeishu" in adapter_source
    assert "pullXhsNotesFromFeishu" in adapter_source
    assert "同步到飞书" in adapter_source
    assert "从飞书回传" in adapter_source
    assert "回传全部分析结果" in adapter_source
    assert "系统分析结果" in adapter_source
    assert "analysis_result" in adapter_source
    assert "score" in adapter_source
    assert "rating" in adapter_source
    assert "评分" in adapter_source
    assert "评级" in adapter_source
    assert "封面类型" in adapter_source
    assert "标题类型" in adapter_source
    assert "笔记结构分析" in adapter_source
    assert "feishu_sync" in adapter_source


def test_content_library_filter_options_are_platform_adapter_owned():
    xhs_adapter_source = open("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts", encoding="utf-8").read()
    wechat_adapter_source = open("frontend/src/pages/wechat-official/wechat-official-content-library-adapter.tsx", encoding="utf-8").read()
    shell_source = open("frontend/src/components/content-library/content-library-shell.tsx", encoding="utf-8").read()
    hook_source = open("frontend/src/components/content-library/use-content-library.ts", encoding="utf-8").read()
    types_source = open("frontend/src/components/content-library/content-library-types.ts", encoding="utf-8").read()

    assert "loadFilterOptions" in types_source
    assert "adapter.loadFilterOptions" in hook_source
    assert "refreshFilterOptions" in hook_source
    assert "filterOptions" in hook_source
    assert "filterOptionsError" in hook_source
    assert "core_product_service: coreProductServiceFilter.length ? coreProductServiceFilter : undefined" in hook_source
    assert "content_type: contentTypeFilter.length ? contentTypeFilter : undefined" in hook_source
    assert "reusable_model: reusableModelFilter.length ? reusableModelFilter : undefined" in hook_source
    assert "content_usage: contentUsageFilter.length ? contentUsageFilter : undefined" in hook_source
    assert "search_attribute: searchAttributeFilter.length ? searchAttributeFilter : undefined" in hook_source
    assert "controller.filterOptions" in shell_source
    assert "controller.filterOptionsError" in shell_source
    assert "adapter.filterOptions" in shell_source
    assert "fetchSavedNoteFilterOptions" in xhs_adapter_source
    assert 'loadFilterOptions: () => fetchSavedNoteFilterOptions("xhs")' in xhs_adapter_source
    assert "场景种草模型" not in xhs_adapter_source
    assert "测评背书模型" not in xhs_adapter_source
    assert "问题驱动模型" not in xhs_adapter_source
    assert "fetchSavedNoteFilterOptions" not in wechat_adapter_source
    assert "loadFilterOptions" not in wechat_adapter_source
    assert "canFilterFeishuAnalysis: false" in wechat_adapter_source
    assert "核心产品/服务" in shell_source
    assert "搜索属性" in shell_source
    assert "观点评论" in wechat_adapter_source
    assert "案例拆解" in wechat_adapter_source
    assert "标题钩子" in wechat_adapter_source
    assert "转化路径" in wechat_adapter_source
    assert "认知升级模型" in wechat_adapter_source


def test_draft_workbench_labels_are_platform_adapter_owned():
    shell_source = open("frontend/src/components/draft-workbench/draft-workbench-shell.tsx", encoding="utf-8").read()
    types_source = open("frontend/src/components/draft-workbench/draft-workbench-types.ts", encoding="utf-8").read()
    xhs_adapter_source = open("frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts", encoding="utf-8").read()
    wechat_adapter_source = open("frontend/src/pages/wechat-official/wechat-official-draft-workbench-adapter.ts", encoding="utf-8").read()
    wechat_workbench_source = open("frontend/src/pages/wechat-official/wechat-official-draft-workbench.tsx", encoding="utf-8").read()
    types_app_source = open("frontend/src/types/index.ts", encoding="utf-8").read()

    assert "editorLabels" in types_source
    assert "adapter.editorLabels" in shell_source
    assert "输入小红书发布标题" not in shell_source
    assert "输入小红书发布标题" in xhs_adapter_source
    assert "公众号标题" in wechat_adapter_source
    assert "公众号正文" in wechat_adapter_source
    assert "来源文章" in wechat_workbench_source
    assert "分析依据" in wechat_workbench_source
    assert "source_article_id?: number | null" in types_app_source
    assert "source_article_id" in wechat_workbench_source


def test_crawler_page_groups_sources_by_huitun_and_xhs_tabs():
    source = open("frontend/src/pages/platforms/xhs/crawler-page.tsx", encoding="utf-8").read()

    assert "热词候选获取" in source
    assert "小红书站内采集" in source
    assert "用于发现热词和候选关键词" in source
    assert "灰豚" not in source
    assert "不直接进入内容库" in source
    assert "按关键词组采集" in source
    assert "临时关键词搜索" in source
    assert "Tabs" in source


def test_discovery_uses_antd_components_and_preserves_core_logic():
    source = open("frontend/src/pages/platforms/xhs/discovery-page.tsx", encoding="utf-8").read()

    assert "antd" in source
    assert "async function ensureNoteDetail" in source or "ensureNoteDetail" in source
    assert "保存" in source
    assert "评论" in source
    assert "原文" in source


def test_discovery_preserves_note_detail_and_media_logic():
    source = open("frontend/src/pages/platforms/xhs/discovery-page.tsx", encoding="utf-8").read()

    assert "function getNoteVideoUrl" in source
    assert "function getNoteKindLabel" in source
    assert "detailMediaIndex" in source
    assert "视频" in source
    assert "图文" in source


def test_library_page_preserves_delete_and_media_logic():
    page_source = open("frontend/src/pages/platforms/xhs/library-page.tsx", encoding="utf-8").read()
    adapter_source = open("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts", encoding="utf-8").read()
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()

    assert "deleteSavedNote" in api_source
    assert "ContentLibraryShell" in page_source
    assert "createXhsContentLibraryAdapter" in page_source
    assert "deleteSavedNote" in adapter_source
    assert "删除" in adapter_source
    assert "function getSavedNoteCoverUrl" in adapter_source
    assert "function getSavedNoteMediaType" in adapter_source
    assert "note.media_type" in adapter_source
    assert "note.video_url" in adapter_source
    assert 'referrerPolicy: "no-referrer"' in adapter_source


def test_platform_navigation_is_registry_owned():
    app_shell_source = open("frontend/src/components/layout/app-shell.tsx", encoding="utf-8").read()
    registry_path = "frontend/src/platform-core/registry/platform-sections.tsx"

    assert os.path.exists(registry_path)
    registry_source = open(registry_path, encoding="utf-8").read()

    assert "getPlatformNavItems" in app_shell_source
    assert "getPlatformIdFromPath" in app_shell_source
    assert 'startsWith("/platforms/wechat-official")' not in app_shell_source
    assert "platformSectionRegistry" in registry_source
    assert '"xhs"' in registry_source
    assert '"wechat-official"' in registry_source
    assert '"/platforms/xhs/dashboard"' in registry_source
    assert '"/platforms/wechat-official/dashboard"' in registry_source
    assert "公众号草稿工坊" in registry_source


def test_platform_accounts_shell_is_shared():
    accounts_shell_path = "frontend/src/platform-core/accounts/platform-accounts-shell.tsx"
    account_types_path = "frontend/src/platform-core/accounts/platform-account-types.ts"

    assert os.path.exists(accounts_shell_path)
    assert os.path.exists(account_types_path)
    accounts_shell_source = open(accounts_shell_path, encoding="utf-8").read()
    account_types_source = open(account_types_path, encoding="utf-8").read()

    assert "PlatformAccountsShell" in accounts_shell_source
    assert "PlatformAccount" in account_types_source
    assert "PlatformAccountsShell" in account_types_source
    assert "xhs" not in accounts_shell_source.lower()
    assert "wechat" not in accounts_shell_source.lower()
    assert "Redfox" not in accounts_shell_source
    assert "sendall" not in accounts_shell_source.lower()
    assert "uploadWechatMaterial" not in accounts_shell_source


def test_xhs_accounts_page_uses_platform_accounts_shell_without_losing_login_actions():
    accounts_shell_path = "frontend/src/platform-core/accounts/platform-accounts-shell.tsx"
    xhs_accounts_source = open("frontend/src/pages/platforms/xhs/accounts-page.tsx", encoding="utf-8").read()

    assert os.path.exists(accounts_shell_path)
    accounts_shell_source = open(accounts_shell_path, encoding="utf-8").read()

    assert "PlatformAccountsShell" in xhs_accounts_source
    assert "fetchAccounts" in xhs_accounts_source
    assert "checkAccount" in xhs_accounts_source
    assert "deleteAccount" in xhs_accounts_source
    assert "AddAccountDrawer" in xhs_accounts_source
    assert "defaultAccountType" in xhs_accounts_source
    assert "login" not in accounts_shell_source.lower()
    assert "QR" not in accounts_shell_source
    assert "qr" not in accounts_shell_source.lower()
    assert "AddAccountDrawer" not in accounts_shell_source


def test_wechat_official_accounts_page_uses_platform_accounts_shell_and_preserves_blocks():
    wechat_accounts_source = open("frontend/src/pages/wechat-official/wechat-official-accounts-page.tsx", encoding="utf-8").read()

    assert "PlatformAccountsShell" in wechat_accounts_source
    assert "fetchWechatOfficialRedfoxConfig" in wechat_accounts_source
    assert "Redfox 数据源" in wechat_accounts_source
    assert "真实公众号授权仍保持阻断" in wechat_accounts_source
    assert "素材上传" in wechat_accounts_source
    assert "预览发送" in wechat_accounts_source
    assert "群发发布" in wechat_accounts_source
    assert "uploadWechatMaterial" not in wechat_accounts_source
    assert "uploadPublishAsset" not in wechat_accounts_source
    assert "sendall(" not in wechat_accounts_source.lower()
    assert "sendToPublish" not in wechat_accounts_source


def test_wechat_official_routes_use_dedicated_pages():
    router_source = open("frontend/src/app/router.tsx", encoding="utf-8").read()

    assert "WechatOfficialDashboardPage" in router_source
    assert "WechatOfficialAccountsPage" in router_source
    assert "WechatOfficialDiscoveryPage" in router_source
    assert "WechatOfficialLibraryPage" in router_source
    assert "WechatOfficialDraftsPage" in router_source
    assert "WechatOfficialSettingsPage" in router_source
    assert 'path="/platforms/wechat-official/dashboard" element={<WechatOfficialDashboardPage />}' in router_source
    assert 'path="/platforms/wechat-official/accounts" element={<WechatOfficialAccountsPage />}' in router_source
    assert 'path="/platforms/wechat-official/discovery" element={<WechatOfficialDiscoveryPage />}' in router_source
    assert 'path="/platforms/wechat-official/library" element={<WechatOfficialLibraryPage />}' in router_source
    assert 'path="/platforms/wechat-official/drafts" element={<WechatOfficialDraftsPage />}' in router_source
    assert 'path="/platforms/wechat-official/settings" element={<AdminRoute><WechatOfficialSettingsPage /></AdminRoute>}' in router_source
    assert "element={<WechatOfficialDashboard />}" not in router_source


def test_wechat_official_dashboard_no_longer_routes_sections_internally():
    dashboard_source = open("frontend/src/pages/wechat-official/wechat-official-dashboard.tsx", encoding="utf-8").read()
    readiness_panel_source = open("frontend/src/platform-core/readiness/platform-readiness-panel.tsx", encoding="utf-8").read()
    action_hub_source = open("frontend/src/platform-core/actions/platform-action-hub.tsx", encoding="utf-8").read()

    assert "sectionFromPath" not in dashboard_source
    assert "showAccounts" not in dashboard_source
    assert "showDiscovery" not in dashboard_source
    assert "showLibrary" not in dashboard_source
    assert "showDrafts" not in dashboard_source
    assert "showSettings" not in dashboard_source
    assert "WechatOfficialDiscoveryPanel" not in dashboard_source
    assert "WechatOfficialContentLibraryPanel" not in dashboard_source
    assert "WechatOfficialDraftWorkbench" not in dashboard_source
    assert "PlatformReadinessPanel" in dashboard_source
    assert "Readiness / Diagnostics" in readiness_panel_source
    assert "推荐下一步" in action_hub_source


def test_wechat_official_platform_split_preserves_safety_boundary():
    page_paths = [
        "frontend/src/pages/wechat-official/wechat-official-dashboard.tsx",
        "frontend/src/pages/wechat-official/wechat-official-accounts-page.tsx",
        "frontend/src/pages/wechat-official/wechat-official-discovery-page.tsx",
        "frontend/src/pages/wechat-official/wechat-official-library-page.tsx",
        "frontend/src/pages/wechat-official/wechat-official-drafts-page.tsx",
        "frontend/src/pages/wechat-official/wechat-official-settings-page.tsx",
    ]

    for path in page_paths:
        assert os.path.exists(path)
    sources = "\n".join(open(path, encoding="utf-8").read() for path in page_paths)

    assert "PlatformSectionPage" in sources
    assert "发布/群发 blocked" in sources or "真实公众号授权仍保持阻断" in sources
    assert "uploadWechatMaterial" not in sources
    assert "uploadPublishAsset" not in sources
    assert "sendToPublish" not in sources
    assert "PublishJob" not in sources
    assert "sendall(" not in sources.lower()


def test_platform_action_hub_is_shared():
    action_hub_path = "frontend/src/platform-core/actions/platform-action-hub.tsx"
    action_types_path = "frontend/src/platform-core/actions/platform-action-types.ts"
    dashboard_source = open("frontend/src/pages/wechat-official/wechat-official-dashboard.tsx", encoding="utf-8").read()

    assert os.path.exists(action_hub_path)
    assert os.path.exists(action_types_path)
    action_hub_source = open(action_hub_path, encoding="utf-8").read()
    action_types_source = open(action_types_path, encoding="utf-8").read()

    assert "PlatformActionHub" in action_hub_source
    assert "PlatformAction" in action_types_source
    assert "推荐下一步" in action_hub_source
    assert "type ReadinessAction" not in dashboard_source
    assert "readinessActions.map" not in dashboard_source


def test_platform_readiness_panel_is_shared():
    readiness_panel_path = "frontend/src/platform-core/readiness/platform-readiness-panel.tsx"
    dashboard_source = open("frontend/src/pages/wechat-official/wechat-official-dashboard.tsx", encoding="utf-8").read()

    assert os.path.exists(readiness_panel_path)
    readiness_panel_source = open(readiness_panel_path, encoding="utf-8").read()

    assert "PlatformReadinessPanel" in readiness_panel_source
    assert "Readiness / Diagnostics" in readiness_panel_source
    assert "PlatformActionHub" in readiness_panel_source
    assert "blockedTags" in readiness_panel_source
    assert "checks.map" in readiness_panel_source
    assert "PlatformReadinessPanel" in dashboard_source


def test_wechat_official_readiness_actions_are_adapter_owned():
    actions_path = "frontend/src/pages/wechat-official/wechat-official-readiness-actions.ts"
    dashboard_source = open("frontend/src/pages/wechat-official/wechat-official-dashboard.tsx", encoding="utf-8").read()

    assert os.path.exists(actions_path)
    actions_source = open(actions_path, encoding="utf-8").read()

    assert "buildWechatOfficialReadinessActions" in actions_source
    assert "PlatformAction" in actions_source
    assert '"/platforms/wechat-official/settings"' in actions_source
    assert '"/platforms/wechat-official/discovery"' in actions_source
    assert '"/platforms/wechat-official/library"' in actions_source
    assert '"/platforms/wechat-official/drafts"' in actions_source
    assert "buildWechatOfficialReadinessActions" in dashboard_source
    assert "function buildReadinessActions" not in dashboard_source


def test_wechat_official_library_reuses_content_library_shell_without_publish_actions():
    library_page_source = open("frontend/src/pages/wechat-official/wechat-official-library-page.tsx", encoding="utf-8").read()
    panel_source = open("frontend/src/pages/wechat-official/wechat-official-content-library-panel.tsx", encoding="utf-8").read()
    adapter_source = open("frontend/src/pages/wechat-official/wechat-official-content-library-adapter.tsx", encoding="utf-8").read()
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    shell_source = open("frontend/src/components/content-library/content-library-shell.tsx", encoding="utf-8").read()
    controller_source = open("frontend/src/components/content-library/use-content-library.ts", encoding="utf-8").read()

    assert "WechatOfficialContentLibraryPanel" in library_page_source
    assert "ContentLibraryShell" in panel_source
    assert "useContentLibrary" in panel_source
    assert "createWechatOfficialContentLibraryAdapter" in panel_source
    assert "createWechatOfficialContentLibraryAdapter" in adapter_source
    assert "fetchWechatOfficialContentLibrary" in adapter_source
    assert "fetchWechatOfficialContentDetail" in adapter_source
    assert "deleteWechatOfficialContentLibraryItem" in adapter_source
    assert "refreshWechatOfficialContentDetail" in adapter_source
    assert "analyzeWechatOfficialHotspots" in adapter_source
    assert "createWechatOfficialDraft" in adapter_source
    assert "createDraftFromItem" in adapter_source
    assert "WECHAT_DRAFT_TEMPLATES" in panel_source
    assert "renderToolbarExtras" in shell_source
    assert "refreshSelectedItem" in controller_source
    assert "refreshSelectedItem" in adapter_source
    assert "pushWechatOfficialArticlesToFeishu" in adapter_source
    assert "pullWechatOfficialArticlesFromFeishu" in adapter_source
    assert "推送飞书分析" in adapter_source
    assert "回拉飞书标注" in adapter_source
    assert "createDraftFromNote" not in adapter_source
    assert "fetchDrafts" not in adapter_source
    assert "sendToPublish" not in adapter_source
    assert "publishJobToCreator" not in adapter_source
    assert "uploadPublishAsset" not in adapter_source
    assert "sendall" not in adapter_source.lower()
    assert "canFilterAssets: false" in adapter_source
    assert "canFilterComments: false" in adapter_source
    assert "pool_status?: string" in api_source
    assert "adapter.capabilities.canTag" in shell_source
    assert "adapter.capabilities.canFilterAssets" in shell_source
    assert "adapter.capabilities.canFilterComments" in shell_source
    assert "wechat" not in shell_source.lower()
    assert "Redfox" not in shell_source
    assert "hotspot" not in shell_source.lower()
    assert "preview send" not in adapter_source.lower()
    assert "sendPreview" not in adapter_source
    assert "previewWechat" not in adapter_source
    assert "PublishJob" not in adapter_source
    assert '"/publish/jobs' not in adapter_source
    assert '"/publish/assets' not in adapter_source


def test_wechat_official_discovery_is_candidate_only_and_delegates_operations_to_library():
    discovery_page_source = open("frontend/src/pages/wechat-official/wechat-official-discovery-page.tsx", encoding="utf-8").read()
    discovery_source = open("frontend/src/pages/wechat-official/wechat-official-discovery-panel.tsx", encoding="utf-8").read()
    library_adapter_source = open("frontend/src/pages/wechat-official/wechat-official-content-library-adapter.tsx", encoding="utf-8").read()

    assert "WechatOfficialDiscoveryPanel" in discovery_page_source
    assert "PlatformSectionPage" in discovery_page_source
    assert "collectWechatOfficialRedfoxArticles" in discovery_source
    assert "collectWechatOfficialRedfoxAccount" in discovery_source
    assert "importWechatOfficialArticleUrl" in discovery_source
    assert "updateWechatOfficialRecommendation" in discovery_source
    assert "deleteWechatOfficialContentLibraryItem" in discovery_source
    assert "去内容库" in discovery_source
    assert "补全正文" not in discovery_source
    assert "refreshWechatOfficialContentDetail" not in discovery_source
    assert "analyzeWechatOfficialHotspots" not in discovery_source
    assert "createWechatOfficialDraft" not in discovery_source
    assert "dryRunWechatOfficialDraft" not in discovery_source
    assert "PublishJob" not in discovery_source
    assert "sendall" not in discovery_source.lower()
    assert "sendToPublish" not in discovery_source
    assert "uploadPublishAsset" not in discovery_source
    assert "refreshWechatOfficialContentDetail" in library_adapter_source
    assert "analyzeWechatOfficialHotspots" in library_adapter_source
    assert "createWechatOfficialDraft" in library_adapter_source


def test_wechat_official_image_studio_reuses_generic_draft_context_without_material_upload():
    generic_context_source = open("frontend/src/components/image-studio/draft-image-studio-context.ts", encoding="utf-8").read()
    xhs_context_source = open("frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts", encoding="utf-8").read()
    wechat_context_source = open("frontend/src/pages/wechat-official/wechat-official-image-studio-context.ts", encoding="utf-8").read()
    wechat_workbench_source = open("frontend/src/pages/wechat-official/wechat-official-draft-workbench.tsx", encoding="utf-8").read()
    image_studio_source = open("frontend/src/pages/platforms/xhs/image-studio-page.tsx", encoding="utf-8").read()
    router_source = open("frontend/src/app/router.tsx", encoding="utf-8").read()

    assert "DraftImageStudioDraftContext" in generic_context_source
    assert "platform" in generic_context_source
    assert "source_article_id" in generic_context_source
    assert "candidate_images" in generic_context_source
    assert "requireFresh" in generic_context_source
    assert "DRAFT_IMAGE_STUDIO_CONTEXT_TTL_MS" in generic_context_source

    assert "saveDraftImageStudioContext" in xhs_context_source
    assert "loadDraftImageStudioContext" in xhs_context_source
    assert 'platform: "xhs"' in xhs_context_source
    assert "XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY" in xhs_context_source

    assert "WECHAT_OFFICIAL_IMAGE_STUDIO_DRAFT_CONTEXT_KEY" in wechat_context_source
    assert 'platform: "wechat_official"' in wechat_context_source
    assert "article_cover" in wechat_context_source
    assert "snapshot_image" in wechat_context_source

    assert "saveWechatOfficialImageStudioDraftContext" in wechat_workbench_source
    assert "extractWechatOfficialDraftImageCandidates" in wechat_workbench_source
    assert "整理封面/正文图" in wechat_workbench_source or "图片工坊" in wechat_workbench_source
    assert '"/platforms/wechat-official/image-studio?from=draft"' in wechat_workbench_source
    assert 'path="/platforms/wechat-official/image-studio"' in router_source
    assert "loadWechatOfficialImageStudioDraftContext" in image_studio_source
    assert "material_upload_blocked" in image_studio_source
    assert "addDraftAsset" in image_studio_source
    assert "回挂到公众号草稿" in image_studio_source
    assert "已挂到草稿本地资产" in image_studio_source
    assert "本地图片资产" in wechat_workbench_source

    forbidden_sources = "\n".join([wechat_context_source, wechat_workbench_source, image_studio_source])
    assert "uploadWechatMaterial" not in forbidden_sources
    assert "uploadPublishAsset" not in forbidden_sources
    assert "sendall(" not in forbidden_sources.lower()
    assert "PublishJob" not in forbidden_sources


def test_wechat_official_readiness_dashboard_contract():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()
    dashboard_source = open("frontend/src/pages/wechat-official/wechat-official-dashboard.tsx", encoding="utf-8").read()
    readiness_panel_source = open("frontend/src/platform-core/readiness/platform-readiness-panel.tsx", encoding="utf-8").read()
    action_hub_source = open("frontend/src/platform-core/actions/platform-action-hub.tsx", encoding="utf-8").read()
    actions_source = open("frontend/src/pages/wechat-official/wechat-official-readiness-actions.ts", encoding="utf-8").read()
    combined_source = "\n".join([dashboard_source, readiness_panel_source, action_hub_source, actions_source])

    assert "fetchWechatOfficialReadiness" in api_source
    assert '"/wechat-official/readiness"' in api_source
    assert "WechatOfficialReadiness" in types_source
    assert "WechatOfficialReadinessCheck" in types_source
    assert "PlatformReadinessPanel" in dashboard_source
    assert "Readiness / Diagnostics" in readiness_panel_source
    assert "推荐下一步" in action_hub_source
    assert "readinessActions" in dashboard_source
    assert "后端服务版本可能未重启" in combined_source
    assert '"/platforms/wechat-official/settings"' in actions_source
    assert '"/platforms/wechat-official/discovery"' in actions_source
    assert '"/platforms/wechat-official/library"' in actions_source
    assert '"/platforms/wechat-official/drafts"' in actions_source
    assert "nextActions" in readiness_panel_source
    assert "material upload blocked" in combined_source
    assert "preview blocked" in combined_source
    assert "sendall blocked" in combined_source
    assert "fetchWechatOfficialReadiness" in dashboard_source
    assert "uploadWechatMaterial" not in combined_source
    assert "uploadPublishAsset" not in combined_source
    assert "sendToPublish" not in combined_source
    assert "PublishJob" not in combined_source


def test_wechat_official_redfox_collect_jobs_frontend_contract():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()
    discovery_source = open("frontend/src/pages/wechat-official/wechat-official-discovery-panel.tsx", encoding="utf-8").read()

    assert "fetchWechatOfficialRedfoxCollectJobs" in api_source
    assert '"/wechat-official/redfox/collect/jobs"' in api_source
    assert "fetchWechatOfficialRedfoxCollectJob" in api_source
    assert "`/wechat-official/redfox/collect/jobs/${jobId}`" in api_source
    assert "job_id?: number" in api_source

    assert "export type WechatOfficialRedfoxCollectJobListResponse" in types_source
    assert "export type WechatOfficialRedfoxCollectJobDetail" in types_source
    assert "FeishuPushWechatOfficialArticlesPayload" in types_source
    assert "FeishuPullWechatOfficialArticlesPayload" in types_source
    assert "params?: Record<string, unknown>" in types_source
    assert "started_at?: string | null" in types_source
    assert "finished_at?: string | null" in types_source

    assert "采集记录" in discovery_source
    assert "selectedJobId" in discovery_source
    assert "setSelectedJobId" in discovery_source
    assert "fetchWechatOfficialRedfoxCollectJobs" in discovery_source
    assert "job_id: effectiveJobId ?? undefined" in discovery_source
    assert "查看全部候选" in discovery_source or "清除批次" in discovery_source
    assert "批次 #" in discovery_source

    assert "PublishJob" not in discovery_source
    assert "sendall" not in discovery_source.lower()
    assert "sendToPublish" not in discovery_source
    assert "uploadPublishAsset" not in discovery_source
    assert "refreshWechatOfficialContentDetail" not in discovery_source
    assert "analyzeWechatOfficialHotspots" not in discovery_source
    assert "createWechatOfficialDraft" not in discovery_source


def test_discovery_cards_show_note_media_type():
    source = open("frontend/src/pages/platforms/xhs/discovery-page.tsx", encoding="utf-8").read()

    assert "function getNoteKindLabel" in source
    assert "视频" in source
    assert "图文" in source


def test_rewrite_page_preserves_mode_switch():
    source = open("frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx", encoding="utf-8").read()

    assert "handleRewrite" in source
    assert "handleGenerateTitles" in source
    assert "handleGenerateTags" in source
    assert "改写" in source
    assert "生成" in source
    assert "antd" in source


def test_publish_page_uses_antd_components():
    source = open("frontend/src/pages/platforms/xhs/publish-page.tsx", encoding="utf-8").read()

    assert "antd" in source
    assert "发布" in source


def test_openai_compatible_text_client_decodes_utf8_json_when_response_headers_are_wrong(monkeypatch):
    from backend.app.services.ai_service import OpenAICompatibleTextClient

    class DummyConfig:
        base_url = "https://api.example.test/v1"
        model_name = "gpt-5.4"

    class FakeResponse:
        def __init__(self):
            self.content = (
                b'{"choices":[{"message":{"content":"'
                + "你好，今天很适合去公园散步。".encode("utf-8")
                + b'"}}]}'
            )
            self.encoding = "ISO-8859-1"
            self.apparent_encoding = "utf-8"
            self.headers = {"content-type": "text/event-stream"}

        def raise_for_status(self):
            return None

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("backend.app.services.ai_service.requests.post", fake_post)

    client = OpenAICompatibleTextClient()
    result = client.rewrite_note(
        model_config=DummyConfig(),
        api_key="test-key",
        title="原文标题",
        body="今天天气很好，我们去公园散步。",
        instruction="保留中文自然表达",
    )

    assert result == "你好，今天很适合去公园散步。"


def test_database_initialization_creates_user_table(tmp_path):
    from alembic import command
    from alembic.config import Config

    db_url = f"sqlite:///{tmp_path / 'init-test.db'}"
    cfg = Config(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "alembic.ini")))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    table_names = inspect(test_engine).get_table_names()
    assert "users" in table_names
    assert "platform_accounts" in table_names
    assert "alembic_version" in table_names


def test_alembic_initial_migration_creates_all_product_tables(tmp_path):
    from alembic import command
    from alembic.config import Config

    db_url = f"sqlite:///{tmp_path / 'alembic-tables-test.db'}"
    cfg = Config(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "alembic.ini")))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    table_names = set(inspect(test_engine).get_table_names())
    expected = {
        "users", "platform_accounts", "account_cookie_versions", "login_sessions",
        "notes", "note_assets", "note_comments", "tags", "note_tags",
        "model_configs", "ai_drafts", "ai_generated_assets",
        "publish_jobs", "publish_assets", "tasks",
        "monitoring_targets", "monitoring_snapshots",
        "keyword_groups", "api_logs",
        "keyword_discovery_runs", "keyword_discovery_items", "crawl_diagnostics",
    }
    assert expected.issubset(table_names)


def test_alembic_adds_keyword_discovery_and_crawl_diagnostic_columns(tmp_path):
    from alembic import command
    from alembic.config import Config

    db_url = f"sqlite:///{tmp_path / 'legacy-integration-tables-test.db'}"
    cfg = Config(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "alembic.ini")))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    inspector = inspect(test_engine)
    run_columns = {column["name"] for column in inspector.get_columns("keyword_discovery_runs")}
    item_columns = {column["name"] for column in inspector.get_columns("keyword_discovery_items")}
    diagnostic_columns = {column["name"] for column in inspector.get_columns("crawl_diagnostics")}

    assert {
        "user_id", "platform", "source", "seed_keywords", "limit_per_seed",
        "source_mode", "status", "error_message", "created_at", "finished_at",
    }.issubset(run_columns)
    assert {
        "run_id", "user_id", "source_keyword", "keyword", "hot_value_number",
        "note_count", "interaction_number", "categories", "selected", "imported_group_id", "raw_json",
    }.issubset(item_columns)
    assert {
        "user_id", "task_id", "platform_account_id", "platform", "source", "note_id",
        "note_url", "stage", "kind", "severity", "recoverable", "message", "user_message", "raw_json",
    }.issubset(diagnostic_columns)

    diagnostic_indexes = {index["name"] for index in inspector.get_indexes("crawl_diagnostics")}
    assert "ix_crawl_diagnostics_task_id" in diagnostic_indexes
    assert "ix_crawl_diagnostics_user_id" in diagnostic_indexes


def test_database_initialization_normalizes_legacy_gpt_54_model_name(tmp_path):
    from backend.app.core.database import _normalize_model_config_names

    engine = create_engine(f"sqlite:///{tmp_path / 'model-name-migration-test.db'}", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE model_configs (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    model_type VARCHAR(32) NOT NULL,
                    provider VARCHAR(64) NOT NULL,
                    model_name VARCHAR(128) NOT NULL,
                    base_url TEXT NOT NULL,
                    encrypted_api_key TEXT NOT NULL,
                    is_default BOOLEAN NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO model_configs "
                "(id, user_id, name, model_type, provider, model_name, base_url, encrypted_api_key, is_default) "
                "VALUES (1, 1, 'Text model', 'text', 'openai-compatible', 'gpt5.4', 'https://api.example.test/v1', '', 1)"
            )
        )

    _normalize_model_config_names(engine)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT model_name FROM model_configs WHERE id = 1")).mappings().one()
        assert row["model_name"] == "gpt-5.4"
        assert connection.execute(
            text("SELECT name FROM app_migrations WHERE name = 'normalize_legacy_gpt_54_model_name_v1'")
        ).first()


def test_database_initialization_normalizes_existing_sqlite_times_to_shanghai(tmp_path):
    from backend.app.core.database import _normalize_sqlite_datetime_storage

    engine = create_engine(f"sqlite:///{tmp_path / 'time-migration-test.db'}", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE platform_accounts (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    platform VARCHAR(32) NOT NULL,
                    sub_type VARCHAR(32),
                    external_user_id VARCHAR(128) NOT NULL,
                    nickname VARCHAR(128) NOT NULL,
                    avatar_url TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    status_message TEXT NOT NULL DEFAULT '',
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO platform_accounts "
                "(id, user_id, platform, sub_type, external_user_id, nickname, avatar_url, status, created_at, updated_at) "
                "VALUES (1, 1, 'xhs', 'pc', 'pc-1', 'cat', '', 'active', '2026-04-30 07:50:43', '2026-04-30 07:50:43')"
            )
        )

    _normalize_sqlite_datetime_storage(engine)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT created_at, updated_at FROM platform_accounts WHERE id = 1")
        ).mappings().one()
        assert str(row["created_at"]).startswith("2026-04-30 15:50:43")
        assert str(row["updated_at"]).startswith("2026-04-30 15:50:43")
        assert connection.execute(
            text("SELECT name FROM app_migrations WHERE name = 'sqlite_datetime_asia_shanghai_v1'")
        ).first()


def _parse_sse_response(response):
    import json as _json
    events = []
    done = {}
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            event = _json.loads(line[6:])
            if event.get("type") == "item":
                events.append(event["item"])
            elif event.get("type") == "done":
                done = event
    return {"items": events, **done}


def _assert_no_private_payload_keys(value):
    if isinstance(value, dict):
        assert "raw" not in value
        assert "raw_json" not in value
        for item in value.values():
            _assert_no_private_payload_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_private_payload_keys(item)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'auth-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    override_get_db.sessionmaker = TestingSessionLocal
    app.dependency_overrides[get_db] = override_get_db
    return get_db


def test_auth_register_login_me_and_refresh_use_real_tokens(tmp_path):
    get_db = _override_database(tmp_path)
    try:
        register_response = client.post(
            "/api/auth/register",
            json={"username": "operator", "password": "secret123", "invite_code": create_test_invite_code()},
        )
        assert register_response.status_code == 200
        registered = register_response.json()
        assert registered["token_type"] == "bearer"
        assert registered["access_token"]
        assert registered["refresh_token"]
        assert registered["user"]["username"] == "operator"

        me_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["username"] == "operator"

        login_response = client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "secret123"},
        )
        assert login_response.status_code == 200
        logged_in = login_response.json()
        assert logged_in["access_token"]
        assert logged_in["refresh_token"]

        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": logged_in["refresh_token"]},
        )
        assert refresh_response.status_code == 200
        refreshed = refresh_response.json()
        assert refreshed["token_type"] == "bearer"
        assert refreshed["access_token"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_auth_rejects_duplicate_user_and_bad_credentials(tmp_path):
    get_db = _override_database(tmp_path)
    try:
        response = client.post(
            "/api/auth/register",
            json={"username": "operator", "password": "secret123", "invite_code": create_test_invite_code()},
        )
        assert response.status_code == 200

        duplicate_response = client.post(
            "/api/auth/register",
            json={"username": "operator", "password": "different123", "invite_code": create_test_invite_code()},
        )
        assert duplicate_response.status_code == 400

        bad_login_response = client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "wrong-password"},
        )
        assert bad_login_response.status_code == 401

        missing_auth_response = client.get("/api/auth/me")
        assert missing_auth_response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


class FakePcLoginAdapter:
    def create_qrcode(self):
        return {
            "cookies": {"a1": "temp-a1"},
            "qr_id": "qr-123",
            "code": "code-123",
            "qr_url": "https://example.test/qr",
        }

    def check_qrcode_status(self, qr_id, code, cookies):
        assert qr_id == "qr-123"
        assert code == "code-123"
        assert cookies == {"a1": "temp-a1"}
        return {"status": "confirmed", "cookies": {"a1": "final-a1", "web_session": "session-123"}}

    def get_user_info(self, cookies):
        assert cookies["web_session"] == "session-123"
        return {
            "external_user_id": "xhs-user-1",
            "nickname": "cat",
            "avatar_url": "https://example.test/avatar.webp",
        }


class FakeCreatorLoginAdapter:
    def create_qrcode(self):
        return {
            "cookies": {"a1": "creator-temp-a1"},
            "qr_id": "creator-qr-123",
            "qr_url": "https://example.test/creator-qr",
        }

    def check_qrcode_status(self, qr_id, cookies):
        assert qr_id == "creator-qr-123"
        assert cookies == {"a1": "creator-temp-a1"}
        return {"status": "confirmed", "cookies": {"a1": "creator-final-a1", "customer_session": "session-456"}}

    def get_user_info(self, cookies):
        assert cookies["customer_session"] == "session-456"
        return {
            "external_user_id": "creator-user-1",
            "nickname": "creator-cat",
            "avatar_url": "https://example.test/creator-avatar.webp",
        }

    def exchange_from_user_cookies(self, user_cookies):
        assert user_cookies["a1"] in {"final-a1", "phone-final-a1", "cookie-a1"}
        return {"status": "confirmed", "cookies": {"a1": user_cookies["a1"], "customer_session": "session-456"}}


class FailingCreatorExchangeAdapter(FakeCreatorLoginAdapter):
    def exchange_from_user_cookies(self, user_cookies):
        raise RuntimeError("creator exchange failed")


class FailingPcUserInfoAdapter(FakePcLoginAdapter):
    def get_user_info(self, cookies):
        raise RuntimeError("user info endpoint failed")


class FailingPcProfilesWithQrIdentityAdapter(FailingPcUserInfoAdapter):
    def check_qrcode_status(self, qr_id, code, cookies):
        result = super().check_qrcode_status(qr_id, code, cookies)
        result["user_info"] = {"external_user_id": "qr-identity-user-1"}
        return result


class MissingSessionPcQrAdapter(FakePcLoginAdapter):
    def check_qrcode_status(self, qr_id, code, cookies):
        assert qr_id == "qr-123"
        assert code == "code-123"
        return {
            "status": "scanned",
            "cookies": {"a1": "final-a1"},
            "user_info": {"external_user_id": "qr-identity-user-1"},
        }


class TransientPcPollingAdapter(FakePcLoginAdapter):
    def __init__(self):
        self.poll_count = 0

    def check_qrcode_status(self, qr_id, code, cookies):
        assert qr_id == "qr-123"
        assert code == "code-123"
        assert cookies == {"a1": "temp-a1"}
        self.poll_count += 1
        if self.poll_count == 1:
            return {"status": "scanned", "cookies": cookies}
        if self.poll_count == 2:
            raise requests.exceptions.JSONDecodeError(
                "Expecting value",
                "The origin web server returned an invalid or incomplete response to Cloudflare.",
                0,
            )
        return {"status": "confirmed", "cookies": {"a1": "final-a1", "web_session": "session-123"}}


class FakePcSelfProfileAdapter:
    def __init__(self, cookies):
        assert cookies == "a1=final-a1; web_session=session-123"

    def get_self_info(self):
        return {
            "data": {
                "basic_info": {
                    "user_id": "self-profile-user-1",
                    "nickname": "self-profile-cat",
                    "images": "https://example.test/self-profile-avatar.webp",
                    "red_id": "self-red-1",
                    "desc": "self profile bio",
                },
                "interactions": [
                    {"type": "fans", "count": 12},
                    {"type": "follows", "count": 3},
                    {"type": "interaction", "count": 45},
                ],
            }
        }


class FailingPcSelfProfileAdapter:
    def __init__(self, cookies):
        assert cookies == "a1=final-a1; web_session=session-123"

    def get_self_info(self):
        raise RuntimeError("self profile endpoint failed")


class FailingQrLoginAdapter:
    def create_qrcode(self):
        raise RuntimeError("proxy refused while creating qrcode")


class FakeHuitunLiveKeywordClient:
    def fetch_huitun_hotwords(self, cookie_text, seed_keyword, limit):
        assert cookie_text == '{"xhsapiToken":"keyword-token"}'
        assert seed_keyword == "低卡早餐"
        assert limit == 20
        return [
            {
                "source_keyword": "低卡早餐",
                "keyword": "低卡早餐食谱",
                "hot_value_text": "12.3w",
                "hot_value_number": 123000,
                "note_count": 456,
                "interaction_text": "3.2w",
                "interaction_number": 32000,
                "categories": [{"label": "美食", "rate": "80"}],
                "rank_index": 1,
            },
            {
                "source_keyword": "低卡早餐",
                "keyword": "低卡早餐搭配",
                "hot_value_text": "8.1w",
                "hot_value_number": 81000,
                "note_count": 220,
                "interaction_text": "1.9w",
                "interaction_number": 19000,
                "categories": [{"label": "生活", "rate": "60"}],
                "rank_index": 2,
            },
        ]


class FakeHuitunAccountClient:
    def create_huitun_qrcode(self):
        return {
            "ticket": "huitun-ticket-123",
            "qr_url": "http://weixin.qq.com/q/huitun-ticket-123",
            "qr_image_data_url": "data:image/png;base64,ZmFrZS1oaXV0dW4tcXI=",
            "state": {"ticket": "huitun-ticket-123", "cookies": {"xhsapiToken": "temp-token"}},
        }

    def check_huitun_qrcode_status(self, state):
        assert state["ticket"] == "huitun-ticket-123"
        assert state["cookies"] == {"xhsapiToken": "temp-token"}
        return {
            "status": "confirmed",
            "cookies_text": '{"xhsapiToken":"final-token"}',
            "user_info": {
                "external_user_id": "huitun-user-1",
                "nickname": "灰豚运营号",
                "avatar_url": "https://example.test/huitun-avatar.webp",
                "profile": {"source": "huitun", "raw": {"userId": "huitun-user-1"}},
            },
        }

    def login_huitun_with_password(self, mobile, password, ticket, rand_str, captcha=None, initial_cookies_text=None):
        assert mobile == "13800138000"
        assert password == "company-pass-123"
        assert ticket == "captcha-ticket"
        assert rand_str == "captcha-rand"
        assert captcha in {None, "123456"}
        assert initial_cookies_text is None
        return {
            "status": "confirmed",
            "cookies_text": '{"xhsapiToken":"password-token"}',
            "user_info": {
                "external_user_id": "huitun-web-user-1",
                "nickname": "灰豚密码号",
                "avatar_url": "https://example.test/huitun-web-avatar.webp",
                "profile": {"source": "huitun", "raw": {"userId": "huitun-web-user-1"}},
            },
        }


class FakePhoneLoginAdapter:
    def create_phone_session(self, phone):
        assert phone == "13800138000"
        return {"cookies": {"a1": "phone-temp-a1"}, "message": "sent"}

    def confirm_phone_login(self, phone, code, cookies):
        assert phone == "13800138000"
        assert code == "123456"
        assert cookies == {"a1": "phone-temp-a1"}
        return {"status": "confirmed", "cookies": {"a1": "phone-final-a1", "web_session": "phone-session"}}

    def get_user_info(self, cookies):
        assert cookies["web_session"] == "phone-session"
        return {
            "external_user_id": "phone-user-1",
            "nickname": "phone-cat",
            "avatar_url": "https://example.test/phone-avatar.webp",
        }


class FailingPhoneUserInfoAdapter(FakePhoneLoginAdapter):
    def get_user_info(self, cookies):
        raise RuntimeError("phone user info endpoint failed")


class FakePhoneSelfProfileAdapter:
    def __init__(self, cookies):
        assert cookies == "a1=phone-final-a1; web_session=phone-session"

    def get_self_info(self):
        return {
            "data": {
                "basic_info": {
                    "user_id": "phone-self-profile-user-1",
                    "nickname": "phone-self-profile-cat",
                    "images": "https://example.test/phone-self-profile-avatar.webp",
                    "red_id": "phone-self-red-1",
                }
            }
        }


def _register_and_get_access_token(username: str = "operator") -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _register_and_get_admin_access_token(username: str = "admin-operator") -> str:
    from backend.app.core.database import get_db
    from backend.app.models import User

    token = _register_and_get_access_token(username)
    db = next(app.dependency_overrides[get_db]())
    try:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.role = "admin"
        db.commit()
    finally:
        db.close()
    return token


def test_huitun_qrcode_login_session_persists_and_confirms_account(tmp_path):
    from backend.app.api.huitun_login_sessions import get_huitun_account_client
    from backend.app.core.database import get_db
    from backend.app.core.security import create_access_token, decrypt_text
    from backend.app.models import AccountCookieVersion, LoginSession, PlatformAccount, User

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_huitun_account_client] = lambda: FakeHuitunAccountClient()
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            admin = User(username="huitun-admin", password_hash="hash", role="admin", status="active")
            db.add(admin)
            db.commit()
            admin_id = admin.id
        finally:
            db.close()
        access_token = create_access_token(admin_id)

        create_response = client.post(
            "/api/huitun/login-sessions/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "pending"
        assert created["qr_url"] == "http://weixin.qq.com/q/huitun-ticket-123"
        assert created["qr_image_data_url"].startswith("data:image/png;base64,")
        assert "xhsapiToken" not in str(created)

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, created["session_id"])
            assert stored_session.platform == "huitun"
            assert stored_session.sub_type == "main"
            assert stored_session.qr_id == "huitun-ticket-123"
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"ticket":"huitun-ticket-123","cookies":{"xhsapiToken":"temp-token"}}'
        finally:
            db.close()

        poll_response = client.get(
            f"/api/huitun/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert poll_response.status_code == 200
        polled = poll_response.json()
        assert polled["status"] == "confirmed"
        assert polled["account"]["platform"] == "huitun"
        assert polled["account"]["sub_type"] == "main"
        assert polled["account"]["nickname"] == "数据账号运营号"
        assert polled["account"]["external_user_id"].startswith("数据账号 ")
        assert "灰豚" not in polled["account"]["nickname"]
        assert "huitun" not in polled["account"]["external_user_id"].lower()
        assert "final-token" not in str(polled)

        accounts_response = client.get(
            "/api/accounts?platform=huitun",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert accounts_response.status_code == 200
        accounts_payload = accounts_response.json()
        assert accounts_payload["total"] == 1
        assert accounts_payload["items"][0]["nickname"] == "数据账号运营号"
        assert accounts_payload["items"][0]["external_user_id"].startswith("数据账号 ")
        assert "灰豚" not in accounts_payload["items"][0]["nickname"]
        assert "huitun" not in accounts_payload["items"][0]["external_user_id"].lower()
        assert accounts_payload["items"][0]["sub_type"] == "main"

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.platform == "huitun"
            assert account.sub_type == "main"
            assert account.external_user_id == "huitun-user-1"
            cookie_version = db.query(AccountCookieVersion).one()
            assert cookie_version.platform_account_id == account.id
            assert decrypt_text(cookie_version.encrypted_cookies) == '{"xhsapiToken":"final-token"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_huitun_account_client, None)


def test_huitun_password_login_session_is_admin_only(tmp_path):
    from backend.app.api.huitun_login_sessions import get_huitun_account_client

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_huitun_account_client] = lambda: FakeHuitunAccountClient()
    try:
        user_token = _register_and_get_access_token("ordinary-huitun-password-user")

        response = client.post(
            "/api/huitun/login-sessions/password/confirm",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "mobile": "13800138000",
                "password": "company-pass-123",
                "ticket": "captcha-ticket",
                "randStr": "captcha-rand",
            },
        )

        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_huitun_account_client, None)


def test_huitun_password_login_persists_cookie_without_storing_plain_password(tmp_path):
    from backend.app.api.huitun_login_sessions import get_huitun_account_client
    from backend.app.core.database import get_db
    from backend.app.core.security import create_access_token, decrypt_text
    from backend.app.models import AccountCookieVersion, LoginSession, PlatformAccount, User

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_huitun_account_client] = lambda: FakeHuitunAccountClient()
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            admin = User(username="huitun-password-admin", password_hash="hash", role="admin", status="active")
            db.add(admin)
            db.commit()
            admin_id = admin.id
        finally:
            db.close()
        access_token = create_access_token(admin_id)

        response = client.post(
            "/api/huitun/login-sessions/password/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "mobile": "13800138000",
                "password": "company-pass-123",
                "ticket": "captcha-ticket",
                "randStr": "captcha-rand",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "confirmed"
        assert payload["account"]["platform"] == "huitun"
        assert payload["account"]["sub_type"] == "main"
        assert payload["account"]["nickname"] == "数据账号密码号"
        assert "company-pass-123" not in str(payload)
        assert "captcha-ticket" not in str(payload)
        assert "captcha-rand" not in str(payload)
        assert "password-token" not in str(payload)

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.query(LoginSession).filter(LoginSession.login_method == "password").one()
            assert stored_session.platform == "huitun"
            assert stored_session.sub_type == "main"
            assert stored_session.status == "confirmed"
            assert stored_session.phone_mask == "138****8000"
            assert stored_session.encrypted_temp_cookies in {None, ""}
            serialized_session = " ".join(
                str(value or "")
                for value in (
                    stored_session.phone_mask,
                    stored_session.qr_id,
                    stored_session.code,
                    stored_session.qr_url,
                    stored_session.encrypted_temp_cookies,
                )
            )
            assert "company-pass-123" not in serialized_session
            assert "captcha-ticket" not in serialized_session
            assert "captcha-rand" not in serialized_session

            account = db.query(PlatformAccount).one()
            assert account.platform == "huitun"
            assert account.external_user_id == "huitun-web-user-1"
            cookie_version = db.query(AccountCookieVersion).one()
            assert cookie_version.platform_account_id == account.id
            assert decrypt_text(cookie_version.encrypted_cookies) == '{"xhsapiToken":"password-token"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_huitun_account_client, None)


def test_huitun_password_login_returns_sms_verification_required(tmp_path):
    from backend.app.api.huitun_login_sessions import get_huitun_account_client
    from backend.app.core.database import get_db
    from backend.app.core.security import create_access_token, decrypt_text
    from backend.app.models import LoginSession, User

    class SmsRequiredHuitunAccountClient(FakeHuitunAccountClient):
        def login_huitun_with_password(self, mobile, password, ticket, rand_str, captcha=None, initial_cookies_text=None):
            assert mobile == "13800138000"
            assert password == "company-pass-123"
            assert ticket == "captcha-ticket"
            assert rand_str == "captcha-rand"
            assert captcha is None
            assert initial_cookies_text is None
            return {
                "status": "verification_required",
                "cookies_text": '{"xhsapiToken":"temporary-token"}',
                "user_info": None,
                "message": "当前设备需要短信验证，请输入短信验证码后继续。",
                "diagnostics": {
                    "http_status": 403,
                    "message": "企业版账号当前设备需要短信验证码",
                },
            }

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_huitun_account_client] = lambda: SmsRequiredHuitunAccountClient()
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            admin = User(username="huitun-sms-admin", password_hash="hash", role="admin", status="active")
            db.add(admin)
            db.commit()
            admin_id = admin.id
        finally:
            db.close()
        access_token = create_access_token(admin_id)

        response = client.post(
            "/api/huitun/login-sessions/password/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "mobile": "13800138000",
                "password": "company-pass-123",
                "ticket": "captcha-ticket",
                "randStr": "captcha-rand",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "verification_required"
        assert payload["account"] is None
        assert payload["message"] == "当前设备需要短信验证，请输入短信验证码后继续。"
        assert "company-pass-123" not in str(payload)
        assert "captcha-ticket" not in str(payload)
        assert "captcha-rand" not in str(payload)
        assert "temporary-token" not in str(payload)
        assert "企业版" not in str(payload)

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.query(LoginSession).filter(LoginSession.login_method == "password").one()
            assert stored_session.status == "verification_required"
            assert stored_session.phone_mask == "138****8000"
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"xhsapiToken":"temporary-token"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_huitun_account_client, None)


def test_huitun_password_login_confirms_sms_with_existing_session(tmp_path):
    from backend.app.api.huitun_login_sessions import get_huitun_account_client
    from backend.app.core.database import get_db
    from backend.app.core.security import create_access_token, decrypt_text
    from backend.app.models import AccountCookieVersion, LoginSession, PlatformAccount, User

    class SmsConfirmHuitunAccountClient(FakeHuitunAccountClient):
        def __init__(self):
            self.calls = []

        def login_huitun_with_password(self, mobile, password, ticket, rand_str, captcha=None, initial_cookies_text=None):
            self.calls.append(
                {
                    "mobile": mobile,
                    "password": password,
                    "ticket": ticket,
                    "rand_str": rand_str,
                    "captcha": captcha,
                    "initial_cookies_text": initial_cookies_text,
                }
            )
            if captcha is None:
                return {
                    "status": "verification_required",
                    "cookies_text": '{"xhsapiToken":"temporary-token"}',
                    "user_info": None,
                    "message": "当前设备需要短信验证，请输入短信验证码后继续。",
                }
            return {
                "status": "confirmed",
                "cookies_text": '{"xhsapiToken":"final-enterprise-token"}',
                "user_info": {
                    "external_user_id": "enterprise-user-1",
                    "nickname": "企业版数据账号",
                    "avatar_url": "",
                    "profile": {"source": "huitun", "raw": {"userId": "enterprise-user-1"}},
                },
            }

    fake_client = SmsConfirmHuitunAccountClient()
    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_huitun_account_client] = lambda: fake_client
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            admin = User(username="huitun-sms-confirm-admin", password_hash="hash", role="admin", status="active")
            db.add(admin)
            db.commit()
            admin_id = admin.id
        finally:
            db.close()
        access_token = create_access_token(admin_id)

        first_response = client.post(
            "/api/huitun/login-sessions/password/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "mobile": "13800138000",
                "password": "company-pass-123",
                "ticket": "captcha-ticket",
                "randStr": "captcha-rand",
            },
        )
        assert first_response.status_code == 200
        first_payload = first_response.json()
        assert first_payload["status"] == "verification_required"

        second_response = client.post(
            "/api/huitun/login-sessions/password/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "mobile": "13800138000",
                "password": "company-pass-123",
                "ticket": "captcha-ticket-2",
                "randStr": "captcha-rand-2",
                "captcha": "654321",
                "session_id": first_payload["session_id"],
            },
        )

        assert second_response.status_code == 200
        second_payload = second_response.json()
        assert second_payload["status"] == "confirmed"
        assert second_payload["account"]["nickname"] == "企业版数据账号"
        assert "company-pass-123" not in str(second_payload)
        assert "temporary-token" not in str(second_payload)
        assert "final-enterprise-token" not in str(second_payload)
        assert fake_client.calls[1]["captcha"] == "654321"
        assert fake_client.calls[1]["initial_cookies_text"] == '{"xhsapiToken":"temporary-token"}'

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.query(LoginSession).filter(LoginSession.login_method == "password").one()
            assert stored_session.status == "confirmed"
            assert stored_session.encrypted_temp_cookies in {None, ""}
            account = db.query(PlatformAccount).one()
            assert account.external_user_id == "enterprise-user-1"
            cookie_version = db.query(AccountCookieVersion).one()
            assert decrypt_text(cookie_version.encrypted_cookies) == '{"xhsapiToken":"final-enterprise-token"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_huitun_account_client, None)


def test_huitun_account_management_is_admin_only(tmp_path):
    from backend.app.api.huitun_login_sessions import get_huitun_account_client
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount, User

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_huitun_account_client] = lambda: FakeHuitunAccountClient()
    try:
        user_token = _register_and_get_access_token("ordinary-data-user")
        db = next(app.dependency_overrides[get_db]())
        try:
            ordinary_user = db.query(User).filter(User.username == "ordinary-data-user").one()
            legacy_data_account = PlatformAccount(
                user_id=ordinary_user.id,
                platform="huitun",
                sub_type="main",
                external_user_id="legacy-data-account",
                nickname="legacy data account",
                status="active",
            )
            db.add(legacy_data_account)
            db.flush()
            db.add(
                AccountCookieVersion(
                    platform_account_id=legacy_data_account.id,
                    encrypted_cookies=encrypt_text('{"xhsapiToken":"legacy-token"}'),
                )
            )
            db.commit()
            legacy_data_account_id = legacy_data_account.id
        finally:
            db.close()

        qrcode_response = client.post(
            "/api/huitun/login-sessions/qrcode",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        cookie_response = client.post(
            "/api/accounts/import-cookie",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"platform": "huitun", "sub_type": "main", "cookie_string": '{"xhsapiToken":"user-token"}'},
        )
        list_response = client.get("/api/accounts?platform=huitun", headers={"Authorization": f"Bearer {user_token}"})
        check_response = client.post(
            f"/api/accounts/{legacy_data_account_id}/check",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        update_response = client.patch(
            f"/api/accounts/{legacy_data_account_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        delete_response = client.delete(
            f"/api/accounts/{legacy_data_account_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert qrcode_response.status_code == 403
        assert cookie_response.status_code == 403
        assert qrcode_response.json()["detail"] == "Admin role required"
        assert cookie_response.json()["detail"] == "Admin role required"
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 0
        assert list_response.json()["items"] == []
        assert check_response.status_code == 403
        assert update_response.status_code == 403
        assert delete_response.status_code == 403
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_huitun_account_client, None)



def test_huitun_live_account_discovery_uses_owned_account_and_persists_candidates(tmp_path):
    from backend.app.api.keyword_groups import get_huitun_live_keyword_client
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, KeywordDiscoveryItem, PlatformAccount, User

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_huitun_live_keyword_client] = lambda: FakeHuitunLiveKeywordClient()
    try:
        access_token = _register_and_get_access_token("huitun-keyword-operator")
        db = next(app.dependency_overrides[get_db]())
        try:
            admin = User(username="huitun-keyword-admin", password_hash="hash", role="admin", status="active")
            db.add(admin)
            db.flush()
            account = PlatformAccount(
                user_id=admin.id,
                platform="huitun",
                sub_type="main",
                external_user_id="huitun-keyword-user",
                nickname="灰豚取词号",
                status="active",
            )
            db.add(account)
            db.flush()
            db.add(
                AccountCookieVersion(
                    platform_account_id=account.id,
                    encrypted_cookies=encrypt_text('{"xhsapiToken":"keyword-token"}'),
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "source_mode": "live_account",
                "limit_per_seed": 20,
                "inputs": [{"source_keyword": "低卡早餐"}],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_mode"] == "live_account"
        assert payload["status"] == "completed"
        assert payload["seed_keywords"] == ["低卡早餐"]
        assert [item["keyword"] for item in payload["items"]] == ["低卡早餐食谱", "低卡早餐搭配"]
        assert payload["items"][0]["source_keyword"] == "低卡早餐"
        assert payload["items"][0]["hot_value_number"] == 123000

        db = next(app.dependency_overrides[get_db]())
        try:
            items = db.query(KeywordDiscoveryItem).order_by(KeywordDiscoveryItem.rank_index).all()
            assert len(items) == 2
            assert items[0].keyword == "低卡早餐食谱"
            assert items[0].raw_json["keyword"] == "低卡早餐食谱"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)



def test_xhs_pc_qrcode_login_session_persists_and_confirms_account(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import AccountCookieVersion, LoginSession, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FakePcLoginAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    try:
        access_token = _register_and_get_access_token()

        create_response = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "pending"
        assert created["qr_url"] == "https://example.test/qr"
        assert created["qr_image_data_url"].startswith("data:image/png;base64,")
        assert isinstance(created["session_id"], int)

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, created["session_id"])
            assert stored_session.platform == "xhs"
            assert stored_session.sub_type == "pc"
            assert stored_session.qr_id == "qr-123"
            assert stored_session.code == "code-123"
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"a1":"temp-a1"}'
        finally:
            db.close()

        poll_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert poll_response.status_code == 200
        polled = poll_response.json()
        assert polled["status"] == "confirmed"
        assert polled["account"]["nickname"] == "cat"
        assert polled["creator_account"] is None

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert accounts_response.status_code == 200
        accounts_payload = accounts_response.json()
        assert accounts_payload["total"] == 1
        assert accounts_payload["items"][0]["nickname"] == "cat"
        assert accounts_payload["items"][0]["sub_type"] == "pc"

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.platform == "xhs"
            assert account.sub_type == "pc"
            assert account.external_user_id == "xhs-user-1"
            cookie_version = db.query(AccountCookieVersion).one()
            assert cookie_version.platform_account_id == account.id
            assert decrypt_text(cookie_version.encrypted_cookies) == '{"a1":"final-a1","web_session":"session-123"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_qrcode_login_recovers_after_transient_cloudflare_poll_failure(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import LoginSession

    db_dependency = _override_database(tmp_path)
    adapter = TransientPcPollingAdapter()
    app.dependency_overrides[get_pc_login_adapter] = lambda: adapter
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    try:
        access_token = _register_and_get_access_token("qr-transient-cloudflare-operator")
        created = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()

        scanned_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert scanned_response.status_code == 200
        assert scanned_response.json()["status"] == "scanned"

        transient_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert transient_response.status_code == 200
        assert transient_response.json()["status"] == "scanned"
        assert transient_response.json()["account"] is None

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, created["session_id"])
            assert stored_session.status == "scanned"
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"a1":"temp-a1"}'
        finally:
            db.close()

        confirmed_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert confirmed_response.status_code == 200
        assert confirmed_response.json()["status"] == "confirmed"
        assert confirmed_response.json()["account"]["nickname"] == "cat"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_qrcode_login_updates_existing_account_for_same_external_user(tmp_path):
    from backend.app.api.accounts import get_pc_account_adapter
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FakePcLoginAdapter()
    app.dependency_overrides[get_pc_account_adapter] = lambda: FakePcLoginAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    try:
        access_token = _register_and_get_access_token("qr-upsert-operator")

        first_create = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()
        first_poll = client.get(
            f"/api/xhs/login-sessions/{first_create['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert first_poll.status_code == 200
        assert first_poll.json()["account"]["action"] == "created"

        second_create = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()
        second_poll = client.get(
            f"/api/xhs/login-sessions/{second_create['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert second_poll.status_code == 200
        assert second_poll.json()["account"]["action"] == "updated"

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        accounts_payload = accounts_response.json()
        assert accounts_payload["total"] == 1
        assert accounts_payload["items"][0]["updated_at"]
        assert accounts_payload["items"][0]["profile"] == {}

        check_response = client.post(
            f"/api/accounts/{accounts_payload['items'][0]['id']}/check",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert check_response.status_code == 200
        assert check_response.json()["status"] == "active", check_response.json().get("status_message")

        db = next(app.dependency_overrides[get_db]())
        try:
            accounts = db.query(PlatformAccount).all()
            assert len(accounts) == 1
            cookie_versions = db.query(AccountCookieVersion).order_by(AccountCookieVersion.id).all()
            assert len(cookie_versions) == 2
            assert cookie_versions[-1].platform_account_id == accounts[0].id
            assert decrypt_text(cookie_versions[-1].encrypted_cookies) == '{"a1":"final-a1","web_session":"session-123"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_pc_account_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_qrcode_login_falls_back_to_self_profile_when_confirmed_user_info_fails(tmp_path, monkeypatch):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FailingPcUserInfoAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    monkeypatch.setattr("backend.app.api.login_sessions.XhsPcApiAdapter", FakePcSelfProfileAdapter)
    try:
        access_token = _register_and_get_access_token("qr-profile-fallback-operator")
        create_response = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert create_response.status_code == 200
        created = create_response.json()

        poll_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert poll_response.status_code == 200
        payload = poll_response.json()
        assert payload["status"] == "confirmed"
        assert payload["account"]["nickname"] == "self-profile-cat"
        assert payload["account"]["external_user_id"] == "self-profile-user-1"
        assert payload["account"]["profile"]["red_id"] == "self-red-1"

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.external_user_id == "self-profile-user-1"
            cookie_version = db.query(AccountCookieVersion).one()
            assert decrypt_text(cookie_version.encrypted_cookies) == '{"a1":"final-a1","web_session":"session-123"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_qrcode_login_uses_qrcode_identity_when_profile_fetches_fail(tmp_path, monkeypatch):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FailingPcProfilesWithQrIdentityAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    monkeypatch.setattr("backend.app.api.login_sessions.XhsPcApiAdapter", FailingPcSelfProfileAdapter)
    try:
        access_token = _register_and_get_access_token("qr-identity-fallback-operator")
        created = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()

        poll_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert poll_response.status_code == 200
        payload = poll_response.json()
        assert payload["status"] == "confirmed"
        assert payload["account"]["external_user_id"] == "qr-identity-user-1"

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.external_user_id == "qr-identity-user-1"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_qrcode_login_does_not_create_account_without_web_session(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.models import AccountCookieVersion, LoginSession, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: MissingSessionPcQrAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    try:
        access_token = _register_and_get_access_token("qr-missing-session-operator")
        created = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()

        poll_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert poll_response.status_code == 200
        assert poll_response.json()["status"] == "scanned"
        assert poll_response.json()["account"] is None

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, created["session_id"])
            assert stored_session.status == "scanned"
            assert db.query(PlatformAccount).count() == 0
            assert db.query(AccountCookieVersion).count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_accounts_list_reuses_matching_identity_profile_without_mutating_storage(tmp_path):
    import json

    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount, User

    db_dependency = _override_database(tmp_path)
    try:
        access_token = _register_and_get_access_token("identity-profile-list-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            user = db.query(User).filter(User.username == "identity-profile-list-owner").one()
            creator_account = PlatformAccount(
                user_id=user.id,
                platform="xhs",
                sub_type="creator",
                external_user_id="shared-xhs-user",
                nickname="Morse",
                avatar_url="https://example.com/morse.png",
                status="active",
                profile_json=json.dumps(
                    {"followers": "88", "following": "12", "likes": "301"},
                    ensure_ascii=False,
                ),
            )
            pc_account = PlatformAccount(
                user_id=user.id,
                platform="xhs",
                sub_type="pc",
                external_user_id="shared-xhs-user",
                nickname="",
                avatar_url="",
                status="active",
                profile_json="{}",
            )
            db.add_all([creator_account, pc_account])
            db.commit()
            pc_account_id = pc_account.id
        finally:
            db.close()

        response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        pc_payload = next(item for item in response.json()["items"] if item["sub_type"] == "pc")
        assert pc_payload["nickname"] == "Morse"
        assert pc_payload["avatar_url"] == "https://example.com/morse.png"
        assert pc_payload["profile"]["followers"] == "88"
        assert pc_payload["profile"]["profile_sync_status"] == "pending"
        assert pc_payload["status"] == "active"
        assert pc_payload["status_message"] == "账号已登录，完整资料待同步。"

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_pc_account = db.get(PlatformAccount, pc_account_id)
            assert stored_pc_account.nickname == ""
            assert stored_pc_account.profile_json == "{}"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_identity_only_upsert_reuses_matching_account_profile(tmp_path):
    import json

    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount, User
    from backend.app.services.account_service import upsert_platform_account_from_login

    db_dependency = _override_database(tmp_path)
    try:
        _register_and_get_access_token("identity-profile-upsert-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            user = db.query(User).filter(User.username == "identity-profile-upsert-owner").one()
            db.add(
                PlatformAccount(
                    user_id=user.id,
                    platform="xhs",
                    sub_type="creator",
                    external_user_id="shared-upsert-user",
                    nickname="Morse",
                    avatar_url="https://example.com/morse.png",
                    status="active",
                    profile_json=json.dumps({"followers": "88"}, ensure_ascii=False),
                )
            )
            db.commit()

            account, action = upsert_platform_account_from_login(
                db=db,
                user_id=user.id,
                platform="xhs",
                sub_type="pc",
                user_info={
                    "external_user_id": "shared-upsert-user",
                    "profile": {"profile_sync_status": "pending"},
                },
                cookies_text='{"a1":"final-a1","web_session":"session-123"}',
            )
            db.commit()

            assert action == "created"
            assert account.nickname == "Morse"
            assert account.avatar_url == "https://example.com/morse.png"
            assert json.loads(account.profile_json)["followers"] == "88"
            assert json.loads(account.profile_json)["profile_sync_status"] == "pending"
            assert account.status == "active"
            assert account.status_message == "账号已登录，完整资料待同步。"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_accounts_with_empty_external_ids_do_not_share_profile():
    import json

    from backend.app.models import PlatformAccount
    from backend.app.services.account_service import serialize_accounts

    source = PlatformAccount(
        id=101,
        user_id=1,
        platform="xhs",
        sub_type="creator",
        external_user_id="",
        nickname="不应复用的账号",
        avatar_url="https://example.com/wrong.png",
        status="active",
        profile_json=json.dumps({"followers": "999"}, ensure_ascii=False),
    )
    target = PlatformAccount(
        id=102,
        user_id=1,
        platform="xhs",
        sub_type="pc",
        external_user_id="",
        nickname="",
        avatar_url="",
        status="active",
        profile_json=json.dumps({"profile_sync_status": "pending"}, ensure_ascii=False),
    )

    target_payload = next(item for item in serialize_accounts([source, target]) if item["id"] == target.id)

    assert target_payload["nickname"] == ""
    assert target_payload["avatar_url"] == ""
    assert "followers" not in target_payload["profile"]


def test_xhs_partial_account_profile_fills_only_missing_fields():
    import json

    from backend.app.models import PlatformAccount
    from backend.app.services.account_service import serialize_accounts

    source = PlatformAccount(
        id=201,
        user_id=1,
        platform="xhs",
        sub_type="creator",
        external_user_id="shared-partial-user",
        nickname="资料源昵称",
        avatar_url="https://example.com/source.png",
        status="active",
        profile_json=json.dumps(
            {"followers": "88", "likes": "301"},
            ensure_ascii=False,
        ),
    )
    target = PlatformAccount(
        id=202,
        user_id=1,
        platform="xhs",
        sub_type="pc",
        external_user_id="shared-partial-user",
        nickname="当前昵称",
        avatar_url="",
        status="active",
        profile_json=json.dumps({"likes": "500"}, ensure_ascii=False),
    )

    target_payload = next(item for item in serialize_accounts([source, target]) if item["id"] == target.id)

    assert target_payload["nickname"] == "当前昵称"
    assert target_payload["avatar_url"] == "https://example.com/source.png"
    assert target_payload["profile"]["followers"] == "88"
    assert target_payload["profile"]["likes"] == "500"
    assert target_payload["profile"]["profile_sync_status"] == "pending"
    assert target_payload["status_message"] == "账号已登录，完整资料待同步。"


def test_xhs_complete_profile_upsert_preserves_old_non_empty_values_without_pending(tmp_path):
    import json

    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount, User
    from backend.app.services.account_service import upsert_platform_account_from_login

    db_dependency = _override_database(tmp_path)
    try:
        _register_and_get_access_token("complete-profile-upsert-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            user = db.query(User).filter(User.username == "complete-profile-upsert-owner").one()
            db.add(
                PlatformAccount(
                    user_id=user.id,
                    platform="xhs",
                    sub_type="creator",
                    external_user_id="complete-profile-user",
                    nickname="旧昵称",
                    avatar_url="https://example.com/old.png",
                    status="active",
                    profile_json=json.dumps(
                        {
                            "followers": "88",
                            "likes": "301",
                            "profile_sync_status": "pending",
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            db.commit()

            account, action = upsert_platform_account_from_login(
                db=db,
                user_id=user.id,
                platform="xhs",
                sub_type="pc",
                user_info={
                    "external_user_id": "complete-profile-user",
                    "nickname": "新昵称",
                    "avatar_url": "https://example.com/new.png",
                    "profile": {"followers": "", "following": "12"},
                },
                cookies_text='{"a1":"complete-a1","web_session":"complete-session"}',
            )
            db.commit()

            profile = json.loads(account.profile_json)
            assert action == "created"
            assert account.nickname == "新昵称"
            assert account.avatar_url == "https://example.com/new.png"
            assert profile["followers"] == "88"
            assert profile["following"] == "12"
            assert profile["likes"] == "301"
            assert "profile_sync_status" not in profile
            assert account.status_message == ""
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_pc_qrcode_login_returns_controlled_error_when_confirmed_profile_fetch_fails(tmp_path, monkeypatch):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import AccountCookieVersion, LoginSession, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FailingPcUserInfoAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    monkeypatch.setattr("backend.app.api.login_sessions.XhsPcApiAdapter", FailingPcSelfProfileAdapter)
    try:
        access_token = _register_and_get_access_token("qr-profile-failure-operator")
        create_response = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert create_response.status_code == 200
        created = create_response.json()

        poll_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert poll_response.status_code == 502
        payload = poll_response.json()
        assert "账号登录已确认，但读取账号资料失败" in payload["detail"]

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, created["session_id"])
            assert stored_session.status == "pending"
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"a1":"temp-a1"}'
            assert db.query(PlatformAccount).count() == 0
            assert db.query(AccountCookieVersion).count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_creator_qrcode_login_session_persists_and_confirms_account(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import LoginSession, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_creator_login_adapter] = lambda: FakeCreatorLoginAdapter()
    try:
        access_token = _register_and_get_access_token("creator-operator")

        create_response = client.post(
            "/api/xhs/login-sessions/creator/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "pending"
        assert created["qr_url"] == "https://example.test/creator-qr"
        assert created["qr_image_data_url"].startswith("data:image/png;base64,")

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, created["session_id"])
            assert stored_session.platform == "xhs"
            assert stored_session.sub_type == "creator"
            assert stored_session.qr_id == "creator-qr-123"
            assert stored_session.code is None
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"a1":"creator-temp-a1"}'
        finally:
            db.close()

        poll_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert poll_response.status_code == 200
        polled = poll_response.json()
        assert polled["status"] == "confirmed"
        assert polled["account"]["nickname"] == "creator-cat"

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        accounts_payload = accounts_response.json()
        assert accounts_payload["total"] == 1
        assert accounts_payload["items"][0]["sub_type"] == "creator"
        assert accounts_payload["items"][0]["nickname"] == "creator-cat"

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.sub_type == "creator"
            assert account.external_user_id == "creator-user-1"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_qrcode_reports_adapter_failure_as_bad_gateway(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FailingQrLoginAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    try:
        access_token = _register_and_get_access_token("qr-failure-operator")
        response = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 502
        assert "proxy refused" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_qrcode_login_can_optionally_sync_creator_account(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FakePcLoginAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FakeCreatorLoginAdapter()
    try:
        access_token = _register_and_get_access_token("pc-auto-creator-operator")

        created = client.post(
            "/api/xhs/login-sessions/pc/qrcode",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"sync_creator": True},
        ).json()
        poll_response = client.get(
            f"/api/xhs/login-sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert poll_response.status_code == 200
        payload = poll_response.json()
        assert payload["status"] == "confirmed"
        assert payload["account"]["sub_type"] == "pc"
        assert payload["creator_account"]["sub_type"] == "creator"
        assert payload["creator_account"]["nickname"] == "creator-cat"

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        accounts_payload = accounts_response.json()
        assert accounts_payload["total"] == 2
        assert {item["sub_type"] for item in accounts_payload["items"]} == {"pc", "creator"}

        db = next(app.dependency_overrides[get_db]())
        try:
            accounts = db.query(PlatformAccount).order_by(PlatformAccount.sub_type.asc()).all()
            assert len(accounts) == 2
            creator_account = next(account for account in accounts if account.sub_type == "creator")
            assert creator_account.external_user_id == "creator-user-1"
            creator_cookie = (
                db.query(AccountCookieVersion)
                .filter(AccountCookieVersion.platform_account_id == creator_account.id)
                .order_by(AccountCookieVersion.id.desc())
                .one()
            )
            assert decrypt_text(creator_cookie.encrypted_cookies) == '{"a1":"final-a1","customer_session":"session-456"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_phone_login_session_sends_code_and_confirms_account(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import LoginSession, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FakePhoneLoginAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    try:
        access_token = _register_and_get_access_token("phone-operator")

        send_response = client.post(
            "/api/xhs/login-sessions/pc/phone/send-code",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"phone": "13800138000"},
        )
        assert send_response.status_code == 200
        sent = send_response.json()
        assert sent["status"] == "pending"
        assert sent["message"] == "sent"

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, sent["session_id"])
            assert stored_session.sub_type == "pc"
            assert stored_session.login_method == "phone"
            assert stored_session.phone_mask == "138****8000"
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"a1":"phone-temp-a1"}'
        finally:
            db.close()

        confirm_response = client.post(
            "/api/xhs/login-sessions/pc/phone/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"session_id": sent["session_id"], "phone": "13800138000", "code": "123456"},
        )
        assert confirm_response.status_code == 200
        confirmed = confirm_response.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["account"]["nickname"] == "phone-cat"
        assert confirmed["creator_account"] is None

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.sub_type == "pc"
            assert account.external_user_id == "phone-user-1"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_phone_login_falls_back_to_self_profile_when_user_info_fails(tmp_path, monkeypatch):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FailingPhoneUserInfoAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FailingCreatorExchangeAdapter()
    monkeypatch.setattr("backend.app.api.login_sessions.XhsPcApiAdapter", FakePhoneSelfProfileAdapter)
    try:
        access_token = _register_and_get_access_token("phone-profile-fallback-operator")

        send_response = client.post(
            "/api/xhs/login-sessions/pc/phone/send-code",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"phone": "13800138000"},
        )
        assert send_response.status_code == 200
        sent = send_response.json()

        confirm_response = client.post(
            "/api/xhs/login-sessions/pc/phone/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"session_id": sent["session_id"], "phone": "13800138000", "code": "123456"},
        )

        assert confirm_response.status_code == 200
        confirmed = confirm_response.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["account"]["nickname"] == "phone-self-profile-cat"
        assert confirmed["account"]["external_user_id"] == "phone-self-profile-user-1"

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.external_user_id == "phone-self-profile-user-1"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_pc_phone_login_can_optionally_sync_creator_account(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter, get_pc_login_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import AccountCookieVersion, LoginSession, PlatformAccount

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_login_adapter] = lambda: FakePhoneLoginAdapter()
    app.dependency_overrides[get_creator_login_adapter] = lambda: FakeCreatorLoginAdapter()
    try:
        access_token = _register_and_get_access_token("phone-auto-creator-operator")

        send_response = client.post(
            "/api/xhs/login-sessions/pc/phone/send-code",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"phone": "13800138000", "sync_creator": True},
        )
        assert send_response.status_code == 200
        sent = send_response.json()

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_session = db.get(LoginSession, sent["session_id"])
            assert decrypt_text(stored_session.encrypted_temp_cookies) == '{"cookies":{"a1":"phone-temp-a1"},"sync_creator":true}'
        finally:
            db.close()

        confirm_response = client.post(
            "/api/xhs/login-sessions/pc/phone/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"session_id": sent["session_id"], "phone": "13800138000", "code": "123456"},
        )
        assert confirm_response.status_code == 200
        confirmed = confirm_response.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["account"]["sub_type"] == "pc"
        assert confirmed["creator_account"]["sub_type"] == "creator"
        assert confirmed["creator_account"]["nickname"] == "creator-cat"

        db = next(app.dependency_overrides[get_db]())
        try:
            accounts = db.query(PlatformAccount).order_by(PlatformAccount.sub_type.asc()).all()
            assert len(accounts) == 2
            creator_account = next(account for account in accounts if account.sub_type == "creator")
            creator_cookie = (
                db.query(AccountCookieVersion)
                .filter(AccountCookieVersion.platform_account_id == creator_account.id)
                .order_by(AccountCookieVersion.id.desc())
                .one()
            )
            assert decrypt_text(creator_cookie.encrypted_cookies) == '{"a1":"phone-final-a1","customer_session":"session-456"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_login_adapter, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_xhs_creator_phone_login_session_sends_code_and_confirms_account(tmp_path):
    from backend.app.api.login_sessions import get_creator_login_adapter

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_creator_login_adapter] = lambda: FakePhoneLoginAdapter()
    try:
        access_token = _register_and_get_access_token("creator-phone-operator")

        send_response = client.post(
            "/api/xhs/login-sessions/creator/phone/send-code",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"phone": "13800138000"},
        )
        assert send_response.status_code == 200
        sent = send_response.json()
        assert sent["status"] == "pending"

        confirm_response = client.post(
            "/api/xhs/login-sessions/creator/phone/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"session_id": sent["session_id"], "phone": "13800138000", "code": "123456"},
        )
        assert confirm_response.status_code == 200
        confirmed = confirm_response.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["account"]["nickname"] == "phone-cat"

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        accounts_payload = accounts_response.json()
        assert accounts_payload["items"][0]["sub_type"] == "creator"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_creator_login_adapter, None)


def test_account_delete_requires_owner_and_removes_account(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount

    db_dependency = _override_database(tmp_path)
    try:
        owner_token = _register_and_get_access_token("delete-account-owner")
        intruder_token = _register_and_get_access_token("delete-account-intruder")
        db = next(app.dependency_overrides[get_db]())
        try:
            account = PlatformAccount(
                user_id=1,
                platform="xhs",
                sub_type="pc",
                external_user_id="delete-user",
                nickname="Delete Me",
                status="active",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            account_id = account.id
        finally:
            db.close()

        intruder_response = client.delete(
            f"/api/accounts/{account_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404

        owner_response = client.delete(
            f"/api/accounts/{account_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        assert owner_response.json() == {"id": account_id, "status": "deleted"}

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert accounts_response.json()["total"] == 0
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_deleting_creator_account_unbinds_editable_publish_jobs(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount, PublishJob

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "delete-creator-unbind-owner"
    )
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            pending_job = PublishJob(
                user_id=1,
                platform="xhs",
                platform_account_id=creator_account_id,
                title="Pending title",
                body="Pending body",
                status="pending",
            )
            failed_job = PublishJob(
                user_id=1,
                platform="xhs",
                platform_account_id=creator_account_id,
                title="Failed title",
                body="Failed body",
                status="failed",
            )
            published_job = PublishJob(
                user_id=1,
                platform="xhs",
                platform_account_id=creator_account_id,
                title="Published title",
                body="Published body",
                status="published",
            )
            db.add_all([pending_job, failed_job, published_job])
            db.commit()
            pending_job_id = pending_job.id
            failed_job_id = failed_job.id
            published_job_id = published_job.id
        finally:
            db.close()

        response = client.delete(
            f"/api/accounts/{creator_account_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert response.status_code == 200
        verify_db = next(app.dependency_overrides[get_db]())
        try:
            account = verify_db.get(PlatformAccount, creator_account_id)
            pending_job = verify_db.get(PublishJob, pending_job_id)
            failed_job = verify_db.get(PublishJob, failed_job_id)
            published_job = verify_db.get(PublishJob, published_job_id)
            assert account.status == "deleted"
            assert pending_job.platform_account_id is None
            assert "原发布账号已删除" in pending_job.publish_error
            assert failed_job.platform_account_id is None
            assert "原发布账号已删除" in failed_job.publish_error
            assert published_job.platform_account_id == creator_account_id
        finally:
            verify_db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_pc_qrcode_requires_platform_login(tmp_path):
    get_db = _override_database(tmp_path)
    try:
        response = client.post("/api/xhs/login-sessions/pc/qrcode")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_accounts_list_requires_platform_login(tmp_path):
    get_db = _override_database(tmp_path)
    try:
        response = client.get("/api/accounts?platform=xhs")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


class FakeCookieAccountAdapter:
    def __init__(self):
        self.calls = 0

    def get_user_info(self, cookies):
        self.calls += 1
        assert cookies["a1"] == "cookie-a1"
        return {
            "external_user_id": "cookie-user-1",
            "nickname": "cookie-cat",
            "avatar_url": "https://example.test/cookie-avatar.webp",
        }


class FakeSelfProfileAdapter:
    calls = []

    def get_self_profile(self, cookies_text):
        self.__class__.calls.append(cookies_text)
        return {
            "success": True,
            "msg": "ok",
            "data": {
                "basic_info": {
                    "nickname": "cookie-cat-live",
                    "images": "https://example.test/live-avatar.webp",
                    "red_id": "red-cookie-1",
                    "desc": "live profile",
                    "ip_location": "上海",
                },
                "interactions": [
                    {"type": "follows", "name": "关注", "count": "28", "i18n_count": "28"},
                    {"type": "fans", "name": "粉丝", "count": "90", "i18n_count": "90"},
                    {"type": "interaction", "name": "获赞与收藏", "count": "340", "i18n_count": "340"},
                ],
            },
            "code": 0,
        }


class FailingCookieAccountAdapter:
    def get_user_info(self, cookies):
        raise RuntimeError("expired")


def test_account_cookie_import_creates_account_and_health_check_updates_status(tmp_path):
    from backend.app.api.accounts import get_creator_account_adapter, get_pc_account_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.core.time import shanghai_now
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency = _override_database(tmp_path)
    fake_adapter = FakeCookieAccountAdapter()
    app.dependency_overrides[get_pc_account_adapter] = lambda: fake_adapter
    app.dependency_overrides[get_creator_account_adapter] = lambda: FailingCreatorExchangeAdapter()
    try:
        access_token = _register_and_get_access_token("cookie-operator")
        before_create = shanghai_now()

        import_response = client.post(
            "/api/accounts/import-cookie",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"platform": "xhs", "sub_type": "pc", "cookie_string": "a1=cookie-a1; web_session=session"},
        )
        after_create = shanghai_now()
        assert import_response.status_code == 200
        imported = import_response.json()
        assert imported["nickname"] == "cookie-cat"
        assert imported["status"] == "active"

        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.query(PlatformAccount).one()
            assert account.external_user_id == "cookie-user-1"
            assert before_create <= account.created_at <= after_create
            assert before_create <= account.updated_at <= after_create
            cookie_version = db.query(AccountCookieVersion).one()
            assert cookie_version.platform_account_id == account.id
            assert decrypt_text(cookie_version.encrypted_cookies) == "a1=cookie-a1; web_session=session"
        finally:
            db.close()

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert accounts_response.status_code == 200
        assert accounts_response.json()["total"] == 1

        check_response = client.post(
            f"/api/accounts/{imported['id']}/check",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert check_response.status_code == 200
        checked = check_response.json()
        assert checked["status"] == "active"
        assert checked["nickname"] == "cookie-cat"
        assert fake_adapter.calls >= 2
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_account_adapter, None)
        app.dependency_overrides.pop(get_creator_account_adapter, None)


def test_account_cookie_import_for_pc_can_optionally_sync_creator_account(tmp_path):
    from backend.app.api.accounts import get_creator_account_adapter, get_pc_account_adapter
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency = _override_database(tmp_path)
    fake_pc_adapter = FakeCookieAccountAdapter()
    app.dependency_overrides[get_pc_account_adapter] = lambda: fake_pc_adapter
    app.dependency_overrides[get_creator_account_adapter] = lambda: FakeCreatorLoginAdapter()
    try:
        access_token = _register_and_get_access_token("cookie-auto-creator-operator")

        import_response = client.post(
            "/api/accounts/import-cookie",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "platform": "xhs",
                "sub_type": "pc",
                "cookie_string": "a1=cookie-a1; web_session=session",
                "sync_creator": True,
            },
        )
        assert import_response.status_code == 200

        accounts_response = client.get(
            "/api/accounts?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        accounts_payload = accounts_response.json()
        assert accounts_payload["total"] == 2
        assert {item["sub_type"] for item in accounts_payload["items"]} == {"pc", "creator"}

        db = next(app.dependency_overrides[get_db]())
        try:
            accounts = db.query(PlatformAccount).order_by(PlatformAccount.sub_type.asc()).all()
            assert len(accounts) == 2
            creator_account = next(account for account in accounts if account.sub_type == "creator")
            creator_cookie = (
                db.query(AccountCookieVersion)
                .filter(AccountCookieVersion.platform_account_id == creator_account.id)
                .order_by(AccountCookieVersion.id.desc())
                .one()
            )
            assert decrypt_text(creator_cookie.encrypted_cookies) == '{"a1":"cookie-a1","customer_session":"session-456"}'
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_account_adapter, None)
        app.dependency_overrides.pop(get_creator_account_adapter, None)


def test_account_check_refreshes_xhs_self_profile_metrics(tmp_path):
    from backend.app.api.accounts import (
        get_creator_account_adapter,
        get_pc_account_adapter,
        get_xhs_self_profile_adapter,
    )

    db_dependency = _override_database(tmp_path)
    fake_adapter = FakeCookieAccountAdapter()
    FakeSelfProfileAdapter.calls = []
    app.dependency_overrides[get_pc_account_adapter] = lambda: fake_adapter
    app.dependency_overrides[get_creator_account_adapter] = lambda: FailingCreatorExchangeAdapter()
    app.dependency_overrides[get_xhs_self_profile_adapter] = lambda: FakeSelfProfileAdapter()
    try:
        access_token = _register_and_get_access_token("profile-metrics-operator")
        import_response = client.post(
            "/api/accounts/import-cookie",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"platform": "xhs", "sub_type": "pc", "cookie_string": "a1=cookie-a1; web_session=session"},
        )
        account_id = import_response.json()["id"]

        check_response = client.post(
            f"/api/accounts/{account_id}/check",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert check_response.status_code == 200
        checked = check_response.json()
        assert checked["status"] == "active"
        assert checked["nickname"] == "cookie-cat-live"
        assert checked["avatar_url"] == "https://example.test/live-avatar.webp"
        assert checked["profile"]["followers"] == "90"
        assert checked["profile"]["following"] == "28"
        assert checked["profile"]["likes"] == "340"
        assert checked["profile"]["red_id"] == "red-cookie-1"
        assert FakeSelfProfileAdapter.calls == ["a1=cookie-a1; web_session=session", "a1=cookie-a1; web_session=session"]
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_account_adapter, None)
        app.dependency_overrides.pop(get_creator_account_adapter, None)
        app.dependency_overrides.pop(get_xhs_self_profile_adapter, None)


def test_account_check_enforces_ownership_and_marks_expired_on_adapter_failure(tmp_path):
    from backend.app.api.accounts import get_pc_account_adapter

    db_dependency = _override_database(tmp_path)
    app.dependency_overrides[get_pc_account_adapter] = lambda: FakeCookieAccountAdapter()
    try:
        owner_token = _register_and_get_access_token("owner-operator")
        intruder_token = _register_and_get_access_token("intruder-operator")

        import_response = client.post(
            "/api/accounts/import-cookie",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "sub_type": "pc", "cookie_string": "a1=cookie-a1; web_session=session"},
        )
        account_id = import_response.json()["id"]

        forbidden_response = client.post(
            f"/api/accounts/{account_id}/check",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert forbidden_response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_pc_account_adapter, None)

    app.dependency_overrides[get_pc_account_adapter] = lambda: FailingCookieAccountAdapter()
    try:
        expired_response = client.post(
            f"/api/accounts/{account_id}/check",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert expired_response.status_code == 200
        assert expired_response.json()["status"] == "expired"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_pc_account_adapter, None)


class FakeXhsPcSearchAdapter:
    calls = []

    def __init__(self, cookies):
        self.cookies = cookies

    def search_note(self, keyword, page=1, **kwargs):
        self.__class__.calls.append({"cookies": self.cookies, "keyword": keyword, "page": page, **kwargs})
        return (
            True,
            "ok",
            {
                "success": True,
                "msg": "ok",
                "data": {
                    "has_more": True,
                    "items": [
                        {
                            "model_type": "note",
                            "xsec_token": "xsec-search-001",
                            "note_card": {
                                "note_id": "note-001",
                                "display_title": "低卡早餐搜索笔记",
                                "desc": "适合工作日的早餐搭配",
                                "type": "normal",
                                "user": {
                                    "user_id": "author-001",
                                    "nickname": "早餐研究员",
                                    "avatar": "https://example.test/avatar.webp",
                                },
                                "cover": {"url_default": "https://example.test/cover.webp"},
                                "interact_info": {
                                    "liked_count": "1234",
                                    "collected_count": "456",
                                    "comment_count": "78",
                                    "share_count": "9",
                                },
                            },
                        }
                    ],
                },
            },
        )


def _create_pc_account_with_cookie(tmp_path, username="search-owner"):
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency = _override_database(tmp_path)
    access_token = _register_and_get_access_token(username)
    db = next(app.dependency_overrides[get_db]())
    try:
        account = PlatformAccount(
            user_id=1,
            platform="xhs",
            sub_type="pc",
            external_user_id="search-user",
            nickname="搜索账号",
            status="active",
        )
        db.add(account)
        db.flush()
        db.add(
            AccountCookieVersion(
                platform_account_id=account.id,
                encrypted_cookies=encrypt_text('{"a1":"json-a1","web_session":"json-session"}'),
            )
        )
        db.commit()
        account_id = account.id
    finally:
        db.close()
    return db_dependency, access_token, account_id


def test_xhs_notes_feishu_analysis_filters_are_dynamic_and_multi_select(tmp_path):
    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "analysis-filter-owner")
    try:
        db = next(app.dependency_overrides[db_dependency]())
        try:
            first = Note(user_id=1, platform_account_id=account_id, platform="xhs", note_id="filter-1", title="AI 教程", content="正文", author_name="作者A")
            second = Note(user_id=1, platform_account_id=account_id, platform="xhs", note_id="filter-2", title="知识管理测评", content="正文", author_name="作者B")
            third = Note(user_id=1, platform_account_id=account_id, platform="xhs", note_id="filter-3", title="AI 避坑", content="正文", author_name="作者C")
            db.add_all([first, second, third])
            db.flush()
            db.add_all([
                NoteAnalysisResult(
                    user_id=1,
                    note_id=first.id,
                    source="feishu",
                    analysis_status="已完成",
                    subject_object="AI 工具",
                    content_type="教程",
                    reusable_models=["教程方法模型", "问题驱动模型"],
                    reuse_value="标题参考",
                    search_attribute="强搜索",
                    push_status="synced",
                ),
                NoteAnalysisResult(
                    user_id=1,
                    note_id=second.id,
                    source="feishu",
                    analysis_status="已完成",
                    subject_object="知识管理",
                    content_type="测评",
                    reusable_models=["测评背书模型"],
                    reuse_value="选题参考、正文结构参考",
                    search_attribute="弱搜索",
                    push_status="synced",
                ),
                NoteAnalysisResult(
                    user_id=1,
                    note_id=third.id,
                    source="feishu",
                    analysis_status="分析中",
                    subject_object="AI 工具",
                    content_type="避坑",
                    reusable_models=["问题驱动模型"],
                    reuse_value="废弃",
                    search_attribute=None,
                    push_status="synced",
                ),
            ])
            db.commit()
        finally:
            db.close()

        options_response = client.get(
            "/api/notes/filter-options?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert options_response.status_code == 200
        options = options_response.json()
        assert {item["value"] for item in options["coreProductService"]} >= {"AI 工具", "知识管理"}
        assert {item["value"] for item in options["contentType"]} >= {"教程", "测评", "避坑"}
        assert {item["value"] for item in options["reusableModel"]} >= {"教程方法模型", "问题驱动模型", "测评背书模型"}
        content_usage_values = {item["value"] for item in options["contentUsage"]}
        assert content_usage_values >= {"标题参考", "正文结构参考", "选题参考", "废弃"}
        assert "选题参考、正文结构参考" not in content_usage_values
        assert {item["value"] for item in options["searchAttribute"]} >= {"强搜索", "弱搜索"}

        usage_response = client.get(
            "/api/notes?platform=xhs&content_usage=正文结构参考",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert usage_response.status_code == 200
        assert [item["note_id"] for item in usage_response.json()["items"]] == ["filter-2"]

        or_response = client.get(
            "/api/notes?platform=xhs&core_product_service=AI 工具,知识管理",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert or_response.status_code == 200
        assert {item["note_id"] for item in or_response.json()["items"]} == {"filter-1", "filter-2", "filter-3"}

        and_response = client.get(
            "/api/notes?platform=xhs&core_product_service=AI 工具,知识管理&content_type=教程",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert and_response.status_code == 200
        assert [item["note_id"] for item in and_response.json()["items"]] == ["filter-1"]

        model_response = client.get(
            "/api/notes?platform=xhs&reusable_model=问题驱动模型&search_attribute=强搜索",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert model_response.status_code == 200
        assert [item["note_id"] for item in model_response.json()["items"]] == ["filter-1"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def _create_creator_account_with_cookie(tmp_path, username="creator-owner"):
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency = _override_database(tmp_path)
    access_token = _register_and_get_access_token(username)
    db = next(app.dependency_overrides[get_db]())
    try:
        account = PlatformAccount(
            user_id=1,
            platform="xhs",
            sub_type="creator",
            external_user_id="creator-user",
            nickname="Creator account",
            status="active",
        )
        db.add(account)
        db.flush()
        db.add(
            AccountCookieVersion(
                platform_account_id=account.id,
                encrypted_cookies=encrypt_text('{"web_session":"creator-session","a1":"creator-a1"}'),
            )
        )
        db.commit()
        account_id = account.id
    finally:
        db.close()
    return db_dependency, access_token, account_id


def test_xhs_pc_note_search_uses_owned_account_cookie_and_normalizes_results(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path)
    FakeXhsPcSearchAdapter.calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcSearchAdapter
    try:
        response = client.post(
            "/api/xhs/pc/search/notes",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"account_id": account_id, "keyword": "低卡早餐", "page": 2},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["page"] == 2
        assert payload["has_more"] is True
        assert FakeXhsPcSearchAdapter.calls == [
            {
                "cookies": "a1=json-a1; web_session=json-session",
                "keyword": "低卡早餐",
                "page": 2,
                "sort_type_choice": 0,
                "note_type": 0,
                "note_time": 0,
                "note_range": 0,
                "pos_distance": 0,
                "geo": "",
            }
        ]
        note = payload["items"][0]
        assert note["note_id"] == "note-001"
        assert note["note_url"] == "https://www.xiaohongshu.com/explore/note-001?xsec_token=xsec-search-001&xsec_source=pc_feed"
        assert note["title"] == "低卡早餐搜索笔记"
        assert note["content"] == "适合工作日的早餐搭配"
        assert note["author_name"] == "早餐研究员"
        assert note["author_id"] == "author-001"
        assert note["cover_url"] == "https://example.test/cover.webp"
        assert note["likes"] == 1234
        assert note["collects"] == 456
        assert note["comments"] == 78
        assert note["shares"] == 9
        assert note["type"] == "normal"
        assert "raw" not in note
        assert "raw" not in payload
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_search_keeps_raw_payload_admin_only(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount, User

    db_dependency, normal_token, normal_account_id = _create_pc_account_with_cookie(tmp_path, "pc-raw-normal")
    admin_token = _register_and_get_admin_access_token("pc-raw-admin")
    db = next(app.dependency_overrides[get_db]())
    try:
        admin = db.scalar(select(User).where(User.username == "pc-raw-admin"))
        assert admin is not None
        admin_account = PlatformAccount(
            user_id=admin.id,
            platform="xhs",
            sub_type="pc",
            external_user_id="admin-pc",
            nickname="admin pc",
            status="active",
        )
        db.add(admin_account)
        db.flush()
        db.add(
            AccountCookieVersion(
                platform_account_id=admin_account.id,
                encrypted_cookies=encrypt_text('{"a1":"admin-a1","web_session":"admin-session"}'),
            )
        )
        db.commit()
        admin_account_id = admin_account.id
    finally:
        db.close()

    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcSearchAdapter
    try:
        normal_response = client.post(
            "/api/xhs/pc/search/notes",
            headers={"Authorization": f"Bearer {normal_token}"},
            json={"account_id": normal_account_id, "keyword": "breakfast"},
        )
        assert normal_response.status_code == 200
        normal_payload = normal_response.json()
        assert "raw" not in normal_payload
        assert "raw" not in normal_payload["items"][0]

        admin_response = client.post(
            "/api/xhs/pc/search/notes",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"account_id": admin_account_id, "keyword": "breakfast"},
        )
        assert admin_response.status_code == 200
        admin_payload = admin_response.json()
        assert admin_payload["raw"]["success"] is True
        assert admin_payload["items"][0]["raw"]["model_type"] == "note"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_note_search_rejects_missing_auth_and_cross_user_account(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    db_dependency, owner_token, account_id = _create_pc_account_with_cookie(tmp_path, "search-owner-2")
    intruder_token = _register_and_get_access_token("search-intruder")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcSearchAdapter
    try:
        missing_auth_response = client.post(
            "/api/xhs/pc/search/notes",
            json={"account_id": account_id, "keyword": "低卡早餐", "page": 1},
        )
        assert missing_auth_response.status_code == 401

        intruder_response = client.post(
            "/api/xhs/pc/search/notes",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"account_id": account_id, "keyword": "低卡早餐", "page": 1},
        )
        assert intruder_response.status_code == 404

        owner_response = client.post(
            "/api/xhs/pc/search/notes",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": account_id, "keyword": "低卡早餐", "page": 1},
        )
        assert owner_response.status_code == 200
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_note_detail_uses_owned_account_cookie_and_normalizes_result(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeXhsPcDetailAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_info(self, url):
            self.calls.append({"cookies": self.cookies, "url": url})
            return (
                True,
                "ok",
                {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "note_card": {
                                    "note_id": "detail-note-001",
                                    "title": "Detail title",
                                    "desc": "Detail body",
                                    "type": "video",
                                    "user": {
                                        "user_id": "author-detail",
                                        "nickname": "Detail author",
                                        "avatar": "https://example.test/author.webp",
                                    },
                                    "image_list": [
                                        {
                                            "url_default": "https://example.test/image-preview.webp",
                                            "info_list": [
                                                {"image_scene": "WB_DFT", "url": "https://example.test/image-low.webp"},
                                                {"image_scene": "WB_PRV", "url": "https://example.test/image-high.webp"},
                                            ],
                                        },
                                    ],
                                    "video": {
                                        "media": {
                                            "stream": {
                                                "h264": [
                                                    {
                                                        "master_url": "https://sns-video-hw.xhscdn.com/detail-video-master.mp4",
                                                        "url": "https://sns-video-hw.xhscdn.com/detail-video-fallback.mp4",
                                                    }
                                                ]
                                            }
                                        }
                                    },
                                    "interact_info": {
                                        "liked_count": "100",
                                        "collected_count": "20",
                                        "comment_count": "3",
                                        "share_count": "4",
                                    },
                                    "tag_list": [{"name": "topic-a"}, {"name": "topic-b"}],
                                }
                            }
                        ]
                    },
                },
            )

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "detail-owner")
    FakeXhsPcDetailAdapter.calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcDetailAdapter
    try:
        response = client.post(
            "/api/xhs/pc/notes/detail",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "url": "https://www.xiaohongshu.com/explore/detail-note-001?xsec_token=detail-token&xsec_source=pc_feed",
            },
        )

        assert response.status_code == 200
        detail = response.json()
        assert detail["note_id"] == "detail-note-001"
        assert detail["note_url"] == "https://www.xiaohongshu.com/explore/detail-note-001?xsec_token=detail-token&xsec_source=pc_feed"
        assert detail["title"] == "Detail title"
        assert detail["content"] == "Detail body"
        assert detail["author_id"] == "author-detail"
        assert detail["author_name"] == "Detail author"
        assert detail["cover_url"] == "https://example.test/image-high.webp"
        assert detail["image_urls"] == ["https://example.test/image-high.webp"]
        assert detail["video_url"] == "https://sns-video-hw.xhscdn.com/detail-video-master.mp4"
        assert detail["video_addr"] == "https://sns-video-hw.xhscdn.com/detail-video-master.mp4"
        assert detail["tags"] == ["topic-a", "topic-b"]
        assert detail["likes"] == 100
        assert FakeXhsPcDetailAdapter.calls == [
            {
                "cookies": "a1=json-a1; web_session=json-session",
                "url": "https://www.xiaohongshu.com/explore/detail-note-001?xsec_token=detail-token&xsec_source=pc_feed",
            }
        ]
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_note_detail_rejects_short_explore_url_before_adapter_call(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class ShouldNotCallAdapter:
        def __init__(self, cookies):
            raise AssertionError("short explore URL must be rejected before adapter call")

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "detail-short-url-owner")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: ShouldNotCallAdapter
    try:
        response = client.post(
            "/api/xhs/pc/notes/detail",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"account_id": account_id, "url": "https://www.xiaohongshu.com/explore/detail-note-001"},
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["quality_status"] == "invalid_source_url"
        assert detail["diagnostic_kind"] == "missing_xsec_token_short_explore"
        assert detail["can_save"] is False
        assert "xsec_token" in detail["user_message"]
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_note_detail_returns_inline_quality_for_empty_payload(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class EmptyDetailAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_info(self, url):
            return True, "ok", {"success": True, "data": {"items": []}}

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "detail-empty-owner")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: EmptyDetailAdapter
    try:
        response = client.post(
            "/api/xhs/pc/notes/detail",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "url": "https://www.xiaohongshu.com/explore/detail-note-002?xsec_token=detail-token&xsec_source=pc_feed",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["quality_status"] in {"empty_detail_payload", "search_card_only"}
        assert payload["can_save"] is False
        assert payload["diagnostic_kind"] == "empty_detail_payload"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_note_detail_rejects_missing_auth_and_cross_user_account(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeXhsPcDetailAdapter:
        def __init__(self, cookies):
            raise AssertionError("cross-user detail must not instantiate adapter")

    db_dependency, _, account_id = _create_pc_account_with_cookie(tmp_path, "detail-cross-owner")
    intruder_token = _register_and_get_access_token("detail-cross-intruder")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcDetailAdapter
    try:
        anonymous_response = client.post(
            "/api/xhs/pc/notes/detail",
            json={"account_id": account_id, "url": "https://www.xiaohongshu.com/explore/detail-note-001"},
        )
        assert anonymous_response.status_code == 401

        intruder_response = client.post(
            "/api/xhs/pc/notes/detail",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"account_id": account_id, "url": "https://www.xiaohongshu.com/explore/detail-note-001"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_note_comments_uses_owned_account_cookie_and_normalizes_result(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeXhsPcCommentAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_comments(self, note_url):
            self.calls.append({"cookies": self.cookies, "note_url": note_url})
            return (
                True,
                "ok",
                {
                    "data": {
                        "comments": [
                            {
                                "id": "comment-001",
                                "content": "Top level comment",
                                "like_count": "12",
                                "create_time": "2026-04-29 12:00:00",
                                "user_info": {"user_id": "user-001", "nickname": "Comment author"},
                                "sub_comments": [
                                    {
                                        "id": "comment-001-1",
                                        "content": "Reply content",
                                        "like_count": 3,
                                        "create_time": "2026-04-29 12:01:00",
                                        "user_info": {"user_id": "user-002", "nickname": "Reply author"},
                                    }
                                ],
                            }
                        ]
                    }
                },
            )

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "comments-owner")
    FakeXhsPcCommentAdapter.calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcCommentAdapter
    try:
        response = client.post(
            "/api/xhs/pc/notes/comments",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"account_id": account_id, "note_url": "https://www.xiaohongshu.com/explore/comment-note-001"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert payload["items"] == [
            {
                "comment_id": "comment-001",
                "user_name": "Comment author",
                "user_id": "user-001",
                "content": "Top level comment",
                "like_count": 12,
                "parent_comment_id": None,
                "created_at_remote": "2026-04-29 12:00:00",
                "raw_json": {
                    "id": "comment-001",
                    "content": "Top level comment",
                    "like_count": "12",
                    "create_time": "2026-04-29 12:00:00",
                    "user_info": {"user_id": "user-001", "nickname": "Comment author"},
                    "sub_comments": [
                        {
                            "id": "comment-001-1",
                            "content": "Reply content",
                            "like_count": 3,
                            "create_time": "2026-04-29 12:01:00",
                            "user_info": {"user_id": "user-002", "nickname": "Reply author"},
                        }
                    ],
                },
            },
            {
                "comment_id": "comment-001-1",
                "user_name": "Reply author",
                "user_id": "user-002",
                "content": "Reply content",
                "like_count": 3,
                "parent_comment_id": "comment-001",
                "created_at_remote": "2026-04-29 12:01:00",
                "raw_json": {
                    "id": "comment-001-1",
                    "content": "Reply content",
                    "like_count": 3,
                    "create_time": "2026-04-29 12:01:00",
                    "user_info": {"user_id": "user-002", "nickname": "Reply author"},
                },
            },
        ]
        assert FakeXhsPcCommentAdapter.calls == [
            {
                "cookies": "a1=json-a1; web_session=json-session",
                "note_url": "https://www.xiaohongshu.com/explore/comment-note-001",
            }
        ]
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_xhs_pc_note_comments_rejects_missing_auth_and_cross_user_account(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeXhsPcCommentAdapter:
        def __init__(self, cookies):
            raise AssertionError("cross-user comments must not instantiate adapter")

    db_dependency, _, account_id = _create_pc_account_with_cookie(tmp_path, "comments-cross-owner")
    intruder_token = _register_and_get_access_token("comments-cross-intruder")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcCommentAdapter
    try:
        anonymous_response = client.post(
            "/api/xhs/pc/notes/comments",
            json={"account_id": account_id, "note_url": "https://www.xiaohongshu.com/explore/comment-note-001"},
        )
        assert anonymous_response.status_code == 401

        intruder_response = client.post(
            "/api/xhs/pc/notes/comments",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"account_id": account_id, "note_url": "https://www.xiaohongshu.com/explore/comment-note-001"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_notes_batch_save_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post(
            "/api/notes/batch-save",
            json={"account_id": 1, "notes": [{"note_id": "note-001", "title": "标题"}]},
        )

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_batch_save_persists_owned_search_results_and_updates_duplicates(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import Note

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "save-owner")
    try:
        first_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "notes": [
                    {
                        "note_id": "note-save-001",
                        "title": "第一版标题",
                        "content": "第一版正文",
                        "author_name": "作者 A",
                        "raw": {"source": "search", "version": 1},
                    }
                ],
            },
        )
        assert first_response.status_code == 200
        first_payload = first_response.json()
        assert first_payload["saved_count"] == 1
        assert first_payload["items"][0]["note_id"] == "note-save-001"
        assert first_payload["items"][0]["title"] == "第一版标题"

        second_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "notes": [
                    {
                        "note_id": "note-save-001",
                        "title": "第二版标题",
                        "content": "第二版正文",
                        "author_name": "作者 B",
                        "raw": {"source": "search", "version": 2},
                    }
                ],
            },
        )
        assert second_response.status_code == 200
        assert second_response.json()["saved_count"] == 1

        db = next(app.dependency_overrides[get_db]())
        try:
            notes = db.query(Note).all()
            assert len(notes) == 1
            assert notes[0].platform == "xhs"
            assert notes[0].platform_account_id == account_id
            assert notes[0].note_id == "note-save-001"
            assert notes[0].title == "第二版标题"
            assert notes[0].content == "第二版正文"
            assert notes[0].author_name == "作者 B"
            assert notes[0].raw_json == {"source": "search", "version": 2}
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_batch_save_persists_detail_assets_and_lists_owned_assets(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import NoteAsset

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "save-assets-owner")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "notes": [
                    {
                        "note_id": "note-assets-001",
                        "title": "Asset detail title",
                        "content": "Asset detail body",
                        "author_name": "Asset author",
                        "image_urls": [
                            "https://example.test/detail-1.webp",
                            "https://example.test/detail-2.webp",
                        ],
                        "video_addr": "https://example.test/detail-video.mp4",
                        "cover_url": "https://example.test/detail-cover.webp",
                        "raw": {"source": "detail"},
                    }
                ],
            },
        )
        assert save_response.status_code == 200
        saved_payload = save_response.json()["items"][0]
        note_id = saved_payload["id"]
        assert saved_payload["cover_url"] == "https://example.test/detail-1.webp"
        assert saved_payload["asset_urls"] == [
            "https://example.test/detail-1.webp",
            "https://example.test/detail-2.webp",
            "https://example.test/detail-video.mp4",
        ]

        list_response = client.get(
            f"/api/notes/{note_id}/assets",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 3
        assert [(item["asset_type"], item["url"]) for item in payload["items"]] == [
            ("image", "https://example.test/detail-1.webp"),
            ("image", "https://example.test/detail-2.webp"),
            ("video", "https://example.test/detail-video.mp4"),
        ]

        note_detail_response = client.get(
            f"/api/notes/{note_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert note_detail_response.status_code == 200
        assert note_detail_response.json()["asset_urls"] == [
            "https://example.test/detail-1.webp",
            "https://example.test/detail-2.webp",
            "https://example.test/detail-video.mp4",
        ]

        update_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "notes": [
                    {
                        "note_id": "note-assets-001",
                        "title": "Asset detail title updated",
                        "image_urls": ["https://example.test/detail-2.webp"],
                    }
                ],
            },
        )
        assert update_response.status_code == 200

        db = next(app.dependency_overrides[get_db]())
        try:
            assets = db.query(NoteAsset).filter(NoteAsset.note_id == note_id).all()
            assert [(asset.asset_type, asset.url) for asset in assets] == [("image", "https://example.test/detail-2.webp")]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_assets_reject_cross_user_note(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "assets-owner")
    intruder_token = _register_and_get_access_token("assets-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "note-assets-cross-001",
                        "title": "Owner note",
                        "image_urls": ["https://example.test/owner.webp"],
                    }
                ],
            },
        )
        note_id = save_response.json()["items"][0]["id"]

        response = client.get(
            f"/api/notes/{note_id}/assets",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_batch_save_fetches_and_persists_comments(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import NoteComment

    class FakeXhsPcCommentPersistAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_comments(self, note_url):
            self.calls.append({"cookies": self.cookies, "note_url": note_url})
            return (
                True,
                "ok",
                {
                    "data": {
                        "comments": [
                            {
                                "id": "persist-comment-001",
                                "content": "Persisted top comment",
                                "like_count": "8",
                                "create_time": "2026-04-29 13:00:00",
                                "user_info": {"user_id": "persist-user-001", "nickname": "Persist author"},
                            }
                        ]
                    }
                },
            )

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "comment-persist-owner")
    FakeXhsPcCommentPersistAdapter.calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcCommentPersistAdapter
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "fetch_comments": True,
                "notes": [
                    {
                        "note_id": "note-comments-001",
                        "note_url": "https://www.xiaohongshu.com/explore/note-comments-001",
                        "title": "Comment note",
                    }
                ],
            },
        )
        assert save_response.status_code == 200
        note_id = save_response.json()["items"][0]["id"]
        assert FakeXhsPcCommentPersistAdapter.calls == [
            {
                "cookies": "a1=json-a1; web_session=json-session",
                "note_url": "https://www.xiaohongshu.com/explore/note-comments-001",
            }
        ]

        list_response = client.get(
            f"/api/notes/{note_id}/comments",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["comment_id"] == "persist-comment-001"
        assert payload["items"][0]["user_name"] == "Persist author"
        assert payload["items"][0]["user_id"] == "persist-user-001"
        assert payload["items"][0]["content"] == "Persisted top comment"
        assert payload["items"][0]["like_count"] == 8
        assert payload["items"][0]["parent_comment_id"] is None
        assert payload["items"][0]["created_at_remote"] == "2026-04-29 13:00:00"

        db = next(app.dependency_overrides[get_db]())
        try:
            comments = db.query(NoteComment).filter(NoteComment.note_id == note_id).all()
            assert len(comments) == 1
            assert comments[0].raw_json["id"] == "persist-comment-001"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_notes_batch_save_replaces_stale_comments_on_refetch(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeXhsPcCommentReplaceAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_comments(self, note_url):
            self.calls.append(note_url)
            comment_id = "stale-comment" if len(self.calls) == 1 else "fresh-comment"
            return (
                True,
                "ok",
                {"data": {"comments": [{"id": comment_id, "content": comment_id, "user_info": {"nickname": "User"}}]}},
            )

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "comment-replace-owner")
    FakeXhsPcCommentReplaceAdapter.calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcCommentReplaceAdapter
    try:
        for _ in range(2):
            save_response = client.post(
                "/api/notes/batch-save",
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "account_id": account_id,
                    "fetch_comments": True,
                    "notes": [
                        {
                            "note_id": "note-comments-replace-001",
                            "note_url": "https://www.xiaohongshu.com/explore/note-comments-replace-001",
                            "title": "Replace comments",
                        }
                    ],
                },
            )
            assert save_response.status_code == 200
        note_id = save_response.json()["items"][0]["id"]

        list_response = client.get(
            f"/api/notes/{note_id}/comments",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["comment_id"] == "fresh-comment"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_notes_comments_list_requires_auth_and_enforces_ownership(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeXhsPcCommentListAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_comments(self, note_url):
            return (
                True,
                "ok",
                {"data": {"comments": [{"id": "owned-comment", "content": "Owned", "user_info": {"nickname": "User"}}]}},
            )

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "comments-list-owner")
    intruder_token = _register_and_get_access_token("comments-list-intruder")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeXhsPcCommentListAdapter
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "fetch_comments": True,
                "notes": [
                    {
                        "note_id": "note-comments-owned-001",
                        "note_url": "https://www.xiaohongshu.com/explore/note-comments-owned-001",
                        "title": "Owned comment note",
                    }
                ],
            },
        )
        note_id = save_response.json()["items"][0]["id"]

        anonymous_response = client.get(f"/api/notes/{note_id}/comments")
        assert anonymous_response.status_code == 401

        intruder_response = client.get(
            f"/api/notes/{note_id}/comments",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)


def test_tags_crud_are_user_scoped_and_validate_duplicates(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        owner_token = _register_and_get_access_token("tags-crud-owner")
        intruder_token = _register_and_get_access_token("tags-crud-intruder")

        create_response = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "High value", "color": "#111111"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["name"] == "High value"
        assert created["color"] == "#111111"

        duplicate_response = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "High value", "color": "#ef4444"},
        )
        assert duplicate_response.status_code == 400

        owner_list_response = client.get(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_list_response.status_code == 200
        assert owner_list_response.json()["total"] == 1

        intruder_list_response = client.get(
            "/api/tags",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_list_response.status_code == 200
        assert intruder_list_response.json()["total"] == 0

        intruder_update_response = client.patch(
            f"/api/tags/{created['id']}",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"name": "Stolen"},
        )
        assert intruder_update_response.status_code == 404

        update_response = client.patch(
            f"/api/tags/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Rewrite queue", "color": "#2563eb"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Rewrite queue"
        assert update_response.json()["color"] == "#2563eb"

        intruder_delete_response = client.delete(
            f"/api/tags/{created['id']}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_delete_response.status_code == 404

        delete_response = client.delete(
            f"/api/tags/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json() == {"id": created["id"], "status": "deleted"}

        empty_list_response = client.get(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert empty_list_response.json()["total"] == 0
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_batch_tag_applies_and_removes_owned_tags(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "batch-tag-owner")
    try:
        first_tag = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Rewrite", "color": "#111111"},
        ).json()
        second_tag = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Benchmark", "color": "#2563eb"},
        ).json()
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "note-tags-001",
                        "title": "Tagged note",
                        "content": "Tag me",
                    }
                ],
            },
        )
        note_id = save_response.json()["items"][0]["id"]

        replace_response = client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "tag_ids": [first_tag["id"]], "mode": "replace"},
        )
        assert replace_response.status_code == 200
        assert replace_response.json()["updated_count"] == 1
        assert replace_response.json()["items"][0]["tags"] == [first_tag]

        add_response = client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "tag_ids": [second_tag["id"]], "mode": "add"},
        )
        assert add_response.status_code == 200
        assert [tag["name"] for tag in add_response.json()["items"][0]["tags"]] == ["Rewrite", "Benchmark"]

        remove_response = client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "tag_ids": [first_tag["id"]], "mode": "remove"},
        )
        assert remove_response.status_code == 200
        assert remove_response.json()["items"][0]["tags"] == [second_tag]

        detail_response = client.get(
            f"/api/notes/{note_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["tags"] == [second_tag]

        list_response = client.get(
            "/api/notes?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert list_response.status_code == 200
        assert list_response.json()["items"][0]["tags"] == [second_tag]
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_batch_tag_rejects_cross_user_note_or_tag(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "batch-tag-cross-owner")
    intruder_token = _register_and_get_access_token("batch-tag-cross-intruder")
    try:
        owner_tag = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Owner tag", "color": "#111111"},
        ).json()
        intruder_tag = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"name": "Intruder tag", "color": "#ef4444"},
        ).json()
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [{"note_id": "note-tags-cross-001", "title": "Owner note"}],
            },
        )
        note_id = save_response.json()["items"][0]["id"]

        intruder_note_response = client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"note_ids": [note_id], "tag_ids": [intruder_tag["id"]], "mode": "replace"},
        )
        assert intruder_note_response.status_code == 404

        owner_cross_tag_response = client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "tag_ids": [intruder_tag["id"]], "mode": "replace"},
        )
        assert owner_cross_tag_response.status_code == 404

        owner_valid_response = client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "tag_ids": [owner_tag["id"]], "mode": "replace"},
        )
        assert owner_valid_response.status_code == 200
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_batch_create_drafts_creates_owned_drafts_and_rejects_cross_user_notes(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "batch-drafts-owner")
    intruder_token = _register_and_get_access_token("batch-drafts-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {"note_id": "batch-draft-001", "title": "First source", "content": "First body"},
                    {"note_id": "batch-draft-002", "title": "Second source", "content": "Second body"},
                ],
            },
        )
        assert save_response.status_code == 200
        note_ids = [item["id"] for item in save_response.json()["items"]]

        response = client.post(
            "/api/notes/batch-create-drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": note_ids, "intent": "rewrite"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 2
        assert [item["title"] for item in payload["items"]] == ["First source", "Second source"]
        assert [item["body"] for item in payload["items"]] == ["First body", "Second body"]
        assert [item["source_note_id"] for item in payload["items"]] == note_ids

        intruder_response = client.post(
            "/api/notes/batch-create-drafts",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"note_ids": [note_ids[0]], "intent": "rewrite"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_export_writes_json_for_owned_notes_and_rejects_cross_user_notes(tmp_path):
    import json
    from pathlib import Path

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "notes-export-owner")
    intruder_token = _register_and_get_access_token("notes-export-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "export-note-001",
                        "title": "Exported note",
                        "content": "Export body",
                        "author_name": "Export author",
                        "raw": {"source": "unit-test"},
                    }
                ],
            },
        )
        assert save_response.status_code == 200
        note_id = save_response.json()["items"][0]["id"]
        tag_response = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Export", "color": "#111111"},
        )
        client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "tag_ids": [tag_response.json()["id"]], "mode": "replace"},
        )

        response = client.post(
            "/api/notes/export",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "format": "json"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["exported_count"] == 1
        assert payload["file_name"].endswith(".json")
        assert f"u{1}-" in payload["file_name"]
        export_path = Path(payload["file_path"])
        assert export_path.exists()
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        assert exported["items"][0]["note_id"] == "export-note-001"
        assert exported["items"][0]["tags"][0]["name"] == "Export"

        download_response = client.get(
            payload["download_url"],
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert download_response.status_code == 200
        assert download_response.json()["items"][0]["note_id"] == "export-note-001"

        intruder_download_response = client.get(
            payload["download_url"],
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_download_response.status_code == 404

        intruder_response = client.post(
            "/api/notes/export",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"note_ids": [note_id], "format": "json"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_export_writes_csv_for_owned_notes(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "notes-export-csv-owner")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "export-csv-001",
                        "title": "CSV 标题",
                        "content": "CSV 正文",
                        "author_name": "CSV 作者",
                    }
                ],
            },
        )
        note_id = save_response.json()["items"][0]["id"]

        response = client.post(
            "/api/notes/export",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [note_id], "format": "csv"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["file_name"].endswith(".csv")
        download_response = client.get(
            payload["download_url"],
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert download_response.status_code == 200
        csv_text = download_response.content.decode("utf-8-sig")
        assert "note_id,title,author_name,content,tags,created_at" in csv_text
        assert "export-csv-001" in csv_text
        assert "CSV 标题" in csv_text
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_analytics_uses_current_user_saved_notes_tags_and_comments(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import NoteComment

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "analytics-owner")
    intruder_token = _register_and_get_access_token("analytics-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "analytics-note-001",
                        "title": "高互动早餐笔记",
                        "content": "早餐选题正文",
                        "author_name": "早餐作者",
                        "raw": {"likes": 100, "collects": 30, "comments": 12, "shares": 8, "tags": ["早餐", "低卡"]},
                    },
                    {
                        "note_id": "analytics-note-002",
                        "title": "普通收纳笔记",
                        "content": "收纳正文",
                        "author_name": "收纳作者",
                        "raw": {"likes": 10, "collects": 2, "comments": 1, "shares": 0, "tags": ["收纳"]},
                    },
                ],
            },
        )
        assert save_response.status_code == 200
        first_note_id = save_response.json()["items"][0]["id"]
        tag_response = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "早餐", "color": "#111111"},
        )
        client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [first_note_id], "tag_ids": [tag_response.json()["id"]], "mode": "add"},
        )
        db = next(app.dependency_overrides[get_db]())
        try:
            db.add(
                NoteComment(
                    note_id=first_note_id,
                    comment_id="analytics-comment-001",
                    user_name="用户 A",
                    content="这个早餐适合通勤吗？价格会不会高？",
                    like_count=9,
                )
            )
            db.commit()
        finally:
            db.close()

        overview_response = client.get(
            "/api/xhs/analytics/overview",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert overview_response.status_code == 200
        overview = overview_response.json()
        assert overview["platform"] == "xhs"
        assert overview["saved_notes"] == 2
        assert overview["total_engagement"] == 163
        assert overview["comment_count"] == 1
        assert overview["hot_topics"][0]["keyword"] == "早餐"

        top_response = client.get(
            "/api/xhs/analytics/top-content",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert top_response.status_code == 200
        top_items = top_response.json()["items"]
        assert [item["note_id"] for item in top_items] == ["analytics-note-001", "analytics-note-002"]
        assert top_items[0]["engagement"] == 150

        topics_response = client.get(
            "/api/xhs/analytics/hot-topics",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert topics_response.status_code == 200
        topics = topics_response.json()["items"]
        assert topics[0]["keyword"] == "早餐"
        assert topics[0]["notes"] == 1
        assert topics[0]["engagement"] == 150

        comments_response = client.get(
            "/api/xhs/analytics/comment-insights",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert comments_response.status_code == 200
        comments = comments_response.json()
        assert comments["total_comments"] == 1
        assert comments["question_count"] == 1
        assert comments["top_comments"][0]["content"] == "这个早餐适合通勤吗？价格会不会高？"

        intruder_response = client.get(
            "/api/xhs/analytics/overview",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 200
        assert intruder_response.json()["saved_notes"] == 0
        assert intruder_response.json()["total_engagement"] == 0
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_analytics_benchmarks_are_user_scoped_from_monitoring_targets(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import MonitoringTarget

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "benchmark-owner")
    intruder_token = _register_and_get_access_token("benchmark-intruder")
    try:
        anonymous_response = client.get("/api/xhs/analytics/benchmarks")
        assert anonymous_response.status_code == 401

        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "benchmark-note-account",
                        "title": "竞品账号低卡早餐",
                        "content": "creator-001 的早餐选题",
                        "author_name": "creator-001",
                        "raw": {"likes": 80, "collects": 12, "comments": 6, "shares": 2},
                    },
                    {
                        "note_id": "benchmark-note-brand",
                        "title": "BrandA 收纳爆文",
                        "content": "BrandA 新品收纳角度",
                        "author_name": "brand-author",
                        "raw": {"likes": 30, "collects": 10, "comments": 4, "shares": 1},
                    },
                    {
                        "note_id": "benchmark-note-keyword-only",
                        "title": "低卡早餐普通趋势",
                        "content": "低卡早餐关键词命中但不是竞品目标",
                        "author_name": "trend-author",
                        "raw": {"likes": 300},
                    },
                ],
            },
        )
        assert save_response.status_code == 200
        db = next(app.dependency_overrides[get_db]())
        try:
            db.add_all(
                [
                    MonitoringTarget(
                        user_id=1,
                        platform="xhs",
                        target_type="account",
                        name="竞品账号",
                        value="creator-001",
                        status="active",
                    ),
                    MonitoringTarget(
                        user_id=1,
                        platform="xhs",
                        target_type="brand",
                        name="BrandA",
                        value="BrandA",
                        status="active",
                    ),
                    MonitoringTarget(
                        user_id=1,
                        platform="xhs",
                        target_type="keyword",
                        name="低卡早餐",
                        value="低卡早餐",
                        status="active",
                    ),
                    MonitoringTarget(
                        user_id=2,
                        platform="xhs",
                        target_type="account",
                        name="Other account",
                        value="creator-001",
                        status="active",
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

        response = client.get(
            "/api/xhs/analytics/benchmarks",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_targets"] == 2
        assert payload["matched_notes"] == 2
        assert payload["total_engagement"] == 145
        assert [item["target_type"] for item in payload["items"]] == ["account", "brand"]
        assert payload["items"][0]["name"] == "竞品账号"
        assert payload["items"][0]["matched_notes"] == 1
        assert payload["items"][0]["total_engagement"] == 100
        assert payload["items"][0]["top_notes"][0]["note_id"] == "benchmark-note-account"
        assert payload["items"][1]["name"] == "BrandA"
        assert payload["items"][1]["total_engagement"] == 45

        intruder_response = client.get(
            "/api/xhs/analytics/benchmarks",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 200
        assert intruder_response.json()["total_targets"] == 1
        assert intruder_response.json()["matched_notes"] == 0
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_benchmark_create_drafts_uses_owned_target_matches(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import AiDraft, MonitoringTarget

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "benchmark-draft-owner")
    intruder_token = _register_and_get_access_token("benchmark-draft-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "benchmark-draft-note-001",
                        "title": "creator-002 爆款标题",
                        "content": "creator-002 的爆款正文",
                        "author_name": "creator-002",
                        "raw": {"likes": 90},
                    },
                    {
                        "note_id": "benchmark-draft-note-002",
                        "title": "creator-002 第二篇",
                        "content": "creator-002 的第二篇正文",
                        "author_name": "creator-002",
                        "raw": {"likes": 40},
                    },
                    {
                        "note_id": "benchmark-draft-note-other",
                        "title": "其他账号内容",
                        "content": "不该命中",
                        "author_name": "other",
                        "raw": {"likes": 500},
                    },
                ],
            },
        )
        assert save_response.status_code == 200
        db = next(app.dependency_overrides[get_db]())
        try:
            target = MonitoringTarget(
                user_id=1,
                platform="xhs",
                target_type="account",
                name="creator-002",
                value="creator-002",
                status="active",
            )
            keyword_target = MonitoringTarget(
                user_id=1,
                platform="xhs",
                target_type="keyword",
                name="普通关键词",
                value="creator-002",
                status="active",
            )
            intruder_target = MonitoringTarget(
                user_id=2,
                platform="xhs",
                target_type="account",
                name="intruder target",
                value="creator-002",
                status="active",
            )
            db.add_all([target, keyword_target, intruder_target])
            db.commit()
            target_id = target.id
            keyword_target_id = keyword_target.id
        finally:
            db.close()

        anonymous_response = client.post(f"/api/xhs/analytics/benchmarks/{target_id}/create-drafts")
        assert anonymous_response.status_code == 401

        intruder_response = client.post(
            f"/api/xhs/analytics/benchmarks/{target_id}/create-drafts",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404

        keyword_response = client.post(
            f"/api/xhs/analytics/benchmarks/{keyword_target_id}/create-drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert keyword_response.status_code == 400

        response = client.post(
            f"/api/xhs/analytics/benchmarks/{target_id}/create-drafts?limit=1",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 1
        assert payload["items"][0]["title"] == "creator-002 爆款标题"
        assert payload["items"][0]["source_note_id"] == save_response.json()["items"][0]["id"]

        db = next(app.dependency_overrides[get_db]())
        try:
            drafts = db.query(AiDraft).all()
            assert len(drafts) == 1
            assert drafts[0].user_id == 1
            assert drafts[0].platform == "xhs"
            assert drafts[0].body == "creator-002 的爆款正文"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_analytics_report_generates_owned_json_export_and_rejects_cross_user_notes(tmp_path):
    import json
    from pathlib import Path

    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "analytics-report-owner")
    intruder_token = _register_and_get_access_token("analytics-report-intruder")
    try:
        anonymous_response = client.post("/api/xhs/analytics/reports")
        assert anonymous_response.status_code == 401

        owner_save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "analytics-report-note-001",
                        "title": "Report note one",
                        "content": "Breakfast content with BrandA",
                        "author_name": "creator-report",
                        "raw": {"likes": 20, "collects": 5, "comments": 3, "shares": 2, "tags": ["breakfast"]},
                    },
                    {
                        "note_id": "analytics-report-note-002",
                        "title": "Report note two",
                        "content": "Storage content",
                        "author_name": "creator-report",
                        "raw": {"likes": 10, "collects": 1, "comments": 0, "shares": 0, "tags": ["storage"]},
                    },
                ],
            },
        )
        assert owner_save_response.status_code == 200
        owner_note_ids = [item["id"] for item in owner_save_response.json()["items"]]

        db = next(app.dependency_overrides[get_db]())
        try:
            intruder_account = PlatformAccount(
                user_id=2,
                platform="xhs",
                sub_type="pc",
                external_user_id="analytics-report-intruder",
                nickname="Intruder",
                status="active",
            )
            db.add(intruder_account)
            db.commit()
            intruder_account_id = intruder_account.id
        finally:
            db.close()

        intruder_save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={
                "account_id": intruder_account_id,
                "notes": [
                    {
                        "note_id": "analytics-report-intruder-note",
                        "title": "Intruder note",
                        "content": "Not visible to owner",
                        "author_name": "intruder",
                        "raw": {"likes": 999},
                    }
                ],
            },
        )
        assert intruder_save_response.status_code == 200
        intruder_note_id = intruder_save_response.json()["items"][0]["id"]

        forbidden_response = client.post(
            "/api/xhs/analytics/reports",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [owner_note_ids[0], intruder_note_id], "format": "json"},
        )
        assert forbidden_response.status_code == 404

        report_response = client.post(
            "/api/xhs/analytics/reports",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": owner_note_ids, "format": "json"},
        )
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["report_type"] == "operations"
        assert report["note_count"] == 2
        assert report["summary"]["total_engagement"] == 41
        assert report["summary"]["top_notes"][0]["note_id"] == "analytics-report-note-001"
        assert report["file_name"].startswith("xhs-report-u1-")
        assert report["download_url"].startswith("/api/files/exports/xhs-report-u1-")

        report_path = Path(report["file_path"])
        assert report_path.is_file()
        report_file = json.loads(report_path.read_text(encoding="utf-8"))
        assert report_file["metadata"]["user_id"] == 1
        assert report_file["summary"]["note_count"] == 2
        assert report_file["top_notes"][0]["title"] == "Report note one"

        download_response = client.get(
            report["download_url"],
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert download_response.status_code == 200
        assert download_response.json()["metadata"]["report_type"] == "operations"

        intruder_download_response = client.get(
            report["download_url"],
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_download_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_crawl_routes_are_authenticated_task_backed_and_persist_notes(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Note, NoteAsset, Task

    class FakeCrawlAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def search_note(self, keyword, page=1, **kwargs):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "crawl-search-001",
                                "display_title": f"{keyword} search title",
                                "desc": "search content",
                                "user": {"nickname": "search author"},
                                "interact_info": {"liked_count": 12, "collected_count": 3, "comment_count": 2},
                                "cover": {"url": "https://img.example/search.png"},
                            }
                        }
                    ],
                    "total": 1,
                    "has_more": False,
                }
            }

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "crawl-url-001",
                                "display_title": "url detail title",
                                "desc": "url detail body",
                                "user": {"nickname": "url author"},
                                "interact_info": {"liked_count": 30},
                                "image_list": [{"url": "https://img.example/url-1.png"}],
                            }
                        }
                    ]
                }
            }

        def get_user_notes(self, user_url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "crawl-user-001",
                                "display_title": "user note title",
                                "desc": "user note body",
                                "user": {"nickname": "profile author"},
                                "interact_info": {"liked_count": 7},
                                "cover": {"url": "https://img.example/user.png"},
                            }
                        }
                    ],
                    "total": 1,
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "crawl-routes-owner")
    intruder_token = _register_and_get_access_token("crawl-routes-intruder")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeCrawlAdapter
    try:
        anonymous_response = client.post(
            "/api/xhs/crawl/search-notes",
            json={"account_id": owner_account_id, "keyword": "breakfast"},
        )
        assert anonymous_response.status_code == 401

        intruder_response = client.post(
            "/api/xhs/crawl/search-notes",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"account_id": owner_account_id, "keyword": "breakfast"},
        )
        assert intruder_response.status_code == 404

        search_response = client.post(
            "/api/xhs/crawl/search-notes",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": owner_account_id, "keyword": "breakfast", "page": 1},
        )
        assert search_response.status_code == 200
        search_payload = search_response.json()
        assert search_payload["task"]["task_type"] == "crawl"
        assert search_payload["task"]["status"] == "completed"
        assert search_payload["saved_count"] == 0
        assert search_payload["skipped_low_quality_count"] == 1
        assert "raw" not in search_payload
        assert search_payload["skipped_items"][0]["note_id"] == "crawl-search-001"
        assert search_payload["skipped_items"][0]["save_diagnostic_kind"] == "save_skipped_low_quality"
        _assert_no_private_payload_keys(search_payload)

        url_response = client.post(
            "/api/xhs/crawl/note-urls",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": owner_account_id, "urls": ["https://www.xiaohongshu.com/explore/crawl-url-001?xsec_token=crawl-token"]},
        )
        assert url_response.status_code == 200
        url_payload = url_response.json()
        assert url_payload["saved_count"] == 1
        assert url_payload["items"][0]["note_id"] == "crawl-url-001"
        assert "raw_json" not in url_payload["items"][0]

        user_response = client.post(
            "/api/xhs/crawl/user-notes",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": owner_account_id, "user_url": "https://www.xiaohongshu.com/user/profile/demo"},
        )
        assert user_response.status_code == 200
        user_payload = user_response.json()
        assert user_payload["saved_count"] == 0
        assert user_payload["skipped_low_quality_count"] == 1
        assert "raw" not in user_payload
        assert user_payload["skipped_items"][0]["note_id"] == "crawl-user-001"
        _assert_no_private_payload_keys(user_payload)

        db = next(app.dependency_overrides[get_db]())
        try:
            tasks = db.query(Task).filter(Task.task_type == "crawl").all()
            notes = db.query(Note).order_by(Note.note_id.asc()).all()
            assets = db.query(NoteAsset).all()
            assert len(tasks) == 3
            assert all(task.user_id == 1 and task.status == "completed" for task in tasks)
            assert [note.note_id for note in notes] == ["crawl-url-001"]
            assert len(assets) == 1
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_keyword_group_crawl_streams_human_summary_and_saves_valid_detail(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import KeywordGroup, Note

    class FakeKeywordGroupCrawlAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def search_note(self, keyword, page=1, **kwargs):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "kg-valid-001",
                                "display_title": f"{keyword} 搜索卡片",
                                "desc": "搜索摘要",
                                "xsec_token": "kg-token-001",
                                "user": {"nickname": "早餐研究员"},
                                "interact_info": {"liked_count": 12, "collected_count": 3, "comment_count": 1},
                                "cover": {"url": "https://img.example/kg-cover.png"},
                            }
                        },
                        {
                            "note_card": {
                                "note_id": "kg-short-001",
                                "display_title": "缺参数卡片",
                                "desc": "只有短链",
                                "user": {"nickname": "短链作者"},
                            }
                        },
                    ],
                    "has_more": False,
                }
            }

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "kg-valid-001",
                                "display_title": "低卡早餐详情",
                                "desc": "鸡蛋、燕麦和酸奶的低卡早餐搭配。",
                                "user": {"nickname": "早餐研究员"},
                                "interact_info": {"liked_count": 88, "collected_count": 21, "comment_count": 5},
                                "image_list": [{"url": "https://img.example/kg-detail.png"}],
                                "tag_list": [{"name": "低卡早餐"}],
                            }
                        }
                    ]
                }
            }

        def get_note_comments(self, note_url):
            return True, "ok", {"data": {"comments": []}}

    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "keyword-group-crawl-owner")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeKeywordGroupCrawlAdapter
    db = next(app.dependency_overrides[get_db]())
    try:
        group = KeywordGroup(user_id=1, platform="xhs", name="早餐热词", keywords=["低卡早餐"])
        db.add(group)
        db.commit()
        group_id = group.id
    finally:
        db.close()

    try:
        response = client.post(
            "/api/xhs/crawl/keyword-group",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"account_id": account_id, "keyword_group_id": group_id, "keyword_limit": 1, "max_notes_per_keyword": 2, "time_sleep": 0},
        )
        assert response.status_code == 200
        parsed = _parse_sse_response(response)
        assert parsed["saved_count"] == 1
        assert parsed["skipped_count"] >= 1
        assert parsed["missing_detail_count"] >= 1
        assert parsed["summary_message"].startswith("采集完成")
        assert any(item.get("keyword") == "低卡早餐" for item in parsed["items"])
        assert any(item.get("saved") is True for item in parsed["items"])
        _assert_no_private_payload_keys(parsed["items"])

        db = next(app.dependency_overrides[get_db]())
        try:
            notes = db.query(Note).filter(Note.note_id == "kg-valid-001").all()
            assert len(notes) == 1
            assert notes[0].title == "低卡早餐详情"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_crawl_raw_payload_is_admin_only(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount, User

    class FakeRawCrawlAdapter(FakeXhsPcSearchAdapter):
        pass

    db_dependency, normal_token, normal_account_id = _create_pc_account_with_cookie(tmp_path, "crawl-raw-normal")
    admin_token = _register_and_get_admin_access_token("crawl-raw-admin")
    db = next(app.dependency_overrides[get_db]())
    try:
        admin = db.scalar(select(User).where(User.username == "crawl-raw-admin"))
        assert admin is not None
        admin_account = PlatformAccount(
            user_id=admin.id,
            platform="xhs",
            sub_type="pc",
            external_user_id="crawl-admin-pc",
            nickname="crawl admin pc",
            status="active",
        )
        db.add(admin_account)
        db.flush()
        db.add(
            AccountCookieVersion(
                platform_account_id=admin_account.id,
                encrypted_cookies=encrypt_text('{"a1":"admin-a1","web_session":"admin-session"}'),
            )
        )
        db.commit()
        admin_account_id = admin_account.id
    finally:
        db.close()

    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeRawCrawlAdapter
    try:
        normal_response = client.post(
            "/api/xhs/crawl/search-notes",
            headers={"Authorization": f"Bearer {normal_token}"},
            json={"account_id": normal_account_id, "keyword": "breakfast", "save_to_library": False},
        )
        assert normal_response.status_code == 200
        normal_payload = normal_response.json()
        assert "raw" not in normal_payload

        admin_response = client.post(
            "/api/xhs/crawl/search-notes",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"account_id": admin_account_id, "keyword": "breakfast", "save_to_library": False},
        )
        assert admin_response.status_code == 200
        admin_payload = admin_response.json()
        assert admin_payload["raw"]["success"] is True
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)



def test_xhs_data_crawl_marks_partial_failures_and_fetches_comments(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeDataCrawlAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_info(self, url):
            self.__class__.calls.append(("detail", url))
            if "bad" in url:
                return False, "detail failed", {}
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-url-001",
                                "display_title": "data crawl detail",
                                "desc": "detail body",
                                "user": {"nickname": "detail author"},
                                "interact_info": {"liked_count": 8, "comment_count": 1},
                                "image_list": [{"url": "https://img.example/data-url.png"}],
                            }
                        }
                    ]
                }
            }

        def get_note_comments(self, url):
            self.__class__.calls.append(("comments", url))
            return True, "ok", {
                "data": {
                    "comments": [
                        {
                            "id": "comment-001",
                            "content": "想看更多",
                            "user_info": {"nickname": "reader"},
                            "like_count": "3",
                        }
                    ]
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-owner")
    FakeDataCrawlAdapter.calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeDataCrawlAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "note_urls",
                "urls": [
                    "https://www.xiaohongshu.com/explore/data-url-001?xsec_token=data-token",
                    "https://www.xiaohongshu.com/explore/bad-url?xsec_token=bad-token",
                ],
                "fetch_comments": True,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["total"] == 2
        assert payload["success_count"] == 1
        assert payload["failed_count"] == 1
        assert payload["items"][0]["status"] == "success"
        assert payload["items"][0]["note"]["note_id"] == "data-url-001"
        assert payload["items"][0]["comment_count"] == 1
        assert payload["items"][0]["comments"][0]["content"] == "想看更多"
        assert payload["items"][1]["status"] == "failed"
        assert payload["items"][1]["error"] == "detail failed"
        assert ("comments", "https://www.xiaohongshu.com/explore/data-url-001?xsec_token=data-token") in FakeDataCrawlAdapter.calls
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_data_crawl_note_urls_saves_notes_and_fetched_comments(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Note, NoteComment

    class FakeDataCrawlSaveAdapter:
        comment_calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-save-url-001",
                                "display_title": "saved data crawl detail",
                                "desc": "saved detail body",
                                "user": {"nickname": "saved detail author"},
                                "interact_info": {"liked_count": 8, "comment_count": 1},
                                "image_list": [{"url": "https://img.example/data-save-url.png"}],
                            }
                        }
                    ]
                }
            }

        def get_note_comments(self, url):
            self.__class__.comment_calls.append(url)
            return True, "ok", {
                "data": {
                    "comments": [
                        {
                            "id": "data-save-comment-001",
                            "content": "保存后的评论",
                            "user_info": {"nickname": "comment author", "user_id": "comment-user"},
                            "like_count": "3",
                        }
                    ]
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-save-url-owner")
    FakeDataCrawlSaveAdapter.comment_calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeDataCrawlSaveAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "note_urls",
                "urls": ["https://www.xiaohongshu.com/explore/data-save-url-001?xsec_token=data-token"],
                "fetch_comments": True,
                "comment_sleep": 0,
                "save_to_library": True,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["success_count"] == 1
        assert payload["saved_count"] == 1
        assert payload["skipped_count"] == 0
        assert payload["items"][0]["saved"] is True
        assert payload["items"][0]["comment_count"] == 1

        db = next(app.dependency_overrides[get_db]())
        try:
            note = db.query(Note).filter(Note.note_id == "data-save-url-001").one()
            assert note.title == "saved data crawl detail"
            assert note.content == "saved detail body"
            comments = db.query(NoteComment).filter(NoteComment.note_id == note.id).all()
            assert len(comments) == 1
            assert comments[0].comment_id == "data-save-comment-001"
            assert comments[0].content == "保存后的评论"
        finally:
            db.close()
        assert FakeDataCrawlSaveAdapter.comment_calls == ["https://www.xiaohongshu.com/explore/data-save-url-001?xsec_token=data-token"]
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)



def test_xhs_data_crawl_search_saves_valid_detail_note(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Note

    class FakeSearchSaveAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def search_note(self, keyword, page=1, **kwargs):
            return True, "ok", {
                "data": {
                    "has_more": False,
                    "items": [
                        {
                            "xsec_token": "xsec-data-save-search",
                            "note_card": {
                                "note_id": "data-save-search-001",
                                "display_title": "search source title",
                                "desc": "search source body",
                                "user": {"nickname": "search author"},
                            },
                        }
                    ],
                }
            }

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-save-search-001",
                                "display_title": "saved search detail",
                                "desc": "saved search detail body",
                                "user": {"nickname": "saved search author"},
                                "image_list": [{"url": "https://img.example/data-save-search.png"}],
                            }
                        }
                    ]
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-save-search-owner")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeSearchSaveAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "search",
                "keyword": "保存测试",
                "pages": 1,
                "max_notes": 1,
                "save_to_library": True,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["success_count"] == 1
        assert payload["saved_count"] == 1
        assert payload["items"][0]["saved"] is True

        db = next(app.dependency_overrides[get_db]())
        try:
            note = db.query(Note).filter(Note.note_id == "data-save-search-001").one()
            assert note.title == "saved search detail"
            assert note.author_name == "saved search author"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)



def test_xhs_data_crawl_does_not_save_when_save_to_library_is_false(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Note

    class FakeNoSaveAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-no-save-001",
                                "display_title": "not saved title",
                                "desc": "not saved body",
                                "user": {"nickname": "not saved author"},
                                "image_list": [{"url": "https://img.example/no-save.png"}],
                            }
                        }
                    ]
                }
            }

        def get_note_comments(self, url):
            return True, "ok", {"data": {"comments": [{"id": "no-save-comment", "content": "not saved"}]}}

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-no-save-owner")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeNoSaveAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "note_urls",
                "urls": ["https://www.xiaohongshu.com/explore/data-no-save-001?xsec_token=data-token"],
                "fetch_comments": True,
                "comment_sleep": 0,
                "save_to_library": False,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["success_count"] == 1
        assert payload["saved_count"] == 0
        assert payload["items"][0]["saved"] is False
        assert payload["items"][0]["comment_count"] == 1

        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.query(Note).filter(Note.note_id == "data-no-save-001").count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)



def test_xhs_data_crawl_search_detail_rate_limit_stops_following_pages(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeDetailRateLimitedSearchAdapter:
        search_calls = []
        detail_calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def search_note(self, keyword, page=1, **kwargs):
            self.__class__.search_calls.append({"keyword": keyword, "page": page, **kwargs})
            return True, "ok", {
                "data": {
                    "has_more": page == 1,
                    "items": [
                        {
                            "xsec_token": "xsec-detail-rate-001",
                            "note_card": {
                                "note_id": "detail-rate-note-001",
                                "display_title": "detail rate source",
                                "desc": "detail rate source body",
                                "user": {"nickname": "detail rate author"},
                            },
                        }
                    ] if page == 1 else [],
                }
            }

        def get_note_info(self, url):
            self.__class__.detail_calls.append(url)
            return False, "300013 访问频繁，请稍后再试", {}

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-detail-rate-owner")
    FakeDetailRateLimitedSearchAdapter.search_calls = []
    FakeDetailRateLimitedSearchAdapter.detail_calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeDetailRateLimitedSearchAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "search",
                "keyword": "浴室",
                "pages": 2,
                "max_notes": 5,
                "save_to_library": True,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["total"] == 1
        assert payload["items"][0]["status"] == "failed"
        assert (
            payload["items"][0].get("quality_status") == "rate_limited"
            or payload["items"][0].get("diagnostic_kind") == "xhs_rate_limited"
        )
        assert [call["page"] for call in FakeDetailRateLimitedSearchAdapter.search_calls] == [1]
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)



def test_xhs_data_crawl_search_comment_rate_limit_keeps_notes_successful(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeCommentRateLimitedSearchAdapter:
        search_calls = []
        detail_calls = []
        comment_calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def search_note(self, keyword, page=1, **kwargs):
            self.__class__.search_calls.append({"keyword": keyword, "page": page, **kwargs})
            return True, "ok", {
                "data": {
                    "has_more": False,
                    "items": [
                        {
                            "xsec_token": "xsec-rate-001",
                            "note_card": {
                                "note_id": "rate-note-001",
                                "display_title": "rate source 1",
                                "desc": "rate source body 1",
                                "user": {"nickname": "rate author"},
                            },
                        },
                        {
                            "xsec_token": "xsec-rate-002",
                            "note_card": {
                                "note_id": "rate-note-002",
                                "display_title": "rate source 2",
                                "desc": "rate source body 2",
                                "user": {"nickname": "rate author"},
                            },
                        },
                    ],
                }
            }

        def get_note_info(self, url):
            self.__class__.detail_calls.append(url)
            note_id = url.split("/explore/")[1].split("?")[0]
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": note_id,
                                "display_title": f"detail {note_id}",
                                "desc": f"detail body {note_id}",
                                "user": {"nickname": "detail author"},
                            }
                        }
                    ]
                }
            }

        def get_note_comments(self, url):
            self.__class__.comment_calls.append(url)
            return False, "300013 访问频繁，请稍后再试", {}

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-comment-rate-owner")
    FakeCommentRateLimitedSearchAdapter.search_calls = []
    FakeCommentRateLimitedSearchAdapter.detail_calls = []
    FakeCommentRateLimitedSearchAdapter.comment_calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeCommentRateLimitedSearchAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "search",
                "keyword": "浴室",
                "pages": 1,
                "max_notes": 2,
                "fetch_comments": True,
                "comment_sleep": 0,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["total"] == 2
        assert payload["success_count"] == 2
        assert payload["failed_count"] == 0
        assert payload["comment_rate_limited_count"] == 1
        assert payload["comment_skipped_count"] == 1
        assert [item["status"] for item in payload["items"]] == ["success", "success"]
        assert payload["items"][0]["comment_status"] == "rate_limited"
        assert "访问频繁" in payload["items"][0]["comment_error"]
        assert payload["items"][1]["comment_status"] == "skipped_rate_limited"
        assert "已跳过" in payload["items"][1]["comment_error"]
        assert len(FakeCommentRateLimitedSearchAdapter.detail_calls) == 2
        assert len(FakeCommentRateLimitedSearchAdapter.comment_calls) == 1
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_crawler_page_has_independent_comment_sleep_control():
    source = open("frontend/src/pages/platforms/xhs/crawler-page.tsx", encoding="utf-8").read()

    assert "commentSleep" in source
    assert "评论间隔（秒）" in source
    assert "comment_sleep" in source


def test_xhs_data_crawl_search_expands_filters_and_fetches_details(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeSearchDataCrawlAdapter:
        search_calls = []
        detail_calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def search_note(self, keyword, page=1, **kwargs):
            self.__class__.search_calls.append({"keyword": keyword, "page": page, **kwargs})
            return True, "ok", {
                "data": {
                    "has_more": False,
                    "items": [
                        {
                            "xsec_token": "xsec-data-search",
                            "note_card": {
                                "note_id": "data-search-001",
                                "display_title": "search source title",
                                "desc": "search source body",
                                "user": {"nickname": "search author"},
                                "interact_info": {"liked_count": 12},
                                "cover": {"url": "https://img.example/search.png"},
                            },
                        }
                    ],
                }
            }

        def get_note_info(self, url):
            self.__class__.detail_calls.append(url)
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-search-001",
                                "display_title": "detail title",
                                "desc": "detail body",
                                "user": {"nickname": "detail author"},
                                "interact_info": {"liked_count": 88},
                                "image_list": [{"url": "https://img.example/detail.png"}],
                            }
                        }
                    ]
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-search-owner")
    FakeSearchDataCrawlAdapter.search_calls = []
    FakeSearchDataCrawlAdapter.detail_calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeSearchDataCrawlAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "search",
                "keyword": "低卡早餐",
                "pages": 1,
                "max_notes": 5,
                "sort_type_choice": 2,
                "note_type": 2,
                "note_time": 1,
                "note_range": 3,
                "pos_distance": 1,
                "geo": "31.2304,121.4737",
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["success_count"] == 1
        assert payload["items"][0]["note"]["title"] == "detail title"
        assert FakeSearchDataCrawlAdapter.search_calls == [
            {
                "keyword": "低卡早餐",
                "page": 1,
                "sort_type_choice": 2,
                "note_type": 2,
                "note_time": 1,
                "note_range": 3,
                "pos_distance": 1,
                "geo": "31.2304,121.4737",
            }
        ]
        assert FakeSearchDataCrawlAdapter.detail_calls == [
            "https://www.xiaohongshu.com/explore/data-search-001?xsec_token=xsec-data-search&xsec_source=pc_feed"
        ]
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_analytics_keyword_trends_are_user_scoped_from_keyword_groups(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import KeywordGroup

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "keyword-trends-owner")
    intruder_token = _register_and_get_access_token("keyword-trends-intruder")
    try:
        anonymous_response = client.get("/api/xhs/analytics/keyword-trends")
        assert anonymous_response.status_code == 401

        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "keyword-trend-note-001",
                        "title": "Breakfast angle",
                        "content": "Low calorie breakfast for commute",
                        "author_name": "trend author",
                        "raw": {"likes": 20, "collects": 5, "comments": 1, "shares": 0},
                    },
                    {
                        "note_id": "keyword-trend-note-002",
                        "title": "Storage angle",
                        "content": "Closet storage checklist",
                        "author_name": "trend author",
                        "raw": {"likes": 10, "collects": 2},
                    },
                ],
            },
        )
        assert save_response.status_code == 200

        db = next(app.dependency_overrides[get_db]())
        try:
            db.add_all(
                [
                    KeywordGroup(user_id=1, platform="xhs", name="Owner ideas", keywords=["breakfast", "storage"]),
                    KeywordGroup(user_id=2, platform="xhs", name="Intruder ideas", keywords=["breakfast"]),
                ]
            )
            db.commit()
        finally:
            db.close()

        owner_response = client.get(
            "/api/xhs/analytics/keyword-trends",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        owner_items = owner_response.json()["items"]
        assert [item["keyword"] for item in owner_items] == ["breakfast", "storage"]
        assert owner_items[0]["group_name"] == "Owner ideas"
        assert owner_items[0]["notes"] == 1
        assert owner_items[0]["engagement"] == 26
        assert owner_items[0]["top_notes"][0]["note_id"] == "keyword-trend-note-001"
        assert owner_items[1]["engagement"] == 12

        intruder_response = client.get(
            "/api/xhs/analytics/keyword-trends",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 200
        assert intruder_response.json()["items"][0]["keyword"] == "breakfast"
        assert intruder_response.json()["items"][0]["notes"] == 0
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_creator_routes_use_owned_creator_account_and_record_tasks(tmp_path):
    from backend.app.api.platforms.xhs.creator import get_creator_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Task

    class FakeCreatorRoutesAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def get_topic(self, keyword):
            return True, "ok", {"data": {"items": [{"id": "topic-creator", "name": keyword}]}, "provider_secret": "topic-secret"}

        def get_location_info(self, keyword):
            return True, "ok", {"data": {"items": [{"id": "loc-creator", "name": keyword}]}, "provider_secret": "loc-secret"}

        def upload_media(self, file_path, media_type):
            return {"fileIds": "file-creator-001", "width": 1080, "height": 1440, "media_type": media_type}

        def post_note(self, note_info):
            return {"success": True, "data": {"note_id": "creator-direct-note"}, "note_info": note_info}

        def get_published_notes(self):
            return True, "ok", {"data": {"items": [{"note_id": "published-001", "title": "Published"}]}}

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "creator-routes-owner"
    )
    intruder_token = _register_and_get_access_token("creator-routes-intruder")
    app.dependency_overrides[get_creator_api_adapter_factory] = lambda: FakeCreatorRoutesAdapter
    try:
        anonymous_response = client.post(
            "/api/xhs/creator/topics/search",
            json={"account_id": creator_account_id, "keyword": "breakfast"},
        )
        assert anonymous_response.status_code == 401

        intruder_response = client.post(
            "/api/xhs/creator/topics/search",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"account_id": creator_account_id, "keyword": "breakfast"},
        )
        assert intruder_response.status_code == 404

        topic_response = client.post(
            "/api/xhs/creator/topics/search",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": creator_account_id, "keyword": "breakfast"},
        )
        assert topic_response.status_code == 200
        assert topic_response.json()["items"][0]["name"] == "breakfast"
        assert "raw" not in topic_response.json()

        location_response = client.post(
            "/api/xhs/creator/locations/search",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": creator_account_id, "keyword": "Shanghai"},
        )
        assert location_response.status_code == 200
        assert location_response.json()["items"][0]["id"] == "loc-creator"
        assert "raw" not in location_response.json()

        upload_response = client.post(
            "/api/xhs/creator/assets/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": creator_account_id, "file_path": "/api/files/media/xhs-upload-u1-cover.png", "media_type": "image"},
        )
        assert upload_response.status_code == 200
        assert upload_response.json()["payload"]["fileIds"] == "file-creator-001"
        assert upload_response.json()["task"]["task_type"] == "creator_direct_upload"

        publish_response = client.post(
            "/api/xhs/creator/publish/image",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": creator_account_id,
                "title": "Direct title",
                "body": "Direct body",
                "image_file_infos": [{"fileIds": "file-creator-001", "width": 1080, "height": 1440}],
            },
        )
        assert publish_response.status_code == 200
        assert publish_response.json()["payload"]["data"]["note_id"] == "creator-direct-note"
        assert publish_response.json()["task"]["task_type"] == "creator_direct_publish"

        video_response = client.post(
            "/api/xhs/creator/publish/video",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": creator_account_id,
                "title": "Video title",
                "body": "Video body",
                "video_info": {"video_id": "video-001"},
            },
        )
        assert video_response.status_code == 200
        assert video_response.json()["payload"]["note_info"]["media_type"] == "video"

        published_response = client.get(
            f"/api/xhs/creator/published?account_id={creator_account_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert published_response.status_code == 200
        assert published_response.json()["items"][0]["note_id"] == "published-001"
        assert "raw" not in published_response.json()

        db = next(app.dependency_overrides[get_db]())
        try:
            tasks = db.query(Task).filter(Task.task_type.in_(["creator_direct_upload", "creator_direct_publish"])).all()
            assert [task.status for task in tasks] == ["completed", "completed", "completed"]
            assert all(task.user_id == 1 for task in tasks)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_creator_direct_publish_accepts_optional_publish_parameters(tmp_path):
    from backend.app.api.platforms.xhs.creator import get_creator_api_adapter_factory

    class FakeCreatorOptionalAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def post_note(self, note_info):
            self.calls.append({"cookies": self.cookies, "note_info": note_info})
            return {"success": True, "data": {"note_id": "optional-note"}, "note_info": note_info}

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "creator-optional-owner"
    )
    FakeCreatorOptionalAdapter.calls = []
    app.dependency_overrides[get_creator_api_adapter_factory] = lambda: FakeCreatorOptionalAdapter
    try:
        image_response = client.post(
            "/api/xhs/creator/publish/image",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": creator_account_id,
                "title": "Direct optional title",
                "image_file_infos": [{"fileIds": "file-optional", "width": 1080, "height": 1440}],
                "topics": ["早餐", "通勤"],
                "location": "上海",
                "is_private": False,
            },
        )

        assert image_response.status_code == 200
        assert FakeCreatorOptionalAdapter.calls == [
            {
                "cookies": "web_session=creator-session; a1=creator-a1",
                "note_info": {
                    "title": "Direct optional title",
                    "desc": "",
                    "media_type": "image",
                    "image_file_infos": [{"fileIds": "file-optional", "width": 1080, "height": 1440}],
                    "type": 0,
                    "postTime": None,
                    "topics": ["早餐", "通勤"],
                    "location": "上海",
                },
            }
        ]
    finally:
        app.dependency_overrides.pop(get_creator_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_xhs_creator_direct_external_actions_are_blocked_in_production_without_opt_in(tmp_path, monkeypatch):
    from backend.app.api.platforms.xhs.creator import get_creator_api_adapter_factory
    from backend.app.core.config import get_settings

    class TrapCreatorRoutesAdapter:
        upload_called = False
        publish_called = False

        def __init__(self, cookies):
            self.cookies = cookies

        def upload_media(self, file_path, media_type):
            TrapCreatorRoutesAdapter.upload_called = True
            raise AssertionError("upload_media should not be called")

        def post_note(self, note_info):
            TrapCreatorRoutesAdapter.publish_called = True
            raise AssertionError("post_note should not be called")

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "production-secret-with-enough-length")
    monkeypatch.setenv("DATABASE_TYPE", "mysql")
    monkeypatch.setenv("DATABASE_MYSQL_PASSWORD", "strong-db-password")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://ops.example.com")
    monkeypatch.delenv("ALLOW_PRODUCTION_EXTERNAL_ACTIONS", raising=False)
    get_settings.cache_clear()
    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "creator-prod-block-owner"
    )
    TrapCreatorRoutesAdapter.upload_called = False
    TrapCreatorRoutesAdapter.publish_called = False
    app.dependency_overrides[get_creator_api_adapter_factory] = lambda: TrapCreatorRoutesAdapter
    try:
        upload_response = client.post(
            "/api/xhs/creator/assets/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"account_id": creator_account_id, "file_path": "/api/files/media/xhs-upload-u1-cover.png", "media_type": "image"},
        )
        publish_response = client.post(
            "/api/xhs/creator/publish/image",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": creator_account_id,
                "title": "Blocked direct title",
                "image_file_infos": [{"fileIds": "file-blocked", "width": 1080, "height": 1440}],
            },
        )

        assert upload_response.status_code == 403
        assert publish_response.status_code == 403
        assert TrapCreatorRoutesAdapter.upload_called is False
        assert TrapCreatorRoutesAdapter.publish_called is False
    finally:
        get_settings.cache_clear()
        app.dependency_overrides.pop(get_creator_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_monitoring_targets_crud_are_user_scoped(tmp_path):
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("monitoring-owner")
    intruder_token = _register_and_get_access_token("monitoring-intruder")
    try:
        anonymous_response = client.get("/api/xhs/monitoring/targets")
        assert anonymous_response.status_code == 401

        create_response = client.post(
            "/api/xhs/monitoring/targets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "target_type": "keyword",
                "name": "早餐趋势",
                "value": "低卡早餐",
                "config": {"frequency": "daily"},
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["target_type"] == "keyword"
        assert created["name"] == "早餐趋势"
        assert created["value"] == "低卡早餐"
        assert created["status"] == "active"

        owner_list_response = client.get(
            "/api/xhs/monitoring/targets",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_list_response.status_code == 200
        assert owner_list_response.json()["total"] == 1

        intruder_list_response = client.get(
            "/api/xhs/monitoring/targets",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_list_response.status_code == 200
        assert intruder_list_response.json()["total"] == 0

        update_response = client.patch(
            f"/api/xhs/monitoring/targets/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "早餐趋势组", "status": "paused"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "早餐趋势组"
        assert update_response.json()["status"] == "paused"

        intruder_update_response = client.patch(
            f"/api/xhs/monitoring/targets/{created['id']}",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"name": "偷看"},
        )
        assert intruder_update_response.status_code == 404

        delete_response = client.delete(
            f"/api/xhs/monitoring/targets/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json() == {"id": created["id"], "status": "deleted"}
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_monitoring_targets_refresh_creates_owned_task(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory

    class FakeMonitoringAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def get_user_notes(self, user_url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "crawled-note-001",
                                "display_title": "竞品账号低卡早餐",
                                "desc": "creator-001 的早餐选题",
                                "user": {"nickname": "creator-001"},
                                "interact_info": {"liked_count": 50, "collected_count": 20, "comment_count": 3},
                                "cover": {"url": "https://img.example/cover.png"},
                            }
                        }
                    ],
                    "total": 1,
                    "has_more": False,
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "monitoring-refresh-owner")
    intruder_token = _register_and_get_access_token("monitoring-refresh-intruder")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeMonitoringAdapter
    try:
        created = client.post(
            "/api/xhs/monitoring/targets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"target_type": "account", "name": "竞品账号", "value": "creator-001"},
        ).json()

        refresh_response = client.post(
            f"/api/xhs/monitoring/targets/{created['id']}/refresh",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert refresh_response.status_code == 200
        payload = refresh_response.json()
        assert payload["target"]["id"] == created["id"]
        assert payload["task"]["task_type"] == "monitoring_crawl"
        assert payload["task"]["status"] == "completed"
        assert payload["task"]["payload"]["target_id"] == created["id"]
        assert payload["task"]["payload"]["crawled_count"] == 1
        assert payload["snapshot"]["payload"]["matched_count"] >= 1
        assert payload["snapshot"]["payload"]["top_notes"][0]["note_id"] == "crawled-note-001"
        assert payload["target"]["consecutive_failures"] == 0

        tasks_response = client.get(
            "/api/tasks?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert tasks_response.status_code == 200
        assert tasks_response.json()["items"][0]["task_type"] == "monitoring_crawl"

        notes_response = client.get(
            f"/api/xhs/monitoring/targets/{created['id']}/notes",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert notes_response.status_code == 200
        assert len(notes_response.json()["items"]) >= 1

        snapshots_response = client.get(
            f"/api/xhs/monitoring/targets/{created['id']}/snapshots",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert snapshots_response.status_code == 200
        assert snapshots_response.json()["items"][0]["payload"]["matched_count"] >= 1

        intruder_response = client.post(
            f"/api/xhs/monitoring/targets/{created['id']}/refresh",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_crawl_rate_limiter_blocks_after_max_requests():
    from backend.app.services.rate_limiter import CrawlRateLimiter

    limiter = CrawlRateLimiter(max_per_minute=3)
    assert limiter.allow(1) is True
    assert limiter.allow(1) is True
    assert limiter.allow(1) is True
    assert limiter.allow(1) is False

    assert limiter.allow(2) is True

    limiter.reset(1)
    assert limiter.allow(1) is True


def test_keyword_groups_require_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.get("/api/keyword-groups")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_keyword_groups_crud_are_user_scoped(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "keyword-group-owner")
    intruder_token = _register_and_get_access_token("keyword-group-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "keyword-note-001",
                        "title": "低卡早餐模板",
                        "content": "适合通勤的低卡早餐搭配。",
                        "author_name": "早餐作者",
                        "raw": {"likes": 30, "collects": 10, "comments": 4, "shares": 1, "tags": ["低卡", "早餐"]},
                    },
                    {
                        "note_id": "keyword-note-002",
                        "title": "家居收纳灵感",
                        "content": "收纳工具清单。",
                        "author_name": "收纳作者",
                        "raw": {"likes": 2, "collects": 1, "comments": 0, "shares": 0, "tags": ["收纳"]},
                    },
                ],
            },
        )
        assert save_response.status_code == 200

        create_response = client.post(
            "/api/keyword-groups",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "name": "早餐机会", "keywords": ["低卡", "早餐"]},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["name"] == "早餐机会"
        assert created["keywords"] == ["低卡", "早餐"]

        owner_list_response = client.get("/api/keyword-groups", headers={"Authorization": f"Bearer {owner_token}"})
        assert owner_list_response.status_code == 200
        assert owner_list_response.json()["total"] == 1

        intruder_list_response = client.get("/api/keyword-groups", headers={"Authorization": f"Bearer {intruder_token}"})
        assert intruder_list_response.status_code == 200
        assert intruder_list_response.json()["total"] == 0

        detail_response = client.get(
            f"/api/keyword-groups/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["trend"]["total_matches"] == 1
        assert detail["trend"]["total_engagement"] == 45
        assert detail["trend"]["keywords"][0]["keyword"] == "低卡"
        assert detail["trend"]["matched_notes"][0]["note_id"] == "keyword-note-001"

        patch_response = client.patch(
            f"/api/keyword-groups/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "早餐选题池", "keywords": ["早餐"]},
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["name"] == "早餐选题池"
        assert patch_response.json()["keywords"] == ["早餐"]

        cross_get_response = client.get(
            f"/api/keyword-groups/{created['id']}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert cross_get_response.status_code == 404

        cross_patch_response = client.patch(
            f"/api/keyword-groups/{created['id']}",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"name": "偷看"},
        )
        assert cross_patch_response.status_code == 404

        delete_response = client.delete(
            f"/api/keyword-groups/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_huitun_discovery_run_creates_persisted_candidates(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import KeywordDiscoveryItem, KeywordDiscoveryRun

    db_dependency = _override_database(tmp_path)
    try:
        owner_token = _register_and_get_access_token("huitun-discovery-owner")
        response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "source_mode": "manual_table",
                "limit_per_seed": 5,
                "inputs": [
                    {
                        "source_keyword": "露营",
                        "table_rows": [
                            ["露营", "12.3万", "3,400", "8.6w", "户外 42.5%\n穿搭 18%"],
                            ["", "1", "2", "3", "bad"],
                            ["露营装备", "9万", "200", "1.2万", "户外 30%"],
                        ],
                    }
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["source"] == "huitun"
        assert payload["seed_keywords"] == ["露营"]
        assert [item["keyword"] for item in payload["items"]] == ["露营", "露营装备"]
        first = payload["items"][0]
        assert first["hot_value_number"] == 123000
        assert first["note_count"] == 3400
        assert first["interaction_number"] == 86000
        assert first["categories"] == [{"label": "户外", "rate": "42.5"}, {"label": "穿搭", "rate": "18"}]

        db = next(app.dependency_overrides[get_db]())
        try:
            run = db.get(KeywordDiscoveryRun, payload["id"])
            assert run is not None
            assert run.status == "completed"
            persisted_items = db.scalars(
                select(KeywordDiscoveryItem)
                .where(KeywordDiscoveryItem.run_id == payload["id"])
                .order_by(KeywordDiscoveryItem.rank_index.asc(), KeywordDiscoveryItem.id.asc())
            ).all()
            assert [item.keyword for item in persisted_items] == ["露营", "露营装备"]
            assert persisted_items[0].raw_json["keyword"] == "露营"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_keyword_candidate_import_appends_to_existing_group_and_marks_items(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import KeywordDiscoveryItem

    db_dependency = _override_database(tmp_path)
    try:
        owner_token = _register_and_get_access_token("keyword-import-owner")
        create_group_response = client.post(
            "/api/keyword-groups",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "name": "露营机会", "keywords": ["露营"]},
        )
        assert create_group_response.status_code == 200
        group_id = create_group_response.json()["id"]

        run_response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "source_mode": "manual_table",
                "limit_per_seed": 10,
                "inputs": [
                    {
                        "source_keyword": "露营",
                        "table_rows": [
                            ["露营", "12.3万", "3400", "8.6万", "户外 42.5%"],
                            ["露营装备", "9万", "200", "1.2万", "户外 30%"],
                            ["户外帐篷", "7万", "180", "9000", "户外 20%"],
                        ],
                    }
                ],
            },
        )
        assert run_response.status_code == 200
        candidate_ids = [item["id"] for item in run_response.json()["items"]]

        import_response = client.post(
            f"/api/keyword-groups/{group_id}/import-keyword-candidates",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"candidate_ids": candidate_ids, "merge_mode": "append_dedupe"},
        )

        assert import_response.status_code == 200
        payload = import_response.json()
        assert payload["group"]["keywords"] == ["露营", "露营装备", "户外帐篷"]
        assert payload["imported_keywords"] == ["露营", "露营装备", "户外帐篷"]

        db = next(app.dependency_overrides[get_db]())
        try:
            persisted_items = db.scalars(
                select(KeywordDiscoveryItem).where(KeywordDiscoveryItem.id.in_(candidate_ids))
            ).all()
            assert all(item.selected for item in persisted_items)
            assert {item.imported_group_id for item in persisted_items} == {group_id}
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_keyword_candidate_import_can_create_group_and_enforces_candidate_ownership(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        owner_token = _register_and_get_access_token("keyword-create-owner")
        intruder_token = _register_and_get_access_token("keyword-create-intruder")
        run_response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "source_mode": "manual_json",
                "limit_per_seed": 5,
                "inputs": [
                    {
                        "source_keyword": "露营",
                        "items": [
                            {"keyword": "露营装备", "hot_value_text": "9万", "note_count": 200},
                            {"keyword": "户外帐篷", "hot_value_text": "7万", "note_count": 180},
                        ],
                    }
                ],
            },
        )
        assert run_response.status_code == 200
        candidate_ids = [item["id"] for item in run_response.json()["items"]]

        intruder_response = client.post(
            "/api/keyword-groups/import-keyword-candidates",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={
                "candidate_ids": candidate_ids,
                "merge_mode": "append_dedupe",
                "target": {"mode": "create", "name": "偷看热词", "platform": "xhs"},
            },
        )
        assert intruder_response.status_code == 404

        owner_response = client.post(
            "/api/keyword-groups/import-keyword-candidates",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "candidate_ids": candidate_ids,
                "merge_mode": "append_dedupe",
                "target": {"mode": "create", "name": "露营热词", "platform": "xhs"},
            },
        )

        assert owner_response.status_code == 200
        group = owner_response.json()["group"]
        assert group["name"] == "露营热词"
        assert group["keywords"] == ["露营装备", "户外帐篷"]

        intruder_get_response = client.get(
            f"/api/keyword-groups/{group['id']}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_get_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_crawl_data_item_contains_quality_fields_by_default():
    from backend.app.api.platforms.xhs.crawl import _crawl_data_item

    item = _crawl_data_item(source="page:1", status="partial", diagnostic_kind="empty_detail_payload")

    assert item["quality_status"] == "unknown"
    assert item["recoverable"] is False
    assert item["diagnostic_kind"] == "empty_detail_payload"
    assert item["save_diagnostic_kind"] is None
    assert item["user_message"] == ""
    assert item["saved"] is False


def test_crawl_save_filter_only_allows_valid_details():
    from backend.app.api.platforms.xhs.crawl import _filter_saveable_notes

    valid = {
        "note_id": "valid-detail",
        "note_url": "https://www.xiaohongshu.com/explore/valid-detail?xsec_token=token",
        "content": "正文",
        "image_urls": [],
    }
    search_card_only = {
        "note_id": "card-only",
        "note_url": "https://www.xiaohongshu.com/explore/card-only?xsec_token=token",
        "title": "只有标题",
        "likes": 12,
    }
    empty = {"note_id": "empty", "note_url": "https://www.xiaohongshu.com/explore/empty?xsec_token=token"}

    saveable, skipped = _filter_saveable_notes([valid, search_card_only, empty])

    assert [item["note_id"] for item in saveable] == ["valid-detail"]
    assert [item["note_id"] for item in skipped] == ["card-only", "empty"]
    assert all(item["save_diagnostic_kind"] == "save_skipped_low_quality" for item in skipped)
    assert skipped[0]["quality_status"] == "search_card_only"
    assert skipped[1]["quality_status"] == "empty_detail_payload"


def test_crawl_diagnostic_persistence_redacts_sensitive_payload_and_query_is_user_scoped(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import CrawlDiagnostic, Task
    from backend.app.services.crawl_diagnostics import create_crawl_diagnostic

    db_dependency, owner_token, account_id = _create_pc_account_with_cookie(tmp_path, "diagnostic-owner")
    intruder_token = _register_and_get_access_token("diagnostic-intruder")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            task = Task(
                user_id=1,
                platform="xhs",
                task_type="crawl",
                status="completed",
                progress=100,
                payload={"crawl_type": "note_urls"},
            )
            db.add(task)
            db.flush()
            diagnostic = create_crawl_diagnostic(
                db,
                user_id=1,
                task_id=task.id,
                platform_account_id=account_id,
                platform="xhs",
                source="https://www.xiaohongshu.com/explore/feed1?xsec_token=abcdefghijk",
                note_id="feed1",
                note_url="https://www.xiaohongshu.com/explore/feed1?xsec_token=abcdefghijk",
                stage="detail",
                kind="xhs_rate_limited",
                severity="blocked",
                recoverable=True,
                message="访问频繁，请稍后再试",
                user_message="小红书提示访问频繁，已停止本轮详情抓取。请稍后低频重试。",
                raw_payload={
                    "headers": {"Authorization": "Bearer secret", "Cookie": "web_session=secret"},
                    "xsec_token": "abcdefghijk",
                    "web_session": "secret-session",
                    "html": "<html>secret</html>",
                    "error_code": 300013,
                    "message": "访问频繁，请稍后再试",
                    "data": {"items": [{"note_card": {"note_id": "feed1", "desc": "正文"}}]},
                },
            )
            db.commit()
            diagnostic_id = diagnostic.id
            task_id = task.id
        finally:
            db.close()

        owner_response = client.get(
            f"/api/xhs/crawl/diagnostics?task_id={task_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        payload = owner_response.json()
        assert payload["total"] == 1
        item = payload["items"][0]
        assert item["id"] == diagnostic_id
        assert item["kind"] == "xhs_rate_limited"
        assert item["raw_json"]["error_code"] == 300013
        assert item["raw_json"]["has_xsec_token"] is True
        assert item["raw_json"]["masked_xsec_token"] == "abcd***hijk"
        assert "abcdefghijk" not in str(item["raw_json"])
        assert "secret" not in str(item["raw_json"])
        assert "<html>" not in str(item["raw_json"])

        intruder_response = client.get(
            f"/api/xhs/crawl/diagnostics?task_id={task_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 200
        assert intruder_response.json()["total"] == 0

        db = next(app.dependency_overrides[get_db]())
        try:
            stored = db.get(CrawlDiagnostic, diagnostic_id)
            assert stored.raw_json["source_url_kind"] == "explore_with_xsec_token"
            assert "abcdefghijk" not in str(stored.raw_json)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_crawl_diagnostics_list_filters_by_kind_and_stage(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import Task
    from backend.app.services.crawl_diagnostics import create_crawl_diagnostic

    db_dependency, owner_token, account_id = _create_pc_account_with_cookie(tmp_path, "diagnostic-filter-owner")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            task = Task(user_id=1, platform="xhs", task_type="crawl", status="completed", progress=100, payload={})
            db.add(task)
            db.flush()
            create_crawl_diagnostic(
                db,
                user_id=1,
                task_id=task.id,
                platform_account_id=account_id,
                platform="xhs",
                source="page:1",
                note_id="feed1",
                note_url=None,
                stage="detail",
                kind="empty_detail_payload",
                severity="warning",
                recoverable=True,
                message="empty",
                user_message="详情为空，本条不会自动入库。请稍后重试或换来源链接。",
                raw_payload={"data": {"items": []}},
            )
            create_crawl_diagnostic(
                db,
                user_id=1,
                task_id=task.id,
                platform_account_id=account_id,
                platform="xhs",
                source="comment-url",
                note_id="feed1",
                note_url=None,
                stage="comments",
                kind="comment_api_failed",
                severity="warning",
                recoverable=True,
                message="comment failed",
                user_message="评论获取失败，笔记可继续处理。",
                raw_payload={"message": "comment failed"},
            )
            db.commit()
            task_id = task.id
        finally:
            db.close()

        response = client.get(
            f"/api/xhs/crawl/diagnostics?task_id={task_id}&stage=detail&kind=empty_detail_payload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["stage"] == "detail"
        assert payload["items"][0]["kind"] == "empty_detail_payload"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_batch_save_rejects_cross_user_account(tmp_path):
    db_dependency, _, account_id = _create_pc_account_with_cookie(tmp_path, "save-owner-2")
    intruder_token = _register_and_get_access_token("save-intruder")
    try:
        response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"account_id": account_id, "notes": [{"note_id": "note-001", "title": "标题"}]},
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_library_list_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.get("/api/notes?platform=xhs")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_library_list_returns_only_current_user_saved_notes(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "library-owner")
    intruder_token = _register_and_get_access_token("library-intruder")
    try:
        owner_save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "owner-note-001",
                        "title": "我的内容库笔记",
                        "content": "这条应该只属于 owner。",
                        "author_name": "作者 Owner",
                        "raw": {"source": "owner"},
                    }
                ],
            },
        )
        assert owner_save_response.status_code == 200

        intruder_response = client.get(
            "/api/notes?platform=xhs",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 200
        assert intruder_response.json()["total"] == 0

        owner_response = client.get(
            "/api/notes?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        payload = owner_response.json()
        assert payload["total"] == 1
        assert payload["page"] == 1
        assert payload["page_size"] == 20
        assert payload["items"][0]["note_id"] == "owner-note-001"
        assert payload["items"][0]["title"] == "我的内容库笔记"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_library_list_exposes_video_media_type_for_regular_users(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.api.notes._download_asset", lambda _url, _user_id, _asset_type: "")
    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "library-video-owner")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": account_id,
                "notes": [
                    {
                        "note_id": "library-video-note-001",
                        "title": "Video note",
                        "content": "A saved video note",
                        "author_name": "Video author",
                        "cover_url": "https://images.example/video-cover.jpg",
                        "video_url": "https://videos.example/video.mp4",
                        "raw": {"noteType": 1},
                    }
                ],
            },
        )
        assert save_response.status_code == 200

        list_response = client.get(
            "/api/notes?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert list_response.status_code == 200
        item = list_response.json()["items"][0]
        assert item["note_id"] == "library-video-note-001"
        assert item["media_type"] == "video"
        assert item["note_type"] == "video"
        assert item["video_url"]
        assert "raw_json" not in item
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_library_filters_by_keyword_tag_assets_and_comments(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import NoteComment

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "library-filter-owner")
    intruder_token = _register_and_get_access_token("library-filter-intruder")
    try:
        first_save = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "filter-note-assets",
                        "title": "低卡早餐灵感",
                        "content": "适合通勤前快速准备。",
                        "author_name": "早餐研究员",
                        "image_urls": ["https://example.test/filter-assets.webp"],
                    },
                    {
                        "note_id": "filter-note-comments",
                        "title": "旅行收纳清单",
                        "content": "评论里有很多问题。",
                        "author_name": "收纳作者",
                    },
                ],
            },
        )
        assert first_save.status_code == 200
        asset_note_id = first_save.json()["items"][0]["id"]
        comment_note_id = first_save.json()["items"][1]["id"]

        tag_response = client.post(
            "/api/tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Breakfast", "color": "#111111"},
        )
        tag_id = tag_response.json()["id"]
        client.post(
            "/api/notes/batch-tag",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"note_ids": [asset_note_id], "tag_ids": [tag_id], "mode": "replace"},
        )
        db = next(app.dependency_overrides[get_db]())
        try:
            db.add(
                NoteComment(
                    note_id=comment_note_id,
                    comment_id="filter-comment-001",
                    user_name="评论用户",
                    content="这条笔记有评论",
                )
            )
            db.commit()
        finally:
            db.close()

        keyword_response = client.get(
            "/api/notes?platform=xhs&q=早餐",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert keyword_response.status_code == 200
        assert [item["note_id"] for item in keyword_response.json()["items"]] == ["filter-note-assets"]

        tag_filter_response = client.get(
            f"/api/notes?platform=xhs&tag_id={tag_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert tag_filter_response.status_code == 200
        assert [item["note_id"] for item in tag_filter_response.json()["items"]] == ["filter-note-assets"]

        assets_response = client.get(
            "/api/notes?platform=xhs&has_assets=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert assets_response.status_code == 200
        assert [item["note_id"] for item in assets_response.json()["items"]] == ["filter-note-assets"]

        comments_response = client.get(
            "/api/notes?platform=xhs&has_comments=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert comments_response.status_code == 200
        assert [item["note_id"] for item in comments_response.json()["items"]] == ["filter-note-comments"]

        intruder_response = client.get(
            f"/api/notes?platform=xhs&tag_id={tag_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_library_detail_enforces_ownership(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import Note, PlatformAccount, User

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "library-detail-owner")
    intruder_token = _register_and_get_access_token("library-detail-intruder")
    admin_token = _register_and_get_admin_access_token("library-detail-admin")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "detail-note-001",
                        "title": "详情页笔记",
                        "content": "详情正文",
                        "author_name": "详情作者",
                        "raw": {"source": "detail"},
                    }
                ],
            },
        )
        note_id = save_response.json()["items"][0]["id"]

        owner_response = client.get(
            f"/api/notes/{note_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        assert owner_response.json()["note_id"] == "detail-note-001"
        assert "raw_json" not in owner_response.json()

        db = next(app.dependency_overrides[get_db]())
        try:
            admin = db.scalar(select(User).where(User.username == "library-detail-admin"))
            assert admin is not None
            admin_account = PlatformAccount(
                user_id=admin.id,
                platform="xhs",
                sub_type="pc",
                external_user_id="admin-detail-pc",
                nickname="admin detail pc",
                status="active",
            )
            db.add(admin_account)
            db.flush()
            admin_note = Note(
                user_id=admin.id,
                platform_account_id=admin_account.id,
                platform="xhs",
                note_id="admin-detail-note-001",
                title="管理员详情页笔记",
                raw_json={"source": "admin-detail"},
            )
            db.add(admin_note)
            db.commit()
            admin_note_id = admin_note.id
        finally:
            db.close()

        admin_response = client.get(
            f"/api/notes/{admin_note_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_response.status_code == 200
        assert admin_response.json()["raw_json"] == {"source": "admin-detail"}

        intruder_response = client.get(
            f"/api/notes/{note_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notes_library_delete_removes_owned_note_children_and_rejects_cross_user(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import AiDraft, Note, NoteAsset, NoteComment, Tag, note_tags

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "library-delete-owner")
    intruder_token = _register_and_get_access_token("library-delete-intruder")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            note = Note(
                user_id=1,
                platform_account_id=owner_account_id,
                platform="xhs",
                note_id="delete-note-001",
                title="Delete me",
            )
            tag = Tag(user_id=1, name="待删除", color="#111111")
            db.add_all([note, tag])
            db.flush()
            db.add(NoteAsset(note_id=note.id, asset_type="image", url="https://example.test/delete.webp"))
            db.add(NoteComment(note_id=note.id, comment_id="delete-comment", content="删除评论"))
            db.add(AiDraft(user_id=1, platform="xhs", title="Draft", body="Body", source_note_id=note.id))
            db.execute(note_tags.insert().values(note_id=note.id, tag_id=tag.id))
            db.commit()
            note_id = note.id
        finally:
            db.close()

        intruder_response = client.delete(
            f"/api/notes/{note_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404

        owner_response = client.delete(
            f"/api/notes/{note_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        assert owner_response.json() == {"id": note_id, "status": "deleted"}

        detail_response = client.get(
            f"/api/notes/{note_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert detail_response.status_code == 404

        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.get(Note, note_id) is None
            assert db.query(NoteAsset).filter(NoteAsset.note_id == note_id).count() == 0
            assert db.query(NoteComment).filter(NoteComment.note_id == note_id).count() == 0
            assert db.execute(select(note_tags).where(note_tags.c.note_id == note_id)).first() is None
            assert db.query(AiDraft).filter(AiDraft.source_note_id == note_id).count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_drafts_api_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post(
            "/api/drafts",
            json={"platform": "xhs", "title": "草稿标题", "body": "草稿正文"},
        )

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_drafts_api_creates_from_owned_note_and_lists_current_user_only(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import AiDraft

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "draft-owner")
    intruder_token = _register_and_get_access_token("draft-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [
                    {
                        "note_id": "draft-source-note",
                        "title": "源笔记标题",
                        "content": "源笔记正文",
                        "author_name": "源作者",
                        "raw": {"source": "draft"},
                    }
                ],
            },
        )
        source_note_id = save_response.json()["items"][0]["id"]

        create_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "source_note_id": source_note_id, "intent": "rewrite"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["platform"] == "xhs"
        assert created["title"] == "源笔记标题"
        assert created["body"] == "源笔记正文"
        assert created["source_note_id"] == source_note_id

        owner_list_response = client.get(
            "/api/drafts?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_list_response.status_code == 200
        owner_payload = owner_list_response.json()
        assert owner_payload["total"] == 1
        assert owner_payload["items"][0]["id"] == created["id"]

        intruder_list_response = client.get(
            "/api/drafts?platform=xhs",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_list_response.status_code == 200
        assert intruder_list_response.json()["total"] == 0

        db = next(app.dependency_overrides[get_db]())
        try:
            draft = db.query(AiDraft).one()
            assert draft.source_note_id == source_note_id
            assert draft.title == "源笔记标题"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_drafts_api_rejects_cross_user_source_note(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "draft-source-owner")
    intruder_token = _register_and_get_access_token("draft-source-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [{"note_id": "foreign-source", "title": " чужая", "content": "nope"}],
            },
        )
        source_note_id = save_response.json()["items"][0]["id"]

        response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"platform": "xhs", "source_note_id": source_note_id, "intent": "publish"},
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_drafts_update_persists_owned_changes_and_rejects_cross_user(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "draft-update-owner")
    intruder_token = _register_and_get_access_token("draft-update-intruder")
    try:
        save_response = client.post(
            "/api/notes/batch-save",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "notes": [{"note_id": "update-source", "title": "旧标题", "content": "旧正文"}],
            },
        )
        source_note_id = save_response.json()["items"][0]["id"]
        create_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "source_note_id": source_note_id},
        )
        draft_id = create_response.json()["id"]

        update_response = client.patch(
            f"/api/drafts/{draft_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"title": "新标题", "body": "新正文"},
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["title"] == "新标题"
        assert updated["body"] == "新正文"

        list_response = client.get(
            "/api/drafts?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        listed = list_response.json()["items"][0]
        assert listed["id"] == draft_id
        assert listed["title"] == "新标题"
        assert listed["body"] == "新正文"

        intruder_response = client.patch(
            f"/api/drafts/{draft_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"title": "攻击标题", "body": "攻击正文"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_configs_require_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.get("/api/model-configs")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_sensitive_config_routes_require_admin_role(tmp_path):
    db_dependency = _override_database(tmp_path)
    user_token = _register_and_get_access_token("sensitive-config-user")
    admin_token = _register_and_get_admin_access_token("sensitive-config-admin")
    try:
        create_model_payload = {
            "name": "Hidden Text",
            "model_type": "text",
            "provider": "openai-compatible",
            "model_name": "gpt-hidden",
            "base_url": "https://api.example.test/v1",
            "api_key": "sk-hidden",
            "is_default": True,
        }
        feishu_payload = {
            "app_id": "cli_xxx",
            "app_secret": "feishu-secret",
            "bitable_url": "https://example.feishu.cn/base/appxxx?table=tblxxx",
            "table_id": "tblxxx",
            "enabled": True,
        }
        data_service_payload = {"name": "Data Service", "base_url": "https://data.example.test", "api_key": "provider-secret"}

        blocked_requests = [
            ("get", "/api/model-configs", None),
            ("post", "/api/model-configs", create_model_payload),
            ("get", "/api/integrations/feishu/config", None),
            ("put", "/api/integrations/feishu/config", feishu_payload),
            ("post", "/api/integrations/feishu/test", None),
            ("get", "/api/wechat-official/redfox/config", None),
            ("post", "/api/wechat-official/redfox/config", data_service_payload),
            ("post", "/api/wechat-official/redfox/config/validate", None),
        ]
        for method, path, payload in blocked_requests:
            kwargs = {"headers": {"Authorization": f"Bearer {user_token}"}}
            if payload is not None:
                kwargs["json"] = payload
            response = getattr(client, method)(path, **kwargs)
            assert response.status_code == 403, path

        assert client.get("/api/model-configs", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
        assert client.get("/api/integrations/feishu/config", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
        assert client.get("/api/wechat-official/redfox/config", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def _create_capability_test_model_config(token: str, **overrides) -> dict:
    payload = {
        "name": "Capability Test Model",
        "model_type": "image",
        "provider": "openai-compatible",
        "model_name": "test-model",
        "base_url": "https://api.example.test/v1",
        "api_key": "sk-test",
        "is_default": False,
    }
    payload.update(overrides)
    response = client.post(
        "/api/model-configs",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    return response.json()


def _assign_capability_default(token: str, capability: str, model_config_id: int) -> dict:
    response = client.put(
        f"/api/model-configs/capability-defaults/{capability}",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_config_id": model_config_id},
    )
    assert response.status_code == 200
    return response.json()


def test_admin_can_assign_distinct_vision_and_image_generation_capability_defaults(tmp_path):
    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("capability-default-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        vision = _create_capability_test_model_config(
            admin_token,
            name="Vision",
            provider="volcengine-ark",
            model_name="doubao-seed-2-0-mini-260428",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )
        generation = _create_capability_test_model_config(
            admin_token,
            name="RunningHub",
            provider="runninghub-ai-app",
            model_name="runninghub-image-g",
            base_url="https://www.runninghub.cn",
        )

        vision_response = client.put(
            "/api/model-configs/capability-defaults/vision",
            headers=headers,
            json={"model_config_id": vision["id"]},
        )
        generation_response = client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": generation["id"]},
        )
        response = client.get(
            "/api/model-configs/capability-defaults",
            headers=headers,
        )

        assert vision_response.status_code == 200
        assert generation_response.status_code == 200
        assert response.status_code == 200
        by_capability = {
            item["capability"]: item
            for item in response.json()["items"]
        }
        assert by_capability["text"]["model_config"] is None
        assert by_capability["vision"]["model_config"]["provider"] == "volcengine-ark"
        assert by_capability["image_generation"]["model_config"]["provider"] == "runninghub-ai-app"
        assert vision_response.json()["model_config"]["assigned_capabilities"] == ["vision"]
        assert generation_response.json()["model_config"]["assigned_capabilities"] == ["image_generation"]
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_capability_default_assignment_rejects_incompatible_model(tmp_path):
    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("capability-incompatible-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        text_config = _create_capability_test_model_config(
            admin_token,
            model_type="text",
            provider="volcengine-ark",
        )

        response = client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": text_config["id"]},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == {
            "code": "MODEL_CAPABILITY_INCOMPATIBLE",
            "capability": "image_generation",
        }
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_bound_model_config_cannot_be_deleted(tmp_path):
    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("bound-config-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        config = _create_capability_test_model_config(
            admin_token,
            provider="runninghub-ai-app",
            model_name="runninghub-image-g",
            base_url="https://www.runninghub.cn",
        )
        assigned = client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": config["id"]},
        )
        assert assigned.status_code == 200

        response = client.delete(
            f"/api/model-configs/{config['id']}",
            headers=headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "MODEL_CONFIG_IN_USE",
            "capabilities": ["image_generation"],
        }
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_normal_user_cannot_manage_capability_defaults(tmp_path):
    db_dependency = _override_database(tmp_path)
    user_token = _register_and_get_access_token("capability-default-user")
    headers = {"Authorization": f"Bearer {user_token}"}
    try:
        assert client.get(
            "/api/model-configs/capability-defaults",
            headers=headers,
        ).status_code == 403
        response = client.put(
            "/api/model-configs/capability-defaults/vision",
            headers=headers,
            json={"model_config_id": 1},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_configs_create_list_filter_and_encrypt_api_key(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import ModelConfig, User

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_admin_access_token("model-owner")
    intruder_token = _register_and_get_access_token("model-intruder")
    try:
        create_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "name": "OpenAI Text",
                "model_type": "text",
                "provider": "openai-compatible",
                "model_name": "gpt-test",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-secret-text",
                "is_default": True,
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["name"] == "OpenAI Text"
        assert created["model_type"] == "text"
        assert created["model_name"] == "gpt-test"
        assert created["has_api_key"] is True
        assert "api_key" not in created
        assert "encrypted_api_key" not in created

        image_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "name": "Image Model",
                "model_type": "image",
                "provider": "openai-compatible",
                "model_name": "image-test",
                "base_url": "",
                "api_key": "",
                "is_default": False,
            },
        )
        assert image_response.status_code == 200

        owner_list_response = client.get(
            "/api/model-configs?model_type=text",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_list_response.status_code == 200
        owner_payload = owner_list_response.json()
        assert owner_payload["total"] == 1
        assert owner_payload["items"][0]["id"] == created["id"]
        assert owner_payload["items"][0]["model_type"] == "text"

        intruder_list_response = client.get(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_list_response.status_code == 403

        db = next(app.dependency_overrides[get_db]())
        try:
            config = db.query(ModelConfig).filter(ModelConfig.name == "OpenAI Text").one()
            assert config.encrypted_api_key != "sk-secret-text"
            assert decrypt_text(config.encrypted_api_key) == "sk-secret-text"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_admin_can_quick_configure_doubao_main_models_without_exposing_api_key(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.core.security import decrypt_text
    from backend.app.models import ModelConfig, User

    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("doubao-quick-config-admin")
    user_token = _register_and_get_access_token("doubao-quick-config-user")
    try:
        forbidden = client.post(
            "/api/model-configs/doubao-main",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"api_key": "sk-ark-user"},
        )
        assert forbidden.status_code == 403

        response = client.post(
            "/api/model-configs/doubao-main",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"api_key": "sk-ark-admin"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert "api_key" not in payload
        assert set(payload.keys()) == {"text", "vision"}
        assert payload["text"]["model_type"] == "text"
        assert payload["vision"]["model_type"] == "image"
        for item in (payload["text"], payload["vision"]):
            assert item["provider"] == "volcengine-ark"
            assert item["model_name"] == "doubao-seed-2-0-mini-260428"
            assert item["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
            assert item["has_api_key"] is True
            assert item["is_default"] is True
            assert "api_key" not in item
            assert "encrypted_api_key" not in item

        defaults_response = client.get(
            "/api/model-configs/capability-defaults",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert defaults_response.status_code == 200
        by_capability = {
            item["capability"]: item
            for item in defaults_response.json()["items"]
        }
        assert by_capability["text"]["model_config"]["id"] == payload["text"]["id"]
        assert by_capability["vision"]["model_config"]["id"] == payload["vision"]["id"]
        assert by_capability["image_generation"]["model_config"] is None

        repeat = client.post(
            "/api/model-configs/doubao-main",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"api_key": "sk-ark-rotated"},
        )

        assert repeat.status_code == 200
        assert repeat.json()["text"]["id"] == payload["text"]["id"]
        assert repeat.json()["vision"]["id"] == payload["vision"]["id"]

        db = next(app.dependency_overrides[get_db]())
        try:
            admin = db.scalar(select(User).where(User.username == "doubao-quick-config-admin"))
            assert admin is not None
            configs = db.scalars(select(ModelConfig).where(ModelConfig.provider == "volcengine-ark")).all()
            assert len(configs) == 2
            assert all(config.user_id == admin.id for config in configs)
            assert {config.model_type for config in configs} == {"text", "image"}
            assert all(config.is_default for config in configs)
            assert all(decrypt_text(config.encrypted_api_key) == "sk-ark-rotated" for config in configs)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_config_test_uses_runninghub_default_base_url_when_blank(tmp_path, monkeypatch):
    db_dependency = _override_database(tmp_path)
    token = _register_and_get_admin_access_token("runninghub-default-base-url-owner")

    class FakeResponse:
        status_code = 200
        text = '{"code":0,"msg":"success","data":{"webappName":"test","nodeInfoList":[]}}'

        def json(self):
            return {"code": 0, "msg": "success", "data": {"webappName": "test", "nodeInfoList": []}}

    def fake_get(url, **kwargs):
        assert url == "https://www.runninghub.cn/api/webapp/apiCallDemo"
        assert kwargs["headers"] == {"Authorization": "Bearer sk-runninghub-default-base", "Host": "www.runninghub.cn"}
        assert kwargs["params"] == {"apiKey": "sk-runninghub-default-base", "webappId": "2046760522573418497"}
        return FakeResponse()

    import backend.app.api.model_configs as model_configs_api

    monkeypatch.setattr(model_configs_api.http_requests, "get", fake_get, raising=False)

    try:
        response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "RunningHub Default Base URL",
                "model_type": "image",
                "provider": "runninghub-ai-app",
                "model_name": "runninghub-image-g",
                "base_url": "",
                "api_key": "sk-runninghub-default-base",
                "is_default": True,
            },
        )
        assert response.status_code == 200
        config_id = response.json()["id"]

        test_response = client.post(
            f"/api/model-configs/{config_id}/test?capability=image_generation",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert test_response.status_code == 200
        assert test_response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_config_test_checks_openai_compatible_image_models_with_chat_vision(tmp_path, monkeypatch):
    db_dependency = _override_database(tmp_path)
    token = _register_and_get_admin_access_token("doubao-image-config-owner")
    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"choices":[{"message":{"content":"ok"}}]}'

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        return FakeResponse()

    import backend.app.api.model_configs as model_configs_api

    monkeypatch.setattr(model_configs_api.http_requests, "post", fake_post, raising=False)

    try:
        response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Doubao Vision",
                "model_type": "image",
                "provider": "volcengine-ark",
                "model_name": "doubao-seed-2-0-mini-260428",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "api_key": "sk-doubao",
                "is_default": True,
            },
        )
        assert response.status_code == 200
        config_id = response.json()["id"]

        test_response = client.post(
            f"/api/model-configs/{config_id}/test?capability=vision",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert test_response.status_code == 200
        assert test_response.json()["status"] == "ok"
        assert captured["url"] == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        assert captured["headers"]["Authorization"] == "Bearer sk-doubao"
        assert captured["json"]["model"] == "doubao-seed-2-0-mini-260428"
        content = captured["json"]["messages"][0]["content"]
        assert {"type": "text", "text": "请用一句话描述这张图片。"} in content
        assert content[0]["type"] == "image_url"
        assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
        assert "images/generations" not in captured["url"]
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_openai_image_generation_model_test_calls_images_generation_endpoint(tmp_path, monkeypatch):
    import backend.app.api.model_configs as model_configs_api

    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"data":[{"url":"https://cdn.example.test/test.png"}]}'

        def json(self):
            return {"data": [{"url": "https://cdn.example.test/test.png"}]}

    def fake_post(url, **kwargs):
        captured.update(url=url, json=kwargs["json"], headers=kwargs["headers"])
        return FakeResponse()

    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("generation-test-admin")
    try:
        config = _create_capability_test_model_config(
            admin_token,
            model_name="image-generation-model",
            base_url="https://api.example.test/v1",
        )
        monkeypatch.setattr(model_configs_api.http_requests, "post", fake_post)

        response = client.post(
            f"/api/model-configs/{config['id']}/test?capability=image_generation",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert captured["url"] == "https://api.example.test/v1/images/generations"
        assert captured["json"]["model"] == "image-generation-model"
        assert captured["headers"]["Authorization"] == "Bearer sk-test"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_test_requires_explicit_capability(tmp_path, monkeypatch):
    import backend.app.api.model_configs as model_configs_api

    def unexpected_post(*args, **kwargs):
        raise AssertionError("provider must not be called without an explicit capability")

    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("explicit-capability-test-admin")
    try:
        config = _create_capability_test_model_config(
            admin_token,
            model_type="text",
            provider="openai-compatible",
        )
        monkeypatch.setattr(model_configs_api.http_requests, "post", unexpected_post)

        response = client.post(
            f"/api/model-configs/{config['id']}/test",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_test_rejects_capability_not_supported_by_config(tmp_path, monkeypatch):
    import backend.app.api.model_configs as model_configs_api

    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("incompatible-test-admin")
    try:
        text_config = _create_capability_test_model_config(
            admin_token,
            model_type="text",
            provider="volcengine-ark",
        )
        monkeypatch.setattr(
            model_configs_api.http_requests,
            "post",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("incompatible capability must not call the provider")
            ),
        )

        response = client.post(
            f"/api/model-configs/{text_config['id']}/test?capability=vision",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == {
            "code": "MODEL_CAPABILITY_INCOMPATIBLE",
            "capability": "vision",
        }
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_openai_compatible_image_describe_converts_local_media_to_base64(tmp_path, monkeypatch):
    from backend.app.models import ModelConfig
    from backend.app.services.ai_service import OpenAICompatibleImageClient
    import backend.app.services.ai_service as ai_service
    import backend.app.core.config as core_config

    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    image_name = "xhs-image-u1-0123456789abcdef0123456789abcdef.png"
    image_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=")
    (media_dir / image_name).write_bytes(image_bytes)
    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"choices":[{"message":{"content":"这是一张早餐图"}}]}'
        content = b'{"choices":[{"message":{"content":"\xe8\xbf\x99\xe6\x98\xaf\xe4\xb8\x80\xe5\xbc\xa0\xe6\x97\xa9\xe9\xa4\x90\xe5\x9b\xbe"}}]}'
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "这是一张早餐图"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr(core_config, "get_settings", lambda: SimpleNamespace(storage_dir=storage_dir), raising=False)
    monkeypatch.setattr(ai_service.requests, "post", fake_post, raising=False)

    result = OpenAICompatibleImageClient().describe_image(
        model_config=ModelConfig(
            provider="volcengine-ark",
            model_name="doubao-seed-2-0-mini-260428",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        ),
        api_key="sk-doubao",
        image_url=f"/api/files/media/{image_name}",
        instruction="描述卖点",
    )

    assert result == "这是一张早餐图"
    assert captured["url"] == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    image_part = captured["json"]["messages"][1]["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_image_generation_prefers_runninghub_when_doubao_is_default_vision_model(tmp_path, monkeypatch):
    import backend.app.api.ai as ai_api
    from backend.app.api.ai import get_image_ai_client
    from backend.app.core.database import get_db
    from backend.app.models import User

    class FakeGenerationClient:
        def __init__(self):
            self.calls = []

        def generate_image(self, *, model_config, api_key, prompt, reference_images=None, owner_user_id=None, aspect_ratio=None):
            self.calls.append((model_config.provider, model_config.model_name, api_key, prompt, reference_images, owner_user_id, aspect_ratio))
            return {"url": "https://cdn.example.test/generated.png", "raw": {"ok": True}}

    fake_client = FakeGenerationClient()
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("image-generation-routing-owner")
    admin_token = _register_and_get_admin_access_token("image-generation-routing-admin")
    try:
        app.dependency_overrides[get_image_ai_client] = lambda: fake_client
        monkeypatch.setattr(ai_api, "RunningHubImageClient", lambda: fake_client)
        monkeypatch.setattr(ai_api, "_download_public_http_image", lambda url: (base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="), "image/png"))
        stale_config = _create_capability_test_model_config(
            admin_token,
            name="Stale OpenAI Image",
            provider="openai-compatible",
            model_name="stale-image-model",
            api_key="sk-stale-image",
        )
        vision_config = _create_capability_test_model_config(
            admin_token,
            name="Doubao Vision",
            provider="volcengine-ark",
            model_name="doubao-seed-2-0-mini-260428",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="sk-doubao",
            is_default=True,
        )
        generation_config = _create_capability_test_model_config(
            admin_token,
            name="RunningHub Image Generation",
            provider="runninghub-ai-app",
            model_name="runninghub-image-g",
            base_url="https://www.runninghub.cn",
            api_key="sk-runninghub",
        )
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.put(
            "/api/model-configs/capability-defaults/vision",
            headers=headers,
            json={"model_config_id": vision_config["id"]},
        ).status_code == 200
        assert client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": generation_config["id"]},
        ).status_code == 200

        db = next(app.dependency_overrides[get_db]())
        try:
            owner = db.scalar(select(User).where(User.username == "image-generation-routing-owner"))
            assert owner is not None
            owner_user_id = owner.id
        finally:
            db.close()

        response = client.post(
            "/api/ai/images/generate",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "生成一张配图", "save_to_assets": False, "aspect_ratio": "1:1"},
        )

        assert response.status_code == 200
        assert fake_client.calls == [
            ("runninghub-ai-app", "runninghub-image-g", "sk-runninghub", "生成一张配图", None, owner_user_id, "1:1")
        ]
        assert stale_config["id"] < generation_config["id"]
        tasks = client.get("/api/tasks?platform=xhs", headers={"Authorization": f"Bearer {owner_token}"}).json()["items"]
        assert tasks[0]["payload"]["model_config_id"] == generation_config["id"]
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_unbound_image_generation_fails_before_quota_or_concurrency_reservation(tmp_path):
    from sqlalchemy import func

    from backend.app.api.ai import get_image_ai_client
    from backend.app.core.database import get_db
    from backend.app.models import BetaConcurrencyLease, UsageLedger

    class UnexpectedGenerationClient:
        def generate_image(self, **kwargs):
            raise AssertionError("provider must not be called without an explicit capability binding")

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("unbound-image-generation-owner")
    admin_token = _register_and_get_admin_access_token("unbound-image-generation-admin")
    try:
        app.dependency_overrides[get_image_ai_client] = lambda: UnexpectedGenerationClient()
        _create_capability_test_model_config(
            admin_token,
            name="Unbound Image Generation",
            provider="openai-compatible",
            model_name="unbound-image-model",
            is_default=True,
        )

        response = client.post(
            "/api/ai/images/generate",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "不应调用上游", "save_to_assets": False},
        )

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED"
        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.scalar(select(func.count(UsageLedger.id))) == 0
            assert db.scalar(select(func.count(BetaConcurrencyLease.id))) == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_async_image_generation_hides_provider_url_for_unauthorized_failure(tmp_path, monkeypatch):
    import backend.app.api.ai as ai_api

    from backend.app.api.ai import get_image_ai_client

    class UnauthorizedGenerationClient:
        def generate_image(self, **kwargs):
            response = requests.Response()
            response.status_code = 401
            response.url = "https://private-provider.example/images/generations"
            error = requests.HTTPError(
                "401 Client Error: Unauthorized for url: https://private-provider.example/images/generations",
                response=response,
            )
            raise ValueError(
                "图片生成失败: 401 Client Error: Unauthorized for url: https://private-provider.example/images/generations"
            ) from error

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("unauthorized-image-owner")
    admin_token = _register_and_get_admin_access_token("unauthorized-image-admin")
    try:
        app.dependency_overrides[get_image_ai_client] = lambda: UnauthorizedGenerationClient()
        monkeypatch.setattr(
            ai_api,
            "SessionLocal",
            app.dependency_overrides[db_dependency].sessionmaker,
        )
        config = _create_capability_test_model_config(
            admin_token,
            name="Unauthorized Image Provider",
            provider="openai-compatible",
            model_name="unauthorized-image-model",
            api_key="sk-private-provider",
        )
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": config["id"]},
        ).status_code == 200

        started = client.post(
            "/api/ai/images/generate-async",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "触发鉴权失败", "save_to_assets": False},
        )
        assert started.status_code == 200
        task = client.get(
            f"/api/tasks/{started.json()['task_id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
        ).json()

        assert task["status"] == "failed"
        assert task["payload"]["error_code"] == "MODEL_PROVIDER_UNAUTHORIZED"
        assert task["payload"]["error"] == "图片生成模型鉴权失败，请管理员检查模型配置"
        assert "private-provider.example" not in str(task["payload"])
        assert "sk-private-provider" not in str(task["payload"])
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_sync_image_generation_hides_provider_url_for_unauthorized_failure(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class UnauthorizedGenerationClient:
        def generate_image(self, **kwargs):
            response = requests.Response()
            response.status_code = 401
            response.url = "https://private-provider.example/images/generations"
            error = requests.HTTPError(
                "401 Client Error: Unauthorized for url: https://private-provider.example/images/generations",
                response=response,
            )
            raise ValueError(
                "图片生成失败: 401 Client Error: Unauthorized for url: https://private-provider.example/images/generations"
            ) from error

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("sync-unauthorized-image-owner")
    admin_token = _register_and_get_admin_access_token("sync-unauthorized-image-admin")
    try:
        app.dependency_overrides[get_image_ai_client] = lambda: UnauthorizedGenerationClient()
        config = _create_capability_test_model_config(
            admin_token,
            name="Sync Unauthorized Image Provider",
            provider="openai-compatible",
            model_name="sync-unauthorized-image-model",
            api_key="sk-private-provider",
        )
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": config["id"]},
        ).status_code == 200

        response = client.post(
            "/api/ai/images/generate",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "同步触发鉴权失败", "save_to_assets": False},
        )

        assert response.status_code == 502
        assert response.json()["detail"] == {
            "code": "MODEL_PROVIDER_UNAUTHORIZED",
            "message": "图片生成模型鉴权失败，请管理员检查模型配置",
        }
        tasks = client.get(
            "/api/tasks?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        ).json()["items"]
        assert tasks[0]["status"] == "failed"
        assert tasks[0]["payload"]["error_code"] == "MODEL_PROVIDER_UNAUTHORIZED"
        assert tasks[0]["payload"]["error"] == "图片生成模型鉴权失败，请管理员检查模型配置"
        assert tasks[0]["payload"]["provider"] == "openai-compatible"
        assert "private-provider.example" not in str(tasks[0]["payload"])
        assert "sk-private-provider" not in str(tasks[0]["payload"])
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_system_note_analysis_uses_admin_default_doubao_models_for_regular_user(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import ModelCapabilityDefault, ModelConfig, Note, NoteAsset, PlatformAccount, User
    from backend.app.services.note_analysis_service import analyze_note_system

    class FakeTextClient:
        def complete_json_prompt(self, *, model_config, api_key, system_prompt, user_prompt, temperature=0.1):
            assert model_config.model_name == "doubao-seed-2-0-mini-260428"
            assert api_key == "sk-doubao-text"
            return '{"subject_object":"低卡早餐","content_type":"经验分享"}'

    class FakeImageClient:
        def describe_image(self, *, model_config, api_key, image_url, instruction):
            assert model_config.model_name == "doubao-seed-2-0-mini-260428"
            assert api_key == "sk-doubao-vision"
            assert image_url == "https://example.test/cover.png"
            return "早餐封面"

    db_dependency = _override_database(tmp_path)
    _register_and_get_access_token("analysis-routing-owner")
    _register_and_get_admin_access_token("analysis-routing-admin")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            owner = db.scalar(select(User).where(User.username == "analysis-routing-owner"))
            admin = db.scalar(select(User).where(User.username == "analysis-routing-admin"))
            account = PlatformAccount(user_id=owner.id, platform="xhs", sub_type="pc", external_user_id="pc-owner", nickname="owner")
            db.add(account)
            db.flush()
            note = Note(
                user_id=owner.id,
                platform_account_id=account.id,
                platform="xhs",
                note_id="analysis-routing-note",
                title="低卡早餐",
                content="适合通勤党的早餐搭配",
            )
            db.add(note)
            db.flush()
            text_config = ModelConfig(
                user_id=admin.id,
                name="Doubao Text",
                model_type="text",
                provider="volcengine-ark",
                model_name="doubao-seed-2-0-mini-260428",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                encrypted_api_key=encrypt_text("sk-doubao-text"),
                is_default=True,
            )
            vision_config = ModelConfig(
                user_id=admin.id,
                name="Doubao Vision",
                model_type="image",
                provider="volcengine-ark",
                model_name="doubao-seed-2-0-mini-260428",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                encrypted_api_key=encrypt_text("sk-doubao-vision"),
                is_default=True,
            )
            db.add_all(
                [
                    NoteAsset(note_id=note.id, asset_type="image", url="https://example.test/cover.png", local_path="", sort_order=0),
                    text_config,
                    vision_config,
                ]
            )
            db.flush()
            db.add_all(
                [
                    ModelCapabilityDefault(
                        capability="text",
                        model_config_id=text_config.id,
                        updated_by_user_id=admin.id,
                    ),
                    ModelCapabilityDefault(
                        capability="vision",
                        model_config_id=vision_config.id,
                        updated_by_user_id=admin.id,
                    ),
                ]
            )
            db.commit()

            result = analyze_note_system(db, user_id=owner.id, note=note, text_client=FakeTextClient(), image_client=FakeImageClient())

            assert result.source == "system"
            assert result.subject_object == "低卡早餐"
            assert result.cover_type == "早餐封面"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_text_model_config_defaults_to_gpt_54_when_model_name_omitted(tmp_path):
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_admin_access_token("model-default-owner")
    try:
        response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "name": "Default Text",
                "model_type": "text",
                "provider": "openai-compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-default",
                "is_default": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["model_name"] == "doubao-seed-2-0-mini-260428"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_image_analysis_model_config_defaults_to_doubao_when_model_name_omitted(tmp_path):
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_admin_access_token("image-model-default-owner")
    try:
        response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "name": "Default Image Analysis",
                "model_type": "image",
                "provider": "volcengine-ark",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "api_key": "sk-default",
                "is_default": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["model_name"] == "doubao-seed-2-0-mini-260428"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_text_model_config_keeps_legacy_gpt_54_alias_normalization(tmp_path):
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_admin_access_token("model-legacy-alias-owner")
    try:
        response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "name": "Legacy GPT Alias",
                "model_type": "text",
                "provider": "openai-compatible",
                "model_name": "gpt5.4",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-default",
                "is_default": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["model_name"] == "gpt-5.4"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_configs_update_and_set_default_are_owner_scoped(tmp_path):
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_admin_access_token("model-update-owner")
    intruder_token = _register_and_get_access_token("model-update-intruder")
    try:
        first_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "name": "Text One",
                "model_type": "text",
                "provider": "provider-a",
                "model_name": "model-a",
                "base_url": "https://a.example.test",
                "api_key": "secret-a",
                "is_default": True,
            },
        )
        second_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "name": "Text Two",
                "model_type": "text",
                "provider": "provider-b",
                "model_name": "model-b",
                "base_url": "https://b.example.test",
                "api_key": "secret-b",
                "is_default": False,
            },
        )
        first_id = first_response.json()["id"]
        second_id = second_response.json()["id"]

        update_response = client.patch(
            f"/api/model-configs/{second_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Text Two Updated", "api_key": "secret-b2"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Text Two Updated"
        assert update_response.json()["has_api_key"] is True

        intruder_update_response = client.patch(
            f"/api/model-configs/{second_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"name": "stolen"},
        )
        assert intruder_update_response.status_code == 403

        default_response = client.post(
            f"/api/model-configs/{second_id}/set-default",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert default_response.status_code == 200
        assert default_response.json()["is_default"] is True

        list_response = client.get(
            "/api/model-configs?model_type=text",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        listed = {item["id"]: item for item in list_response.json()["items"]}
        assert listed[first_id]["is_default"] is False
        assert listed[second_id]["is_default"] is True

        intruder_default_response = client.post(
            f"/api/model-configs/{second_id}/set-default",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_default_response.status_code == 403
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_ai_rewrite_note_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/ai/rewrite-note", json={"draft_id": 1})

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_ai_rewrite_note_requires_owned_draft_and_default_text_model(tmp_path):
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("ai-rewrite-owner")
    intruder_token = _register_and_get_access_token("ai-rewrite-intruder")
    try:
        create_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Original title", "body": "Original body"},
        )
        draft_id = create_response.json()["id"]

        no_model_response = client.post(
            "/api/ai/rewrite-note",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"draft_id": draft_id},
        )
        assert no_model_response.status_code == 503
        assert no_model_response.json()["detail"] == {
            "code": "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED",
            "capability": "text",
        }

        intruder_response = client.post(
            "/api/ai/rewrite-note",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"draft_id": draft_id},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_ai_rewrite_note_returns_preview_candidate_without_overwriting_owned_draft(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    class FakeTextAiClient:
        def __init__(self):
            self.calls = []

        def rewrite_note(self, *, model_config, api_key, title, body, instruction):
            self.calls.append(
                {
                    "model_name": model_config.model_name,
                    "api_key": api_key,
                    "title": title,
                    "body": body,
                    "instruction": instruction,
                }
            )
            return f"{title}\n\n改写结果：{title} / {instruction}"

    fake_client = FakeTextAiClient()
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("ai-rewrite-success")
    admin_token = _register_and_get_admin_access_token("ai-rewrite-admin")
    try:
        app.dependency_overrides[get_text_ai_client] = lambda: fake_client

        model_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Default Text",
                "model_type": "text",
                "provider": "openai-compatible",
                "model_name": "gpt-rewrite-test",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-rewrite-secret",
                "is_default": True,
            },
        )
        assert model_response.status_code == 200
        _assign_capability_default(admin_token, "text", model_response.json()["id"])

        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "爆款标题", "body": "原始正文"},
        )
        draft_id = draft_response.json()["id"]
        tag_response = client.patch(
            f"/api/drafts/{draft_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"tags": [{"name": "种草"}, {"name": "种草"}, {"name": "探店"}]},
        )
        assert tag_response.status_code == 200
        assert tag_response.json()["body"] == "原始正文"

        rewrite_response = client.post(
            "/api/ai/rewrite-note",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"draft_id": draft_id, "instruction": "更适合小红书种草"},
        )
        assert rewrite_response.status_code == 200
        rewritten = rewrite_response.json()
        assert rewritten["id"] == draft_id
        assert rewritten["title"] == "爆款标题"
        assert rewritten["body"] == "改写结果：爆款标题 / 更适合小红书种草"
        assert rewritten["tags"] == [{"name": "种草"}, {"name": "探店"}]
        assert fake_client.calls == [
            {
                "model_name": "gpt-rewrite-test",
                "api_key": "sk-rewrite-secret",
                "title": "爆款标题",
                "body": "原始正文",
                "instruction": "更适合小红书种草",
            }
        ]

        list_response = client.get(
            "/api/drafts?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        persisted = list_response.json()["items"][0]
        assert persisted["title"] == "爆款标题"
        assert persisted["body"] == "原始正文"
        assert persisted["tags"] == [{"name": "种草"}, {"name": "探店"}]

        tasks_response = client.get(
            "/api/tasks?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert tasks_response.status_code == 200
        task_payload = tasks_response.json()
        assert task_payload["total"] == 1
        task = task_payload["items"][0]
        assert task["task_type"] == "ai_rewrite"
        assert task["status"] == "completed"
        assert task["progress"] == 100
        assert task["payload"]["draft_id"] == draft_id
        assert task["payload"]["model_config_id"] == model_response.json()["id"]
        assert task["payload"]["preview_only"] is True
        assert task["payload"]["result"] == {
            "title": "爆款标题",
            "body": "改写结果：爆款标题 / 更适合小红书种草",
            "tags": [{"name": "种草"}, {"name": "探店"}],
        }
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_draft_ai_score_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/drafts/1/ai-score", json={})

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


class FakeDraftScoreClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def complete_json_prompt(self, *, model_config, api_key, system_prompt, user_prompt, temperature=0.2):
        self.calls.append({
            "model_name": model_config.model_name,
            "api_key": api_key,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": temperature,
        })
        return self.response


def _create_default_text_model(token: str, model_name: str = "gpt-score-test"):
    response = client.post(
        "/api/model-configs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Default Text",
            "model_type": "text",
            "provider": "openai-compatible",
            "model_name": model_name,
            "base_url": "https://api.example.test/v1",
            "api_key": "sk-score-secret",
            "is_default": True,
        },
    )
    assert response.status_code == 200
    _assign_capability_default(token, "text", response.json()["id"])
    return response.json()


def test_draft_ai_score_requires_owned_draft_and_default_text_model(tmp_path):
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("draft-score-owner")
    intruder_token = _register_and_get_access_token("draft-score-intruder")
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "系统打分标题", "body": "系统打分正文"},
        )
        assert draft_response.status_code == 200
        draft_id = draft_response.json()["id"]

        no_model_response = client.post(
            f"/api/drafts/{draft_id}/ai-score",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={},
        )
        assert no_model_response.status_code == 503
        assert no_model_response.json()["detail"] == {
            "code": "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED",
            "capability": "text",
        }

        intruder_response = client.post(
            f"/api/drafts/{draft_id}/ai-score",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_draft_ai_score_creates_task_and_latest_result(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    fake_client = FakeDraftScoreClient(
        '{"overall_score":86,"potential_level":"high","summary":"选题清晰，适合发布前优化。",'
        '"dimensions":[{"key":"opportunity_fit","label":"机会匹配","score":25,"max_score":30,"reason":"命中关键词机会。"}],'
        '"risks":[{"level":"medium","title":"案例不足","detail":"缺少真实案例。"}],'
        '"suggestions":[{"priority":"high","title":"补充案例","example":"增加一个前后对比案例。"}],'
        '"opportunities":[{"type":"keyword","label":"低卡早餐","reason":"命中关键词。"}]}'
    )
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("draft-score-success")
    admin_token = _register_and_get_admin_access_token("draft-score-success-admin")
    try:
        app.dependency_overrides[get_text_ai_client] = lambda: fake_client
        model = _create_default_text_model(admin_token)
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "低卡早餐怎么搭", "body": "低卡早餐步骤和避坑建议，适合通勤党收藏。" * 6},
        )
        draft_id = draft_response.json()["id"]
        asset_response = client.post(
            f"/api/drafts/{draft_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "url": "https://example.test/breakfast.jpg"},
        )
        assert asset_response.status_code == 200

        score_response = client.post(
            f"/api/drafts/{draft_id}/ai-score",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={},
        )
        assert score_response.status_code == 200
        score = score_response.json()
        assert score["overall_score"] == 86
        assert score["potential_level"] == "high"
        assert score["fallback_used"] is False
        assert score["dimensions"][0]["key"] == "opportunity_fit"
        assert "不代表实际流量预测" in score["disclaimer"]

        latest_response = client.get(
            f"/api/drafts/{draft_id}/ai-score/latest",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert latest_response.status_code == 200
        assert latest_response.json()["id"] == score["id"]

        tasks_response = client.get("/api/tasks?platform=xhs", headers={"Authorization": f"Bearer {owner_token}"})
        task = tasks_response.json()["items"][0]
        assert task["task_type"] == "draft_ai_score"
        assert task["status"] == "completed"
        assert task["payload"]["draft_id"] == draft_id
        assert task["payload"]["model_config_id"] == model["id"]
        assert task["payload"]["result_id"] == score["id"]
        assert task["payload"]["fallback_used"] is False
        assert fake_client.calls[0]["model_name"] == "gpt-score-test"
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_draft_ai_score_falls_back_to_rules_when_ai_json_invalid(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    fake_client = FakeDraftScoreClient("not json")
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("draft-score-fallback")
    admin_token = _register_and_get_admin_access_token("draft-score-fallback-admin")
    try:
        app.dependency_overrides[get_text_ai_client] = lambda: fake_client
        _create_default_text_model(admin_token)
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "AI 打分怎么做", "body": "步骤 清单 避坑 数据 案例 " * 20},
        )
        draft_id = draft_response.json()["id"]

        score_response = client.post(
            f"/api/drafts/{draft_id}/ai-score",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={},
        )
        assert score_response.status_code == 200
        score = score_response.json()
        assert score["fallback_used"] is True
        assert score["summary"]
        assert score["dimensions"]
        assert score["suggestions"]
        assert "ai_error" not in score
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_draft_ai_score_scopes_comments_through_owned_notes(tmp_path):
    from backend.app.api.ai import get_text_ai_client
    from backend.app.models import NoteComment, PlatformAccount, User

    fake_client = FakeDraftScoreClient('{"overall_score":72,"potential_level":"medium","summary":"可优化。"}')
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("draft-score-comment-owner")
    intruder_token = _register_and_get_access_token("draft-score-comment-intruder")
    admin_token = _register_and_get_admin_access_token("draft-score-comment-admin")
    try:
        app.dependency_overrides[get_text_ai_client] = lambda: fake_client
        _create_default_text_model(admin_token)
        db = next(app.dependency_overrides[get_db]())
        try:
            owner = db.scalar(select(User).where(User.username == "draft-score-comment-owner"))
            intruder = db.scalar(select(User).where(User.username == "draft-score-comment-intruder"))
            owner_account = PlatformAccount(user_id=owner.id, platform="xhs", nickname="owner")
            intruder_account = PlatformAccount(user_id=intruder.id, platform="xhs", nickname="intruder")
            db.add_all([owner_account, intruder_account])
            db.flush()
            owner_note = Note(user_id=owner.id, platform_account_id=owner_account.id, platform="xhs", note_id="owner-note", title="早餐", content="低卡早餐")
            intruder_note = Note(user_id=intruder.id, platform_account_id=intruder_account.id, platform="xhs", note_id="intruder-note", title="竞品", content="不要泄露")
            db.add_all([owner_note, intruder_note])
            db.flush()
            db.add_all([
                NoteComment(note_id=owner_note.id, comment_id="c-owner", content="owner-only-comment", like_count=9),
                NoteComment(note_id=intruder_note.id, comment_id="c-intruder", content="intruder-secret-comment", like_count=99),
            ])
            db.commit()
            owner_note_id = owner_note.id
        finally:
            db.close()

        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "source_note_id": owner_note_id, "title": "低卡早餐", "body": "低卡早餐怎么搭配" * 10},
        )
        assert draft_response.status_code == 200
        draft_id = draft_response.json()["id"]

        score_response = client.post(
            f"/api/drafts/{draft_id}/ai-score",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={},
        )
        assert score_response.status_code == 200
        prompt = fake_client.calls[0]["user_prompt"]
        assert "owner-only-comment" in prompt
        assert "intruder-secret-comment" not in prompt
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_ai_text_generation_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/ai/generate-note", json={"topic": "低卡早餐"})

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_ai_text_generation_endpoints_use_default_model_and_create_tasks(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    class FakeTextGenerationClient:
        def __init__(self):
            self.calls = []

        def rewrite_note(self, *, model_config, api_key, title, body, instruction):
            raise AssertionError("rewrite_note should not be called")

        def generate_note(self, *, model_config, api_key, topic, reference, instruction):
            self.calls.append(("generate_note", model_config.model_name, api_key, topic, reference, instruction))
            return {"title": f"{topic} 标题", "body": f"{topic} 正文 {reference} {instruction}".strip()}

        def generate_titles(self, *, model_config, api_key, title, body, count):
            self.calls.append(("generate_titles", model_config.model_name, api_key, title, body, count))
            return ["标题 A", "标题 B"][:count]

        def generate_tags(self, *, model_config, api_key, title, body, count):
            self.calls.append(("generate_tags", model_config.model_name, api_key, title, body, count))
            return ["低卡", "早餐", "通勤"][:count]

        def polish_text(self, *, model_config, api_key, text, instruction):
            self.calls.append(("polish_text", model_config.model_name, api_key, text, instruction))
            return f"润色：{text} / {instruction}"

    fake_client = FakeTextGenerationClient()
    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("ai-generate-owner")
    admin_token = _register_and_get_admin_access_token("ai-generate-admin")
    try:
        app.dependency_overrides[get_text_ai_client] = lambda: fake_client
        model_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Default Text",
                "model_type": "text",
                "provider": "openai-compatible",
                "model_name": "gpt-generate-test",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-generate-secret",
                "is_default": True,
            },
        )
        assert model_response.status_code == 200
        _assign_capability_default(admin_token, "text", model_response.json()["id"])

        generate_response = client.post(
            "/api/ai/generate-note",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "topic": "低卡早餐", "reference": "参考笔记", "instruction": "更具体"},
        )
        assert generate_response.status_code == 200
        generated = generate_response.json()
        assert generated["title"] == "低卡早餐 标题"
        assert generated["body"] == "低卡早餐 正文 参考笔记 更具体"

        titles_response = client.post(
            "/api/ai/generate-title",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"title": "旧标题", "body": "正文", "count": 2},
        )
        assert titles_response.status_code == 200
        assert titles_response.json()["items"] == ["标题 A", "标题 B"]

        tags_response = client.post(
            "/api/ai/generate-tags",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"title": "早餐", "body": "低卡早餐正文", "count": 3},
        )
        assert tags_response.status_code == 200
        assert tags_response.json()["items"] == ["低卡", "早餐", "通勤"]

        polish_response = client.post(
            "/api/ai/polish-text",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"text": "原文", "instruction": "更自然"},
        )
        assert polish_response.status_code == 200
        assert polish_response.json()["text"] == "润色：原文 / 更自然"

        tasks_response = client.get("/api/tasks?platform=xhs", headers={"Authorization": f"Bearer {owner_token}"})
        assert tasks_response.status_code == 200
        task_types = [item["task_type"] for item in tasks_response.json()["items"]]
        assert task_types == ["ai_polish_text", "ai_generate_tags", "ai_generate_title", "ai_generate_note"]
        assert fake_client.calls[0] == (
            "generate_note",
            "gpt-generate-test",
            "sk-generate-secret",
            "低卡早餐",
            "参考笔记",
            "更具体",
        )
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_runninghub_upload_reference_image_accepts_success_code_zero(tmp_path, monkeypatch):
    from backend.app.core import config as config_module
    from backend.app.services.ai_service import RunningHubImageClient

    media_dir = tmp_path / "storage" / "media"
    media_dir.mkdir(parents=True)
    ref = media_dir / "xhs-upload-u1-ref.png"
    ref.write_bytes(b"fake-image")
    monkeypatch.setattr(config_module, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"))

    class FakeResponse:
        status_code = 200
        content = b'{"code":0,"msg":"success","data":{"filename":"openapi/ref.png"}}'
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = content.decode("utf-8")

        def raise_for_status(self):
            pass

    class FakeSession:
        def post(self, url, **kwargs):
            return FakeResponse()

    client_instance = RunningHubImageClient(session=FakeSession(), poll_interval_seconds=0, max_poll_attempts=1)

    filename = client_instance._upload_reference_image(
        base_url="https://www.runninghub.cn",
        api_key="sk-test",
        image_ref="/api/files/media/xhs-upload-u1-ref.png",
        owner_user_id=1,
    )

    assert filename == "openapi/ref.png"


def test_runninghub_upload_reference_image_accepts_camel_case_file_name(tmp_path, monkeypatch):
    from backend.app.core import config as config_module
    from backend.app.services.ai_service import RunningHubImageClient

    media_dir = tmp_path / "storage" / "media"
    media_dir.mkdir(parents=True)
    ref = media_dir / "xhs-upload-u1-ref.png"
    ref.write_bytes(b"fake-image")
    monkeypatch.setattr(config_module, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"))

    class FakeResponse:
        status_code = 200
        content = b'{"code":0,"message":"success","data":{"fileName":"openapi/ref.png"}}'
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = content.decode("utf-8")

        def raise_for_status(self):
            pass

    class FakeSession:
        def post(self, url, **kwargs):
            return FakeResponse()

    client_instance = RunningHubImageClient(session=FakeSession(), poll_interval_seconds=0, max_poll_attempts=1)

    filename = client_instance._upload_reference_image(
        base_url="https://www.runninghub.cn",
        api_key="sk-test",
        image_ref="/api/files/media/xhs-upload-u1-ref.png",
        owner_user_id=1,
    )

    assert filename == "openapi/ref.png"


def test_runninghub_upload_reference_image_accepts_filename_even_when_code_differs(tmp_path, monkeypatch):
    from backend.app.core import config as config_module
    from backend.app.services.ai_service import RunningHubImageClient

    media_dir = tmp_path / "storage" / "media"
    media_dir.mkdir(parents=True)
    ref = media_dir / "xhs-upload-u1-ref.png"
    ref.write_bytes(b"fake-image")
    monkeypatch.setattr(config_module, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"))

    class FakeResponse:
        status_code = 200
        content = b'{"code":1,"msg":"success","data":{"filename":"openapi/ref.png"}}'
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = content.decode("utf-8")

        def raise_for_status(self):
            pass

    class FakeSession:
        def post(self, url, **kwargs):
            return FakeResponse()

    client_instance = RunningHubImageClient(session=FakeSession(), poll_interval_seconds=0, max_poll_attempts=1)

    filename = client_instance._upload_reference_image(
        base_url="https://www.runninghub.cn",
        api_key="sk-test",
        image_ref="/api/files/media/xhs-upload-u1-ref.png",
        owner_user_id=1,
    )

    assert filename == "openapi/ref.png"


def test_runninghub_uses_landscape_aspect_ratio_from_first_reference_image(tmp_path, monkeypatch):
    from backend.app.core import config as config_module
    from backend.app.models import ModelConfig
    from backend.app.services.ai_service import RunningHubImageClient
    from PIL import Image

    media_dir = tmp_path / "storage" / "media"
    media_dir.mkdir(parents=True)
    ref = media_dir / "xhs-upload-u1-landscape.png"
    Image.new("RGB", (1440, 1080), (255, 255, 255)).save(ref)
    monkeypatch.setattr(config_module, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"))

    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        apparent_encoding = "utf-8"

        def __init__(self, content: bytes):
            self.content = content
            self.text = content.decode("utf-8")

        def raise_for_status(self):
            pass

    class FakeSession:
        def __init__(self):
            self.run_payload = None

        def post(self, url, **kwargs):
            if url.endswith("/openapi/v2/media/upload/binary"):
                return FakeResponse(b'{"code":0,"data":{"filename":"openapi/landscape.png"}}')
            if url.endswith("/task/openapi/ai-app/run"):
                self.run_payload = kwargs["json"]
                return FakeResponse(b'{"code":0,"data":{"taskId":"task-1"}}')
            if url.endswith("/task/openapi/status"):
                return FakeResponse(b'{"code":0,"data":"SUCCESS"}')
            if url.endswith("/task/openapi/outputs"):
                return FakeResponse(b'{"code":0,"data":[{"fileUrl":"https://cdn.example.test/output.png"}]}')
            raise AssertionError(f"unexpected url: {url}")

    fake_session = FakeSession()
    config = ModelConfig(provider="runninghub-ai-app", model_name="runninghub-image-g", base_url="https://www.runninghub.cn")
    client_instance = RunningHubImageClient(session=fake_session, poll_interval_seconds=0, max_poll_attempts=1)

    client_instance.generate_image(
        model_config=config,
        api_key="sk-test",
        prompt="测试",
        reference_images=["/api/files/media/xhs-upload-u1-landscape.png"],
        owner_user_id=1,
        aspect_ratio="auto",
    )

    assert fake_session.run_payload is not None
    aspect_ratio_nodes = [
        item for item in fake_session.run_payload["nodeInfoList"]
        if item["fieldName"] == "aspectRatio"
    ]
    assert aspect_ratio_nodes == [{"nodeId": "4", "fieldName": "aspectRatio", "fieldValue": "4:3"}]


def test_runninghub_text_to_image_keeps_default_portrait_aspect_ratio():
    from backend.app.services.ai_service import RunningHubImageClient

    node_info = RunningHubImageClient.build_text_to_image_node_info_list("测试")

    assert {"nodeId": "136", "fieldName": "aspectRatio", "fieldValue": "3:4"} in node_info


def test_runninghub_rejects_too_many_reference_images_before_upload(tmp_path, monkeypatch):
    from backend.app.core import config as config_module
    from backend.app.models import ModelConfig
    from backend.app.services.ai_service import RunningHubImageClient

    media_dir = tmp_path / "storage" / "media"
    media_dir.mkdir(parents=True)
    refs = [f"xhs-upload-u1-ref-{index}.png" for index in range(3)]
    for ref in refs:
        (media_dir / ref).write_bytes(b"fake-image")
    monkeypatch.setattr(config_module, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"))

    class FakeSession:
        def post(self, url, **kwargs):
            raise AssertionError("RunningHub upload should not be called when reference images exceed the workflow limit")

    config = ModelConfig(provider="runninghub-ai-app", model_name="runninghub-image-g", base_url="https://www.runninghub.cn")
    client_instance = RunningHubImageClient(session=FakeSession(), poll_interval_seconds=0, max_poll_attempts=1)

    with pytest.raises(ValueError, match="最多支持 2 张参考图"):
        client_instance.generate_image(
            model_config=config,
            api_key="sk-test",
            prompt="测试",
            reference_images=[f"/api/files/media/{ref}" for ref in refs],
            owner_user_id=1,
        )


def test_image_client_for_model_uses_runninghub_client_for_any_fallback():
    from backend.app.api.ai import _image_client_for_model
    from backend.app.models import ModelConfig
    from backend.app.services.ai_service import RunningHubImageClient

    class FakeImageClient:
        pass

    model_config = ModelConfig(provider="runninghub-ai-app", model_name="runninghub-image-g")

    image_client = _image_client_for_model(model_config, FakeImageClient())

    assert isinstance(image_client, RunningHubImageClient)


def test_runninghub_default_wait_window_allows_long_image_jobs():
    from backend.app.services.ai_service import RunningHubImageClient

    client_instance = RunningHubImageClient()

    assert client_instance.poll_interval_seconds * client_instance.max_poll_attempts >= 480


def test_frontend_ai_image_generate_uses_async_task_polling_for_long_runninghub_jobs():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    page_source = open("frontend/src/pages/platforms/xhs/image-studio-page.tsx", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()

    assert "generate-async" in api_source
    assert "startImageGenerationTask" in page_source
    assert "fetchTask" in page_source
    assert "图片生成任务已提交" in page_source
    assert "图片生成任务仍在运行" in page_source
    assert "aspect_ratio" in types_source
    assert "aspect_ratio: aspectRatio" in page_source
    assert "跟随参考图" in page_source
    assert "横屏 4:3" in page_source


def test_image_studio_publish_handoff_uses_server_managed_generated_asset_and_blocks_reference_limit():
    page_source = open("frontend/src/pages/platforms/xhs/image-studio-page.tsx", encoding="utf-8").read()

    assert "asset_file_path: generatedPreview" not in page_source
    assert "generatedPublishMediaPath" in page_source
    assert "referenceLimitReached" in page_source
    assert "已达上限" in page_source
    assert 'cursor: referenceLimitReached ? "not-allowed" : "pointer"' in page_source


def test_image_studio_draft_context_requires_explicit_handoff_and_fresh_timestamp():
    page_source = open("frontend/src/pages/platforms/xhs/image-studio-page.tsx", encoding="utf-8").read()
    context_source = open("frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts", encoding="utf-8").read()

    assert "useLocation" in page_source
    assert 'searchParams.get("from") === "draft"' in page_source
    assert "navigate(\"/platforms/xhs/image-studio\", { replace: true })" in page_source
    assert "loadImageStudioDraftContext({ requireFresh: true })" in page_source
    assert "created_at" in context_source
    assert "IMAGE_STUDIO_DRAFT_CONTEXT_TTL_MS" in context_source
    assert "Date.now()" in context_source


def test_runninghub_resolve_local_image_path_enforces_owned_media_prefixes(tmp_path, monkeypatch):
    from backend.app.core import config as config_module
    from backend.app.services.ai_service import RunningHubImageClient

    media_dir = tmp_path / "storage" / "media"
    media_dir.mkdir(parents=True)
    upload_file = media_dir / "xhs-upload-u1-owned.png"
    asset_file = media_dir / "xhs-asset-u1-owned.png"
    image_file = media_dir / "xhs-image-u1-owned.png"
    other_file = media_dir / "xhs-asset-u2-other.png"
    upload_file.write_bytes(b"upload")
    asset_file.write_bytes(b"asset")
    image_file.write_bytes(b"image")
    other_file.write_bytes(b"other")
    monkeypatch.setattr(config_module, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"))

    assert RunningHubImageClient._resolve_local_image_path(
        "/api/files/media/xhs-upload-u1-owned.png",
        owner_user_id=1,
    ) == upload_file.resolve()
    assert RunningHubImageClient._resolve_local_image_path(
        "/api/files/media/xhs-asset-u1-owned.png",
        owner_user_id=1,
    ) == asset_file.resolve()
    assert RunningHubImageClient._resolve_local_image_path(
        "/api/files/media/xhs-image-u1-owned.png",
        owner_user_id=1,
    ) == image_file.resolve()
    with pytest.raises(ValueError, match="参考图文件不存在或无权访问"):
        RunningHubImageClient._resolve_local_image_path(
            "/api/files/media/xhs-asset-u2-other.png",
            owner_user_id=1,
        )


def test_ai_image_routes_require_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/ai/images/generate-cover", json={"prompt": "低卡早餐封面"})

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_generated_image_media_storage_rejects_content_type_spoofed_bytes(tmp_path, monkeypatch):
    import backend.app.api.ai as ai_api

    monkeypatch.setattr(ai_api, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"), raising=False)

    with pytest.raises(ValueError, match="不是受支持的图片格式"):
        ai_api._store_generated_image_bytes(1, b"not an image", content_type="image/png")

    media_dir = tmp_path / "storage" / "media"
    assert not media_dir.exists() or list(media_dir.iterdir()) == []


def test_download_public_http_image_rejects_private_resolved_ip(monkeypatch):
    import backend.app.api.ai as ai_api

    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        return [(ai_api.socket.AF_INET, ai_api.socket.SOCK_STREAM, 6, "", ("127.0.0.1", int(port or 80)))]

    monkeypatch.setattr(ai_api.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="内网地址"):
        ai_api._download_public_http_image("http://example.test/spoof.png")


def test_download_public_http_image_rejects_non_global_resolved_ip(monkeypatch):
    import backend.app.api.ai as ai_api

    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        return [(ai_api.socket.AF_INET, ai_api.socket.SOCK_STREAM, 6, "", ("100.64.0.1", int(port or 80)))]

    monkeypatch.setattr(ai_api.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="内网地址"):
        ai_api._download_public_http_image("http://example.test/spoof.png")


def test_ai_image_routes_use_default_model_store_assets_and_enforce_scope(tmp_path, monkeypatch):
    import backend.app.api.ai as ai_api
    from backend.app.api.ai import get_image_ai_client

    class FakeImageAiClient:
        def __init__(self):
            self.calls = []

        def generate_cover(self, *, model_config, api_key, prompt, size, style):
            self.calls.append(("generate_cover", model_config.model_name, api_key, prompt, size, style))
            return {"url": "https://cdn.example.test/cover.png", "raw": {"seed": 1}}

        def generate_image(self, *, model_config, api_key, prompt, reference_images=None, owner_user_id=None, aspect_ratio=None):
            self.calls.append(("generate_image", model_config.model_name, api_key, prompt, reference_images, owner_user_id, aspect_ratio))
            return {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=", "raw": {"seed": 2}}

        def describe_image(self, *, model_config, api_key, image_url, instruction):
            self.calls.append(("describe_image", model_config.model_name, api_key, image_url, instruction))
            return "这是一张低卡早餐封面"

    fake_client = FakeImageAiClient()
    downloaded_urls = []
    valid_png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=")

    def fake_checked_download(url):
        downloaded_urls.append(url)
        return valid_png_bytes, "image/png"

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("ai-image-owner")
    admin_token = _register_and_get_admin_access_token("ai-image-admin")
    intruder_token = _register_and_get_access_token("ai-image-intruder")
    try:
        app.dependency_overrides[get_image_ai_client] = lambda: fake_client
        monkeypatch.setattr(ai_api, "SessionLocal", app.dependency_overrides[db_dependency].sessionmaker)
        monkeypatch.setattr(ai_api, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"), raising=False)
        monkeypatch.setattr(ai_api, "_download_public_http_image", fake_checked_download)
        model_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Default Image",
                "model_type": "image",
                "provider": "openai-compatible",
                "model_name": "image-generate-test",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-image-secret",
                "is_default": True,
            },
        )
        assert model_response.status_code == 200
        _assign_capability_default(admin_token, "vision", model_response.json()["id"])
        _assign_capability_default(admin_token, "image_generation", model_response.json()["id"])

        generate_response = client.post(
            "/api/ai/images/generate-cover",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "低卡早餐封面", "size": "1024x1024", "style": "clean"},
        )
        assert generate_response.status_code == 200
        generated = generate_response.json()
        assert re.match(r"^/api/files/media/xhs-image-u\d+-[0-9a-f]{32}\.png$", generated["file_path"])
        cover_media_file_name = generated["file_path"].removeprefix("/api/files/media/")
        assert (tmp_path / "storage" / "media" / cover_media_file_name).is_file()
        assert downloaded_urls == ["https://cdn.example.test/cover.png"]
        assert generated["prompt"] == "低卡早餐封面"
        assert generated["model_name"] == "image-generate-test"

        list_response = client.get("/api/ai/images/assets", headers={"Authorization": f"Bearer {owner_token}"})
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["id"] == generated["id"]

        intruder_list_response = client.get("/api/ai/images/assets", headers={"Authorization": f"Bearer {intruder_token}"})
        assert intruder_list_response.status_code == 200
        assert intruder_list_response.json()["total"] == 0

        describe_response = client.post(
            "/api/ai/images/describe",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"image_url": generated["file_path"], "instruction": "描述卖点"},
        )
        assert describe_response.status_code == 200
        assert describe_response.json()["text"] == "这是一张低卡早餐封面"

        async_response = client.post(
            "/api/ai/images/generate-async",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "异步生成测试", "reference_images": ["https://cdn.example.test/ref.png"], "save_to_assets": True, "aspect_ratio": "4:3"},
        )
        assert async_response.status_code == 200
        async_payload = async_response.json()
        assert async_payload["task_id"] > 0
        task_detail_response = client.get(f"/api/tasks/{async_payload['task_id']}", headers={"Authorization": f"Bearer {owner_token}"})
        assert task_detail_response.status_code == 200
        task_detail = task_detail_response.json()
        assert task_detail["status"] == "completed"
        assert task_detail["payload"]["result"]["url"].startswith("data:image/png;base64,")
        generated_asset_path = task_detail["payload"]["result"]["asset"]["file_path"]
        assert re.match(r"^/api/files/media/xhs-image-u\d+-[0-9a-f]{32}\.png$", generated_asset_path)
        media_file_name = generated_asset_path.removeprefix("/api/files/media/")
        assert (tmp_path / "storage" / "media" / media_file_name).is_file()

        tasks_response = client.get("/api/tasks?platform=xhs", headers={"Authorization": f"Bearer {owner_token}"})
        assert tasks_response.status_code == 200
        task_types = [item["task_type"] for item in tasks_response.json()["items"]]
        assert task_types == ["ai_image_generate", "ai_image_describe", "ai_image_generate_cover"]
        assert fake_client.calls == [
            ("generate_cover", "image-generate-test", "sk-image-secret", "低卡早餐封面", "1024x1024", "clean"),
            ("describe_image", "image-generate-test", "sk-image-secret", generated["file_path"], "描述卖点"),
            ("generate_image", "image-generate-test", "sk-image-secret", "异步生成测试", ["https://cdn.example.test/ref.png"], None, "4:3"),
        ]
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_ai_image_generate_asset_import_failure_returns_clear_failure(tmp_path, monkeypatch):
    import backend.app.api.ai as ai_api
    from backend.app.api.ai import get_image_ai_client

    class InvalidAssetImageClient:
        def generate_image(self, *, model_config, api_key, prompt, reference_images=None, owner_user_id=None, aspect_ratio=None):
            return {"url": "not-a-valid-image-reference", "raw": {"seed": 3}}

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("ai-image-import-failure-owner")
    admin_token = _register_and_get_admin_access_token("ai-image-import-failure-admin")
    tolerant_client = TestClient(app, raise_server_exceptions=False)
    try:
        app.dependency_overrides[get_image_ai_client] = lambda: InvalidAssetImageClient()
        monkeypatch.setattr(ai_api, "SessionLocal", app.dependency_overrides[db_dependency].sessionmaker)
        monkeypatch.setattr(ai_api, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"), raising=False)
        model_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Default Invalid Image",
                "model_type": "image",
                "provider": "openai-compatible",
                "model_name": "image-import-failure-test",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-image-secret",
                "is_default": True,
            },
        )
        assert model_response.status_code == 200
        _assign_capability_default(admin_token, "image_generation", model_response.json()["id"])

        sync_response = tolerant_client.post(
            "/api/ai/images/generate",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "同步资产导入失败", "save_to_assets": True},
        )
        assert sync_response.status_code == 400
        assert sync_response.json()["detail"] == "生成图片结果必须是媒体资产、HTTP(S) 图片或 base64 图片"

        assets_response = client.get("/api/ai/images/assets", headers={"Authorization": f"Bearer {owner_token}"})
        assert assets_response.status_code == 200
        assert assets_response.json()["total"] == 0

        async_response = tolerant_client.post(
            "/api/ai/images/generate-async",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "异步资产导入失败", "save_to_assets": True},
        )
        assert async_response.status_code == 200
        async_payload = async_response.json()
        task_detail_response = client.get(f"/api/tasks/{async_payload['task_id']}", headers={"Authorization": f"Bearer {owner_token}"})
        assert task_detail_response.status_code == 200
        task_detail = task_detail_response.json()
        assert task_detail["status"] == "failed"
        assert task_detail["progress"] == 100
        assert task_detail["payload"]["error"] == "生成图片结果必须是媒体资产、HTTP(S) 图片或 base64 图片"
        assert "asset_id" not in task_detail["payload"]
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_tasks_api_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.get("/api/tasks?platform=xhs")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_tasks_api_lists_only_current_user_tasks_and_filters_platform(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import Task

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("task-owner")
    intruder_token = _register_and_get_access_token("task-intruder")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            db.add_all(
                [
                    Task(
                        user_id=1,
                        platform="xhs",
                        task_type="ai_rewrite",
                        status="completed",
                        progress=100,
                        payload={"draft_id": 11},
                    ),
                    Task(
                        user_id=1,
                        platform="douyin",
                        task_type="crawl",
                        status="pending",
                        progress=0,
                        payload={"keyword": "demo"},
                    ),
                    Task(
                        user_id=2,
                        platform="xhs",
                        task_type="publish",
                        status="failed",
                        progress=100,
                        payload={"error": "nope"},
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

        owner_response = client.get(
            "/api/tasks?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        owner_payload = owner_response.json()
        assert owner_payload["total"] == 1
        assert owner_payload["items"][0]["platform"] == "xhs"
        assert owner_payload["items"][0]["task_type"] == "ai_rewrite"
        assert owner_payload["items"][0]["payload"] == {"draft_id": 11}

        intruder_response = client.get(
            "/api/tasks?platform=xhs",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 200
        assert intruder_response.json()["total"] == 1
        assert intruder_response.json()["items"][0]["task_type"] == "publish"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_scheduler_status_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.get("/api/tasks/scheduler/status")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_scheduler_status_reports_config_and_recent_owned_scheduler_tasks(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import Task

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("scheduler-status-owner")
    _register_and_get_access_token("scheduler-status-other")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            db.add_all(
                [
                    Task(
                        user_id=1,
                        platform="xhs",
                        task_type="monitoring_refresh",
                        status="completed",
                        progress=100,
                        payload={"scheduler": True, "target_id": 1},
                    ),
                    Task(
                        user_id=1,
                        platform="xhs",
                        task_type="ai_rewrite",
                        status="completed",
                        progress=100,
                        payload={"draft_id": 10},
                    ),
                    Task(
                        user_id=1,
                        platform="xhs",
                        task_type="monitoring_refresh",
                        status="pending",
                        progress=0,
                        payload={"target_id": 2},
                    ),
                    Task(
                        user_id=2,
                        platform="xhs",
                        task_type="creator_publish_scheduler",
                        status="completed",
                        progress=100,
                        payload={"publish_job_id": 99},
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

        response = client.get(
            "/api/tasks/scheduler/status",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["enabled"] is False
        assert payload["running"] is False
        assert payload["interval_seconds"] == 60
        assert payload["jobs"] == []
        assert [task["task_type"] for task in payload["recent_tasks"]] == ["monitoring_refresh"]
        assert payload["recent_tasks"][0]["payload"] == {"scheduler": True, "target_id": 1}
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_tasks_detail_enforces_ownership(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import Task

    db_dependency = _override_database(tmp_path)
    owner_token = _register_and_get_access_token("task-detail-owner")
    intruder_token = _register_and_get_access_token("task-detail-intruder")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            task = Task(
                user_id=1,
                platform="xhs",
                task_type="ai_rewrite",
                status="completed",
                progress=100,
                payload={"draft_id": 22},
            )
            db.add(task)
            db.commit()
            task_id = task.id
        finally:
            db.close()

        owner_response = client.get(
            f"/api/tasks/{task_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_response.status_code == 200
        assert owner_response.json()["id"] == task_id
        assert owner_response.json()["payload"] == {"draft_id": 22}

        intruder_response = client.get(
            f"/api/tasks/{task_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_task_execution_fields_and_retry_with_exhausted_status(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.core.time import shanghai_now
    from backend.app.models import Task

    db_dependency = _override_database(tmp_path)
    token = _register_and_get_access_token("task-fields-user")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            now = shanghai_now()
            parent = Task(
                user_id=1, platform="xhs", task_type="monitoring_crawl",
                status="completed", progress=100,
                started_at=now, finished_at=now,
            )
            child = Task(
                user_id=1, platform="xhs", task_type="note_crawl",
                status="failed", progress=0, error_type="network",
                retry_count=2, max_retries=3,
                started_at=now, finished_at=now,
            )
            db.add(parent)
            db.flush()
            child.parent_task_id = parent.id
            db.add(child)
            db.commit()
            parent_id, child_id = parent.id, child.id
        finally:
            db.close()

        detail = client.get(f"/api/tasks/{parent_id}", headers={"Authorization": f"Bearer {token}"})
        assert detail.status_code == 200
        body = detail.json()
        assert body["started_at"] is not None
        assert body["finished_at"] is not None
        assert body["duration_ms"] is not None
        assert body["duration_ms"] >= 0
        assert len(body["children"]) == 1
        assert body["children"][0]["id"] == child_id
        assert body["children"][0]["error_type"] == "network"

        child_detail = client.get(f"/api/tasks/{child_id}", headers={"Authorization": f"Bearer {token}"})
        assert child_detail.json()["parent_task_id"] == parent_id
        assert child_detail.json()["retry_count"] == 2
        assert child_detail.json()["max_retries"] == 3

        retry = client.post(f"/api/tasks/{child_id}/retry", headers={"Authorization": f"Bearer {token}"})
        assert retry.status_code == 200
        assert retry.json()["status"] == "pending"
        assert retry.json()["retry_count"] == 3
        assert retry.json()["error_type"] is None

        db2 = next(app.dependency_overrides[get_db]())
        try:
            t = db2.get(Task, child_id)
            t.status = "exhausted"
            t.error_type = "network"
            db2.commit()
        finally:
            db2.close()

        exhausted_retry = client.post(f"/api/tasks/{child_id}/retry", headers={"Authorization": f"Bearer {token}"})
        assert exhausted_retry.status_code == 200
        assert exhausted_retry.json()["status"] == "pending"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/drafts/1/send-to-publish", json={"platform_account_id": 1})

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_notifications_crud_and_trigger_helpers(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import Notification, Task
    from backend.app.services.notification_service import notify_task_failed, notify_task_exhausted

    db_dependency = _override_database(tmp_path)
    token = _register_and_get_access_token("notif-user")
    other_token = _register_and_get_access_token("notif-other")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            task = Task(user_id=1, platform="xhs", task_type="ai_rewrite", status="failed", error_type="network")
            db.add(task)
            db.flush()
            n1 = notify_task_failed(db, task)
            task.status = "exhausted"
            n2 = notify_task_exhausted(db, task)
            other_n = Notification(user_id=2, title="other", level="info")
            db.add(other_n)
            db.commit()
        finally:
            db.close()

        unauth = client.get("/api/notifications")
        assert unauth.status_code == 401

        listing = client.get("/api/notifications", headers={"Authorization": f"Bearer {token}"})
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert len(items) == 2
        levels = {items[0]["level"], items[1]["level"]}
        assert levels == {"warning", "error"}

        unread_only = client.get("/api/notifications?unread=true", headers={"Authorization": f"Bearer {token}"})
        assert len(unread_only.json()["items"]) == 2

        mark = client.post(f"/api/notifications/{items[0]['id']}/read", headers={"Authorization": f"Bearer {token}"})
        assert mark.status_code == 200
        assert mark.json()["read"] is True

        unread_after = client.get("/api/notifications?unread=true", headers={"Authorization": f"Bearer {token}"})
        assert len(unread_after.json()["items"]) == 1

        mark_all = client.post("/api/notifications/read-all", headers={"Authorization": f"Bearer {token}"})
        assert mark_all.status_code == 200
        assert mark_all.json()["marked"] == 1

        other_listing = client.get("/api/notifications", headers={"Authorization": f"Bearer {other_token}"})
        assert len(other_listing.json()["items"]) == 1

        cross_mark = client.post(f"/api/notifications/{items[0]['id']}/read", headers={"Authorization": f"Bearer {other_token}"})
        assert cross_mark.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_draft_send_to_publish_creates_job_and_enforces_ownership(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import PublishJob

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "publish-owner")
    intruder_token = _register_and_get_access_token("publish-intruder")
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Ready title", "body": "Ready body"},
        )
        draft_id = draft_response.json()["id"]

        create_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": owner_account_id, "publish_mode": "immediate"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["platform"] == "xhs"
        assert created["platform_account_id"] == owner_account_id
        assert created["source_draft_id"] == draft_id
        assert created["title"] == "Ready title"
        assert created["body"] == "Ready body"
        assert created["publish_mode"] == "immediate"
        assert created["status"] == "pending"

        intruder_draft_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"platform_account_id": owner_account_id, "publish_mode": "immediate"},
        )
        assert intruder_draft_response.status_code == 404

        db = next(app.dependency_overrides[get_db]())
        try:
            publish_job = db.query(PublishJob).one()
            assert publish_job.source_draft_id == draft_id
            assert publish_job.platform_account_id == owner_account_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_jobs_list_requires_auth_and_filters_current_user(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "publish-list-owner")
    intruder_token = _register_and_get_access_token("publish-list-intruder")
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            intruder_account = PlatformAccount(
                user_id=2,
                platform="xhs",
                sub_type="pc",
                external_user_id="publish-list-intruder",
                nickname="发布测试账号",
                status="active",
            )
            db.add(intruder_account)
            db.flush()
            db.add(
                AccountCookieVersion(
                    platform_account_id=intruder_account.id,
                    encrypted_cookies=encrypt_text('{"a1":"intruder-a1"}'),
                )
            )
            db.commit()
            intruder_account_id = intruder_account.id
        finally:
            db.close()

        owner_draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Owner publish", "body": "Owner body"},
        )
        owner_draft_id = owner_draft_response.json()["id"]
        owner_create_response = client.post(
            f"/api/drafts/{owner_draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": owner_account_id},
        )
        assert owner_create_response.status_code == 200

        intruder_draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"platform": "xhs", "title": "Intruder publish", "body": "Intruder body"},
        )
        intruder_draft_id = intruder_draft_response.json()["id"]
        intruder_create_response = client.post(
            f"/api/drafts/{intruder_draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"platform_account_id": intruder_account_id},
        )
        assert intruder_create_response.status_code == 200

        anonymous_response = client.get("/api/publish/jobs?platform=xhs")
        assert anonymous_response.status_code == 401

        owner_list_response = client.get(
            "/api/publish/jobs?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_list_response.status_code == 200
        owner_payload = owner_list_response.json()
        assert owner_payload["total"] == 1
        assert owner_payload["items"][0]["title"] == "Owner publish"

        intruder_list_response = client.get(
            "/api/publish/jobs?platform=xhs",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_list_response.status_code == 200
        intruder_payload = intruder_list_response.json()
        assert intruder_payload["total"] == 1
        assert intruder_payload["items"][0]["title"] == "Intruder publish"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_detail_and_update_enforce_ownership(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "publish-detail-owner")
    intruder_token = _register_and_get_access_token("publish-detail-intruder")
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Draft title", "body": "Draft body"},
        )
        draft_id = draft_response.json()["id"]
        create_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": owner_account_id},
        )
        job_id = create_response.json()["id"]

        owner_detail_response = client.get(
            f"/api/publish/jobs/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_detail_response.status_code == 200
        assert owner_detail_response.json()["title"] == "Draft title"

        intruder_detail_response = client.get(
            f"/api/publish/jobs/{job_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_detail_response.status_code == 404

        update_response = client.patch(
            f"/api/publish/jobs/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "title": "Edited publish title",
                "body": "Edited publish body",
                "publish_mode": "scheduled",
                "scheduled_at": "2030-01-02T03:04:05",
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["title"] == "Edited publish title"
        assert updated["body"] == "Edited publish body"
        assert updated["publish_mode"] == "scheduled"
        assert updated["scheduled_at"] == "2030-01-02T03:04:05"

        list_response = client.get(
            "/api/publish/jobs?platform=xhs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert list_response.json()["items"][0]["title"] == "Edited publish title"

        intruder_update_response = client.patch(
            f"/api/publish/jobs/{job_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"title": "stolen"},
        )
        assert intruder_update_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_assets_api_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.get("/api/publish/jobs/1/assets")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_assets_api_adds_lists_and_deletes_owned_assets(tmp_path):
    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "publish-assets-owner")
    intruder_token = _register_and_get_access_token("publish-assets-intruder")
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Asset title", "body": "Asset body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": owner_account_id},
        )
        job_id = job_response.json()["id"]

        create_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["publish_job_id"] == job_id
        assert created["asset_type"] == "image"
        assert created["file_path"] == "/api/files/media/xhs-upload-u1-cover.png"

        list_response = client.get(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["id"] == created["id"]

        intruder_list_response = client.get(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_list_response.status_code == 404

        intruder_delete_response = client.delete(
            f"/api/publish/assets/{created['id']}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_delete_response.status_code == 404

        delete_response = client.delete(
            f"/api/publish/assets/{created['id']}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

        empty_response = client.get(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert empty_response.json()["total"] == 0
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_asset_upload_rejects_deleted_creator_account_before_adapter(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount, PublishAsset, PublishJob

    class TrapCreatorPublishAdapter:
        def __init__(self, cookies):
            raise AssertionError("deleted account must be rejected before adapter init")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "upload-deleted-creator-owner"
    )
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: TrapCreatorPublishAdapter
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            account = db.get(PlatformAccount, creator_account_id)
            account.status = "deleted"
            account.status_message = "Account credentials deleted by user"
            job = PublishJob(
                user_id=1,
                platform="xhs",
                platform_account_id=creator_account_id,
                title="Deleted account upload",
                body="Body",
                status="pending",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            asset = PublishAsset(publish_job_id=job.id, asset_type="image", file_path="/api/files/media/xhs-upload-u1-cover.png")
            db.add(asset)
            db.commit()
            asset_id = asset.id
        finally:
            db.close()

        response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "发布账号已删除，请重新选择 Creator 账号"
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_rejects_creator_account_without_cookies_before_adapter(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import AccountCookieVersion, PublishAsset, PublishJob

    class TrapCreatorPublishAdapter:
        def __init__(self, cookies):
            raise AssertionError("missing cookies must be rejected before adapter init")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-missing-cookie-owner"
    )
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: TrapCreatorPublishAdapter
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            for cookie_version in db.query(AccountCookieVersion).filter(AccountCookieVersion.platform_account_id == creator_account_id).all():
                db.delete(cookie_version)
            job = PublishJob(
                user_id=1,
                platform="xhs",
                platform_account_id=creator_account_id,
                title="Missing cookie publish",
                body="Body",
                status="pending",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            asset = PublishAsset(publish_job_id=job.id, asset_type="image", file_path="/api/files/media/xhs-upload-u1-cover.png")
            db.add(asset)
            db.commit()
            job_id = job.id
        finally:
            db.close()

        response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Creator 账号缺少 Cookie，请在账号矩阵重新登录后再发布"
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_asset_upload_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/publish/assets/1/upload")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_asset_upload_uses_creator_cookie_and_updates_asset(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory

    class FakeCreatorPublishAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def upload_media(self, file_path, media_type):
            self.calls.append({"cookies": self.cookies, "file_path": file_path, "media_type": media_type})
            return {"creator_media_id": "creator-media-001", "fileIds": "file-001"}

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-upload-owner"
    )
    FakeCreatorPublishAdapter.calls = []
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Upload title", "body": "Upload body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]
        asset_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        asset_id = asset_response.json()["id"]

        upload_response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert upload_response.status_code == 200
        uploaded = upload_response.json()
        assert uploaded["upload_status"] == "uploaded"
        assert uploaded["creator_media_id"] == "creator-media-001"
        assert uploaded["upload_error"] == ""
        assert FakeCreatorPublishAdapter.calls == [
            {
                "cookies": "web_session=creator-session; a1=creator-a1",
                "file_path": "/api/files/media/xhs-upload-u1-cover.png",
                "media_type": "image",
            }
        ]
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_asset_upload_auth_failure_marks_account_expired(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount

    class AuthExpiredCreatorPublishAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def upload_media(self, file_path, media_type):
            raise RuntimeError("cookie expired while uploading")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-upload-auth-expired-owner"
    )
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: AuthExpiredCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Upload auth title", "body": "Upload auth body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]
        asset_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        asset_id = asset_response.json()["id"]

        upload_response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert upload_response.status_code == 502
        db = next(app.dependency_overrides[get_db]())
        try:
            refreshed_account = db.get(PlatformAccount, creator_account_id)
            assert refreshed_account.status == "expired"
            assert "重新登录" in refreshed_account.status_message
            assert "Cookie" in refreshed_account.status_message
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_asset_upload_rejects_cross_user_asset(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory

    class FakeCreatorPublishAdapter:
        def __init__(self, cookies):
            raise AssertionError("cross-user upload must not instantiate adapter")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-upload-cross-owner"
    )
    intruder_token = _register_and_get_access_token("publish-upload-cross-intruder")
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Owner asset", "body": "Owner body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]
        asset_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        asset_id = asset_response.json()["id"]

        response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/publish/jobs/1/publish")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_uses_creator_cookie_and_updates_status(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Task

    class FakeCreatorPublishAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def post_note(self, note_info):
            self.calls.append({"cookies": self.cookies, "note_info": note_info})
            return {"note_id": "xhs-note-001", "success": True}

        def upload_media(self, file_path, media_type):
            return {"creator_media_id": "creator-media-001", "fileIds": "file-001", "width": 1080, "height": 1440}

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-action-owner"
    )
    FakeCreatorPublishAdapter.calls = []
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Publish title", "body": "Publish body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]
        asset_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        asset_id = asset_response.json()["id"]
        upload_response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert upload_response.status_code == 200

        publish_response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert publish_response.status_code == 200
        published = publish_response.json()
        assert published["status"] == "published"
        assert published["external_note_id"] == "xhs-note-001"
        assert published["publish_error"] == ""
        assert published["published_at"] is not None
        assert FakeCreatorPublishAdapter.calls == [
            {
                "cookies": "web_session=creator-session; a1=creator-a1",
                "note_info": {
                    "title": "Publish title",
                    "desc": "Publish body",
                    "media_type": "image",
                    "image_file_infos": [
                        {
                            "creator_media_id": "creator-media-001",
                            "fileIds": "file-001",
                            "width": 1080,
                            "height": 1440,
                        }
                    ],
                    "type": 1,
                    "postTime": None,
                },
            }
        ]

        db = next(app.dependency_overrides[get_db]())
        try:
            task = db.query(Task).filter(Task.task_type == "creator_publish").one()
            assert task.user_id == 1
            assert task.platform == "xhs"
            assert task.status == "completed"
            assert task.progress == 100
            assert task.payload["publish_job_id"] == job_id
            assert task.payload["external_note_id"] == "xhs-note-001"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_passes_optional_creator_parameters(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory

    class FakeCreatorOptionalPublishAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def post_note(self, note_info):
            self.calls.append({"cookies": self.cookies, "note_info": note_info})
            return {"note_id": "optional-job-note", "success": True}

        def upload_media(self, file_path, media_type):
            return {"creator_media_id": "creator-media-optional", "fileIds": "file-optional", "width": 1080, "height": 1440}

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-optional-owner"
    )
    FakeCreatorOptionalPublishAdapter.calls = []
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorOptionalPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Optional title", "body": ""},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "platform_account_id": creator_account_id,
                "topics": ["早餐"],
                "location": "上海",
                "is_private": False,
            },
        )
        job_id = job_response.json()["id"]
        assert job_response.json()["publish_options"] == {
            "topics": ["早餐"],
            "location": "上海",
            "is_private": False,
            "privacy_type": 0,
        }

        asset_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        asset_id = asset_response.json()["id"]
        upload_response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert upload_response.status_code == 200

        update_response = client.patch(
            f"/api/publish/jobs/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"topics": ["早餐", "通勤"], "is_private": True, "location": ""},
        )
        assert update_response.status_code == 200
        assert update_response.json()["publish_options"] == {
            "topics": ["早餐", "通勤"],
            "is_private": True,
            "privacy_type": 1,
        }

        publish_response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert publish_response.status_code == 200
        assert FakeCreatorOptionalPublishAdapter.calls == [
            {
                "cookies": "web_session=creator-session; a1=creator-a1",
                "note_info": {
                    "title": "Optional title",
                    "desc": "",
                    "media_type": "image",
                    "image_file_infos": [
                        {
                            "creator_media_id": "creator-media-optional",
                            "fileIds": "file-optional",
                            "width": 1080,
                            "height": 1440,
                        }
                    ],
                    "type": 1,
                    "postTime": None,
                    "topics": ["早餐", "通勤"],
                },
            }
        ]
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_records_failed_task(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Task

    class FakeFailingCreatorPublishAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def post_note(self, note_info):
            raise RuntimeError("creator publish denied")

        def upload_media(self, file_path, media_type):
            return {"creator_media_id": "creator-media-001", "fileIds": "file-001", "width": 1080, "height": 1440}

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-action-failed-owner"
    )
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeFailingCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Publish title", "body": "Publish body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]
        asset_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        asset_id = asset_response.json()["id"]
        upload_response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert upload_response.status_code == 200

        publish_response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert publish_response.status_code == 502
        db = next(app.dependency_overrides[get_db]())
        try:
            task = db.query(Task).filter(Task.task_type == "creator_publish").one()
            assert task.status == "failed"
            assert task.progress == 100
            assert task.payload["publish_job_id"] == job_id
            assert task.payload["error"] == "creator publish denied"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_creator_auth_failure_marks_account_expired(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import PlatformAccount, PublishAsset, PublishJob

    class AuthExpiredCreatorPublishAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def upload_media(self, file_path, media_type):
            return {"creator_media_id": "creator-media-001", "fileIds": "file-001", "width": 1080, "height": 1440}

        def post_note(self, note_info):
            raise RuntimeError("login expired: creator cookie invalid")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-auth-expired-owner"
    )
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: AuthExpiredCreatorPublishAdapter
    headers = {"Authorization": f"Bearer {owner_token}"}

    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            job = PublishJob(
                user_id=1,
                platform="xhs",
                platform_account_id=creator_account_id,
                title="Auth expired title",
                body="Auth expired body",
                status="pending",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            asset = PublishAsset(
                publish_job_id=job.id,
                asset_type="image",
                file_path="/api/files/media/xhs-upload-u1-auth-expired.png",
                upload_status="pending",
            )
            db.add(asset)
            db.commit()
            job_id = job.id
        finally:
            db.close()

        response = client.post(f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true", headers=headers)

        assert response.status_code == 502
        verify_db = next(app.dependency_overrides[get_db]())
        try:
            refreshed_job = verify_db.get(PublishJob, job_id)
            refreshed_account = verify_db.get(PlatformAccount, creator_account_id)
            assert refreshed_job.status == "failed"
            assert "login expired" in refreshed_job.publish_error
            assert refreshed_account.status == "expired"
            assert "重新登录" in refreshed_account.status_message
            assert "Cookie" in refreshed_account.status_message
        finally:
            verify_db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_rejects_empty_content_before_adapter(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Task

    class FakeCreatorPublishAdapter:
        def __init__(self, cookies):
            raise AssertionError("invalid publish content must not instantiate adapter")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-preflight-owner"
    )
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Valid title", "body": "Valid body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]

        update_response = client.patch(
            f"/api/publish/jobs/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"title": "   ", "body": ""},
        )
        assert update_response.status_code == 200

        publish_response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert publish_response.status_code == 400
        assert publish_response.json()["detail"] == "Publish title is required"
        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.query(Task).filter(Task.task_type == "creator_publish").count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_rejects_past_scheduled_time_before_adapter(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.core.time import shanghai_now
    from backend.app.models import PublishAsset, Task

    class FakeCreatorPublishAdapter:
        def __init__(self, cookies):
            raise AssertionError("past scheduled publish must not instantiate adapter")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-past-schedule-owner"
    )
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Scheduled title", "body": "Scheduled body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]

        update_response = client.patch(
            f"/api/publish/jobs/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "publish_mode": "scheduled",
                "scheduled_at": (shanghai_now() - timedelta(minutes=5)).isoformat(),
            },
        )
        assert update_response.status_code == 200

        db = next(app.dependency_overrides[get_db]())
        try:
            db.add(
                PublishAsset(
                    publish_job_id=job_id,
                    asset_type="image",
                    file_path="/api/files/media/xhs-upload-u1-cover.png",
                    upload_status="uploaded",
                    creator_media_id="creator-media-001",
                    creator_upload_info='{"fileIds":"file-001","width":1080,"height":1440}',
                )
            )
            db.commit()
        finally:
            db.close()

        publish_response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert publish_response.status_code == 400
        assert publish_response.json()["detail"] == "Scheduled publish time must be in the future"
        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.query(Task).filter(Task.task_type == "creator_publish").count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_rejects_already_completed_job(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Task

    class FakeCreatorPublishAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def post_note(self, note_info):
            self.calls.append({"cookies": self.cookies, "note_info": note_info})
            return {"note_id": "xhs-note-001", "success": True}

        def upload_media(self, file_path, media_type):
            return {"creator_media_id": "creator-media-001", "fileIds": "file-001", "width": 1080, "height": 1440}

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-completed-owner"
    )
    FakeCreatorPublishAdapter.calls = []
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Publish title", "body": "Publish body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]
        asset_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"asset_type": "image", "file_path": "/api/files/media/xhs-upload-u1-cover.png"},
        )
        asset_id = asset_response.json()["id"]
        upload_response = client.post(
            f"/api/publish/assets/{asset_id}/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert upload_response.status_code == 200

        first_response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert first_response.status_code == 200

        second_response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert second_response.status_code == 400
        assert second_response.json()["detail"] == "Publish job is already completed"
        assert len(FakeCreatorPublishAdapter.calls) == 1
        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.query(Task).filter(Task.task_type == "creator_publish").count() == 1
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_publish_rejects_cross_user_job(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory

    class FakeCreatorPublishAdapter:
        def __init__(self, cookies):
            raise AssertionError("cross-user publish must not instantiate adapter")

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-action-cross-owner"
    )
    intruder_token = _register_and_get_access_token("publish-action-cross-intruder")
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    try:
        draft_response = client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform": "xhs", "title": "Owner publish", "body": "Owner body"},
        )
        draft_id = draft_response.json()["id"]
        job_response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"platform_account_id": creator_account_id},
        )
        job_id = job_response.json()["id"]

        response = client.post(
            f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_image_utility_routes_require_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        compose_response = client.post(
            "/api/files/images/compose",
            json={"title": "低卡早餐", "body": "三分钟做完", "width": 720, "height": 960},
        )
        resize_response = client.post(
            "/api/files/images/resize",
            json={"source_file_name": "xhs-image-u1-missing.png", "width": 320, "height": 320},
        )
        download_response = client.get("/api/files/media/xhs-image-u1-missing.png")

        assert compose_response.status_code == 401
        assert resize_response.status_code == 401
        assert download_response.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_image_utilities_compose_resize_download_and_enforce_scope(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        owner_token = _register_and_get_access_token("image-utility-owner")
        intruder_token = _register_and_get_access_token("image-utility-intruder")

        compose_response = client.post(
            "/api/files/images/compose",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "title": "低卡早餐合集",
                "body": "适合通勤前快速准备的小红书封面",
                "width": 720,
                "height": 960,
                "accent_color": "#111111",
            },
        )

        assert compose_response.status_code == 200
        composed = compose_response.json()
        assert composed["file_name"].startswith("xhs-image-u1-")
        assert composed["file_name"].endswith(".png")
        assert composed["download_url"].startswith(f"/api/files/media/{composed['file_name']}?token=")
        assert composed["width"] == 720
        assert composed["height"] == 960
        assert composed["media_type"] == "image/png"

        download_response = client.get(
            composed["download_url"],
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert download_response.status_code == 200
        assert download_response.headers["content-type"].startswith("image/png")
        assert download_response.content.startswith(b"\x89PNG")

        resize_response = client.post(
            "/api/files/images/resize",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "source_file_name": composed["file_name"],
                "width": 320,
                "height": 320,
                "mode": "cover",
                "format": "jpeg",
                "quality": 82,
            },
        )

        assert resize_response.status_code == 200
        resized = resize_response.json()
        assert resized["file_name"].startswith("xhs-image-u1-")
        assert resized["file_name"].endswith(".jpg")
        assert resized["file_name"] != composed["file_name"]
        assert resized["width"] == 320
        assert resized["height"] == 320
        assert resized["media_type"] == "image/jpeg"

        resized_download_response = client.get(
            resized["download_url"],
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resized_download_response.status_code == 200
        assert resized_download_response.content.startswith(b"\xff\xd8")

        bare_download = client.get(f"/api/files/media/{composed['file_name']}")
        assert bare_download.status_code == 404

        forbidden_resize = client.post(
            "/api/files/images/resize",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"source_file_name": composed["file_name"], "width": 320, "height": 320},
        )
        assert forbidden_resize.status_code == 404
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_retry_and_cancel_require_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        retry_response = client.post("/api/publish/jobs/1/retry")
        cancel_response = client.post("/api/publish/jobs/1/cancel")

        assert retry_response.status_code == 401
        assert cancel_response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_retry_resets_failed_job_and_enforces_ownership(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import PublishJob, Task

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-retry-owner"
    )
    intruder_token = _register_and_get_access_token("publish-retry-intruder")
    db = next(app.dependency_overrides[get_db]())
    try:
        failed_job = PublishJob(
            user_id=1,
            platform_account_id=creator_account_id,
            platform="xhs",
            title="Failed title",
            body="Failed body",
            status="failed",
            external_note_id="old-note",
            publish_error="creator denied",
            published_at=datetime.utcnow(),
        )
        db.add(failed_job)
        db.commit()
        db.refresh(failed_job)
        job_id = failed_job.id
    finally:
        db.close()

    try:
        forbidden_response = client.post(
            f"/api/publish/jobs/{job_id}/retry",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert forbidden_response.status_code == 404

        retry_response = client.post(
            f"/api/publish/jobs/{job_id}/retry",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert retry_response.status_code == 200
        retried = retry_response.json()
        assert retried["status"] == "pending"
        assert retried["publish_error"] == ""
        assert retried["external_note_id"] == ""
        assert retried["published_at"] is None

        db = next(app.dependency_overrides[get_db]())
        try:
            task = db.query(Task).filter(Task.task_type == "creator_publish_retry").one()
            assert task.user_id == 1
            assert task.status == "pending"
            assert task.progress == 0
            assert task.payload["publish_job_id"] == job_id
            assert db.get(PublishJob, job_id).status == "pending"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_publish_job_cancel_transitions_pending_or_scheduled_and_rejects_locked(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import PublishJob, Task

    db_dependency, owner_token, creator_account_id = _create_creator_account_with_cookie(
        tmp_path, "publish-cancel-owner"
    )
    db = next(app.dependency_overrides[get_db]())
    try:
        pending_job = PublishJob(
            user_id=1,
            platform_account_id=creator_account_id,
            platform="xhs",
            title="Pending title",
            body="Pending body",
            status="pending",
        )
        scheduled_job = PublishJob(
            user_id=1,
            platform_account_id=creator_account_id,
            platform="xhs",
            title="Scheduled title",
            body="Scheduled body",
            publish_mode="scheduled",
            status="scheduled",
            scheduled_at=datetime.utcnow(),
        )
        published_job = PublishJob(
            user_id=1,
            platform_account_id=creator_account_id,
            platform="xhs",
            title="Published title",
            body="Published body",
            status="published",
        )
        db.add_all([pending_job, scheduled_job, published_job])
        db.commit()
        db.refresh(pending_job)
        db.refresh(scheduled_job)
        db.refresh(published_job)
        pending_id = pending_job.id
        scheduled_id = scheduled_job.id
        published_id = published_job.id
    finally:
        db.close()

    try:
        pending_response = client.post(
            f"/api/publish/jobs/{pending_id}/cancel",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        scheduled_response = client.post(
            f"/api/publish/jobs/{scheduled_id}/cancel",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        locked_response = client.post(
            f"/api/publish/jobs/{published_id}/cancel",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert pending_response.status_code == 200
        assert pending_response.json()["status"] == "cancelled"
        assert scheduled_response.status_code == 200
        assert scheduled_response.json()["status"] == "cancelled"
        assert locked_response.status_code == 400
        assert locked_response.json()["detail"] == "Publish job cannot be cancelled"

        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.get(PublishJob, pending_id).status == "cancelled"
            assert db.get(PublishJob, scheduled_id).status == "cancelled"
            assert db.get(PublishJob, published_id).status == "published"
            assert db.query(Task).filter(Task.task_type == "creator_publish_cancel").count() == 2
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_run_due_tasks_requires_authentication(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        response = client.post("/api/tasks/run-due?platform=xhs")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_run_due_tasks_executes_current_user_due_scheduled_publish_jobs(tmp_path):
    from backend.app.api.publish import get_creator_publish_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.core.time import shanghai_now
    from backend.app.models import AccountCookieVersion, PlatformAccount, PublishAsset, PublishJob, Task

    class FakeDuePublishAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def post_note(self, note_info):
            self.calls.append({"cookies": self.cookies, "note_info": note_info})
            return {"note_id": "due-note-001"}

    db_dependency, owner_token, owner_account_id = _create_creator_account_with_cookie(
        tmp_path, "due-publish-owner"
    )
    intruder_token = _register_and_get_access_token("due-publish-intruder")
    db = next(app.dependency_overrides[get_db]())
    try:
        now = shanghai_now()
        intruder_account = PlatformAccount(
            user_id=2,
            platform="xhs",
            sub_type="creator",
            external_user_id="intruder-creator",
            nickname="Intruder creator",
            status="active",
        )
        db.add(intruder_account)
        db.flush()
        db.add(
            AccountCookieVersion(
                platform_account_id=intruder_account.id,
                encrypted_cookies=encrypt_text('{"web_session":"intruder-session","a1":"intruder-a1"}'),
            )
        )

        due_job = PublishJob(
            user_id=1,
            platform_account_id=owner_account_id,
            platform="xhs",
            title="Due title",
            body="Due body",
            publish_mode="scheduled",
            status="pending",
            scheduled_at=now - timedelta(minutes=5),
        )
        future_job = PublishJob(
            user_id=1,
            platform_account_id=owner_account_id,
            platform="xhs",
            title="Future title",
            body="Future body",
            publish_mode="scheduled",
            status="pending",
            scheduled_at=now + timedelta(hours=2),
        )
        intruder_due_job = PublishJob(
            user_id=2,
            platform_account_id=intruder_account.id,
            platform="xhs",
            title="Intruder due title",
            body="Intruder due body",
            publish_mode="scheduled",
            status="pending",
            scheduled_at=now - timedelta(minutes=5),
        )
        db.add_all([due_job, future_job, intruder_due_job])
        db.flush()
        db.add_all(
            [
                PublishAsset(
                    publish_job_id=due_job.id,
                    asset_type="image",
                    file_path="storage/media/due.png",
                    upload_status="uploaded",
                    creator_media_id="media-due",
                    creator_upload_info='{"fileIds":"file-due","width":1080,"height":1440}',
                ),
                PublishAsset(
                    publish_job_id=future_job.id,
                    asset_type="image",
                    file_path="storage/media/future.png",
                    upload_status="uploaded",
                    creator_media_id="media-future",
                    creator_upload_info='{"fileIds":"file-future","width":1080,"height":1440}',
                ),
                PublishAsset(
                    publish_job_id=intruder_due_job.id,
                    asset_type="image",
                    file_path="storage/media/intruder.png",
                    upload_status="uploaded",
                    creator_media_id="media-intruder",
                    creator_upload_info='{"fileIds":"file-intruder","width":1080,"height":1440}',
                ),
            ]
        )
        db.commit()
        due_job_id = due_job.id
        future_job_id = future_job.id
        intruder_job_id = intruder_due_job.id
    finally:
        db.close()

    FakeDuePublishAdapter.calls = []
    app.dependency_overrides[get_creator_publish_adapter_factory] = lambda: FakeDuePublishAdapter
    try:
        intruder_response = client.post(
            "/api/tasks/run-due?platform=xhs&confirm_real_publish=true",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert intruder_response.status_code == 200
        assert intruder_response.json()["executed_count"] == 1

        owner_response = client.post(
            "/api/tasks/run-due?platform=xhs&confirm_real_publish=true",
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        assert owner_response.status_code == 200
        payload = owner_response.json()
        assert payload["executed_count"] == 1
        assert payload["failed_count"] == 0
        assert payload["items"][0]["id"] == due_job_id
        assert payload["items"][0]["status"] == "published"
        assert len(FakeDuePublishAdapter.calls) == 2
        owner_call = FakeDuePublishAdapter.calls[-1]
        assert owner_call["cookies"] == "web_session=creator-session; a1=creator-a1"
        assert owner_call["note_info"]["title"] == "Due title"
        assert owner_call["note_info"]["postTime"] is None

        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.get(PublishJob, due_job_id).status == "published"
            assert db.get(PublishJob, due_job_id).external_note_id == "due-note-001"
            assert db.get(PublishJob, future_job_id).status == "pending"
            assert db.get(PublishJob, intruder_job_id).status == "published"
            tasks = db.query(Task).filter(Task.task_type == "creator_publish_scheduler").all()
            assert len(tasks) == 2
            assert {task.user_id for task in tasks} == {1, 2}
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_creator_publish_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_run_due_publish_jobs_for_all_users_executes_each_due_user(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.core.security import encrypt_text
    from backend.app.models import AccountCookieVersion, PlatformAccount, PublishAsset, PublishJob, Task
    from backend.app.services.scheduler_service import run_due_publish_jobs_for_all_users

    class FakeAllUsersDuePublishAdapter:
        calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def post_note(self, note_info):
            self.calls.append({"cookies": self.cookies, "note_info": note_info})
            return {"note_id": f"note-{len(self.calls)}"}

    db_dependency, owner_token, owner_account_id = _create_creator_account_with_cookie(
        tmp_path, "all-users-due-owner"
    )
    _register_and_get_access_token("all-users-due-second")
    db = next(app.dependency_overrides[get_db]())
    try:
        second_account = PlatformAccount(
            user_id=2,
            platform="xhs",
            sub_type="creator",
            external_user_id="second-creator",
            nickname="Second creator",
            status="active",
        )
        db.add(second_account)
        db.flush()
        db.add(
            AccountCookieVersion(
                platform_account_id=second_account.id,
                encrypted_cookies=encrypt_text('{"web_session":"second-session","a1":"second-a1"}'),
            )
        )
        first_job = PublishJob(
            user_id=1,
            platform_account_id=owner_account_id,
            platform="xhs",
            title="First due",
            body="First body",
            publish_mode="scheduled",
            status="pending",
            scheduled_at=datetime.utcnow() - timedelta(minutes=10),
        )
        second_job = PublishJob(
            user_id=2,
            platform_account_id=second_account.id,
            platform="xhs",
            title="Second due",
            body="Second body",
            publish_mode="scheduled",
            status="pending",
            scheduled_at=datetime.utcnow() - timedelta(minutes=8),
        )
        db.add_all([first_job, second_job])
        db.flush()
        db.add_all(
            [
                PublishAsset(
                    publish_job_id=first_job.id,
                    asset_type="image",
                    file_path="storage/media/first.png",
                    upload_status="uploaded",
                    creator_media_id="first-media",
                    creator_upload_info='{"fileIds":"first-file"}',
                ),
                PublishAsset(
                    publish_job_id=second_job.id,
                    asset_type="image",
                    file_path="storage/media/second.png",
                    upload_status="uploaded",
                    creator_media_id="second-media",
                    creator_upload_info='{"fileIds":"second-file"}',
                ),
            ]
        )
        db.commit()
        first_job_id = first_job.id
        second_job_id = second_job.id
    finally:
        db.close()

    FakeAllUsersDuePublishAdapter.calls = []
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            result = run_due_publish_jobs_for_all_users(
                db=db,
                now=datetime.utcnow(),
                platform="xhs",
                adapter_factory=FakeAllUsersDuePublishAdapter,
            )

            assert result["executed_count"] == 2
            assert result["failed_count"] == 0
            assert {item["id"] for item in result["items"]} == {first_job_id, second_job_id}
            assert db.get(PublishJob, first_job_id).status == "published"
            assert db.get(PublishJob, second_job_id).status == "published"
            assert db.query(Task).filter(Task.task_type == "creator_publish_scheduler").count() == 2
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_due_publish_scheduler_registers_interval_job():
    from backend.app.services.scheduler_service import build_due_publish_scheduler, shutdown_due_publish_scheduler

    scheduler = build_due_publish_scheduler(interval_seconds=17, job_func=lambda: None)

    try:
        jobs = scheduler.get_jobs()
        assert {job.id for job in jobs} == {"due_publish_runner", "monitoring_refresh_runner", "auto_tasks_runner", "cookie_health_checker"}
        job_intervals = {job.id: job.trigger.interval.total_seconds() for job in jobs}
        assert job_intervals["due_publish_runner"] == 17
        assert job_intervals["monitoring_refresh_runner"] == 17
        assert job_intervals["auto_tasks_runner"] == 60
        assert job_intervals["cookie_health_checker"] == 7200
    finally:
        shutdown_due_publish_scheduler(scheduler)


def test_run_monitoring_refresh_for_all_users_refreshes_active_targets(tmp_path):
    from backend.app.core.database import get_db
    from backend.app.models import MonitoringSnapshot, MonitoringTarget, Note, PlatformAccount, Task
    from backend.app.services.scheduler_service import run_monitoring_refresh_for_all_users

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(
        tmp_path, "scheduled-monitor-owner"
    )
    _register_and_get_access_token("scheduled-monitor-second")
    db = next(app.dependency_overrides[get_db]())
    try:
        second_account = PlatformAccount(
            user_id=2,
            platform="xhs",
            sub_type="pc",
            external_user_id="second-pc",
            nickname="Second PC",
            status="active",
        )
        db.add(second_account)
        db.flush()
        db.add_all(
            [
                Note(
                    user_id=1,
                    platform_account_id=owner_account_id,
                    platform="xhs",
                    note_id="monitor-auto-owner",
                    title="低卡早餐自动监控",
                    content="适合通勤的低卡早餐",
                    author_name="owner-author",
                    raw_json={"likes": 20, "collects": 5, "comments": 2, "shares": 1},
                ),
                Note(
                    user_id=2,
                    platform_account_id=second_account.id,
                    platform="xhs",
                    note_id="monitor-auto-second",
                    title="低卡早餐第二用户",
                    content="第二用户的低卡早餐",
                    author_name="second-author",
                    raw_json={"likes": 100},
                ),
            ]
        )
        active_owner = MonitoringTarget(
            user_id=1,
            platform="xhs",
            target_type="keyword",
            name="Owner breakfast",
            value="低卡早餐",
            status="active",
        )
        paused_owner = MonitoringTarget(
            user_id=1,
            platform="xhs",
            target_type="keyword",
            name="Paused breakfast",
            value="低卡早餐",
            status="paused",
        )
        active_second = MonitoringTarget(
            user_id=2,
            platform="xhs",
            target_type="keyword",
            name="Second breakfast",
            value="低卡早餐",
            status="active",
        )
        db.add_all([active_owner, paused_owner, active_second])
        db.commit()
        active_owner_id = active_owner.id
        paused_owner_id = paused_owner.id
        active_second_id = active_second.id
    finally:
        db.close()

    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            result = run_monitoring_refresh_for_all_users(db=db, now=datetime.utcnow(), platform="xhs")

            assert result["refreshed_count"] == 2
            assert result["items"][0]["target_id"] in {active_owner_id, active_second_id}
            assert db.get(MonitoringTarget, active_owner_id).last_refreshed_at is not None
            assert db.get(MonitoringTarget, active_second_id).last_refreshed_at is not None
            assert db.get(MonitoringTarget, paused_owner_id).last_refreshed_at is None
            owner_snapshot = db.scalars(
                select(MonitoringSnapshot).where(MonitoringSnapshot.target_id == active_owner_id)
            ).one()
            second_snapshot = db.scalars(
                select(MonitoringSnapshot).where(MonitoringSnapshot.target_id == active_second_id)
            ).one()
            assert owner_snapshot.payload["matched_count"] == 1
            assert owner_snapshot.payload["total_engagement"] == 28
            assert second_snapshot.payload["matched_count"] == 1
            assert second_snapshot.payload["total_engagement"] == 100
            tasks = db.query(Task).filter(Task.task_type == "monitoring_refresh").all()
            assert len(tasks) == 2
            assert {task.user_id for task in tasks} == {1, 2}
            assert all(task.status == "completed" for task in tasks)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)

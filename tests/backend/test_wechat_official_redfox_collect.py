from __future__ import annotations

import requests
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import (
    AiDraft,
    PublishJob,
    WechatOfficialArticle,
    WechatOfficialArticleComment,
    WechatOfficialArticleCommentReply,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialCrawlAccount,
    WechatOfficialCrawlJob,
    WechatOfficialDraftSource,
    WechatOfficialRedfoxConfig,
)
from backend.app.services import wechat_official_redfox_service as redfox_service
from backend.app.services.wechat_official_redfox_client import WechatOfficialRedfoxClient

client = TestClient(app)


class FakeRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def search_articles(self, *, keyword: str, offset: int, sort_type: str) -> dict:
        assert keyword == "私域增长"
        assert offset == 0
        assert sort_type == "_4"
        return {
            "code": 2000,
            "data": {
                "list": [
                    {
                        "workUuid": "viral-work-1",
                        "title": "10万+私域案例",
                        "summary": "私域增长摘要",
                        "workUrl": "https://mp.weixin.qq.com/s/redfox-viral",
                        "publishTime": "2026-06-16 10:00:00",
                        "author": "增长研究所",
                        "coverUrl": "https://example.com/cover.jpg",
                        "content": "正文：可复制的私域增长路径。",
                        "readCount": 120000,
                        "likeCount": 3500,
                        "watchCount": 1200,
                        "commentCount": 280,
                        "shareCount": 150,
                    },
                    {
                        "workUuid": "normal-work-1",
                        "title": "普通私域案例",
                        "summary": "普通摘要",
                        "workUrl": "https://mp.weixin.qq.com/s/redfox-normal",
                        "publishTime": "2026-06-16 11:00:00",
                        "author": "增长研究所",
                        "content": "正文：普通私域增长文章。",
                        "readCount": 50000,
                        "likeCount": 30,
                    },
                ]
            },
        }

    def query_work_list(self, *, account: str, account_name: str, offset: int, sort_type: str, publish_time_start: str | None, publish_time_end: str | None) -> dict:
        assert account == "rmrbwx"
        return {
            "code": 2000,
            "data": {
                "list": [
                    {
                        "workUuid": "account-work-1",
                        "title": "公众号热文",
                        "summary": "公众号热文摘要",
                        "workUrl": "https://mp.weixin.qq.com/s/redfox-account-viral",
                        "author": account_name,
                        "readCount": 150000,
                    }
                ]
            },
        }

    def query_article_detail(self, *, url: str) -> dict:
        assert url == "https://mp.weixin.qq.com/s/redfox-url"
        return {
            "code": 2000,
            "data": {
                "workUuid": "url-work-1",
                "title": "URL补全爆文",
                "summary": "URL补全摘要",
                "workUrl": url,
                "author": "URL公众号",
                "coverUrl": "https://example.com/url-cover.jpg",
                "content": "URL 详情正文。",
                "html": '<p>URL 详情正文。</p><img src="https://example.com/html-image.jpg" />',
                "contentImages": [{"url": "https://example.com/body-image.jpg", "width": 640, "height": 480}],
                "comments": [
                    {
                        "commentId": "comment-1",
                        "nickName": "读者一",
                        "userId": "reader-1",
                        "content": "这篇很有启发",
                        "likeCount": 12,
                        "createTime": "2026-06-18 10:00:00",
                        "replies": [
                            {"replyId": "reply-1", "nickName": "作者", "content": "谢谢", "likeCount": 2}
                        ],
                        "api_key": "comment-secret",
                    }
                ],
                "readCount": 130000,
                "commentCount": 1,
                "shareCount": 66,
                "api_key": "detail-secret",
                "token": "detail-token",
                "cookie": "detail-cookie",
            },
        }

    def validate_key(self) -> dict:
        return {"code": 2000, "data": {"ok": True}}


class FakeTargetCountRedfoxClient:
    calls: list[tuple[str, int, str]] = []

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def search_articles(self, *, keyword: str, offset: int, sort_type: str) -> dict:
        self.__class__.calls.append((keyword, offset, sort_type))
        assert keyword == "浴缸"
        assert sort_type == "_4"
        pages = {
            0: [
                {
                    "workUuid": "bathtub-work-1",
                    "title": "阳台上的浴缸改造",
                    "summary": "阳台改造",
                    "workUrl": "https://mp.weixin.qq.com/s/redfox-bathtub-1",
                    "publishTime": "2026-06-16 09:00:00",
                    "author": "家居改造社",
                    "content": "正文：阳台上的浴缸改造方案。",
                    "readCount": 180000,
                    "likeCount": 2000,
                },
                {
                    "workUuid": "bathtub-offtopic-1",
                    "title": "淋浴房选购清单",
                    "summary": "普通装修内容",
                    "workUrl": "https://mp.weixin.qq.com/s/redfox-bathtub-offtopic-1",
                    "publishTime": "2026-06-16 09:10:00",
                    "author": "家居改造社",
                    "content": "正文：普通装修内容。",
                    "readCount": 120000,
                    "likeCount": 1200,
                },
            ],
            20: [
                {
                    "workUuid": "bathtub-work-2",
                    "title": "小户型浴缸怎么选",
                    "summary": "小户型选浴缸",
                    "workUrl": "https://mp.weixin.qq.com/s/redfox-bathtub-2",
                    "publishTime": "2026-06-16 10:00:00",
                    "author": "家居改造社",
                    "content": "正文：小户型浴缸选型指南。",
                    "readCount": 150000,
                    "likeCount": 1800,
                },
                {
                    "workUuid": "bathtub-offtopic-2",
                    "title": "卫生间地砖防滑指南",
                    "summary": "普通装修内容",
                    "workUrl": "https://mp.weixin.qq.com/s/redfox-bathtub-offtopic-2",
                    "publishTime": "2026-06-16 10:10:00",
                    "author": "家居改造社",
                    "content": "正文：普通装修内容。",
                    "readCount": 110000,
                    "likeCount": 900,
                },
            ],
            40: [
                {
                    "workUuid": "bathtub-work-3",
                    "title": "浴缸材质怎么选",
                    "summary": "材质选型",
                    "workUrl": "https://mp.weixin.qq.com/s/redfox-bathtub-3",
                    "publishTime": "2026-06-16 11:00:00",
                    "author": "家居改造社",
                    "content": "正文：浴缸材质对比。",
                    "readCount": 140000,
                    "likeCount": 1600,
                },
                {
                    "workUuid": "bathtub-offtopic-3",
                    "title": "瓷砖收边细节",
                    "summary": "普通装修内容",
                    "workUrl": "https://mp.weixin.qq.com/s/redfox-bathtub-offtopic-3",
                    "publishTime": "2026-06-16 11:10:00",
                    "author": "家居改造社",
                    "content": "正文：普通装修内容。",
                    "readCount": 105000,
                    "likeCount": 800,
                },
            ],
        }
        return {"code": 2000, "data": {"list": pages[offset]}}


class FakeFailingSearchRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def search_articles(self, *, keyword: str, offset: int, sort_type: str) -> dict:
        response = requests.Response()
        response.status_code = 502
        response._content = b"bad gateway"
        raise requests.HTTPError("502 Server Error", response=response)


class FakeListOnlyRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def search_articles(self, *, keyword: str, offset: int, sort_type: str) -> dict:
        assert keyword == "自动补正文"
        assert offset == 0
        return {
            "code": 2000,
            "data": {
                "list": [
                    {
                        "workUuid": "list-only-work-1",
                        "title": "列表文章自动补正文",
                        "summary": "Redfox 列表摘要，不应作为最终正文",
                        "workUrl": "https://mp.weixin.qq.com/s/redfox-list-only",
                        "author": "列表公众号",
                        "readCount": 120000,
                    }
                ]
            },
        }


class FakeMaterializeArticlePageProvider:
    def fetch_article(self, *, url: str) -> dict:
        assert url == "https://mp.weixin.qq.com/s/redfox-list-only"
        return {
            "external_id": "article_page:redfox-list-only",
            "article_url": url,
            "content_url": url,
            "title": "列表文章自动补正文",
            "digest": "公开页摘要",
            "author_name": "列表公众号",
            "account_name": "列表公众号",
            "account": "列表公众号",
            "publish_time_remote": "2026-06-25 11:00",
            "cover_url": "https://mmbiz.qpic.cn/materialized-cover.jpg",
            "content_text": "公开页完整正文，入库时应自动保存。",
            "content_html": '<div id="js_content"><p>公开页完整正文，入库时应自动保存。</p><img src="https://mmbiz.qpic.cn/materialized-body.jpg" /></div>',
            "images": [{"url": "https://mmbiz.qpic.cn/materialized-body.jpg", "type": "content", "source": "article_page"}],
            "comments": [],
            "detail_completeness": {"has_text": True, "has_html": True, "image_count": 1},
            "metrics": {"read_count": 0, "like_count": 0, "wow_count": 0, "share_count": 0, "comment_count": 0},
            "raw": {"source": "article_page"},
        }


def test_redfox_detail_client_retries_recoverable_ssl_disconnect(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 2000, "data": {"title": "重试后成功"}}

    def fake_post(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        if len(calls) == 1:
            raise requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")
        return FakeResponse()

    monkeypatch.setattr("backend.app.services.wechat_official_redfox_client.requests.post", fake_post)

    client = WechatOfficialRedfoxClient(base_url="https://redfox.hk", api_key="redfox-collect-secret")
    result = client.query_article_detail(url="https://mp.weixin.qq.com/s/retry-redfox-url")

    assert result["data"]["title"] == "重试后成功"
    assert len(calls) == 2
    assert calls[0]["kwargs"]["json"] == {"url": "https://mp.weixin.qq.com/s/retry-redfox-url"}


class FakeNestedArticleDetailRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def query_article_detail(self, *, url: str) -> dict:
        assert url == "https://mp.weixin.qq.com/s/nested-redfox-url"
        return {
            "code": 2000,
            "data": {
                "article": {
                    "id": "nested-work-1",
                    "appmsg_title": "嵌套结构爆文标题",
                    "appmsg_digest": "嵌套结构摘要",
                    "nickname": "嵌套公众号",
                    "biz": "MzNestedBiz",
                    "read_num": "1",
                    "like_num": "3210",
                    "comment_num": "88",
                    "content": "嵌套详情正文",
                }
            },
        }


class FakeUnparseableArticleDetailRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def query_article_detail(self, *, url: str) -> dict:
        assert url in {
            "https://mp.weixin.qq.com/s/unparseable-redfox-url",
            "https://mp.weixin.qq.com/s/redfox-fallback-url",
        }
        return {"code": 2000, "data": {"article": {"read_num": 120000}}}


class FakeTimeoutArticleDetailRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def query_article_detail(self, *, url: str) -> dict:
        assert url in {
            "https://mp.weixin.qq.com/s/timeout-redfox-url",
            "https://mp.weixin.qq.com/s/redfox-fallback-url",
            "https://mp.weixin.qq.com/s/redfox-fallback-fails-url",
        }
        raise requests.Timeout("detail timeout")


class FakeArticlePageProvider:
    def fetch_article(self, *, url: str) -> dict:
        assert url == "https://mp.weixin.qq.com/s/redfox-fallback-url"
        return {
            "external_id": "article-page:redfox-fallback-url",
            "article_url": url,
            "content_url": url,
            "title": "公开页兜底标题",
            "digest": "",
            "author_name": "公开页公众号",
            "account_name": "公开页公众号",
            "account": "公开页公众号",
            "publish_time_remote": "2026-06-20 08:30",
            "cover_url": "https://mmbiz.qpic.cn/cover.jpg",
            "content_text": "公开页正文",
            "content_html": '<div id="js_content"><p>公开页正文</p><img src="https://mmbiz.qpic.cn/body.jpg" /></div>',
            "images": [{"url": "https://mmbiz.qpic.cn/body.jpg", "type": "content", "alt": "", "width": None, "height": None, "source": "article_page"}],
            "comments": [],
            "detail_completeness": {"has_text": True, "has_html": True, "image_count": 1},
            "metrics": {"read_count": 0, "like_count": 0, "wow_count": 0, "share_count": 0, "comment_count": 0},
            "raw": {"source": "article_page"},
        }


class FakeFailingArticlePageProvider:
    def fetch_article(self, *, url: str) -> dict:
        from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError

        assert url == "https://mp.weixin.qq.com/s/redfox-fallback-fails-url"
        raise WechatOfficialProviderError(
            provider="article_page",
            stage="parse",
            message="未能从公开文章页解析出标题和正文；请确认 URL 是公开微信公众号文章，或稍后重试 Redfox",
            details={"url": url, "reason": "parse_failed", "next_action": "请换一个公开文章 URL，或稍后重试 Redfox 详情接口"},
        )


class FakeDenseMatchRedfoxClient:
    calls: list[tuple[str, int, str]] = []

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def search_articles(self, *, keyword: str, offset: int, sort_type: str) -> dict:
        self.__class__.calls.append((keyword, offset, sort_type))
        assert keyword == "浴缸"
        assert sort_type == "_4"
        assert offset == 0
        return {
            "code": 2000,
            "data": {
                "list": [
                    {
                        "workUuid": f"dense-bathtub-{index}",
                        "title": f"浴缸方案 {index}",
                        "summary": "浴缸选购方案",
                        "workUrl": f"https://mp.weixin.qq.com/s/redfox-dense-bathtub-{index}",
                        "publishTime": "2026-06-16 12:00:00",
                        "author": "家居改造社",
                        "content": f"正文：浴缸内容 {index}。",
                        "readCount": index,
                        "likeCount": index,
                    }
                    for index in range(1, 21)
                ]
            },
        }


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-redfox-collect-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return get_db, TestingSessionLocal


def _register(username: str) -> dict:
    response = client.post("/api/auth/register", json={"username": username, "password": "secret123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _save_config(headers: dict) -> None:
    response = client.post("/api/wechat-official/redfox/config", headers=headers, json={"api_key": "redfox-collect-secret"})
    assert response.status_code == 200


def test_redfox_keyword_collect_saves_articles_metrics_snapshots_and_candidates(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxClient, raising=False)
    try:
        headers = _register("redfox-keyword-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "私域增长", "pages": 1, "sort_type": "_4", "min_read_count": 100000, "save_snapshot": True},
        )

        assert response.status_code == 200
        payload = response.json()
        summary = payload["summary"]
        assert summary["fetched"] == 2
        assert summary["saved"] == 2
        assert summary["deduped"] == 0
        assert summary["viral_candidates"] == 1
        assert summary["failed"] == 0
        assert summary["api_calls"] == 1
        assert summary["estimated_credit_cost"] is None
        assert summary["requested_target_count"] == 20
        assert summary["max_pages"] == 1
        assert summary["filtered"] == 0
        assert summary["relevance_matched"] == 2
        assert summary["target_reached"] is False
        assert len(payload["items"]) == 2
        viral = next(item for item in payload["items"] if item["title"] == "10万+私域案例")
        normal = next(item for item in payload["items"] if item["title"] == "普通私域案例")
        assert viral["is_candidate"] is True
        assert viral["latest_metric"]["read_count"] == 120000
        assert viral["analysis"]["recommendation_status"] == "candidate"
        assert viral["analysis"]["low_follower_evidence"] == "unknown"
        assert normal["is_candidate"] is False

        library = client.get("/api/wechat-official/content-library?viral_only=true&min_read_count=100000", headers=headers)
        assert library.status_code == 200
        assert library.json()["total"] == 1
        assert library.json()["items"][0]["title"] == "10万+私域案例"

        unknown_library = client.get("/api/wechat-official/content-library?low_follower_evidence=unknown", headers=headers)
        assert unknown_library.status_code == 200
        assert unknown_library.json()["total"] == 2

        draft_response = client.post(
            f"/api/wechat-official/content-library/{viral['id']}/create-draft",
            headers=headers,
            json={"rewrite_style": "专业克制", "target_audience": "私域运营", "call_to_action": "预约咨询"},
        )
        assert draft_response.status_code == 200
        draft_payload = draft_response.json()
        assert draft_payload["platform"] == "wechat_official"
        assert "正文：可复制的私域增长路径" in draft_payload["body"]

        dry_run = client.post(f"/api/wechat-official/drafts/{draft_payload['id']}/dry-run", headers=headers)
        assert dry_run.status_code == 200
        assert dry_run.json()["publish_blocked"] is True
        assert dry_run.json()["sendall_blocked"] is True

        send_to_publish = client.post(f"/api/drafts/{draft_payload['id']}/send-to-publish", headers=headers, json={"publish_mode": "immediate"})
        assert send_to_publish.status_code in {400, 403, 422}

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob))
            assert job is not None
            assert job.source == "redfox"
            serialized_job = str(job.params_json) + job.error_message
            assert "redfox-collect-secret" not in serialized_job
            assert db.scalars(select(WechatOfficialArticle)).all()
            assert len(db.scalars(select(WechatOfficialArticleMetric)).all()) == 2
            assert len(db.scalars(select(WechatOfficialArticleSnapshot)).all()) == 2
            draft = db.get(AiDraft, draft_payload["id"])
            assert draft is not None
            assert draft.platform == "wechat_official"
            source = db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == draft_payload["id"]))
            assert source is not None
            assert source.article_id == viral["id"]
            assert db.scalar(select(PublishJob).where(PublishJob.source_draft_id == draft_payload["id"])) is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_keyword_collect_filters_unrelated_articles_and_stops_at_target_count(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeTargetCountRedfoxClient, raising=False)
    FakeTargetCountRedfoxClient.calls = []
    try:
        headers = _register("redfox-target-count-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "浴缸", "target_count": 2, "max_pages": 3, "sort_type": "_4", "min_read_count": 100000, "save_snapshot": True},
        )

        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["fetched"] == 4
        assert summary["saved"] == 2
        assert summary["filtered"] == 2
        assert summary["relevance_matched"] == 2
        assert summary["requested_target_count"] == 2
        assert summary["max_pages"] == 3
        assert summary["target_reached"] is True
        assert summary["api_calls"] == 2
        assert {item["title"] for item in response.json()["items"]} == {"阳台上的浴缸改造", "小户型浴缸怎么选"}
        assert FakeTargetCountRedfoxClient.calls == [("浴缸", 0, "_4"), ("浴缸", 20, "_4")]

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob).order_by(WechatOfficialCrawlJob.id.desc()))
            assert job is not None
            assert job.keyword == "浴缸"
            assert job.requested_limit == 2
            assert job.fetched_count == 4
            assert job.saved_count == 2
            assert job.params_json["keyword"] == "浴缸"
            assert job.params_json["sort_type"] == "_4"
            assert job.params_json["relevance_matched"] == 2
            assert job.params_json["target_count"] == 2
            assert job.params_json["max_pages"] == 3
            assert job.params_json["filtered"] == 2
            assert job.params_json["target_reached"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_keyword_collect_reports_target_not_reached_when_relevant_results_are_insufficient(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeTargetCountRedfoxClient, raising=False)
    FakeTargetCountRedfoxClient.calls = []
    try:
        headers = _register("redfox-target-count-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "浴缸", "target_count": 4, "max_pages": 2, "sort_type": "_4", "min_read_count": 0, "save_snapshot": True},
        )

        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["fetched"] == 4
        assert summary["saved"] == 2
        assert summary["filtered"] == 2
        assert summary["relevance_matched"] == 2
        assert summary["requested_target_count"] == 4
        assert summary["max_pages"] == 2
        assert summary["target_reached"] is False
        assert summary["api_calls"] == 2
        assert summary["viral_candidates"] == 2
        assert {item["title"] for item in response.json()["items"]} == {"阳台上的浴缸改造", "小户型浴缸怎么选"}
        assert FakeTargetCountRedfoxClient.calls == [("浴缸", 0, "_4"), ("浴缸", 20, "_4")]

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob).order_by(WechatOfficialCrawlJob.id.desc()))
            assert job is not None
            assert job.keyword == "浴缸"
            assert job.requested_limit == 4
            assert job.fetched_count == 4
            assert job.saved_count == 2
            assert job.params_json["keyword"] == "浴缸"
            assert job.params_json["sort_type"] == "_4"
            assert job.params_json["relevance_matched"] == 2
            assert job.params_json["target_count"] == 4
            assert job.params_json["max_pages"] == 2
            assert job.params_json["filtered"] == 2
            assert job.params_json["target_reached"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_keyword_collect_counts_full_matching_page_even_when_target_reached(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeDenseMatchRedfoxClient, raising=False)
    FakeDenseMatchRedfoxClient.calls = []
    try:
        headers = _register("redfox-dense-match-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "浴缸", "target_count": 1, "max_pages": 3, "sort_type": "_4", "min_read_count": 0, "save_snapshot": True},
        )

        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["fetched"] == 20
        assert summary["saved"] == 1
        assert summary["filtered"] == 0
        assert summary["relevance_matched"] == 20
        assert summary["requested_target_count"] == 1
        assert summary["max_pages"] == 3
        assert summary["target_reached"] is True
        assert summary["api_calls"] == 1
        assert summary["viral_candidates"] == 1
        assert len(response.json()["items"]) == 1
        assert FakeDenseMatchRedfoxClient.calls == [("浴缸", 0, "_4")]

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob).order_by(WechatOfficialCrawlJob.id.desc()))
            assert job is not None
            assert job.keyword == "浴缸"
            assert job.requested_limit == 1
            assert job.fetched_count == 20
            assert job.saved_count == 1
            assert job.params_json["relevance_matched"] == 20
            assert job.params_json["target_reached"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_keyword_collect_legacy_pages_preserves_historic_requested_limit(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeTargetCountRedfoxClient, raising=False)
    FakeTargetCountRedfoxClient.calls = []
    try:
        headers = _register("redfox-legacy-pages-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "浴缸", "pages": 3, "sort_type": "_4", "min_read_count": 100000, "save_snapshot": True},
        )

        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["requested_target_count"] == 60
        assert summary["max_pages"] == 3
        assert summary["target_reached"] is False
        assert summary["saved"] == 3
        assert summary["fetched"] == 6
        assert summary["filtered"] == 3
        assert summary["relevance_matched"] == 3
        assert summary["api_calls"] == 3
        assert FakeTargetCountRedfoxClient.calls == [("浴缸", 0, "_4"), ("浴缸", 20, "_4"), ("浴缸", 40, "_4")]

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob).order_by(WechatOfficialCrawlJob.id.desc()))
            assert job is not None
            assert job.keyword == "浴缸"
            assert job.requested_limit == 60
            assert job.params_json["target_count"] == 60
            assert job.params_json["max_pages"] == 3
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_keyword_collect_materializes_public_article_content_when_saving(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeListOnlyRedfoxClient, raising=False)
    monkeypatch.setattr(redfox_service, "WechatOfficialArticlePageProvider", FakeMaterializeArticlePageProvider, raising=False)
    try:
        headers = _register("redfox-materialize-keyword-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "自动补正文", "target_count": 1, "max_pages": 1, "sort_type": "_4", "min_read_count": 100000, "save_snapshot": True},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["saved"] == 1
        item = payload["items"][0]
        assert item["title"] == "列表文章自动补正文"
        assert item["cover_url"] == "https://mmbiz.qpic.cn/materialized-cover.jpg"

        with TestingSessionLocal() as db:
            article = db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == "https://mp.weixin.qq.com/s/redfox-list-only"))
            assert article is not None
            assert article.cover_url == "https://mmbiz.qpic.cn/materialized-cover.jpg"
            snapshot = db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
            assert snapshot is not None
            assert snapshot.text == "公开页完整正文，入库时应自动保存。"
            assert snapshot.html.startswith('<div id="js_content">')
            assert snapshot.images_json == [{"url": "https://mmbiz.qpic.cn/materialized-body.jpg", "type": "content", "source": "article_page"}]
            assert snapshot.raw_json["source"] == "redfox"
            assert snapshot.raw_json["detail_completeness"]["image_count"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_keyword_collect_returns_bad_gateway_when_upstream_request_fails(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeFailingSearchRedfoxClient, raising=False)
    try:
        headers = _register("redfox-upstream-error-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "浴缸", "target_count": 1, "max_pages": 1, "sort_type": "_4"},
        )

        assert response.status_code == 502
        assert response.json()["detail"] == "Redfox search request failed with HTTP 502"

        with TestingSessionLocal() as db:
            assert db.scalar(select(WechatOfficialCrawlJob)) is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_keyword_collect_returns_bad_request_when_api_key_cannot_be_decrypted(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("redfox-invalid-token-user")
        user_id = int(client.get("/api/auth/me", headers=headers).json()["id"])
        encrypted_with_other_key = Fernet(Fernet.generate_key()).encrypt(b"redfox-collect-secret").decode("utf-8")
        with TestingSessionLocal() as db:
            db.add(WechatOfficialRedfoxConfig(user_id=user_id, encrypted_api_key=encrypted_with_other_key))
            db.commit()

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "浴缸", "target_count": 1, "max_pages": 1, "sort_type": "_4"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Redfox API Key cannot be decrypted; please re-save the configuration"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_import_url_normalizes_nested_article_detail_and_falls_back_to_input_url(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeNestedArticleDetailRedfoxClient, raising=False)
    try:
        headers = _register("redfox-nested-url-user")
        _save_config(headers)
        article_url = "https://mp.weixin.qq.com/s/nested-redfox-url"

        response = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": article_url, "min_read_count": 100000},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["saved"] == 1
        assert payload["summary"]["viral_candidates"] == 1
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["title"] == "嵌套结构爆文标题"
        assert item["digest"] == "嵌套结构摘要"
        assert item["author_name"] == "嵌套公众号"
        assert item["article_url"] == article_url
        assert item["content_url"] == article_url
        assert item["latest_metric"]["read_count"] == 1
        assert item["latest_metric"]["like_count"] == 3210
        assert item["latest_metric"]["comment_count"] == 88

        with TestingSessionLocal() as db:
            article = db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == article_url))
            assert article is not None
            assert article.title == "嵌套结构爆文标题"
            assert article.author_name == "嵌套公众号"
            metric = db.scalar(select(WechatOfficialArticleMetric).where(WechatOfficialArticleMetric.article_id == article.id))
            assert metric is not None
            assert metric.read_count == 1
            assert metric.like_count == 3210
            assert metric.comment_count == 88
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_import_url_falls_back_to_public_article_page_when_detail_times_out(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeTimeoutArticleDetailRedfoxClient, raising=False)
    monkeypatch.setattr(redfox_service, "WechatOfficialArticlePageProvider", FakeArticlePageProvider, raising=False)
    try:
        headers = _register("redfox-fallback-url-user")
        _save_config(headers)
        article_url = "https://mp.weixin.qq.com/s/redfox-fallback-url"

        response = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": article_url, "min_read_count": 0},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["saved"] == 1
        assert payload["summary"]["fallback_provider"] == "article_page"
        assert payload["summary"]["fallback_reason"] == "Redfox 文章详情接口超时"
        item = payload["items"][0]
        assert item["title"] == "公开页兜底标题"
        assert item["author_name"] == "公开页公众号"
        assert item["article_url"] == article_url

        with TestingSessionLocal() as db:
            article = db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == article_url))
            assert article is not None
            assert article.title == "公开页兜底标题"
            snapshot = db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
            assert snapshot is not None
            assert snapshot.text == "公开页正文"
            assert snapshot.raw_json["source"] == "redfox"
            assert snapshot.raw_json["detail_completeness"]["image_count"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_import_url_returns_structured_error_without_shell_when_redfox_and_fallback_fail(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeTimeoutArticleDetailRedfoxClient, raising=False)
    monkeypatch.setattr(redfox_service, "WechatOfficialArticlePageProvider", FakeFailingArticlePageProvider, raising=False)
    try:
        headers = _register("redfox-fallback-fails-url-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-fallback-fails-url"},
        )

        assert response.status_code == 502
        detail = response.json()["detail"]
        assert detail["message"] == "公众号公开文章页兜底抓取失败；未保存空壳文章"
        assert detail["redfox"]["provider"] == "redfox"
        assert detail["redfox"]["stage"] == "detail"
        assert detail["fallback"]["provider"] == "article_page"
        assert detail["fallback"]["stage"] == "parse"
        assert detail["fallback"]["details"]["reason"] == "parse_failed"
        assert detail["next_action"] == "请确认 URL 是公开微信公众号文章，或稍后重试 Redfox 详情接口"

        with TestingSessionLocal() as db:
            assert db.scalar(select(WechatOfficialCrawlJob)) is None
            assert db.scalar(select(WechatOfficialArticle)) is None
            assert db.scalar(select(WechatOfficialArticleMetric)) is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_import_url_falls_back_when_detail_is_unparseable(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeUnparseableArticleDetailRedfoxClient, raising=False)
    monkeypatch.setattr(redfox_service, "WechatOfficialArticlePageProvider", FakeArticlePageProvider, raising=False)
    try:
        headers = _register("redfox-unparseable-url-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-fallback-url", "min_read_count": 100000},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["saved"] == 1
        assert payload["summary"]["fallback_provider"] == "article_page"
        assert payload["summary"]["fallback_reason"] == "Redfox 已返回文章详情，但未识别到文章标题"
        item = payload["items"][0]
        assert item["title"] == "公开页兜底标题"
        assert item["article_url"] == "https://mp.weixin.qq.com/s/redfox-fallback-url"

        with TestingSessionLocal() as db:
            article = db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == "https://mp.weixin.qq.com/s/redfox-fallback-url"))
            assert article is not None
            assert article.title == "公开页兜底标题"
            snapshot = db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
            assert snapshot is not None
            assert snapshot.text == "公开页正文"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_import_url_skips_tombstoned_article(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxClient, raising=False)
    try:
        headers = _register("redfox-delete-user")
        _save_config(headers)

        first = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-url", "min_read_count": 100000},
        )
        assert first.status_code == 200
        assert first.json()["summary"]["saved"] == 1
        article_id = first.json()["items"][0]["id"]

        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            account = db.get(WechatOfficialCrawlAccount, article.account_id)
            assert account is not None
            owner_user_id = account.user_id

        deleted = client.delete(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert deleted.status_code == 200

        second = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-url", "min_read_count": 100000},
        )
        assert second.status_code == 200
        assert second.json()["summary"]["saved"] == 0
        assert second.json()["items"] == []

        with TestingSessionLocal() as db:
            assert (
                db.scalar(
                    select(WechatOfficialArticle)
                    .join(WechatOfficialCrawlAccount, WechatOfficialArticle.account_id == WechatOfficialCrawlAccount.id)
                    .where(
                        WechatOfficialArticle.article_url == "https://mp.weixin.qq.com/s/redfox-url",
                        WechatOfficialCrawlAccount.user_id == owner_user_id,
                    )
                )
                is None
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_account_collect_and_url_import_use_same_library_path(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxClient, raising=False)
    try:
        headers = _register("redfox-account-url-user")
        _save_config(headers)

        account_response = client.post(
            "/api/wechat-official/redfox/collect/account",
            headers=headers,
            json={"account": "rmrbwx", "account_name": "人民日报", "pages": 1, "sort_type": "_4", "min_read_count": 100000},
        )
        assert account_response.status_code == 200
        assert account_response.json()["summary"]["viral_candidates"] == 1

        url_response = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-url", "min_read_count": 100000},
        )
        assert url_response.status_code == 200
        assert url_response.json()["summary"]["viral_candidates"] == 1

        library = client.get("/api/wechat-official/content-library?viral_only=true", headers=headers)
        assert library.status_code == 200
        titles = {item["title"] for item in library.json()["items"]}
        assert {"公众号热文", "URL补全爆文"}.issubset(titles)
        url_item = next(item for item in library.json()["items"] if item["title"] == "URL补全爆文")

        detail = client.get(f"/api/wechat-official/content-library/{url_item['id']}", headers=headers)
        assert detail.status_code == 200
        serialized_detail = detail.text
        assert "detail-secret" not in serialized_detail
        assert "detail-token" not in serialized_detail
        assert "detail-cookie" not in serialized_detail
        assert "comment-secret" not in serialized_detail
        detail_payload = detail.json()
        assert detail_payload["latest_snapshot"]["images_json"]
        assert {image["url"] for image in detail_payload["latest_snapshot"]["images_json"]} >= {
            "https://example.com/url-cover.jpg",
            "https://example.com/html-image.jpg",
            "https://example.com/body-image.jpg",
        }
        assert detail_payload["comments"]["total"] == 1
        assert detail_payload["comments"]["items"][0]["content"] == "这篇很有启发"
        assert detail_payload["comments"]["items"][0]["replies"][0]["content"] == "谢谢"

        with TestingSessionLocal() as db:
            snapshot = db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == url_item["id"]))
            assert snapshot is not None
            assert len(snapshot.images_json or []) == 3
            assert db.scalar(select(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == url_item["id"])) is not None
            assert db.scalar(select(WechatOfficialArticleCommentReply)) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)

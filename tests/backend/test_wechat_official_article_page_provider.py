from __future__ import annotations

import pytest

from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError
from backend.app.services.wechat_official_article_page_provider import WechatOfficialArticlePageProvider


ARTICLE_URL = "https://mp.weixin.qq.com/s/public-article-url"


class FakeResponse:
    def __init__(self, text: str, *, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.url = ARTICLE_URL
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP {self.status_code}")


PUBLIC_ARTICLE_HTML = """
<!doctype html>
<html>
  <head>
    <meta property="og:title" content="公开文章标题" />
    <meta property="og:image" content="https://mmbiz.qpic.cn/cover.jpg" />
    <meta name="author" content="作者甲" />
  </head>
  <body>
    <h1 id="activity-name">公开文章标题</h1>
    <div id="meta_content">
      <span id="js_name">公众号甲</span>
      <em id="publish_time">2026-06-20 08:30</em>
    </div>
    <div id="js_content">
      <p>第一段正文</p>
      <p>第二段正文</p>
      <img data-src="https://mmbiz.qpic.cn/body-1.jpg" alt="图一" />
      <img src="https://mmbiz.qpic.cn/body-2.jpg" />
    </div>
  </body>
</html>
"""


def test_article_page_provider_extracts_public_article_fields(monkeypatch) -> None:
    def fake_get(url: str, **kwargs):
        assert url == ARTICLE_URL
        assert kwargs["timeout"] > 0
        return FakeResponse(PUBLIC_ARTICLE_HTML)

    monkeypatch.setattr("backend.app.services.wechat_official_article_page_provider.requests.get", fake_get)

    article = WechatOfficialArticlePageProvider().fetch_article(url=ARTICLE_URL)

    assert article["article_url"] == ARTICLE_URL
    assert article["content_url"] == ARTICLE_URL
    assert article["title"] == "公开文章标题"
    assert article["author_name"] == "公众号甲"
    assert article["account_name"] == "公众号甲"
    assert article["account"] == "公众号甲"
    assert article["publish_time_remote"] == "2026-06-20 08:30"
    assert "第一段正文" in article["content_text"]
    assert "第二段正文" in article["content_text"]
    assert "js_content" in article["content_html"]
    assert {image["url"] for image in article["images"]} == {
        "https://mmbiz.qpic.cn/cover.jpg",
        "https://mmbiz.qpic.cn/body-1.jpg",
        "https://mmbiz.qpic.cn/body-2.jpg",
    }
    assert article["detail_completeness"] == {"has_text": True, "has_html": True, "image_count": 3}
    assert article["metrics"] == {"read_count": 0, "like_count": 0, "wow_count": 0, "share_count": 0, "comment_count": 0}
    assert article["raw"]["source"] == "article_page"


@pytest.mark.parametrize(
    ("html", "stage", "message_fragment", "reason"),
    [
        (
            "<html><body>当前访问环境异常，请完成验证后继续访问</body></html>",
            "fetch",
            "需要完成微信验证",
            "verification_required",
        ),
        (
            "<html><body>该内容已被发布者删除</body></html>",
            "fetch",
            "文章已删除或不可访问",
            "deleted_or_unavailable",
        ),
        (
            "<html><body><div id='js_content'></div></body></html>",
            "parse",
            "未能从公开文章页解析出标题和正文",
            "parse_failed",
        ),
    ],
)
def test_article_page_provider_reports_actionable_failure_states(monkeypatch, html: str, stage: str, message_fragment: str, reason: str) -> None:
    monkeypatch.setattr(
        "backend.app.services.wechat_official_article_page_provider.requests.get",
        lambda url, **kwargs: FakeResponse(html),
    )

    with pytest.raises(WechatOfficialProviderError) as exc_info:
        WechatOfficialArticlePageProvider().fetch_article(url=ARTICLE_URL)

    diagnostic = exc_info.value.to_dict()
    assert diagnostic["provider"] == "article_page"
    assert diagnostic["stage"] == stage
    assert diagnostic["severity"] == "error"
    assert message_fragment in diagnostic["message"]
    assert diagnostic["details"]["reason"] == reason
    assert diagnostic["details"]["url"] == ARTICLE_URL
    assert diagnostic["details"]["next_action"]


def test_article_page_provider_marks_browser_fallback_for_verification_pages(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.wechat_official_article_page_provider.requests.get",
        lambda url, **kwargs: FakeResponse("<html><body>当前访问环境异常，请完成验证后继续访问</body></html>"),
    )

    with pytest.raises(WechatOfficialProviderError) as exc_info:
        WechatOfficialArticlePageProvider().fetch_article(url=ARTICLE_URL)

    diagnostic = exc_info.value.to_dict()
    assert diagnostic["details"]["browser_fallback"] == "manual_verification_required"
    assert diagnostic["details"]["retry_policy"] == "do_not_auto_retry"
    assert "验证码绕过" not in diagnostic["details"]["next_action"]

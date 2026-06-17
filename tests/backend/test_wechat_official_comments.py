from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import WechatOfficialArticleComment, WechatOfficialArticleCommentReply

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-comments-test.db'}", connect_args={"check_same_thread": False})
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


def _create_article(headers: dict) -> int:
    start = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
    assert start.status_code == 200
    session_id = start.json()["login_session_id"]
    complete = client.post(
        f"/api/wechat-official/accounts/login/{session_id}/complete",
        headers=headers,
        json={"cookie": "cookie-secret", "token": "token-secret", "auth_key": "auth-secret", "biz": "MzA-comment", "nickname": "Comment Account"},
    )
    assert complete.status_code == 200
    sync = client.post(
        "/api/wechat-official/crawl/articles/sync",
        headers=headers,
        json={"backend_session_id": session_id, "upstream_payload": {"publish_page": '{"publish_list":[{"publish_info":{"appmsgex":[{"title":"评论文章","link":"https://mp.weixin.qq.com/s/comments"}]}}]}'}},
    )
    assert sync.status_code == 200
    return sync.json()["items"][0]["id"]


def test_article_comments_store_first_n_comments_and_replies(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("comments-user")
        article_id = _create_article(headers)
        comments = [
            {
                "content_id": "c1",
                "nick_name": "读者一",
                "logo_url": "https://img.example/u1.png",
                "content": "第一条评论",
                "like_num": 11,
                "create_time": 1780000000,
                "reply": {"reply_list": [{"content_id": "r1", "nick_name": "作者", "content": "谢谢", "like_num": 3, "create_time": 1780000001}]},
            },
            {"content_id": "c2", "nick_name": "读者二", "content": "第二条评论", "like_num": 2},
            {"content_id": "c3", "nick_name": "读者三", "content": "第三条评论", "like_num": 1},
        ]

        response = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/comments",
            headers=headers,
            json={"comments_payload": {"elected_comment": comments}, "limit": 2},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert [item["comment_id"] for item in payload["items"]] == ["c1", "c2"]
        assert payload["items"][0]["replies"][0]["reply_id"] == "r1"
        assert payload["items"][0]["replies"][0]["content"] == "谢谢"

        with TestingSessionLocal() as db:
            stored_comments = db.scalars(select(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == article_id)).all()
            stored_replies = db.scalars(select(WechatOfficialArticleCommentReply)).all()
            assert len(stored_comments) == 2
            assert len(stored_replies) == 1
            assert stored_comments[0].content == "第一条评论"
            assert stored_replies[0].content == "谢谢"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_article_comments_default_limit_is_50(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("comments-limit-user")
        article_id = _create_article(headers)
        comments = [{"content_id": f"c{i}", "nick_name": f"读者{i}", "content": f"评论{i}"} for i in range(60)]

        response = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/comments",
            headers=headers,
            json={"comments_payload": {"elected_comment": comments}},
        )

        assert response.status_code == 200
        assert response.json()["total"] == 50
    finally:
        app.dependency_overrides.pop(get_db, None)

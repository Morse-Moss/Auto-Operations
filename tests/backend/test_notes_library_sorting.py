from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import Note, NoteAnalysisResult, User

client = TestClient(app)


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'notes-library-sorting.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestingSessionLocal


def _create_user_and_notes(SessionLocal):
    db = SessionLocal()
    try:
        user = User(username="library-owner", password_hash=hash_password("secret123"))
        db.add(user)
        db.flush()
        notes = [
            Note(
                user_id=user.id,
                platform_account_id=1,
                platform="xhs",
                note_id="note-like-top",
                title="点赞最高",
                content="content",
                author_name="author",
                raw_json={"liked_count": 100, "comment_count": 2, "collected_count": 1},
            ),
            Note(
                user_id=user.id,
                platform_account_id=1,
                platform="xhs",
                note_id="note-comment-top",
                title="评论最高",
                content="content",
                author_name="author",
                raw_json={"liked_count": 3, "comment_count": 80, "collected_count": 2},
            ),
            Note(
                user_id=user.id,
                platform_account_id=1,
                platform="xhs",
                note_id="note-collect-top",
                title="收藏最高",
                content="content",
                author_name="author",
                raw_json={"liked_count": 1, "comment_count": 4, "collected_count": 70},
            ),
        ]
        db.add_all(notes)
        db.commit()
        return user.id
    finally:
        db.close()


def test_notes_library_sorts_by_interaction_metrics_and_paginates(tmp_path):
    SessionLocal = _override_database(tmp_path)
    try:
        user_id = _create_user_and_notes(SessionLocal)
        headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}

        response = client.get("/api/notes", headers=headers, params={"platform": "xhs", "sort_by": "likes", "page": 1, "page_size": 2})

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 3
        assert payload["page"] == 1
        assert payload["page_size"] == 2
        assert [item["note_id"] for item in payload["items"]] == ["note-like-top", "note-comment-top"]
        assert payload["items"][0]["engagement_metrics"]["likes"] == 100
        assert "点赞TOP20" in payload["items"][0]["analysis_marks"]
        assert payload["items"][0]["is_analysis_focus"] is True

        comments_response = client.get("/api/notes", headers=headers, params={"platform": "xhs", "sort_by": "comments", "page_size": 3})
        assert comments_response.status_code == 200
        assert comments_response.json()["items"][0]["note_id"] == "note-comment-top"

        collects_response = client.get("/api/notes", headers=headers, params={"platform": "xhs", "sort_by": "collects", "page_size": 3})
        assert collects_response.status_code == 200
        assert collects_response.json()["items"][0]["note_id"] == "note-collect-top"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_notes_library_filters_by_feishu_analysis_fields(tmp_path):
    SessionLocal = _override_database(tmp_path)
    try:
        user_id = _create_user_and_notes(SessionLocal)
        db = SessionLocal()
        try:
            note = db.scalar(select(Note).where(Note.note_id == "note-like-top"))
            result = NoteAnalysisResult(
                user_id=user_id,
                note_id=note.id,
                source="feishu",
                analysis_status="已完成",
                content_type="种草",
                reuse_value="可直接改写",
                reusable_models=["问题驱动模型", "场景种草模型"],
                push_status="synced",
            )
            db.add(result)
            db.commit()
        finally:
            db.close()
        headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}

        response = client.get(
            "/api/notes",
            headers=headers,
            params={
                "platform": "xhs",
                "feishu_push_status": "synced",
                "analysis_status": "已完成",
                "content_type": "种草",
                "reuse_value": "可直接改写",
                "reusable_model": "问题驱动模型",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        item = payload["items"][0]
        assert item["note_id"] == "note-like-top"
        assert item["feishu_sync"]["push_status"] == "synced"
        assert item["analysis_result"]["analysis_status"] == "已完成"
        assert item["analysis_result"]["content_type"] == "种草"
        assert "问题驱动模型" in item["analysis_result"]["reusable_models"]
    finally:
        app.dependency_overrides.pop(get_db, None)

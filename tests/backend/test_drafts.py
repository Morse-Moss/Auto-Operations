from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import AiDraft, DraftAsset, Note, PlatformAccount, User

client = TestClient(app)


def override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'drafts-test.db'}", connect_args={"check_same_thread": False})
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


def create_user(db, username: str) -> User:
    user = User(username=username, password_hash=hash_password("secret123"))
    db.add(user)
    db.flush()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def create_original_draft_with_assets(db, user: User) -> AiDraft:
    account = PlatformAccount(
        user_id=user.id,
        platform="xhs",
        sub_type="pc",
        external_user_id=f"account-{user.id}",
        nickname="测试账号",
        status="active",
    )
    db.add(account)
    db.flush()
    source_note = Note(
        user_id=user.id,
        platform_account_id=account.id,
        platform="xhs",
        note_id=f"source-note-{user.id}",
        title="源笔记",
        content="源正文",
        author_name="源作者",
    )
    db.add(source_note)
    db.flush()
    draft = AiDraft(
        user_id=user.id,
        platform="xhs",
        title="原始草稿",
        body="原始正文",
        tags=[{"id": "topic-1", "name": "咖啡"}, {"name": "探店"}],
        source_note_id=source_note.id,
    )
    db.add(draft)
    db.flush()
    db.add_all(
        [
            DraftAsset(
                draft_id=draft.id,
                asset_type="image",
                url="https://example.test/image-a.webp",
                local_path="drafts/image-a.webp",
                sort_order=0,
            ),
            DraftAsset(
                draft_id=draft.id,
                asset_type="video",
                url="https://example.test/video-b.mp4",
                local_path="drafts/video-b.mp4",
                sort_order=1,
            ),
        ]
    )
    db.commit()
    db.refresh(draft)
    return draft


def test_duplicate_draft_copies_owned_draft_and_asset_references(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-duplicate-owner")
            original = create_original_draft_with_assets(db, owner)
            original_id = original.id
            source_note_id = original.source_note_id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(f"/api/drafts/{original_id}/duplicate", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] != original_id
        assert payload["platform"] == "xhs"
        assert payload["title"] == "原始草稿 - 副本"
        assert payload["body"] == "原始正文"
        assert payload["tags"] == [{"id": "topic-1", "name": "咖啡"}, {"name": "探店"}]
        assert payload["source_note_id"] == source_note_id

        db = SessionLocal()
        try:
            drafts = db.scalars(select(AiDraft).order_by(AiDraft.id.asc())).all()
            assert len(drafts) == 2
            original, duplicated = drafts
            assert original.id == original_id
            assert original.title == "原始草稿"
            assert original.body == "原始正文"
            assert original.tags == [{"id": "topic-1", "name": "咖啡"}, {"name": "探店"}]
            assert duplicated.id == payload["id"]
            assert duplicated.user_id == original.user_id
            assert duplicated.platform == original.platform
            assert duplicated.title == "原始草稿 - 副本"
            assert duplicated.body == original.body
            assert duplicated.tags == original.tags
            assert duplicated.source_note_id == original.source_note_id

            original_assets = db.scalars(
                select(DraftAsset).where(DraftAsset.draft_id == original_id).order_by(DraftAsset.sort_order.asc())
            ).all()
            copied_assets = db.scalars(
                select(DraftAsset).where(DraftAsset.draft_id == duplicated.id).order_by(DraftAsset.sort_order.asc())
            ).all()
            assert len(original_assets) == 2
            assert len(copied_assets) == 2
            assert [asset.id for asset in copied_assets] != [asset.id for asset in original_assets]
            assert [
                (asset.asset_type, asset.url, asset.local_path, asset.sort_order) for asset in copied_assets
            ] == [
                ("image", "https://example.test/image-a.webp", "drafts/image-a.webp", 0),
                ("video", "https://example.test/video-b.mp4", "drafts/video-b.mp4", 1),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_duplicate_draft_requires_authentication(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-duplicate-auth-owner")
            original = create_original_draft_with_assets(db, owner)
            original_id = original.id
        finally:
            db.close()

        response = client.post(f"/api/drafts/{original_id}/duplicate")

        assert response.status_code == 401

        db = SessionLocal()
        try:
            drafts = db.scalars(select(AiDraft)).all()
            assert len(drafts) == 1
            assert drafts[0].id == original_id
            assets = db.scalars(select(DraftAsset)).all()
            assert len(assets) == 2
            assert {asset.draft_id for asset in assets} == {original_id}
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_duplicate_draft_returns_404_for_missing_draft_without_creating_records(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-duplicate-missing-owner")
            headers = auth_headers(owner)
            db.commit()
        finally:
            db.close()

        response = client.post("/api/drafts/999999/duplicate", headers=headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Draft not found"

        db = SessionLocal()
        try:
            drafts = db.scalars(select(AiDraft)).all()
            assert drafts == []
            assets = db.scalars(select(DraftAsset)).all()
            assert assets == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)



def test_duplicate_draft_returns_404_for_another_users_draft_without_copying(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-duplicate-owner-isolated")
            intruder = create_user(db, "draft-duplicate-intruder")
            original = create_original_draft_with_assets(db, owner)
            original_id = original.id
            intruder_headers = auth_headers(intruder)
        finally:
            db.close()

        response = client.post(f"/api/drafts/{original_id}/duplicate", headers=intruder_headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Draft not found"

        db = SessionLocal()
        try:
            drafts = db.scalars(select(AiDraft)).all()
            assert len(drafts) == 1
            assert drafts[0].id == original_id
            assets = db.scalars(select(DraftAsset)).all()
            assert len(assets) == 2
            assert {asset.draft_id for asset in assets} == {original_id}
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)

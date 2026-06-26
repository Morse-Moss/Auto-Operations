from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as SqlAlchemySession, sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import AiDraft, DraftAsset, Note, NoteAsset, PlatformAccount, PublishAsset, PublishJob, User

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


def test_create_update_and_list_draft_uses_internal_draft_name(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-name-owner")
            headers = auth_headers(owner)
            db.commit()
        finally:
            db.close()

        create_response = client.post(
            "/api/drafts",
            headers=headers,
            json={
                "platform": "xhs",
                "draft_name": "浴缸案例图替换 - A版",
                "title": "卫生间浴缸怎么选？",
                "body": "正文",
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["draft_name"] == "浴缸案例图替换 - A版"
        assert created["title"] == "卫生间浴缸怎么选？"

        update_response = client.patch(
            f"/api/drafts/{created['id']}",
            headers=headers,
            json={"draft_name": "浴缸案例图替换 - B版"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["draft_name"] == "浴缸案例图替换 - B版"
        assert update_response.json()["title"] == "卫生间浴缸怎么选？"

        list_response = client.get("/api/drafts", headers=headers, params={"platform": "xhs"})
        assert list_response.status_code == 200
        assert list_response.json()["items"][0]["draft_name"] == "浴缸案例图替换 - B版"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_draft_from_source_note_copies_note_assets_to_draft_assets(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-create-source-assets-owner")
            account = PlatformAccount(
                user_id=owner.id,
                platform="xhs",
                sub_type="pc",
                external_user_id=f"source-account-{owner.id}",
                nickname="来源账号",
                status="active",
            )
            db.add(account)
            db.flush()
            source_note = Note(
                user_id=owner.id,
                platform_account_id=account.id,
                platform="xhs",
                note_id=f"source-note-with-assets-{owner.id}",
                title="来源标题",
                content="来源正文",
                author_name="来源作者",
            )
            db.add(source_note)
            db.flush()
            db.add_all([
                NoteAsset(
                    note_id=source_note.id,
                    asset_type="image",
                    url="https://example.test/source-a.webp",
                    local_path="notes/source-a.webp",
                    sort_order=0,
                ),
                NoteAsset(
                    note_id=source_note.id,
                    asset_type="image",
                    url="https://example.test/source-b.webp",
                    local_path="notes/source-b.webp",
                    sort_order=1,
                ),
            ])
            db.commit()
            headers = auth_headers(owner)
            source_note_id = source_note.id
        finally:
            db.close()

        response = client.post(
            "/api/drafts",
            headers=headers,
            json={"platform": "xhs", "source_note_id": source_note_id, "intent": "rewrite"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_note_id"] == source_note_id
        assert payload["title"] == "来源标题"
        assert payload["body"] == "来源正文"

        db = SessionLocal()
        try:
            copied_assets = db.scalars(
                select(DraftAsset)
                .where(DraftAsset.draft_id == payload["id"])
                .order_by(DraftAsset.sort_order.asc(), DraftAsset.id.asc())
            ).all()
            assert [
                (asset.asset_type, asset.url, asset.local_path, asset.sort_order)
                for asset in copied_assets
            ] == [
                ("image", "https://example.test/source-a.webp", "notes/source-a.webp", 0),
                ("image", "https://example.test/source-b.webp", "notes/source-b.webp", 1),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_update_draft_normalizes_repeated_title_and_markdown_symbols(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-normalize-owner")
            draft = AiDraft(user_id=owner.id, platform="xhs", title="旧标题", body="旧正文", tags=[])
            db.add(draft)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.patch(
            f"/api/drafts/{draft_id}",
            headers=headers,
            json={
                "title": "SaaS 工具怎么选？",
                "body": "# SaaS 工具怎么选？\n\n**重点**\n- 第一条",
                "tags": [{"name": "工具"}, {"name": "工具"}],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "SaaS 工具怎么选？"
        assert payload["body"] == "重点\n第一条"
        assert payload["tags"] == [{"name": "工具"}]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_update_wechat_official_draft_preserves_markdown_body_and_tags(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-wechat-preserve-owner")
            body = "# 公众号标题\n\n**重点**\n- 第一条"
            tags = [{"name": "公众号"}, {"name": "公众号"}]
            draft = AiDraft(user_id=owner.id, platform="wechat_official", title="公众号标题", body=body, tags=tags)
            db.add(draft)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.patch(
            f"/api/drafts/{draft_id}",
            headers=headers,
            json={"title": "公众号标题", "body": body, "tags": tags},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "公众号标题"
        assert payload["body"] == body
        assert "# 公众号标题" in payload["body"]
        assert "**重点**" in payload["body"]
        assert "- 第一条" in payload["body"]
        assert payload["tags"] == tags
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_uses_normalized_content(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-normalize-owner")
            draft = AiDraft(
                user_id=owner.id,
                platform="xhs",
                title="SaaS 工具怎么选？",
                body="SaaS 工具怎么选？\n\n正文第一段",
                tags=[{"name": "SaaS"}, {"name": "SaaS"}],
            )
            db.add(draft)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(f"/api/drafts/{draft_id}/send-to-publish", headers=headers, json={"publish_mode": "immediate"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "SaaS 工具怎么选？"
        assert payload["body"] == "正文第一段"
        assert payload["publish_options"]["draft_tags"] == [{"name": "SaaS"}]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_accepts_current_user_existing_managed_media_path(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-generated-image-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-image-u{owner.id}-generated-cover.png"
            (media_dir / file_name).write_bytes(b"fake-image")
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_path": f"/api/files/media/{file_name}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "pending"
        assert payload["source_draft_id"] == draft_id

        db = SessionLocal()
        try:
            publish_assets = db.scalars(select(PublishAsset).where(PublishAsset.publish_job_id == payload["id"])).all()
            assert len(publish_assets) == 1
            assert publish_assets[0].asset_type == "image"
            assert publish_assets[0].file_path == f"/api/files/media/{file_name}"
            assert publish_assets[0].upload_status == "pending"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_accepts_ordered_asset_file_paths(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-multi-image-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-image-u{owner.id}-generated-final.png"
            download_a = f"xhs-asset-u{owner.id}-download-a.jpg"
            download_b = f"xhs-asset-u{owner.id}-download-b.jpg"
            (media_dir / file_name).write_bytes(b"fake-image")
            (media_dir / download_a).write_bytes(b"download-a")
            (media_dir / download_b).write_bytes(b"download-b")
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            monkeypatch.setattr(
                "backend.app.api.drafts.download_asset_to_local",
                lambda url, user_id, asset_type, platform="xhs": {
                    "https://cdn.example.test/final-a.webp": download_a,
                    "https://cdn.example.test/final-b.webp": download_b,
                }.get(url),
                raising=False,
            )
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={
                "publish_mode": "immediate",
                "asset_file_paths": [
                    "https://cdn.example.test/final-a.webp",
                    "",
                    f"/api/files/media/{file_name}",
                    "https://cdn.example.test/final-a.webp",
                    "https://cdn.example.test/final-b.webp",
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "pending"
        assert payload["source_draft_id"] == draft_id

        db = SessionLocal()
        try:
            publish_assets = db.scalars(
                select(PublishAsset)
                .where(PublishAsset.publish_job_id == payload["id"])
                .order_by(PublishAsset.id.asc())
            ).all()
            assert [asset.asset_type for asset in publish_assets] == ["image", "image", "image"]
            assert [asset.file_path for asset in publish_assets] == [
                f"/api/files/media/{download_a}",
                f"/api/files/media/{file_name}",
                f"/api/files/media/{download_b}",
            ]
            assert [asset.upload_status for asset in publish_assets] == ["pending", "pending", "pending"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_empty_explicit_asset_file_paths_before_creating_job(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-empty-multi-owner")
            draft = create_original_draft_with_assets(db, owner)
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_paths": ["", "   "]},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_paths must include at least one usable image"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_too_many_asset_file_paths_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    download_calls = []
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-too-many-owner")
            draft = create_original_draft_with_assets(db, owner)
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        def fail_if_downloaded(url, user_id, asset_type, platform="xhs"):
            download_calls.append((url, user_id, asset_type, platform))
            raise AssertionError("download_asset_to_local should not be called for too many explicit assets")

        monkeypatch.setattr("backend.app.api.drafts.download_asset_to_local", fail_if_downloaded, raising=False)

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={
                "publish_mode": "immediate",
                "asset_file_paths": [f"https://cdn.example.test/generated-{idx:02d}.webp" for idx in range(19)],
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_paths supports at most 18 images"
        assert download_calls == []

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_external_asset_file_path_when_download_fails_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    (storage_dir / "media").mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-download-fails-owner")
            draft = create_original_draft_with_assets(db, owner)
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            monkeypatch.setattr(
                "backend.app.api.drafts.download_asset_to_local",
                lambda url, user_id, asset_type, platform="xhs": None,
                raising=False,
            )
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_paths": ["https://cdn.example.test/final-a.webp"]},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path external image download failed"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_video_media_path_in_asset_file_paths_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-video-media-path-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-image-u{owner.id}-not-image.mp4"
            (media_dir / file_name).write_bytes(b"fake-video")
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_paths": [f"/api/files/media/{file_name}"]},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path must be an image media file"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_external_asset_file_path_downloaded_as_video_and_cleans_file(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-external-video-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-asset-u{owner.id}-downloaded-video.mp4"
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))

            def fake_download(url, user_id, asset_type, platform="xhs"):
                (media_dir / file_name).write_bytes(b"fake-video")
                return file_name

            monkeypatch.setattr("backend.app.api.drafts.download_asset_to_local", fake_download, raising=False)
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_paths": ["https://cdn.example.test/video.mp4"]},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path must be an image media file"
        assert not (media_dir / file_name).exists()

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_cleans_previous_external_download_when_later_download_fails(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    first_url = "https://cdn.example.test/final-a.jpg"
    second_url = "https://cdn.example.test/final-b.jpg"
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-clean-explicit-owner")
            draft = create_original_draft_with_assets(db, owner)
            first_file_name = f"xhs-asset-u{owner.id}-downloaded-a.jpg"
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))

            def fake_download(url, user_id, asset_type, platform="xhs"):
                if url == first_url:
                    (media_dir / first_file_name).write_bytes(b"fake-image")
                    return first_file_name
                if url == second_url:
                    return None
                raise AssertionError(f"unexpected download url: {url}")

            monkeypatch.setattr("backend.app.api.drafts.download_asset_to_local", fake_download, raising=False)
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_paths": [first_url, second_url]},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path external image download failed"
        assert not (media_dir / first_file_name).exists()

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_cleans_fallback_external_download_when_later_draft_asset_download_fails(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    first_url = "https://cdn.example.test/fallback-a.jpg"
    second_url = "https://cdn.example.test/fallback-b.jpg"
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-clean-fallback-owner")
            draft = AiDraft(user_id=owner.id, platform="xhs", title="草稿", body="正文", tags=[])
            db.add(draft)
            db.flush()
            db.add_all(
                [
                    DraftAsset(
                        draft_id=draft.id,
                        asset_type="image",
                        url=first_url,
                        local_path="",
                        sort_order=0,
                    ),
                    DraftAsset(
                        draft_id=draft.id,
                        asset_type="image",
                        url=second_url,
                        local_path="",
                        sort_order=1,
                    ),
                ]
            )
            first_file_name = f"xhs-asset-u{owner.id}-downloaded-a.jpg"
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))

            def fake_download(url, user_id, asset_type, platform="xhs"):
                if url == first_url:
                    (media_dir / first_file_name).write_bytes(b"fake-image")
                    return first_file_name
                if url == second_url:
                    return None
                raise AssertionError(f"unexpected download url: {url}")

            monkeypatch.setattr("backend.app.api.drafts.download_asset_to_local", fake_download, raising=False)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path external image download failed"
        assert not (media_dir / first_file_name).exists()

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_cleans_explicit_external_download_when_db_commit_fails(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-explicit-commit-fail-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-asset-u{owner.id}-commit-fail.jpg"
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))

            def fake_download(url, user_id, asset_type, platform="xhs"):
                assert url == "https://cdn.example.test/a.jpg"
                (media_dir / file_name).write_bytes(b"fake-image")
                return file_name

            monkeypatch.setattr("backend.app.api.drafts.download_asset_to_local", fake_download, raising=False)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        def fail_commit(self):
            raise RuntimeError("commit failed after download")

        monkeypatch.setattr(SqlAlchemySession, "commit", fail_commit)

        try:
            response = client.post(
                f"/api/drafts/{draft_id}/send-to-publish",
                headers=headers,
                json={"publish_mode": "immediate", "asset_file_paths": ["https://cdn.example.test/a.jpg"]},
            )
        except RuntimeError as exc:
            assert "commit failed after download" in str(exc)
        else:
            assert response.status_code == 500

        assert not (media_dir / file_name).exists()

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_cleans_fallback_external_download_when_db_commit_fails(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-fallback-commit-fail-owner")
            draft = AiDraft(user_id=owner.id, platform="xhs", title="草稿", body="正文", tags=[])
            db.add(draft)
            db.flush()
            source_url = "https://cdn.example.test/fallback-a.jpg"
            db.add(
                DraftAsset(
                    draft_id=draft.id,
                    asset_type="image",
                    url=source_url,
                    local_path="",
                    sort_order=0,
                )
            )
            file_name = f"xhs-asset-u{owner.id}-commit-fail.jpg"
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))

            def fake_download(url, user_id, asset_type, platform="xhs"):
                assert url == source_url
                (media_dir / file_name).write_bytes(b"fake-image")
                return file_name

            monkeypatch.setattr("backend.app.api.drafts.download_asset_to_local", fake_download, raising=False)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        def fail_commit(self):
            raise RuntimeError("commit failed after download")

        monkeypatch.setattr(SqlAlchemySession, "commit", fail_commit)

        try:
            response = client.post(
                f"/api/drafts/{draft_id}/send-to-publish",
                headers=headers,
                json={"publish_mode": "immediate"},
            )
        except RuntimeError as exc:
            assert "commit failed after download" in str(exc)
        else:
            assert response.status_code == 500

        assert not (media_dir / file_name).exists()

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_localizes_external_draft_asset_urls_in_fallback_before_creating_assets(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    download_calls = []
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-fallback-external-owner")
            draft = create_original_draft_with_assets(db, owner)
            image_asset = db.scalars(
                select(DraftAsset).where(DraftAsset.draft_id == draft.id, DraftAsset.asset_type == "image")
            ).first()
            image_asset.local_path = ""
            image_asset.url = "https://cdn.example.test/fallback-a.webp"
            file_name = f"xhs-asset-u{owner.id}-fallback-a.jpg"
            (media_dir / file_name).write_bytes(b"downloaded-image")
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))

            def fake_download(url, user_id, asset_type, platform="xhs"):
                download_calls.append((url, user_id, asset_type, platform))
                if url == "https://cdn.example.test/fallback-a.webp":
                    return file_name
                return None

            monkeypatch.setattr("backend.app.api.drafts.download_asset_to_local", fake_download, raising=False)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert download_calls == [("https://cdn.example.test/fallback-a.webp", owner.id, "image", "xhs")]

        db = SessionLocal()
        try:
            publish_assets = db.scalars(
                select(PublishAsset)
                .where(PublishAsset.publish_job_id == payload["id"])
                .order_by(PublishAsset.id.asc())
            ).all()
            image_assets = [asset for asset in publish_assets if asset.asset_type == "image"]
            assert [asset.file_path for asset in image_assets] == [f"/api/files/media/{file_name}"]
            assert all(not asset.file_path.startswith("https://") for asset in image_assets)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_too_many_fallback_image_assets_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-fallback-too-many-owner")
            draft = AiDraft(user_id=owner.id, platform="xhs", title="草稿", body="正文", tags=[])
            db.add(draft)
            db.flush()
            for idx in range(19):
                file_name = f"xhs-image-u{owner.id}-fallback-{idx}.png"
                (media_dir / file_name).write_bytes(b"fake-image")
                db.add(
                    DraftAsset(
                        draft_id=draft.id,
                        asset_type="image",
                        url=f"https://example.test/fallback-{idx}.png",
                        local_path=file_name,
                        sort_order=idx,
                    )
                )
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_paths supports at most 18 images"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_invalid_managed_path_in_asset_file_paths_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    (storage_dir / "media").mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-multi-invalid-owner")
            draft = create_original_draft_with_assets(db, owner)
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={
                "publish_mode": "immediate",
                "asset_file_paths": [
                    "/api/files/media/xhs-image-u999999-stolen.png",
                ],
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path must be a current-user managed media file"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_wrong_user_managed_media_path_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-wrong-user-asset-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-image-u{owner.id + 999}-generated-cover.png"
            (media_dir / file_name).write_bytes(b"fake-image")
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_path": f"/api/files/media/{file_name}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path must be a current-user managed media file"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_missing_managed_media_path_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    (storage_dir / "media").mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-missing-asset-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-image-u{owner.id}-missing-cover.png"
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_path": f"/api/files/media/{file_name}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path media file not found"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_rejects_non_media_asset_file_path_before_creating_job(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-invalid-asset-owner")
            draft = create_original_draft_with_assets(db, owner)
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate", "asset_file_path": "https://cdn.example.test/generated-cover.png"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path must start with /api/files/media/"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_duplicate_draft_copies_internal_name_with_copy_suffix(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-name-duplicate-owner")
            original = create_original_draft_with_assets(db, owner)
            original.draft_name = "浴缸案例图替换"
            db.commit()
            original_id = original.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(f"/api/drafts/{original_id}/duplicate", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_name"] == "浴缸案例图替换 副本"
        assert payload["title"] == "原始草稿 - 副本"
    finally:
        app.dependency_overrides.pop(get_db, None)


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

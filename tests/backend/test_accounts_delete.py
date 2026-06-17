from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.models import AccountCookieVersion, CrawlDiagnostic, Note, PlatformAccount

client = TestClient(app)


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounts-delete-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return get_db


def _register_token(username: str = "account-delete-owner") -> str:
    response = client.post("/api/auth/register", json={"username": username, "password": "secret123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_delete_account_removes_credentials_and_hides_account_without_deleting_history(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        token = _register_token()
        db = next(app.dependency_overrides[get_db]())
        try:
            account = PlatformAccount(user_id=1, platform="xhs", sub_type="pc", nickname="expired pc", status="expired")
            db.add(account)
            db.flush()
            db.add(AccountCookieVersion(platform_account_id=account.id, encrypted_cookies="encrypted-cookie"))
            note = Note(user_id=1, platform_account_id=account.id, platform="xhs", note_id="history-note-1", title="历史笔记")
            db.add(note)
            db.add(
                CrawlDiagnostic(
                    user_id=1,
                    task_id=None,
                    platform_account_id=account.id,
                    platform="xhs",
                    source="飞书",
                    stage="search",
                    kind="xhs_account_expired",
                    severity="blocked",
                    recoverable=False,
                    message="登录已过期",
                    user_message="重新登录",
                    raw_json={"error_code": -100},
                )
            )
            db.commit()
            account_id = account.id
        finally:
            db.close()

        delete_response = client.delete(f"/api/accounts/{account_id}", headers={"Authorization": f"Bearer {token}"})

        assert delete_response.status_code == 200
        assert delete_response.json() == {"id": account_id, "status": "deleted"}

        list_response = client.get("/api/accounts", headers={"Authorization": f"Bearer {token}"})
        assert list_response.status_code == 200
        assert all(item["id"] != account_id for item in list_response.json()["items"])

        check_response = client.post(f"/api/accounts/{account_id}/check", headers={"Authorization": f"Bearer {token}"})
        assert check_response.status_code == 404

        db = next(app.dependency_overrides[get_db]())
        try:
            stored_account = db.get(PlatformAccount, account_id)
            assert stored_account is not None
            assert stored_account.status == "deleted"
            assert db.query(AccountCookieVersion).filter(AccountCookieVersion.platform_account_id == account_id).count() == 0
            assert db.query(Note).filter(Note.platform_account_id == account_id).count() == 1
            assert db.query(CrawlDiagnostic).filter(CrawlDiagnostic.platform_account_id == account_id).count() == 1
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)

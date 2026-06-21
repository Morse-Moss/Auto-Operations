from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.adapters.xhs.creator_api_adapter import XhsCreatorApiAdapter


def test_creator_upload_rejects_remote_url(monkeypatch):
    def forbidden_get(*args, **kwargs):
        raise AssertionError("remote URL must be rejected before requests.get")

    monkeypatch.setattr("requests.get", forbidden_get)

    with pytest.raises(ValueError, match="Only server-managed media files"):
        XhsCreatorApiAdapter._resolve_file_data("https://example.com/image.jpg")


def test_creator_upload_rejects_local_path(tmp_path):
    local = tmp_path / "secret.txt"
    local.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="Only server-managed media files"):
        XhsCreatorApiAdapter._resolve_file_data(str(local))


def test_creator_upload_rejects_traversal_media_path():
    with pytest.raises(ValueError, match="Invalid media file name"):
        XhsCreatorApiAdapter._resolve_file_data("/api/files/media/../secret.jpg")


def test_creator_upload_reads_only_server_managed_media(monkeypatch, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media = media_dir / "valid.jpg"
    media.write_bytes(b"safe-image-bytes")

    monkeypatch.setattr("backend.app.core.config.get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    assert XhsCreatorApiAdapter._resolve_file_data("/api/files/media/valid.jpg") == b"safe-image-bytes"

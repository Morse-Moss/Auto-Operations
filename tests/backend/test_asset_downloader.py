from __future__ import annotations

from types import SimpleNamespace

from backend.app.services import asset_downloader


class FakeResponse:
    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None) -> None:
        self._chunks = chunks
        self.headers = headers or {"content-type": "image/jpeg"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        yield from self._chunks


def test_download_asset_to_local_streams_to_owned_media_file(tmp_path, monkeypatch):
    calls: list[dict] = []

    def fake_get(url, *, timeout, headers, stream):
        calls.append({"url": url, "timeout": timeout, "headers": headers, "stream": stream})
        return FakeResponse([b"a" * 128], {"content-type": "image/webp", "content-length": "128"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    file_name = asset_downloader.download_asset_to_local(
        "https://cdn.example.test/image",
        7,
        "image",
        timeout=(1, 2),
        max_bytes=1024,
    )

    assert file_name is not None
    assert file_name.startswith("xhs-asset-u7-")
    assert file_name.endswith(".webp")
    assert (tmp_path / "media" / file_name).read_bytes() == b"a" * 128
    assert calls == [
        {
            "url": "https://cdn.example.test/image",
            "timeout": (1, 2),
            "headers": {"Referer": ""},
            "stream": True,
        }
    ]


def test_download_asset_to_local_rejects_oversized_stream_and_deletes_partial_file(tmp_path, monkeypatch):
    def fake_get(url, *, timeout, headers, stream):
        return FakeResponse([b"a" * 64, b"b" * 64], {"content-type": "image/jpeg"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    file_name = asset_downloader.download_asset_to_local(
        "https://cdn.example.test/too-large.jpg",
        7,
        "image",
        max_bytes=100,
    )

    assert file_name is None
    media_dir = tmp_path / "media"
    assert media_dir.exists()
    assert list(media_dir.iterdir()) == []


def test_download_asset_to_local_rejects_oversized_content_length_without_writing(tmp_path, monkeypatch):
    def fake_get(url, *, timeout, headers, stream):
        return FakeResponse([], {"content-type": "image/jpeg", "content-length": "1000"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    file_name = asset_downloader.download_asset_to_local(
        "https://cdn.example.test/too-large.jpg",
        7,
        "image",
        max_bytes=100,
    )

    assert file_name is None
    assert not (tmp_path / "media").exists()


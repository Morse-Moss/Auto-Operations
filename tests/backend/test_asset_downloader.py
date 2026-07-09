from __future__ import annotations

from types import SimpleNamespace

from backend.app.services import asset_downloader


class FakeResponse:
    def __init__(
        self,
        chunks: list[bytes],
        headers: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self._chunks = chunks
        self.headers = headers or {"content-type": "image/jpeg"}
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} Client Error")
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
            "headers": asset_downloader.DOWNLOAD_HEADERS,
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


def test_download_asset_to_local_repairs_expired_xhs_webpic_note_image_url(tmp_path, monkeypatch):
    calls: list[str] = []
    expired_url = (
        "http://sns-webpic-qc.xhscdn.com/202607091550/"
        "b8a8c1cba93f50c03a5a744ad39e860a/c/notes_pre_post/"
        "1040g3k8321r7di7t7k8g49g5ujh30vom9sk6u58"
    )
    repaired_webp_url = (
        "https://sns-img-hw.xhscdn.com/notes_pre_post/"
        "1040g3k8321r7di7t7k8g49g5ujh30vom9sk6u58"
        "?imageView2/2/w/1080/format/webp"
    )
    repaired_raw_url = (
        "https://sns-img-hw.xhscdn.com/notes_pre_post/"
        "1040g3k8321r7di7t7k8g49g5ujh30vom9sk6u58"
    )

    def fake_get(url, *, timeout, headers, stream):
        calls.append(url)
        if url == expired_url:
            return FakeResponse([], {"content-type": "", "content-length": "0"}, status_code=403)
        if url == repaired_webp_url:
            return FakeResponse([b"a" * 128], {"content-type": "image/webp", "content-length": "128"})
        if url == repaired_raw_url:
            raise AssertionError("raw HEIC candidate should not be needed when WebP candidate succeeds")
        raise AssertionError(f"unexpected download URL: {url}")

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    file_name = asset_downloader.download_asset_to_local(
        expired_url,
        7,
        "image",
        max_bytes=1024,
    )

    assert file_name is not None
    assert file_name.endswith(".webp")
    assert (tmp_path / "media" / file_name).read_bytes() == b"a" * 128
    assert calls == [expired_url, repaired_webp_url]


def test_download_asset_to_local_uses_heic_extension_when_raw_image_is_returned(tmp_path, monkeypatch):
    def fake_get(url, *, timeout, headers, stream):
        return FakeResponse([b"a" * 128], {"content-type": "image/heic", "content-length": "128"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    file_name = asset_downloader.download_asset_to_local(
        "https://cdn.example.test/raw-image",
        7,
        "image",
        max_bytes=1024,
    )

    assert file_name is not None
    assert file_name.endswith(".heic")

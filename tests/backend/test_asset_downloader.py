from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services import asset_downloader
from backend.app.services.public_url_guard import PublicUrlBlockedError


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

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308} and "location" in {key.lower() for key in self.headers}

    @property
    def is_permanent_redirect(self) -> bool:
        return self.status_code in {301, 308} and "location" in {key.lower() for key in self.headers}

    def close(self) -> None:
        return None

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


def _allow_all_urls(monkeypatch):
    monkeypatch.setattr(asset_downloader, "assert_public_http_url", lambda url, *, label="下载地址": None)


def test_download_asset_to_local_streams_to_owned_media_file(tmp_path, monkeypatch):
    calls: list[dict] = []

    def fake_get(url, *, timeout, headers, stream, allow_redirects):
        calls.append({"url": url, "timeout": timeout, "headers": headers, "stream": stream, "allow_redirects": allow_redirects})
        return FakeResponse([b"a" * 128], {"content-type": "image/webp", "content-length": "128"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))
    _allow_all_urls(monkeypatch)

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
            "allow_redirects": False,
        }
    ]


def test_download_asset_to_local_rejects_oversized_stream_and_deletes_partial_file(tmp_path, monkeypatch):
    def fake_get(url, *, timeout, headers, stream, allow_redirects):
        return FakeResponse([b"a" * 64, b"b" * 64], {"content-type": "image/jpeg"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))
    _allow_all_urls(monkeypatch)

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
    def fake_get(url, *, timeout, headers, stream, allow_redirects):
        return FakeResponse([], {"content-type": "image/jpeg", "content-length": "1000"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))
    _allow_all_urls(monkeypatch)

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

    def fake_get(url, *, timeout, headers, stream, allow_redirects):
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
    _allow_all_urls(monkeypatch)

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
    def fake_get(url, *, timeout, headers, stream, allow_redirects):
        return FakeResponse([b"a" * 128], {"content-type": "image/heic", "content-length": "128"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))
    _allow_all_urls(monkeypatch)

    file_name = asset_downloader.download_asset_to_local(
        "https://cdn.example.test/raw-image",
        7,
        "image",
        max_bytes=1024,
    )

    assert file_name is not None
    assert file_name.endswith(".heic")


@pytest.mark.parametrize(
    "target_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.10/internal.jpg",
        "http://127.0.0.1:18081/api/files/media/secret.jpg",
        "http://10.0.0.8/img.png",
        "https://[::1]/img.png",
    ],
)
def test_download_asset_to_local_rejects_non_public_targets(tmp_path, monkeypatch, target_url):
    def fail_get(*args, **kwargs):
        raise AssertionError("no HTTP request may be issued for a non-public target")

    monkeypatch.setattr("requests.get", fail_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    with pytest.raises(PublicUrlBlockedError, match="内网地址"):
        asset_downloader.download_asset_to_local(target_url, 7, "image")

    assert not (tmp_path / "media").exists()


def test_download_asset_to_local_rejects_hostname_resolving_to_private_ip(tmp_path, monkeypatch):
    import socket

    from backend.app.services import public_url_guard

    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.5", int(port or 80)))]

    def fail_get(*args, **kwargs):
        raise AssertionError("no HTTP request may be issued when DNS resolves to a private IP")

    monkeypatch.setattr(public_url_guard.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("requests.get", fail_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    with pytest.raises(PublicUrlBlockedError, match="内网地址"):
        asset_downloader.download_asset_to_local("https://evil.example.test/rebind.jpg", 7, "image")


def test_download_asset_to_local_returns_none_when_host_cannot_be_resolved(tmp_path, monkeypatch):
    import socket

    from backend.app.services import public_url_guard

    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        raise socket.gaierror("name or service not known")

    def fail_get(*args, **kwargs):
        raise AssertionError("no HTTP request may be issued when DNS resolution fails")

    monkeypatch.setattr(public_url_guard.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("requests.get", fail_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    assert asset_downloader.download_asset_to_local("https://gone.example.test/x.jpg", 7, "image") is None


def test_download_asset_to_local_revalidates_redirect_target(tmp_path, monkeypatch):
    validated_urls: list[str] = []
    requested_urls: list[str] = []

    def fake_assert(url, *, label="下载地址"):
        validated_urls.append(url)
        if "192.168." in url:
            raise PublicUrlBlockedError(f"{label}不允许指向内网地址")

    def fake_get(url, *, timeout, headers, stream, allow_redirects):
        requested_urls.append(url)
        assert allow_redirects is False
        return FakeResponse([], {"content-type": "", "location": "http://192.168.1.1/internal.jpg"}, status_code=302)

    monkeypatch.setattr(asset_downloader, "assert_public_http_url", fake_assert)
    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(asset_downloader, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path))

    file_name = asset_downloader.download_asset_to_local("https://cdn.example.test/redirect.jpg", 7, "image")

    assert file_name is None
    # First hop was fetched once, then the private redirect target was
    # rejected during re-validation before any second request went out.
    assert requested_urls == ["https://cdn.example.test/redirect.jpg"]
    assert "http://192.168.1.1/internal.jpg" in validated_urls

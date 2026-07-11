from __future__ import annotations

import base64
import binascii
import ipaddress
import re
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlparse
from uuid import uuid4

import urllib3
from starlette.requests import Request

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import SessionLocal, get_db
from backend.app.core.deps import get_current_tenant_context, get_current_user
from backend.app.core.time import shanghai_now
from backend.app.models import AiDraft, AiGeneratedAsset, ModelConfig, Task, User
from backend.app.schemas.common import paginated
from backend.app.services.ai_service import ImageAiClient, OpenAICompatibleImageClient, OpenAICompatibleTextClient, RunningHubImageClient, TextAiClient
from backend.app.services.asset_storage_policy import asset_owner_prefix
from backend.app.services.beta_concurrency_service import BetaConcurrencyLeaseGuard, BetaConcurrencyService, acquire_image_generation_leases
from backend.app.services.model_config_service import require_model_capability_context
from backend.app.services.usage_quota_service import CREDITS_BUCKET, UsageQuotaService, credit_cost_for_feature, usage_idempotency_key
from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content

router = APIRouter(prefix="/ai", tags=["ai"])

GENERATED_IMAGE_MAX_IMPORT_SIZE = 20 * 1024 * 1024
GENERATED_IMAGE_ALLOWED_MEDIA_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class RewriteNoteRequest(BaseModel):
    draft_id: int
    instruction: str = Field(default="", max_length=800)


class GenerateNoteRequest(BaseModel):
    platform: Literal["xhs", "douyin", "kuaishou", "weibo", "xianyu", "taobao"] = "xhs"
    topic: str = Field(min_length=1, max_length=300)
    reference: str = Field(default="", max_length=4000)
    instruction: str = Field(default="", max_length=1000)


class GenerateTitleRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=6000)
    count: int = Field(default=5, ge=1, le=10)


class GenerateTagsRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=6000)
    count: int = Field(default=8, ge=1, le=20)


class PolishTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    instruction: str = Field(default="", max_length=800)


class GenerateCoverRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1200)
    draft_id: Optional[int] = None
    size: str = Field(default="1024x1024", max_length=32)
    style: str = Field(default="clean", max_length=120)


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    reference_images: list[str] = Field(default_factory=list)
    save_to_assets: bool = True
    aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9"] = "auto"


class DescribeImageRequest(BaseModel):
    image_url: str = Field(min_length=1, max_length=4000)
    instruction: str = Field(default="", max_length=800)


def get_text_ai_client() -> TextAiClient:
    return OpenAICompatibleTextClient()


def get_image_ai_client() -> ImageAiClient:
    return OpenAICompatibleImageClient()


def _serialize_draft(draft: AiDraft) -> dict:
    return {
        "id": draft.id,
        "platform": draft.platform,
        "draft_name": draft.draft_name or "",
        "title": draft.title,
        "body": draft.body,
        "tags": draft.tags or [],
        "source_note_id": draft.source_note_id,
        "created_at": draft.created_at.isoformat(),
    }


def _text_model_context(db: Session, current_user: User) -> tuple[ModelConfig, str]:
    return require_model_capability_context(db, "text")


def _image_model_context(db: Session, current_user: User, *, capability: str) -> tuple[ModelConfig, str]:
    return require_model_capability_context(db, capability)


def _image_client_for_model(model_config: ModelConfig, fallback_client: ImageAiClient) -> ImageAiClient:
    if model_config.provider == "runninghub-ai-app":
        return RunningHubImageClient()
    return fallback_client


def _redact_sensitive_text(message: str, sensitive_values: list[str] | None = None) -> str:
    redacted = str(message)
    for value in sensitive_values or []:
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    redacted = re.sub(r"(?i)\b(apiKey|api_key)=([^&\s]+)", r"\1=[REDACTED]", redacted)
    redacted = re.sub(r"(?i)(Authorization:\s*Bearer\s+)([^\s,;]+)", r"\1[REDACTED]", redacted)
    return redacted


def _provider_http_status(exc: Exception) -> int | None:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        response = getattr(current, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        current = current.__cause__ or current.__context__
    return None


def _public_image_generation_error(exc: Exception) -> tuple[str, str]:
    if _provider_http_status(exc) in {401, 403}:
        return (
            "MODEL_PROVIDER_UNAUTHORIZED",
            "图片生成模型鉴权失败，请管理员检查模型配置",
        )
    return (
        "MODEL_PROVIDER_FAILED",
        "图片生成模型调用失败，请稍后重试或联系管理员",
    )


def _serialize_generated_asset(asset: AiGeneratedAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "draft_id": asset.draft_id,
        "prompt": asset.prompt,
        "model_name": asset.model_name,
        "params": asset.params or {},
        "file_path": asset.file_path,
        "created_at": asset.created_at.isoformat(),
    }


def _media_dir() -> Path:
    return Path(get_settings().storage_dir) / "media"


def _generated_image_media_name(user_id: int, extension: str) -> str:
    try:
        prefix = asset_owner_prefix("xhs", "image", user_id)
    except ValueError as exc:  # pragma: no cover - constant platform/kind should stay valid.
        raise ValueError("Invalid media owner") from exc
    return f"{prefix}{uuid4().hex}{extension}"


def _image_extension_from_content_type(content_type: str | None) -> str:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    extension = GENERATED_IMAGE_ALLOWED_MEDIA_TYPES.get(media_type)
    if not extension:
        raise ValueError("生成图片格式不支持保存到媒体资产")
    return extension


def _image_content_type_from_bytes(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("生成图片内容不是受支持的图片格式")


def _is_public_ip_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(ip.is_global) and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_public_http_image_url(url: str) -> tuple[Any, str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("生成图片 URL 不支持保存到媒体资产")
    if parsed.username or parsed.password:
        raise ValueError("生成图片 URL 不支持用户信息")
    if not _is_public_ip_address(parsed.hostname):
        try:
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("生成图片 URL 无法解析") from exc
        public_ips = []
        for address in addresses:
            ip_text = str(address[4][0])
            if not _is_public_ip_address(ip_text):
                raise ValueError("生成图片 URL 不允许指向内网地址")
            if ip_text not in public_ips:
                public_ips.append(ip_text)
        if not public_ips:
            raise ValueError("生成图片 URL 无法解析")
        resolved_host = public_ips[0]
    else:
        resolved_host = parsed.hostname
    if not _is_public_ip_address(resolved_host):
        raise ValueError("生成图片 URL 不允许指向内网地址")
    return parsed, parsed.hostname, resolved_host, parsed.port or (443 if parsed.scheme == "https" else 80)


def _assert_public_http_image_url(url: str) -> None:
    _resolve_public_http_image_url(url)


def _download_public_http_image(url: str) -> tuple[bytes, str]:
    parsed, original_host, resolved_host, port = _resolve_public_http_image_url(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    pool_class = urllib3.HTTPSConnectionPool if parsed.scheme == "https" else urllib3.HTTPConnectionPool
    pool_kwargs: dict[str, Any] = {"timeout": 30.0, "retries": False}
    headers = {"Host": original_host}
    if parsed.scheme == "https":
        pool_kwargs.update({"assert_hostname": original_host, "server_hostname": original_host})
    pool = pool_class(resolved_host, port=port, **pool_kwargs)
    try:
        response = pool.request("GET", path, headers=headers, preload_content=False, redirect=False)
        try:
            if response.status >= 400:
                raise ValueError("生成图片 URL 下载失败，无法保存到媒体资产")
            if 300 <= response.status < 400:
                raise ValueError("生成图片 URL 不允许重定向")
            content_type = response.headers.get("content-type")
            _image_extension_from_content_type(content_type)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > GENERATED_IMAGE_MAX_IMPORT_SIZE:
                    raise ValueError("生成图片超过 20MB，无法保存到媒体资产")
                chunks.append(chunk)
            content = b"".join(chunks)
            detected_content_type = _image_content_type_from_bytes(content)
            declared_extension = _image_extension_from_content_type(content_type)
            detected_extension = _image_extension_from_content_type(detected_content_type)
            if declared_extension != detected_extension:
                raise ValueError("生成图片内容与声明格式不一致")
            return content, detected_content_type
        finally:
            response.release_conn()
    except urllib3.exceptions.HTTPError as exc:
        raise ValueError("生成图片 URL 下载失败，无法保存到媒体资产") from exc
    finally:
        pool.close()


def _store_generated_image_bytes(user_id: int, content: bytes, *, content_type: str | None) -> str:
    if not content:
        raise ValueError("生成图片内容为空")
    if len(content) > GENERATED_IMAGE_MAX_IMPORT_SIZE:
        raise ValueError("生成图片超过 20MB，无法保存到媒体资产")
    detected_content_type = _image_content_type_from_bytes(content)
    if content_type:
        declared_extension = _image_extension_from_content_type(content_type)
        detected_extension = _image_extension_from_content_type(detected_content_type)
        if declared_extension != detected_extension:
            raise ValueError("生成图片内容与声明格式不一致")
    extension = _image_extension_from_content_type(detected_content_type)
    media_dir = _media_dir()
    media_dir.mkdir(parents=True, exist_ok=True)
    file_name = _generated_image_media_name(user_id, extension)
    output_path = (media_dir / file_name).resolve()
    output_path.write_bytes(content)
    return f"/api/files/media/{file_name}"


def _import_generated_image_to_media(image_ref: str, *, user_id: int) -> str:
    value = (image_ref or "").strip()
    if not value:
        raise ValueError("生成图片结果为空，无法保存到媒体资产")
    if value.startswith("/api/files/media/"):
        return value
    if value.startswith("data:image/"):
        header, separator, encoded = value.partition(",")
        if not separator:
            raise ValueError("生成图片 data URL 格式无效")
        match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64$", header, re.IGNORECASE)
        if not match:
            raise ValueError("生成图片 data URL 仅支持 base64 图片")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("生成图片 data URL 无法解码") from exc
        return _store_generated_image_bytes(user_id, content, content_type=match.group(1))
    if not value.startswith(("http://", "https://")):
        try:
            content = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("生成图片结果必须是媒体资产、HTTP(S) 图片或 base64 图片") from None
        return _store_generated_image_bytes(user_id, content, content_type=_image_content_type_from_bytes(content))
    if value.startswith(("http://", "https://")):
        content, content_type = _download_public_http_image(value)
        return _store_generated_image_bytes(user_id, content, content_type=content_type)
    raise ValueError("生成图片结果必须是媒体资产、HTTP(S) 图片或 base64 图片")


def _create_generated_image_asset(
    *,
    db: Session,
    user_id: int,
    prompt: str,
    model_config: ModelConfig,
    params: dict[str, Any],
    source_url: str,
    draft_id: int | None = None,
) -> AiGeneratedAsset:
    file_path = _import_generated_image_to_media(source_url, user_id=user_id)
    asset = AiGeneratedAsset(
        user_id=user_id,
        draft_id=draft_id,
        prompt=prompt,
        model_name=model_config.model_name,
        params=params,
        file_path=file_path,
    )
    db.add(asset)
    db.flush()
    return asset


def _recorded_text_task(
    *,
    db: Session,
    current_user: User,
    platform: str,
    task_type: str,
    payload: dict[str, Any],
    action: Callable[[], Any],
    usage_reservation_id: int | None = None,
):
    task = Task(
        user_id=current_user.id,
        platform=platform,
        task_type=task_type,
        status="running",
        progress=10,
        payload=payload,
    )
    db.add(task)
    db.flush()
    try:
        result = action()
    except ValueError as exc:
        if usage_reservation_id is not None:
            UsageQuotaService(db).refund(usage_reservation_id, failure_reason=str(exc))
        task.status = "failed"
        task.progress = 100
        task.payload = {**(task.payload or {}), "error": str(exc)}
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        if usage_reservation_id is not None:
            UsageQuotaService(db).refund(usage_reservation_id, failure_reason=str(exc))
        task.status = "failed"
        task.progress = 100
        task.payload = {**(task.payload or {}), "error": str(exc)}
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI text generation failed: {exc}") from exc

    if usage_reservation_id is not None:
        UsageQuotaService(db).commit(usage_reservation_id)
    task.status = "completed"
    task.progress = 100
    return task, result


def _quota_idempotency_key(request: Request | None, fallback: str) -> str:
    return usage_idempotency_key(request, fallback)


def _reserve_usage(
    *,
    db: Session,
    current_user: User,
    feature_key: str,
    idempotency_key: str,
    request_summary: dict[str, Any] | None = None,
    model_config_id: int | None = None,
    provider: str = "",
):
    context = get_current_tenant_context(current_user=current_user, db=db)
    return UsageQuotaService(db).reserve(
        tenant_id=context.tenant.id,
        user_id=current_user.id,
        feature_key=feature_key,
        bucket=CREDITS_BUCKET,
        amount=credit_cost_for_feature(feature_key),
        idempotency_key=idempotency_key,
        request_summary=request_summary,
        model_config_id=model_config_id,
        provider=provider,
    )


def _acquire_image_generation_guard(
    *,
    db: Session,
    current_user: User,
    feature_key: str,
    idempotency_key: str,
) -> BetaConcurrencyLeaseGuard:
    context = get_current_tenant_context(current_user=current_user, db=db)
    return acquire_image_generation_leases(
        db=db,
        tenant_id=context.tenant.id,
        user_id=current_user.id,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
    )


def _recorded_image_task(
    *,
    db: Session,
    current_user: User,
    task_type: str,
    payload: dict[str, Any],
    action: Callable[[], Any],
    sensitive_values: list[str] | None = None,
    usage_reservation_id: int | None = None,
    provider: str | None = None,
):
    task = Task(
        user_id=current_user.id,
        platform="xhs",
        task_type=task_type,
        status="running",
        progress=10,
        payload=payload,
    )
    db.add(task)
    db.flush()
    try:
        result = action()
    except Exception as exc:
        if provider is not None and (
            not isinstance(exc, ValueError) or _provider_http_status(exc) is not None
        ):
            error_code, public_error = _public_image_generation_error(exc)
            if usage_reservation_id is not None:
                UsageQuotaService(db).refund(
                    usage_reservation_id,
                    failure_reason=public_error,
                )
            task.status = "failed"
            task.progress = 100
            task.payload = {
                **(task.payload or {}),
                "error_code": error_code,
                "error": public_error,
                "provider": provider,
            }
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": error_code, "message": public_error},
            ) from exc

        redacted_error = _redact_sensitive_text(str(exc), sensitive_values)
        if usage_reservation_id is not None:
            UsageQuotaService(db).refund(usage_reservation_id, failure_reason=redacted_error)
        task.status = "failed"
        task.progress = 100
        task.payload = {**(task.payload or {}), "error": redacted_error}
        db.commit()
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=redacted_error,
            ) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI image generation failed: {redacted_error}") from exc

    if usage_reservation_id is not None:
        UsageQuotaService(db).commit(usage_reservation_id)
    task.status = "completed"
    task.progress = 100
    return task, result


def _run_async_image_generate_task(task_id: int, current_user_id: int, model_config_id: int, api_key: str, fallback_client: ImageAiClient | None = None) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        model_config = db.get(ModelConfig, model_config_id)
        if task is None or model_config is None or task.user_id != current_user_id:
            return

        task.status = "running"
        task.progress = 20
        task.started_at = shanghai_now()
        db.commit()

        payload = task.payload or {}
        usage_reservation_id = payload.get("usage_reservation_id")
        reference_images = payload.get("reference_images")
        refs = reference_images if isinstance(reference_images, list) else []
        image_client = _image_client_for_model(model_config, fallback_client or OpenAICompatibleImageClient())
        try:
            if model_config.provider == "runninghub-ai-app":
                for image_ref in refs:
                    if isinstance(image_ref, str):
                        RunningHubImageClient._resolve_local_image_path(image_ref, owner_user_id=current_user_id)
                result = image_client.generate_image(
                    model_config=model_config,
                    api_key=api_key,
                    prompt=str(payload.get("prompt") or ""),
                    reference_images=[str(item) for item in refs],
                    owner_user_id=current_user_id,
                    aspect_ratio=str(payload.get("aspect_ratio") or "auto"),
                )
            else:
                result = image_client.generate_image(
                    model_config=model_config,
                    api_key=api_key,
                    prompt=str(payload.get("prompt") or ""),
                    reference_images=[str(item) for item in refs] or None,
                    aspect_ratio=str(payload.get("aspect_ratio") or "auto"),
                )
        except Exception as exc:
            error_code, public_error = _public_image_generation_error(exc)
            if isinstance(usage_reservation_id, int):
                UsageQuotaService(db).refund(
                    usage_reservation_id,
                    failure_reason=public_error,
                )
            task.status = "failed"
            task.progress = 100
            task.finished_at = shanghai_now()
            task.payload = {
                **(task.payload or {}),
                "error_code": error_code,
                "error": public_error,
                "provider": model_config.provider,
            }
            db.commit()
            return

        response_data: dict[str, Any] = {"url": result.get("url") or "", "raw": result.get("raw")}
        if bool(payload.get("save_to_assets", True)):
            try:
                asset = _create_generated_image_asset(
                    db=db,
                    user_id=current_user_id,
                    prompt=str(payload.get("prompt") or ""),
                    model_config=model_config,
                    params={
                        "provider": model_config.provider,
                        "reference_images": refs,
                        "aspect_ratio": str(payload.get("aspect_ratio") or "auto"),
                        "raw": result.get("raw"),
                        "source_url": result.get("url"),
                    },
                    source_url=result.get("url") or "",
                )
            except ValueError as exc:
                redacted_error = _redact_sensitive_text(str(exc), [api_key])
                if isinstance(usage_reservation_id, int):
                    UsageQuotaService(db).refund(usage_reservation_id, failure_reason=redacted_error)
                task.status = "failed"
                task.progress = 100
                task.finished_at = shanghai_now()
                task.payload = {**(task.payload or {}), "error": redacted_error}
                db.commit()
                return
            response_data["asset"] = _serialize_generated_asset(asset)
            task.payload = {**(task.payload or {}), "result": response_data, "asset_id": asset.id}
        else:
            task.payload = {**(task.payload or {}), "result": response_data}
        if isinstance(usage_reservation_id, int):
            UsageQuotaService(db).commit(usage_reservation_id)
        task.status = "completed"
        task.progress = 100
        task.finished_at = shanghai_now()
        db.commit()
    finally:
        try:
            task = db.get(Task, task_id)
            payload = task.payload if task is not None and isinstance(task.payload, dict) else {}
            lease_ids = payload.get("concurrency_lease_ids") if isinstance(payload, dict) else None
            if isinstance(lease_ids, list):
                for lease_id in lease_ids:
                    if isinstance(lease_id, int):
                        BetaConcurrencyService(db).release(lease_id, reason="async image task finished")
        finally:
            db.close()


@router.post("/rewrite-note")
def rewrite_note(
    payload: RewriteNoteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    draft = db.get(AiDraft, payload.draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    model_config, api_key = _text_model_context(db, current_user)
    usage_reservation = _reserve_usage(
        db=db,
        current_user=current_user,
        feature_key="ai.rewrite_note",
        idempotency_key=_quota_idempotency_key(request, f"ai.rewrite_note:{current_user.id}:{draft.id}:{payload.instruction}"),
        request_summary={"draft_id": draft.id, "instruction_length": len(payload.instruction), "body_length": len(draft.body)},
        model_config_id=model_config.id,
        provider=model_config.provider,
    )
    task, rewritten_body = _recorded_text_task(
        db=db,
        current_user=current_user,
        platform=draft.platform,
        task_type="ai_rewrite",
        payload={"draft_id": draft.id, "model_config_id": model_config.id, "instruction": payload.instruction},
        action=lambda: text_ai_client.rewrite_note(
            model_config=model_config,
            api_key=api_key,
            title=draft.title,
            body=draft.body,
            instruction=payload.instruction,
        ),
        usage_reservation_id=usage_reservation.id,
    )
    normalized = normalize_xhs_generated_content(draft.title, rewritten_body, draft.tags or [])
    candidate = {
        **_serialize_draft(draft),
        "title": normalized.title,
        "body": normalized.body,
        "tags": normalized.tags,
    }
    task.payload = {
        **(task.payload or {}),
        "source_draft_id": draft.id,
        "preview_only": True,
        "result": {
            "title": normalized.title,
            "body": normalized.body,
            "tags": normalized.tags,
        },
        "result_length": len(normalized.body),
        "normalization_warnings": normalized.warnings,
    }
    db.commit()
    return candidate


@router.post("/generate-note")
def generate_note(
    payload: GenerateNoteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
    usage_reservation = _reserve_usage(
        db=db,
        current_user=current_user,
        feature_key="ai.generate_note",
        idempotency_key=_quota_idempotency_key(request, f"ai.generate_note:{current_user.id}:{payload.platform}:{payload.topic}:{payload.instruction}"),
        request_summary={
            "topic_length": len(payload.topic),
            "reference_length": len(payload.reference),
            "instruction_length": len(payload.instruction),
        },
        model_config_id=model_config.id,
        provider=model_config.provider,
    )
    task, result = _recorded_text_task(
        db=db,
        current_user=current_user,
        platform=payload.platform,
        task_type="ai_generate_note",
        payload={"model_config_id": model_config.id, "topic": payload.topic},
        action=lambda: text_ai_client.generate_note(
            model_config=model_config,
            api_key=api_key,
            topic=payload.topic,
            reference=payload.reference,
            instruction=payload.instruction,
        ),
        usage_reservation_id=usage_reservation.id,
    )
    draft = AiDraft(
        user_id=current_user.id,
        platform=payload.platform,
        title=result.get("title") or payload.topic,
        body=result.get("body") or "",
    )
    db.add(draft)
    db.flush()
    task.payload = {**(task.payload or {}), "result_draft_id": draft.id}
    db.commit()
    db.refresh(draft)
    return _serialize_draft(draft)


@router.post("/generate-title")
def generate_title(
    payload: GenerateTitleRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
    usage_reservation = _reserve_usage(
        db=db,
        current_user=current_user,
        feature_key="ai.generate_title",
        idempotency_key=_quota_idempotency_key(request, f"ai.generate_title:{current_user.id}:{payload.title}:{payload.body}:{payload.count}"),
        request_summary={"title_length": len(payload.title), "body_length": len(payload.body), "count": payload.count},
        model_config_id=model_config.id,
        provider=model_config.provider,
    )
    task, items = _recorded_text_task(
        db=db,
        current_user=current_user,
        platform="xhs",
        task_type="ai_generate_title",
        payload={"model_config_id": model_config.id, "count": payload.count},
        action=lambda: text_ai_client.generate_titles(
            model_config=model_config,
            api_key=api_key,
            title=payload.title,
            body=payload.body,
            count=payload.count,
        ),
        usage_reservation_id=usage_reservation.id,
    )
    task.payload = {**(task.payload or {}), "result_count": len(items)}
    db.commit()
    return {"items": items}


@router.post("/generate-tags")
def generate_tags(
    payload: GenerateTagsRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
    usage_reservation = _reserve_usage(
        db=db,
        current_user=current_user,
        feature_key="ai.generate_tags",
        idempotency_key=_quota_idempotency_key(request, f"ai.generate_tags:{current_user.id}:{payload.title}:{payload.body}:{payload.count}"),
        request_summary={"title_length": len(payload.title), "body_length": len(payload.body), "count": payload.count},
        model_config_id=model_config.id,
        provider=model_config.provider,
    )
    task, items = _recorded_text_task(
        db=db,
        current_user=current_user,
        platform="xhs",
        task_type="ai_generate_tags",
        payload={"model_config_id": model_config.id, "count": payload.count},
        action=lambda: text_ai_client.generate_tags(
            model_config=model_config,
            api_key=api_key,
            title=payload.title,
            body=payload.body,
            count=payload.count,
        ),
        usage_reservation_id=usage_reservation.id,
    )
    task.payload = {**(task.payload or {}), "result_count": len(items)}
    db.commit()
    return {"items": items}


@router.post("/polish-text")
def polish_text(
    payload: PolishTextRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
    usage_reservation = _reserve_usage(
        db=db,
        current_user=current_user,
        feature_key="ai.polish_text",
        idempotency_key=_quota_idempotency_key(request, f"ai.polish_text:{current_user.id}:{payload.text}:{payload.instruction}"),
        request_summary={"text_length": len(payload.text), "instruction_length": len(payload.instruction)},
        model_config_id=model_config.id,
        provider=model_config.provider,
    )
    task, text = _recorded_text_task(
        db=db,
        current_user=current_user,
        platform="xhs",
        task_type="ai_polish_text",
        payload={"model_config_id": model_config.id, "instruction": payload.instruction},
        action=lambda: text_ai_client.polish_text(
            model_config=model_config,
            api_key=api_key,
            text=payload.text,
            instruction=payload.instruction,
        ),
        usage_reservation_id=usage_reservation.id,
    )
    task.payload = {**(task.payload or {}), "result_length": len(text)}
    db.commit()
    return {"text": text}


@router.get("/images/assets")
def generated_image_assets(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assets = db.scalars(
        select(AiGeneratedAsset)
        .where(AiGeneratedAsset.user_id == current_user.id)
        .order_by(AiGeneratedAsset.created_at.desc(), AiGeneratedAsset.id.desc())
    ).all()
    return paginated([_serialize_generated_asset(asset) for asset in assets], page, page_size)


@router.delete("/images/assets/{asset_id}")
def delete_generated_image_asset(
    asset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.get(AiGeneratedAsset, asset_id)
    if asset is None or asset.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    db.delete(asset)
    db.commit()
    return {"id": asset_id, "status": "deleted"}


@router.post("/images/generate-cover")
def generate_cover(
    payload: GenerateCoverRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    if payload.draft_id is not None:
        draft = db.get(AiDraft, payload.draft_id)
        if draft is None or draft.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    model_config, api_key = _image_model_context(db, current_user, capability="image_generation")
    image_client = _image_client_for_model(model_config, image_ai_client)
    feature_key = "ai.image_generate_cover"
    idempotency_key = _quota_idempotency_key(request, f"ai.image_generate_cover:{current_user.id}:{payload.draft_id}:{payload.prompt}:{payload.size}:{payload.style}")
    concurrency_guard = _acquire_image_generation_guard(
        db=db,
        current_user=current_user,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
    )
    try:
        usage_reservation = _reserve_usage(
            db=db,
            current_user=current_user,
            feature_key=feature_key,
            idempotency_key=idempotency_key,
            request_summary={"prompt_length": len(payload.prompt), "size": payload.size, "style": payload.style, "draft_id": payload.draft_id},
            model_config_id=model_config.id,
            provider=model_config.provider,
        )
    except Exception:
        concurrency_guard.release(reason="image cover quota reservation failed")
        raise
    try:
        task, result = _recorded_image_task(
            db=db,
            current_user=current_user,
            task_type="ai_image_generate_cover",
            payload={"model_config_id": model_config.id, "prompt": payload.prompt, "size": payload.size, "style": payload.style},
            action=lambda: image_client.generate_cover(
                model_config=model_config,
                api_key=api_key,
                prompt=payload.prompt,
                size=payload.size,
                style=payload.style,
            ),
            sensitive_values=[api_key],
            usage_reservation_id=usage_reservation.id,
            provider=model_config.provider,
        )
        try:
            asset = _create_generated_image_asset(
                db=db,
                user_id=current_user.id,
                draft_id=payload.draft_id,
                prompt=payload.prompt,
                model_config=model_config,
                params={
                    "provider": model_config.provider,
                    "size": payload.size,
                    "style": payload.style,
                    "raw": result.get("raw"),
                    "source_url": result.get("url"),
                },
                source_url=result.get("url") or "",
            )
        except ValueError as exc:
            redacted_error = _redact_sensitive_text(str(exc), [api_key])
            task.status = "failed"
            task.progress = 100
            task.payload = {**(task.payload or {}), "error": redacted_error}
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=redacted_error) from exc
        task.payload = {**(task.payload or {}), "asset_id": asset.id}
        db.commit()
        db.refresh(asset)
        return _serialize_generated_asset(asset)
    finally:
        concurrency_guard.release(reason="image cover finished")


@router.post("/images/generate")
def generate_image(
    payload: GenerateImageRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    model_config, api_key = _image_model_context(db, current_user, capability="image_generation")
    image_client = _image_client_for_model(model_config, image_ai_client)
    feature_key = "ai.image_generate"
    idempotency_key = _quota_idempotency_key(request, f"ai.image_generate:{current_user.id}:{payload.prompt}:{payload.reference_images}:{payload.aspect_ratio}")
    concurrency_guard = _acquire_image_generation_guard(
        db=db,
        current_user=current_user,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
    )
    try:
        usage_reservation = _reserve_usage(
            db=db,
            current_user=current_user,
            feature_key=feature_key,
            idempotency_key=idempotency_key,
            request_summary={
                "prompt_length": len(payload.prompt),
                "reference_image_count": len(payload.reference_images or []),
                "aspect_ratio": payload.aspect_ratio,
                "save_to_assets": payload.save_to_assets,
            },
            model_config_id=model_config.id,
            provider=model_config.provider,
        )
    except Exception:
        concurrency_guard.release(reason="image generation quota reservation failed")
        raise

    def run_generate_image():
        reference_images = payload.reference_images or None
        if model_config.provider == "runninghub-ai-app":
            from backend.app.services.ai_service import RunningHubImageClient as RealRunningHubImageClient

            for image_ref in reference_images or []:
                RealRunningHubImageClient._resolve_local_image_path(image_ref, owner_user_id=current_user.id)
            return image_client.generate_image(
                model_config=model_config,
                api_key=api_key,
                prompt=payload.prompt,
                reference_images=reference_images,
                owner_user_id=current_user.id,
                aspect_ratio=payload.aspect_ratio,
            )
        return image_client.generate_image(
            model_config=model_config,
            api_key=api_key,
            prompt=payload.prompt,
            reference_images=reference_images,
            aspect_ratio=payload.aspect_ratio,
        )

    try:
        task, result = _recorded_image_task(
            db=db,
            current_user=current_user,
            task_type="ai_image_generate",
            payload={"model_config_id": model_config.id, "prompt": payload.prompt, "reference_images": payload.reference_images, "aspect_ratio": payload.aspect_ratio},
            action=run_generate_image,
            sensitive_values=[api_key],
            usage_reservation_id=usage_reservation.id,
            provider=model_config.provider,
        )
        response_data: dict = {"url": result.get("url") or "", "raw": result.get("raw")}
        if payload.save_to_assets:
            try:
                asset = _create_generated_image_asset(
                    db=db,
                    user_id=current_user.id,
                    prompt=payload.prompt,
                    model_config=model_config,
                    params={
                        "provider": model_config.provider,
                        "reference_images": payload.reference_images,
                        "aspect_ratio": payload.aspect_ratio,
                        "raw": result.get("raw"),
                        "source_url": result.get("url"),
                    },
                    source_url=result.get("url") or "",
                )
            except ValueError as exc:
                redacted_error = _redact_sensitive_text(str(exc), [api_key])
                task.status = "failed"
                task.progress = 100
                task.payload = {**(task.payload or {}), "error": redacted_error}
                db.commit()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=redacted_error) from exc
            task.payload = {**(task.payload or {}), "asset_id": asset.id}
            db.commit()
            db.refresh(asset)
            response_data["asset"] = _serialize_generated_asset(asset)
        else:
            db.commit()
        return response_data
    finally:
        concurrency_guard.release(reason="image generation finished")


@router.post("/images/generate-async")
def generate_image_async(
    payload: GenerateImageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    model_config, api_key = _image_model_context(db, current_user, capability="image_generation")
    reference_images = payload.reference_images or []
    if model_config.provider == "runninghub-ai-app":
        for image_ref in reference_images:
            RunningHubImageClient._resolve_local_image_path(image_ref, owner_user_id=current_user.id)

    feature_key = "ai.image_generate_async"
    idempotency_key = _quota_idempotency_key(request, f"ai.image_generate_async:{current_user.id}:{payload.prompt}:{reference_images}:{payload.aspect_ratio}")
    concurrency_guard = _acquire_image_generation_guard(
        db=db,
        current_user=current_user,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
    )
    try:
        usage_reservation = _reserve_usage(
            db=db,
            current_user=current_user,
            feature_key=feature_key,
            idempotency_key=idempotency_key,
            request_summary={
                "prompt_length": len(payload.prompt),
                "reference_image_count": len(reference_images),
                "aspect_ratio": payload.aspect_ratio,
                "save_to_assets": payload.save_to_assets,
            },
            model_config_id=model_config.id,
            provider=model_config.provider,
        )
    except Exception:
        concurrency_guard.release(reason="async image quota reservation failed")
        raise

    try:
        task = Task(
            user_id=current_user.id,
            platform="xhs",
            task_type="ai_image_generate",
            status="pending",
            progress=0,
            payload={
                "model_config_id": model_config.id,
                "prompt": payload.prompt,
                "reference_images": reference_images,
                "save_to_assets": payload.save_to_assets,
                "aspect_ratio": payload.aspect_ratio,
                "usage_reservation_id": usage_reservation.id,
                "feature_key": feature_key,
                "usage_bucket": CREDITS_BUCKET,
                "idempotency_key": usage_reservation.idempotency_key,
                "concurrency_lease_ids": concurrency_guard.lease_ids,
            },
        )
        db.add(task)
        db.commit()
        db.refresh(task)
    except Exception:
        concurrency_guard.release(reason="async image task creation failed")
        raise
    fallback_client = image_ai_client if model_config.provider != "runninghub-ai-app" else None
    background_tasks.add_task(_run_async_image_generate_task, task.id, current_user.id, model_config.id, api_key, fallback_client)
    return {"task_id": task.id, "status": task.status, "progress": task.progress, "payload": task.payload or {}}


@router.post("/images/describe")
def describe_image(
    payload: DescribeImageRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    model_config, api_key = _image_model_context(db, current_user, capability="vision")
    image_client = _image_client_for_model(model_config, image_ai_client)
    usage_reservation = _reserve_usage(
        db=db,
        current_user=current_user,
        feature_key="ai.describe_image",
        idempotency_key=_quota_idempotency_key(request, f"ai.describe_image:{current_user.id}:{payload.image_url}:{payload.instruction}"),
        request_summary={"image_url_length": len(payload.image_url), "instruction_length": len(payload.instruction)},
        model_config_id=model_config.id,
        provider=model_config.provider,
    )
    task, text = _recorded_image_task(
        db=db,
        current_user=current_user,
        task_type="ai_image_describe",
        payload={"model_config_id": model_config.id, "image_url": payload.image_url, "instruction": payload.instruction},
        action=lambda: image_client.describe_image(
            model_config=model_config,
            api_key=api_key,
            image_url=payload.image_url,
            instruction=payload.instruction,
        ),
        sensitive_values=[api_key],
        usage_reservation_id=usage_reservation.id,
    )
    task.payload = {**(task.payload or {}), "result_length": len(text)}
    db.commit()
    return {"text": text}

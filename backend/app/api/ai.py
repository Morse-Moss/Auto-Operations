from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal, get_db
from backend.app.core.deps import get_current_user
from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import AiDraft, AiGeneratedAsset, ModelConfig, Task, User
from backend.app.schemas.common import paginated
from backend.app.services.ai_service import ImageAiClient, OpenAICompatibleImageClient, OpenAICompatibleTextClient, RunningHubImageClient, TextAiClient

router = APIRouter(prefix="/ai", tags=["ai"])


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
        "title": draft.title,
        "body": draft.body,
        "source_note_id": draft.source_note_id,
        "created_at": draft.created_at.isoformat(),
    }


def _get_default_text_model(db: Session, current_user: User) -> ModelConfig:
    config = db.scalars(
        select(ModelConfig).where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.model_type == "text",
            ModelConfig.is_default.is_(True),
        )
    ).first()
    if config is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default text model is not configured")
    return config


def _get_default_image_model(db: Session, current_user: User) -> ModelConfig:
    config = db.scalars(
        select(ModelConfig).where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.model_type == "image",
            ModelConfig.is_default.is_(True),
        )
    ).first()
    if config is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default image model is not configured")
    return config


def _text_model_context(db: Session, current_user: User) -> tuple[ModelConfig, str]:
    model_config = _get_default_text_model(db, current_user)
    api_key = decrypt_text(model_config.encrypted_api_key) if model_config.encrypted_api_key else ""
    return model_config, api_key


def _image_model_context(db: Session, current_user: User) -> tuple[ModelConfig, str]:
    model_config = _get_default_image_model(db, current_user)
    api_key = decrypt_text(model_config.encrypted_api_key) if model_config.encrypted_api_key else ""
    return model_config, api_key


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


def _recorded_text_task(
    *,
    db: Session,
    current_user: User,
    platform: str,
    task_type: str,
    payload: dict[str, Any],
    action: Callable[[], Any],
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
        task.status = "failed"
        task.progress = 100
        task.payload = {**(task.payload or {}), "error": str(exc)}
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        task.status = "failed"
        task.progress = 100
        task.payload = {**(task.payload or {}), "error": str(exc)}
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI text generation failed: {exc}") from exc

    task.status = "completed"
    task.progress = 100
    return task, result


def _recorded_image_task(
    *,
    db: Session,
    current_user: User,
    task_type: str,
    payload: dict[str, Any],
    action: Callable[[], Any],
    sensitive_values: list[str] | None = None,
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
    except ValueError as exc:
        redacted_error = _redact_sensitive_text(str(exc), sensitive_values)
        task.status = "failed"
        task.progress = 100
        task.payload = {**(task.payload or {}), "error": redacted_error}
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=redacted_error) from exc
    except Exception as exc:
        redacted_error = _redact_sensitive_text(str(exc), sensitive_values)
        task.status = "failed"
        task.progress = 100
        task.payload = {**(task.payload or {}), "error": redacted_error}
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI image generation failed: {redacted_error}") from exc

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
                )
            else:
                result = image_client.generate_image(
                    model_config=model_config,
                    api_key=api_key,
                    prompt=str(payload.get("prompt") or ""),
                    reference_images=[str(item) for item in refs] or None,
                )
        except ValueError as exc:
            redacted_error = _redact_sensitive_text(str(exc), [api_key])
            task.status = "failed"
            task.progress = 100
            task.finished_at = shanghai_now()
            task.payload = {**(task.payload or {}), "error": redacted_error}
            db.commit()
            return
        except Exception as exc:
            redacted_error = _redact_sensitive_text(str(exc), [api_key])
            task.status = "failed"
            task.progress = 100
            task.finished_at = shanghai_now()
            task.payload = {**(task.payload or {}), "error": f"AI image generation failed: {redacted_error}"}
            db.commit()
            return

        response_data: dict[str, Any] = {"url": result.get("url") or "", "raw": result.get("raw")}
        if bool(payload.get("save_to_assets", True)):
            asset = AiGeneratedAsset(
                user_id=current_user_id,
                prompt=str(payload.get("prompt") or ""),
                model_name=model_config.model_name,
                params={
                    "provider": model_config.provider,
                    "reference_images": refs,
                    "raw": result.get("raw"),
                },
                file_path=result.get("url") or "",
            )
            db.add(asset)
            db.flush()
            response_data["asset"] = _serialize_generated_asset(asset)
            task.payload = {**(task.payload or {}), "result": response_data, "asset_id": asset.id}
        else:
            task.payload = {**(task.payload or {}), "result": response_data}
        task.status = "completed"
        task.progress = 100
        task.finished_at = shanghai_now()
        db.commit()
    finally:
        db.close()


@router.post("/rewrite-note")
def rewrite_note(
    payload: RewriteNoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    draft = db.get(AiDraft, payload.draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    model_config, api_key = _text_model_context(db, current_user)
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
    )
    draft.body = rewritten_body
    task.payload = {**(task.payload or {}), "result_draft_id": draft.id, "result_length": len(rewritten_body)}
    db.commit()
    db.refresh(draft)
    return _serialize_draft(draft)


@router.post("/generate-note")
def generate_note(
    payload: GenerateNoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
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
    )
    task.payload = {**(task.payload or {}), "result_count": len(items)}
    db.commit()
    return {"items": items}


@router.post("/generate-tags")
def generate_tags(
    payload: GenerateTagsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
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
    )
    task.payload = {**(task.payload or {}), "result_count": len(items)}
    db.commit()
    return {"items": items}


@router.post("/polish-text")
def polish_text(
    payload: PolishTextRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context(db, current_user)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    if payload.draft_id is not None:
        draft = db.get(AiDraft, payload.draft_id)
        if draft is None or draft.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    model_config, api_key = _image_model_context(db, current_user)
    image_client = _image_client_for_model(model_config, image_ai_client)
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
    )
    asset = AiGeneratedAsset(
        user_id=current_user.id,
        draft_id=payload.draft_id,
        prompt=payload.prompt,
        model_name=model_config.model_name,
        params={"provider": model_config.provider, "size": payload.size, "style": payload.style, "raw": result.get("raw")},
        file_path=result.get("url") or "",
    )
    db.add(asset)
    db.flush()
    task.payload = {**(task.payload or {}), "asset_id": asset.id}
    db.commit()
    db.refresh(asset)
    return _serialize_generated_asset(asset)


@router.post("/images/generate")
def generate_image(
    payload: GenerateImageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    model_config, api_key = _image_model_context(db, current_user)
    image_client = _image_client_for_model(model_config, image_ai_client)

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
            )
        return image_client.generate_image(
            model_config=model_config,
            api_key=api_key,
            prompt=payload.prompt,
            reference_images=reference_images,
        )

    task, result = _recorded_image_task(
        db=db,
        current_user=current_user,
        task_type="ai_image_generate",
        payload={"model_config_id": model_config.id, "prompt": payload.prompt, "reference_images": payload.reference_images},
        action=run_generate_image,
        sensitive_values=[api_key],
    )
    response_data: dict = {"url": result.get("url") or "", "raw": result.get("raw")}
    if payload.save_to_assets:
        asset = AiGeneratedAsset(
            user_id=current_user.id,
            prompt=payload.prompt,
            model_name=model_config.model_name,
            params={
                "provider": model_config.provider,
                "reference_images": payload.reference_images,
                "raw": result.get("raw"),
            },
            file_path=result.get("url") or "",
        )
        db.add(asset)
        db.flush()
        task.payload = {**(task.payload or {}), "asset_id": asset.id}
        db.commit()
        db.refresh(asset)
        response_data["asset"] = _serialize_generated_asset(asset)
    else:
        db.commit()
    return response_data


@router.post("/images/generate-async")
def generate_image_async(
    payload: GenerateImageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    model_config, api_key = _image_model_context(db, current_user)
    reference_images = payload.reference_images or []
    if model_config.provider == "runninghub-ai-app":
        for image_ref in reference_images:
            RunningHubImageClient._resolve_local_image_path(image_ref, owner_user_id=current_user.id)

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
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    fallback_client = image_ai_client if model_config.provider != "runninghub-ai-app" else None
    background_tasks.add_task(_run_async_image_generate_task, task.id, current_user.id, model_config.id, api_key, fallback_client)
    return {"task_id": task.id, "status": task.status, "progress": task.progress, "payload": task.payload or {}}


@router.post("/images/describe")
def describe_image(
    payload: DescribeImageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_ai_client: ImageAiClient = Depends(get_image_ai_client),
):
    model_config, api_key = _image_model_context(db, current_user)
    image_client = _image_client_for_model(model_config, image_ai_client)
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
    )
    task.payload = {**(task.payload or {}), "result_length": len(text)}
    db.commit()
    return {"text": text}

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import requests

from backend.app.models import ModelConfig


class TextAiClient(Protocol):
    def rewrite_note(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        title: str,
        body: str,
        instruction: str,
    ) -> str:
        ...

    def generate_note(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        topic: str,
        reference: str,
        instruction: str,
    ) -> dict[str, str]:
        ...

    def generate_titles(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        title: str,
        body: str,
        count: int,
    ) -> list[str]:
        ...

    def generate_tags(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        title: str,
        body: str,
        count: int,
    ) -> list[str]:
        ...

    def polish_text(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        text: str,
        instruction: str,
    ) -> str:
        ...

    def complete_json_prompt(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        ...


class ImageAiClient(Protocol):
    def generate_cover(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        prompt: str,
        size: str,
        style: str,
    ) -> dict[str, Any]:
        ...

    def generate_image(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        prompt: str,
        reference_images: list[str] | None = None,
    ) -> dict[str, Any]:
        ...

    def describe_image(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        image_url: str,
        instruction: str,
    ) -> str:
        ...


def _candidate_response_encodings(response: requests.Response) -> list[str]:
    encodings: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", response.apparent_encoding, response.encoding):
        normalized = (encoding or "").strip()
        if normalized and normalized.lower() not in {item.lower() for item in encodings}:
            encodings.append(normalized)
    return encodings


def _load_json_response(response: requests.Response) -> Any:
    raw = response.content
    last_error: Exception | None = None
    for encoding in _candidate_response_encodings(response):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc

    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        last_error = exc

    raise ValueError("AI response is not valid JSON") from last_error


class OpenAICompatibleTextClient:
    def _complete(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> str:
        if not model_config.base_url:
            raise ValueError("Text model base_url is required")
        if not model_config.model_name:
            raise ValueError("Text model_name is required")
        if not api_key:
            raise ValueError("Text model api_key is required")

        endpoint = f"{model_config.base_url.rstrip('/')}/chat/completions"
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_config.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = _load_json_response(response)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("AI response missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError("AI response content is empty")
        return content.strip()

    def complete_json_prompt(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        return self._complete(
            model_config=model_config,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )

    def rewrite_note(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        title: str,
        body: str,
        instruction: str,
    ) -> str:
        return self._complete(
            model_config=model_config,
            api_key=api_key,
            system_prompt="你是小红书内容运营编辑，负责在保留事实的前提下改写成自然、可发布的种草笔记。",
            user_prompt=(
                f"改写要求：{instruction or '提升表达、增强小红书语感'}\n\n"
                f"标题：{title}\n\n正文：\n{body}"
            ),
        )

    def generate_note(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        topic: str,
        reference: str,
        instruction: str,
    ) -> dict[str, str]:
        content = self._complete(
            model_config=model_config,
            api_key=api_key,
            system_prompt="你是小红书内容策划，输出可发布的标题和正文。",
            user_prompt=(
                "请生成一篇小红书笔记，格式必须是：\n标题：...\n正文：...\n\n"
                f"选题：{topic}\n参考材料：{reference or '无'}\n要求：{instruction or '自然、有信息密度'}"
            ),
        )
        title = topic
        body = content
        for line in content.splitlines():
            if line.startswith("标题："):
                title = line.replace("标题：", "", 1).strip() or title
                break
        if "正文：" in content:
            body = content.split("正文：", 1)[1].strip()
        return {"title": title, "body": body}

    def generate_titles(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        title: str,
        body: str,
        count: int,
    ) -> list[str]:
        content = self._complete(
            model_config=model_config,
            api_key=api_key,
            system_prompt="你是小红书标题优化专家。",
            user_prompt=f"请给出 {count} 个小红书标题，每行一个。\n原标题：{title}\n正文：{body}",
        )
        return [line.strip(" -0123456789.、") for line in content.splitlines() if line.strip()][:count]

    def generate_tags(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        title: str,
        body: str,
        count: int,
    ) -> list[str]:
        content = self._complete(
            model_config=model_config,
            api_key=api_key,
            system_prompt="你是小红书 SEO 和话题标签专家。",
            user_prompt=f"请给出 {count} 个小红书话题标签，只输出标签，用逗号或换行分隔。\n标题：{title}\n正文：{body}",
        )
        separators = content.replace("，", ",").replace("\n", ",").split(",")
        return [item.strip().lstrip("#") for item in separators if item.strip()][:count]

    def polish_text(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        text: str,
        instruction: str,
    ) -> str:
        return self._complete(
            model_config=model_config,
            api_key=api_key,
            system_prompt="你是小红书正文润色编辑。",
            user_prompt=f"润色要求：{instruction or '更自然、清晰、有种草感'}\n\n原文：\n{text}",
        )


RUNNINGHUB_TEXT_TO_IMAGE_WEBAPP_ID = "2046760522573418497"
RUNNINGHUB_IMAGE_TO_IMAGE_WEBAPP_ID = "2046794946094571522"
RUNNINGHUB_DEFAULT_BASE_URL = "https://www.runninghub.cn"
RUNNINGHUB_DEFAULT_ASPECT_RATIO = "3:4"
RUNNINGHUB_DEFAULT_RESOLUTION = "1k"
RUNNINGHUB_TEXT_PROMPT_NODE_ID = "136"
RUNNINGHUB_IMAGE_PROMPT_NODE_ID = "4"
RUNNINGHUB_IMAGE_INPUT_NODES = ["3", "2"]


class RunningHubImageClient:
    def __init__(self, *, session: Any | None = None, poll_interval_seconds: float = 2.0, max_poll_attempts: int = 90) -> None:
        self.session = session or requests
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max_poll_attempts

    def _validate(self, *, model_config: ModelConfig, api_key: str) -> str:
        if not api_key:
            raise ValueError("RunningHub API Key 未配置")
        return (model_config.base_url or RUNNINGHUB_DEFAULT_BASE_URL).rstrip("/")

    @staticmethod
    def build_text_to_image_node_info_list(prompt: str) -> list[dict[str, Any]]:
        return [
            {"nodeId": RUNNINGHUB_TEXT_PROMPT_NODE_ID, "fieldName": "prompt", "fieldValue": prompt},
            {"nodeId": RUNNINGHUB_TEXT_PROMPT_NODE_ID, "fieldName": "aspectRatio", "fieldValue": RUNNINGHUB_DEFAULT_ASPECT_RATIO},
        ]

    @staticmethod
    def build_image_to_image_node_info_list(*, prompt: str, uploaded_filenames: list[str]) -> list[dict[str, Any]]:
        max_images = len(RUNNINGHUB_IMAGE_INPUT_NODES)
        if not uploaded_filenames:
            raise ValueError("参考图生图至少需要 1 张参考图")
        if len(uploaded_filenames) > max_images:
            raise ValueError(f"当前 RunningHub 图生图工作流最多支持 {max_images} 张参考图")

        node_info: list[dict[str, Any]] = []
        for node_id, filename in zip(RUNNINGHUB_IMAGE_INPUT_NODES, uploaded_filenames):
            node_info.append({"nodeId": node_id, "fieldName": "image", "fieldValue": filename})
        node_info.extend([
            {"nodeId": RUNNINGHUB_IMAGE_PROMPT_NODE_ID, "fieldName": "prompt", "fieldValue": prompt},
            {"nodeId": RUNNINGHUB_IMAGE_PROMPT_NODE_ID, "fieldName": "aspectRatio", "fieldValue": RUNNINGHUB_DEFAULT_ASPECT_RATIO},
            {"nodeId": RUNNINGHUB_IMAGE_PROMPT_NODE_ID, "fieldName": "resolution", "fieldValue": RUNNINGHUB_DEFAULT_RESOLUTION},
        ])
        return node_info

    def generate_cover(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        prompt: str,
        size: str,
        style: str,
    ) -> dict[str, Any]:
        return self.generate_image(
            model_config=model_config,
            api_key=api_key,
            prompt=f"{prompt}\nStyle: {style or 'clean XHS cover'}",
        )

    def generate_image(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        prompt: str,
        reference_images: list[str] | None = None,
        owner_user_id: int | None = None,
    ) -> dict[str, Any]:
        base_url = self._validate(model_config=model_config, api_key=api_key)
        refs = [item for item in (reference_images or []) if str(item).strip()]
        if refs:
            max_images = len(RUNNINGHUB_IMAGE_INPUT_NODES)
            if len(refs) > max_images:
                raise ValueError(f"当前 RunningHub 图生图工作流最多支持 {max_images} 张参考图")
            filenames = [self._upload_reference_image(base_url=base_url, api_key=api_key, image_ref=ref, owner_user_id=owner_user_id) for ref in refs]
            webapp_id = RUNNINGHUB_IMAGE_TO_IMAGE_WEBAPP_ID
            node_info = self.build_image_to_image_node_info_list(prompt=prompt, uploaded_filenames=filenames)
        else:
            webapp_id = RUNNINGHUB_TEXT_TO_IMAGE_WEBAPP_ID
            node_info = self.build_text_to_image_node_info_list(prompt)

        task_payload = self._run_ai_app(base_url=base_url, api_key=api_key, webapp_id=webapp_id, node_info_list=node_info)
        task_id = ((task_payload.get("data") or {}).get("taskId") if isinstance(task_payload, dict) else None)
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("RunningHub response missing taskId")
        status_value = self._wait_for_success(base_url=base_url, api_key=api_key, task_id=task_id)
        outputs_payload = self._get_outputs(base_url=base_url, api_key=api_key, task_id=task_id)
        file_url = self._first_output_url(outputs_payload)
        return {
            "url": file_url,
            "raw": {
                "provider": "runninghub-ai-app",
                "webapp_id": webapp_id,
                "task_id": task_id,
                "status": status_value,
                "outputs": outputs_payload.get("data"),
            },
        }

    def describe_image(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        image_url: str,
        instruction: str,
    ) -> str:
        raise ValueError("RunningHub 图片上游当前不支持图片描述，请配置支持视觉理解的 OpenAI-compatible 图片模型。")

    def _headers(self, api_key: str, *, content_type: str | None = "application/json") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {api_key}", "Host": "www.runninghub.cn"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _upload_reference_image(self, *, base_url: str, api_key: str, image_ref: str, owner_user_id: int | None = None) -> str:
        path = self._resolve_local_image_path(image_ref, owner_user_id=owner_user_id)
        endpoint = f"{base_url}/openapi/v2/media/upload/binary"
        with path.open("rb") as file_obj:
            response = self.session.post(
                endpoint,
                headers=self._headers(api_key, content_type=None),
                files={"file": (path.name, file_obj, self._mime_for_path(path))},
                timeout=120,
            )
        response.raise_for_status()
        payload = _load_json_response(response)
        data = payload.get("data") if isinstance(payload, dict) else None
        filename = data.get("filename") if isinstance(data, dict) else None
        if isinstance(filename, str) and filename:
            return filename
        if not isinstance(payload, dict) or payload.get("code") not in {0, 200}:
            message = self._message_from_payload(payload)
            raise ValueError(f"RunningHub 参考图上传失败: {message}")
        raise ValueError("RunningHub upload response missing filename")

    @staticmethod
    def _resolve_local_image_path(image_ref: str, *, owner_user_id: int | None = None) -> Path:
        from backend.app.core.config import get_settings

        media_dir = (Path(get_settings().storage_dir) / "media").resolve()
        ref = image_ref.strip()
        if ref.startswith("/api/files/media/"):
            candidate = media_dir / ref.removeprefix("/api/files/media/")
        else:
            ref_path = Path(ref)
            candidate = ref_path if ref_path.is_absolute() else media_dir / ref_path

        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(media_dir)
        except ValueError as exc:
            raise ValueError("参考图必须来自媒体资产目录") from exc

        if owner_user_id is not None and not resolved.name.startswith(f"xhs-upload-u{owner_user_id}-"):
            raise ValueError("参考图文件不存在或无权访问")
        if not resolved.is_file():
            if owner_user_id is not None:
                raise ValueError("参考图文件不存在或无权访问")
            raise ValueError(f"参考图文件不存在: {image_ref}")
        return resolved

    @staticmethod
    def _mime_for_path(path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "application/octet-stream")

    def _run_ai_app(self, *, base_url: str, api_key: str, webapp_id: str, node_info_list: list[dict[str, Any]]) -> dict[str, Any]:
        # RunningHub requires apiKey both in the JSON body and Authorization header.
        # This payload contains credentials; never persist/log it or include it in returned raw.
        payload = {"apiKey": api_key, "webappId": webapp_id, "nodeInfoList": node_info_list}
        response = self.session.post(
            f"{base_url}/task/openapi/ai-app/run",
            headers=self._headers(api_key),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        result = _load_json_response(response)
        if not isinstance(result, dict) or result.get("code") != 0:
            raise ValueError(f"RunningHub 任务启动失败: {self._message_from_payload(result)}")
        return result

    def _wait_for_success(self, *, base_url: str, api_key: str, task_id: str) -> str:
        import time

        for _ in range(self.max_poll_attempts):
            # RunningHub requires apiKey both in the JSON body and Authorization header.
            # This payload contains credentials; never persist/log it or include it in returned raw.
            response = self.session.post(
                f"{base_url}/task/openapi/status",
                headers=self._headers(api_key),
                json={"apiKey": api_key, "taskId": task_id},
                timeout=30,
            )
            response.raise_for_status()
            payload = _load_json_response(response)
            if not isinstance(payload, dict) or payload.get("code") != 0:
                raise ValueError(f"RunningHub 状态查询失败: {self._message_from_payload(payload)}")
            status_value = payload.get("data")
            if status_value == "SUCCESS":
                return "SUCCESS"
            if status_value == "FAILED":
                raise ValueError("RunningHub 生成任务失败")
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError("RunningHub 生成超时")

    def _get_outputs(self, *, base_url: str, api_key: str, task_id: str) -> dict[str, Any]:
        # RunningHub requires apiKey both in the JSON body and Authorization header.
        # This payload contains credentials; never persist/log it or include it in returned raw.
        response = self.session.post(
            f"{base_url}/task/openapi/outputs",
            headers=self._headers(api_key),
            json={"apiKey": api_key, "taskId": task_id},
            timeout=30,
        )
        response.raise_for_status()
        payload = _load_json_response(response)
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise ValueError(f"RunningHub 输出查询失败: {self._message_from_payload(payload)}")
        return payload

    @staticmethod
    def _first_output_url(payload: dict[str, Any]) -> str:
        outputs = payload.get("data")
        if not isinstance(outputs, list):
            raise ValueError("RunningHub output response missing data")
        for item in outputs:
            if isinstance(item, dict) and isinstance(item.get("fileUrl"), str) and item["fileUrl"]:
                return item["fileUrl"]
        raise ValueError("RunningHub output response missing fileUrl")

    @staticmethod
    def _message_from_payload(payload: Any) -> str:
        if isinstance(payload, dict):
            message = payload.get("msg") or payload.get("message") or payload.get("error")
            if message:
                return str(message)
        return "unknown error"


class OpenAICompatibleImageClient:
    def _validate(self, *, model_config: ModelConfig, api_key: str) -> None:
        if not model_config.base_url:
            raise ValueError("Image model base_url is required")
        if not model_config.model_name:
            raise ValueError("Image model_name is required")
        if not api_key:
            raise ValueError("Image model api_key is required")

    def generate_cover(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        prompt: str,
        size: str,
        style: str,
    ) -> dict[str, Any]:
        return self.generate_image(
            model_config=model_config, api_key=api_key, prompt=f"{prompt}\nStyle: {style or 'clean XHS cover'}",
        )

    def generate_image(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        prompt: str,
        reference_images: list[str] | None = None,
        owner_user_id: int | None = None,
    ) -> dict[str, Any]:
        self._validate(model_config=model_config, api_key=api_key)
        endpoint = f"{model_config.base_url.rstrip('/')}/images/generations"
        body: dict[str, Any] = {
            "model": model_config.model_name,
            "prompt": prompt,
            "response_format": "url",
        }
        if reference_images:
            resolved = [self._resolve_image_ref(url) for url in reference_images]
            if len(resolved) == 1:
                body["image"] = resolved[0]
            else:
                body["image"] = resolved
                body["sequential_image_generation"] = "disabled"
            body["watermark"] = False
        try:
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=180,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = ""
            try:
                error_payload = _load_json_response(exc.response) if exc.response else {}
                detail = error_payload.get("error", {}).get("message", "") if isinstance(error_payload, dict) else ""
            except Exception:
                pass
            raise ValueError(f"图片生成失败: {detail or exc}") from exc
        payload = _load_json_response(response)
        try:
            item = payload["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Image response missing data[0]") from exc
        image_ref = item.get("url") or item.get("b64_json")
        if not isinstance(image_ref, str) or not image_ref:
            raise ValueError("Image response missing url or b64_json")
        return {"url": image_ref, "raw": payload}

    @staticmethod
    def _resolve_image_ref(url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("/api/files/media/"):
            import base64
            from pathlib import Path
            from backend.app.core.config import get_settings
            file_name = url.split("/")[-1]
            local = Path(get_settings().storage_dir) / "media" / file_name
            if local.is_file():
                raw = local.read_bytes()
                ext = local.suffix.lower().lstrip(".")
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
                return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        return url

    def describe_image(
        self,
        *,
        model_config: ModelConfig,
        api_key: str,
        image_url: str,
        instruction: str,
    ) -> str:
        self._validate(model_config=model_config, api_key=api_key)
        endpoint = f"{model_config.base_url.rstrip('/')}/chat/completions"
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_config.model_name,
                "messages": [
                    {"role": "system", "content": "你是小红书图片分析助手。"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": instruction or "描述这张图片适合的小红书卖点。"},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = _load_json_response(response)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("AI response missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError("AI image description is empty")
        return content.strip()

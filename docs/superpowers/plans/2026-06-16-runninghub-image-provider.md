# RunningHub Image Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RunningHub AI App the default image provider for 图片工坊, automatically routing text-to-image and reference-image generation through the correct RunningHub webapp.

**Architecture:** Add a focused `RunningHubImageClient` behind the existing `ImageAiClient` protocol, then select the client from `ModelConfig.provider`. Keep the existing `/api/ai/images/generate` contract stable; only the backend provider implementation changes, with small UI copy updates so users can configure RunningHub safely.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, requests, React + Vite + Ant Design, pytest/TestClient.

---

## File Structure

- Modify `backend/app/services/ai_service.py`
  - Add RunningHub constants, helper functions, and `RunningHubImageClient`.
  - Keep `OpenAICompatibleImageClient` unchanged except shared helper reuse if necessary.
- Modify `backend/app/api/ai.py`
  - Import `RunningHubImageClient`.
  - Return provider-specific image client from `get_image_ai_client` or route inside endpoint using the default image config.
  - Store provider-specific metadata in `AiGeneratedAsset.params`.
- Modify `backend/app/api/model_configs.py`
  - Make `/model-configs/{id}/test` understand `provider="runninghub-ai-app"` without calling OpenAI image endpoints.
- Modify `frontend/src/pages/models/model-config-page.tsx`
  - Add RunningHub preset behavior for image model forms.
  - Update copy from “all models must be OpenAI-compatible” to provider-aware guidance.
- Modify `frontend/src/pages/platforms/xhs/image-studio-page.tsx`
  - Enforce the current RunningHub reference-image cap in the UI once the default provider is RunningHub, or at minimum improve the error message from backend 422. Do not hard-code the product rule as “2 forever”; phrase it as current workflow capacity.
- Modify `frontend/src/types/index.ts`
  - Allow the known provider string in the type if strict enough; otherwise no change.
- Modify `tests/backend/test_api.py`
  - Add provider selection and RunningHub image-generation tests using fake clients or mocked requests.

Do not commit automatically. The project CLAUDE.md says commits only happen when the user explicitly asks.

---

### Task 1: Add RunningHub request builders and validation tests

**Files:**
- Modify: `backend/app/services/ai_service.py`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Write failing tests for RunningHub nodeInfoList builders**

Add these tests near the existing AI image route tests in `tests/backend/test_api.py`, before `test_ai_image_routes_use_default_model_store_assets_and_enforce_scope`:

```python
def test_runninghub_builds_text_to_image_node_info_list():
    from backend.app.services.ai_service import RunningHubImageClient

    client = RunningHubImageClient()

    node_info = client.build_text_to_image_node_info_list("低卡早餐封面")

    assert node_info == [
        {"nodeId": "136", "fieldName": "prompt", "fieldValue": "低卡早餐封面"},
        {"nodeId": "136", "fieldName": "aspectRatio", "fieldValue": "3:4"},
    ]


def test_runninghub_builds_image_to_image_node_info_list_from_uploaded_filenames():
    from backend.app.services.ai_service import RunningHubImageClient

    client = RunningHubImageClient()

    node_info = client.build_image_to_image_node_info_list(
        prompt="保持第一张场景，只替换第二张产品",
        uploaded_filenames=["openapi/scene.png", "openapi/product.png"],
    )

    assert node_info == [
        {"nodeId": "3", "fieldName": "image", "fieldValue": "openapi/scene.png"},
        {"nodeId": "2", "fieldName": "image", "fieldValue": "openapi/product.png"},
        {"nodeId": "4", "fieldName": "prompt", "fieldValue": "保持第一张场景，只替换第二张产品"},
        {"nodeId": "4", "fieldName": "aspectRatio", "fieldValue": "3:4"},
        {"nodeId": "4", "fieldName": "resolution", "fieldValue": "1k"},
    ]


def test_runninghub_rejects_more_reference_images_than_exposed_image_nodes():
    from backend.app.services.ai_service import RunningHubImageClient

    client = RunningHubImageClient()

    try:
        client.build_image_to_image_node_info_list(
            prompt="测试",
            uploaded_filenames=["openapi/a.png", "openapi/b.png", "openapi/c.png"],
        )
    except ValueError as exc:
        assert "最多支持 2 张参考图" in str(exc)
    else:
        raise AssertionError("Expected ValueError for too many reference images")
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_runninghub_builds_text_to_image_node_info_list tests/backend/test_api.py::test_runninghub_builds_image_to_image_node_info_list_from_uploaded_filenames tests/backend/test_api.py::test_runninghub_rejects_more_reference_images_than_exposed_image_nodes -q
```

Expected: FAIL with `ImportError` or `AttributeError` because `RunningHubImageClient` does not exist.

- [ ] **Step 3: Implement constants and nodeInfoList builders**

In `backend/app/services/ai_service.py`, add imports at the top:

```python
from pathlib import Path
```

Then add these constants and class skeleton after `OpenAICompatibleImageClient` or before it if you prefer provider classes grouped alphabetically:

```python
RUNNINGHUB_TEXT_TO_IMAGE_WEBAPP_ID = "2046760522573418497"
RUNNINGHUB_IMAGE_TO_IMAGE_WEBAPP_ID = "2046794946094571522"
RUNNINGHUB_DEFAULT_BASE_URL = "https://www.runninghub.cn"
RUNNINGHUB_DEFAULT_ASPECT_RATIO = "3:4"
RUNNINGHUB_DEFAULT_RESOLUTION = "1k"
RUNNINGHUB_TEXT_PROMPT_NODE_ID = "136"
RUNNINGHUB_IMAGE_PROMPT_NODE_ID = "4"
RUNNINGHUB_IMAGE_INPUT_NODES = ["3", "2"]


class RunningHubImageClient:
    def _validate(self, *, model_config: ModelConfig, api_key: str) -> str:
        if not api_key:
            raise ValueError("RunningHub API Key 未配置")
        base_url = (model_config.base_url or RUNNINGHUB_DEFAULT_BASE_URL).rstrip("/")
        return base_url

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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_runninghub_builds_text_to_image_node_info_list tests/backend/test_api.py::test_runninghub_builds_image_to_image_node_info_list_from_uploaded_filenames tests/backend/test_api.py::test_runninghub_rejects_more_reference_images_than_exposed_image_nodes -q
```

Expected: PASS.

---

### Task 2: Implement RunningHub upload, task run, polling, and output retrieval

**Files:**
- Modify: `backend/app/services/ai_service.py`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Write failing tests with a fake RunningHub HTTP session**

Add these tests after the Task 1 RunningHub tests in `tests/backend/test_api.py`:

```python
def test_runninghub_generate_text_to_image_polls_and_returns_output(tmp_path):
    from backend.app.models import ModelConfig
    from backend.app.services.ai_service import RunningHubImageClient

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
            self.content = json.dumps(payload).encode("utf-8")
            self.encoding = "utf-8"
            self.apparent_encoding = "utf-8"
            self.text = json.dumps(payload)

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

    class FakeSession:
        def __init__(self):
            self.posts = []
            self.status_calls = 0

        def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            if url.endswith("/task/openapi/ai-app/run"):
                return FakeResponse({"code": 0, "msg": "success", "data": {"taskId": "task-1", "taskStatus": "QUEUED"}})
            if url.endswith("/task/openapi/status"):
                self.status_calls += 1
                return FakeResponse({"code": 0, "msg": "success", "data": "SUCCESS"})
            if url.endswith("/task/openapi/outputs"):
                return FakeResponse({"code": 0, "msg": "success", "data": [{"fileUrl": "https://cdn.example/generated.png", "fileType": "png", "nodeId": "9"}]})
            raise AssertionError(f"Unexpected URL {url}")

    config = ModelConfig(provider="runninghub-ai-app", model_name="runninghub-image-g", base_url="https://www.runninghub.cn")
    fake_session = FakeSession()
    client = RunningHubImageClient(session=fake_session, poll_interval_seconds=0, max_poll_attempts=1)

    result = client.generate_image(model_config=config, api_key="sk-test", prompt="低卡早餐封面")

    assert result["url"] == "https://cdn.example/generated.png"
    assert result["raw"]["provider"] == "runninghub-ai-app"
    assert result["raw"]["webapp_id"] == "2046760522573418497"
    run_call = fake_session.posts[0]
    assert run_call[0].endswith("/task/openapi/ai-app/run")
    assert run_call[1]["json"]["nodeInfoList"] == [
        {"nodeId": "136", "fieldName": "prompt", "fieldValue": "低卡早餐封面"},
        {"nodeId": "136", "fieldName": "aspectRatio", "fieldValue": "3:4"},
    ]


def test_runninghub_generate_image_to_image_uploads_references_and_returns_output(tmp_path):
    from backend.app.core.config import get_settings
    from backend.app.models import ModelConfig
    from backend.app.services.ai_service import RunningHubImageClient

    media_dir = get_settings().storage_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "ref-a.png").write_bytes(b"fake-image-a")
    (media_dir / "ref-b.png").write_bytes(b"fake-image-b")

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
            self.content = json.dumps(payload).encode("utf-8")
            self.encoding = "utf-8"
            self.apparent_encoding = "utf-8"
            self.text = json.dumps(payload)

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

    class FakeSession:
        def __init__(self):
            self.posts = []
            self.upload_count = 0

        def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            if url.endswith("/openapi/v2/media/upload/binary"):
                self.upload_count += 1
                return FakeResponse({"code": 200, "message": "success", "data": {"filename": f"openapi/ref-{self.upload_count}.png", "download_url": "https://cdn.example/ref.png", "type": "image", "size": "10"}})
            if url.endswith("/task/openapi/ai-app/run"):
                return FakeResponse({"code": 0, "msg": "success", "data": {"taskId": "task-2", "taskStatus": "RUNNING"}})
            if url.endswith("/task/openapi/status"):
                return FakeResponse({"code": 0, "msg": "success", "data": "SUCCESS"})
            if url.endswith("/task/openapi/outputs"):
                return FakeResponse({"code": 0, "msg": "success", "data": [{"fileUrl": "https://cdn.example/i2i.png", "fileType": "png", "nodeId": "9"}]})
            raise AssertionError(f"Unexpected URL {url}")

    config = ModelConfig(provider="runninghub-ai-app", model_name="runninghub-image-g", base_url="https://www.runninghub.cn")
    fake_session = FakeSession()
    client = RunningHubImageClient(session=fake_session, poll_interval_seconds=0, max_poll_attempts=1)

    result = client.generate_image(
        model_config=config,
        api_key="sk-test",
        prompt="保持场景，替换产品",
        reference_images=["/api/files/media/ref-a.png", "/api/files/media/ref-b.png"],
    )

    assert result["url"] == "https://cdn.example/i2i.png"
    assert fake_session.upload_count == 2
    run_payload = [kwargs["json"] for url, kwargs in fake_session.posts if url.endswith("/task/openapi/ai-app/run")][0]
    assert run_payload["webappId"] == "2046794946094571522"
    assert run_payload["nodeInfoList"] == [
        {"nodeId": "3", "fieldName": "image", "fieldValue": "openapi/ref-1.png"},
        {"nodeId": "2", "fieldName": "image", "fieldValue": "openapi/ref-2.png"},
        {"nodeId": "4", "fieldName": "prompt", "fieldValue": "保持场景，替换产品"},
        {"nodeId": "4", "fieldName": "aspectRatio", "fieldValue": "3:4"},
        {"nodeId": "4", "fieldName": "resolution", "fieldValue": "1k"},
    ]
```

Also add imports near the top of `tests/backend/test_api.py` if missing:

```python
import json
import requests
```

If `json` already exists, only add `requests`.

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_runninghub_generate_text_to_image_polls_and_returns_output tests/backend/test_api.py::test_runninghub_generate_image_to_image_uploads_references_and_returns_output -q
```

Expected: FAIL because `RunningHubImageClient.__init__`, `generate_image`, upload, run, poll, or output methods are not implemented.

- [ ] **Step 3: Implement `RunningHubImageClient` methods**

Replace the Task 1 skeleton class in `backend/app/services/ai_service.py` with this complete implementation, preserving the constants:

```python
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
    ) -> dict[str, Any]:
        base_url = self._validate(model_config=model_config, api_key=api_key)
        refs = [item for item in (reference_images or []) if str(item).strip()]
        if refs:
            filenames = [self._upload_reference_image(base_url=base_url, api_key=api_key, image_ref=ref) for ref in refs]
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
                "node_info_list": node_info,
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

    def _upload_reference_image(self, *, base_url: str, api_key: str, image_ref: str) -> str:
        path = self._resolve_local_image_path(image_ref)
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
        if not isinstance(payload, dict) or payload.get("code") != 200:
            message = payload.get("message") if isinstance(payload, dict) else "unknown"
            raise ValueError(f"RunningHub 参考图上传失败: {message}")
        data = payload.get("data") or {}
        filename = data.get("filename") if isinstance(data, dict) else None
        if not isinstance(filename, str) or not filename:
            raise ValueError("RunningHub upload response missing filename")
        return filename

    @staticmethod
    def _resolve_local_image_path(image_ref: str) -> Path:
        from backend.app.core.config import get_settings

        if image_ref.startswith("/api/files/media/"):
            candidate = Path(get_settings().storage_dir) / "media" / image_ref.split("/")[-1]
        else:
            candidate = Path(image_ref)
        if not candidate.is_file():
            raise ValueError(f"参考图文件不存在: {image_ref}")
        return candidate

    @staticmethod
    def _mime_for_path(path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "application/octet-stream")

    def _run_ai_app(self, *, base_url: str, api_key: str, webapp_id: str, node_info_list: list[dict[str, Any]]) -> dict[str, Any]:
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
```

- [ ] **Step 4: Run the RunningHub client tests**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_runninghub_builds_text_to_image_node_info_list tests/backend/test_api.py::test_runninghub_builds_image_to_image_node_info_list_from_uploaded_filenames tests/backend/test_api.py::test_runninghub_rejects_more_reference_images_than_exposed_image_nodes tests/backend/test_api.py::test_runninghub_generate_text_to_image_polls_and_returns_output tests/backend/test_api.py::test_runninghub_generate_image_to_image_uploads_references_and_returns_output -q
```

Expected: PASS.

---

### Task 3: Select RunningHub provider in image API and preserve existing OpenAI-compatible behavior

**Files:**
- Modify: `backend/app/api/ai.py`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Write failing API tests for provider selection**

Add this test near the existing image route tests in `tests/backend/test_api.py`:

```python
def test_ai_image_generate_uses_runninghub_provider_when_default_image_config_is_runninghub(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class FakeRunningHubClient:
        def __init__(self):
            self.calls = []

        def generate_cover(self, *, model_config, api_key, prompt, size, style):
            raise AssertionError("not used")

        def generate_image(self, *, model_config, api_key, prompt, reference_images=None):
            self.calls.append((model_config.provider, model_config.model_name, api_key, prompt, reference_images))
            return {
                "url": "https://cdn.example/runninghub.png",
                "raw": {"provider": "runninghub-ai-app", "task_id": "task-1"},
            }

        def describe_image(self, *, model_config, api_key, image_url, instruction):
            raise AssertionError("not used")

    fake_client = FakeRunningHubClient()
    db_dependency = _override_database(tmp_path)
    token = _register_and_get_access_token("runninghub-owner")
    try:
        app.dependency_overrides[get_image_ai_client] = lambda: fake_client
        model_response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "RunningHub Image",
                "model_type": "image",
                "provider": "runninghub-ai-app",
                "model_name": "runninghub-image-g",
                "base_url": "https://www.runninghub.cn",
                "api_key": "sk-runninghub-secret",
                "is_default": True,
            },
        )
        assert model_response.status_code == 200

        response = client.post(
            "/api/ai/images/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "低卡早餐封面", "reference_images": ["/api/files/media/ref.png"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["url"] == "https://cdn.example/runninghub.png"
        assert body["asset"]["params"]["raw"]["provider"] == "runninghub-ai-app"
        assert fake_client.calls == [
            ("runninghub-ai-app", "runninghub-image-g", "sk-runninghub-secret", "低卡早餐封面", ["/api/files/media/ref.png"])
        ]
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)
```

- [ ] **Step 2: Run the test and verify it fails if necessary**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_ai_image_generate_uses_runninghub_provider_when_default_image_config_is_runninghub -q
```

Expected: This may already pass if the endpoint only depends on the fake `ImageAiClient`. If it passes, keep it as regression coverage. If it fails due provider restrictions, proceed with Step 3.

- [ ] **Step 3: Update imports and provider factory**

In `backend/app/api/ai.py`, update the import line:

```python
from backend.app.services.ai_service import ImageAiClient, OpenAICompatibleImageClient, OpenAICompatibleTextClient, RunningHubImageClient, TextAiClient
```

Then replace `get_image_ai_client` with a provider-neutral default that still returns OpenAI-compatible for dependency overrides:

```python
def get_image_ai_client() -> ImageAiClient:
    return OpenAICompatibleImageClient()
```

Add this helper below `_image_model_context`:

```python
def _image_client_for_model(model_config: ModelConfig, fallback_client: ImageAiClient) -> ImageAiClient:
    if model_config.provider == "runninghub-ai-app":
        return RunningHubImageClient()
    return fallback_client
```

In `generate_cover`, after `model_config, api_key = _image_model_context(...)`, add:

```python
    image_client = _image_client_for_model(model_config, image_ai_client)
```

Then change `action=lambda: image_ai_client.generate_cover(` to:

```python
        action=lambda: image_client.generate_cover(
```

In `generate_image`, after `model_config, api_key = _image_model_context(...)`, add:

```python
    image_client = _image_client_for_model(model_config, image_ai_client)
```

Then change `action=lambda: image_ai_client.generate_image(` to:

```python
        action=lambda: image_client.generate_image(
```

In `describe_image`, do the same if image description should follow provider selection. RunningHub does not support image description, so this gives a clear ValueError instead of calling OpenAI-compatible with RunningHub config:

```python
    image_client = _image_client_for_model(model_config, image_ai_client)
```

Then call `image_client.describe_image(...)`.

- [ ] **Step 4: Run provider selection and existing image route tests**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_ai_image_generate_uses_runninghub_provider_when_default_image_config_is_runninghub tests/backend/test_api.py::test_ai_image_routes_use_default_model_store_assets_and_enforce_scope -q
```

Expected: PASS.

---

### Task 4: Make model-config test endpoint provider-aware

**Files:**
- Modify: `backend/app/api/model_configs.py`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Write failing test for RunningHub model-config connection check**

Add this test near other model config tests in `tests/backend/test_api.py`:

```python
def test_model_config_test_supports_runninghub_provider(tmp_path, monkeypatch):
    db_dependency = _override_database(tmp_path)
    token = _register_and_get_access_token("runninghub-config-owner")

    class FakeResponse:
        status_code = 200
        text = '{"code":0,"msg":"success","data":{"webappName":"test","nodeInfoList":[]}}'

        def json(self):
            return {"code": 0, "msg": "success", "data": {"webappName": "test", "nodeInfoList": []}}

    def fake_get(url, **kwargs):
        assert url.startswith("https://www.runninghub.cn/api/webapp/apiCallDemo")
        assert kwargs["headers"]["Authorization"] == "Bearer sk-runninghub-secret"
        return FakeResponse()

    try:
        import backend.app.api.model_configs as model_configs_api
        monkeypatch.setattr(model_configs_api.http_requests, "get", fake_get, raising=False)
    except AttributeError:
        pass

    try:
        response = client.post(
            "/api/model-configs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "RunningHub Image",
                "model_type": "image",
                "provider": "runninghub-ai-app",
                "model_name": "runninghub-image-g",
                "base_url": "https://www.runninghub.cn",
                "api_key": "sk-runninghub-secret",
                "is_default": True,
            },
        )
        assert response.status_code == 200
        config_id = response.json()["id"]

        test_response = client.post(f"/api/model-configs/{config_id}/test", headers={"Authorization": f"Bearer {token}"})

        assert test_response.status_code == 200
        assert test_response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
```

If monkeypatching module-level `http_requests` is awkward because it is imported inside the function, instead implement Step 3 first with a module-level import and then use this test.

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_model_config_test_supports_runninghub_provider -q
```

Expected: FAIL because `/model-configs/{id}/test` currently posts to `/images/generations` for every image provider.

- [ ] **Step 3: Refactor request import and add RunningHub branch**

In `backend/app/api/model_configs.py`, add a module-level import near the top:

```python
import requests as http_requests
```

Remove the inside-function `import requests as http_requests` from `test_model_config`.

Inside `test_model_config`, after `base_url = config.base_url.rstrip("/")`, add this branch before the existing `if config.model_type == "image":` branch:

```python
        if config.provider == "runninghub-ai-app":
            resp = http_requests.get(
                f"{base_url}/api/webapp/apiCallDemo",
                headers={"Authorization": f"Bearer {api_key}", "Host": "www.runninghub.cn"},
                params={"apiKey": api_key, "webappId": "2046760522573418497"},
                timeout=15,
            )
        elif config.model_type == "image":
```

Ensure the existing `if config.model_type == "image":` becomes `elif config.model_type == "image":`.

Update the response validation block to treat RunningHub success as valid:

```python
                if body.get("choices") or body.get("data") or body.get("object"):
                    if config.provider == "runninghub-ai-app" and body.get("code") not in (0, None):
                        return {"id": config.id, "status": "error", "message": f"RunningHub 连接失败: {body.get('msg') or body.get('message') or body}"[:200]}
                    return {"id": config.id, "status": "ok", "message": f"连接成功 ({resp.status_code})"}
```

- [ ] **Step 4: Run model-config tests**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_model_config_test_supports_runninghub_provider -q
```

Expected: PASS.

---

### Task 5: Add frontend RunningHub provider preset and copy updates

**Files:**
- Modify: `frontend/src/pages/models/model-config-page.tsx`
- Modify: `frontend/src/types/index.ts` if needed

- [ ] **Step 1: Update provider guidance copy**

In `frontend/src/pages/models/model-config-page.tsx`, replace the alert at lines 230-240 with provider-aware copy:

```tsx
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="模型配置建议"
        description={<>
          图片工坊默认推荐 RunningHub：Provider <Typography.Text code>runninghub-ai-app</Typography.Text>，Base URL <Typography.Text code>https://www.runninghub.cn</Typography.Text>，模型名称可填 <Typography.Text code>runninghub-image-g</Typography.Text>。<br />
          文本模型仍使用 OpenAI 兼容接口：例如 <Typography.Text code>https://api.openai-next.com/v1</Typography.Text>、火山方舟或阿里云百炼兼容模式。
        </>}
      />
```

- [ ] **Step 2: Add a provider input label that explains RunningHub values**

The current form has no provider field in the visible UI even though `provider` is submitted. Add this `Form.Item` before “模型名称”:

```tsx
                <Form.Item label="Provider">
                  <Input
                    value={form.provider}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        provider: e.target.value,
                      }))
                    }
                    placeholder={form.model_type === "image" ? "runninghub-ai-app" : "openai-compatible"}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    图片工坊推荐 runninghub-ai-app；OpenAI 兼容服务使用 openai-compatible。
                  </Text>
                </Form.Item>
```

- [ ] **Step 3: Make image tab default to RunningHub values**

Update `defaultModelName`:

```tsx
function defaultModelName(type: ModelType): string {
  return type === "text" ? "gpt-5.4" : "runninghub-image-g";
}
```

Add this helper near `defaultModelName`:

```tsx
function defaultProvider(type: ModelType): string {
  return type === "text" ? "openai-compatible" : "runninghub-ai-app";
}

function defaultBaseUrl(type: ModelType): string {
  return type === "text" ? "" : "https://www.runninghub.cn";
}
```

Update the `Segmented` `onChange` block to reset provider/base URL when switching type:

```tsx
                  provider: defaultProvider(val as ModelType),
                  base_url: defaultBaseUrl(val as ModelType),
```

Update `handleCancelEdit` and the post-save reset to preserve defaults for the selected type:

```tsx
const nextType = form.model_type;
setForm({ ...emptyForm, model_type: nextType, provider: defaultProvider(nextType), model_name: defaultModelName(nextType), base_url: defaultBaseUrl(nextType) });
```

Apply that pattern anywhere the form resets with `{ ...emptyForm, model_type: form.model_type }`.

- [ ] **Step 4: Update placeholders**

Change model name placeholder:

```tsx
placeholder={form.model_type === "text" ? "gpt-5.4" : "runninghub-image-g"}
```

Change Base URL placeholder:

```tsx
placeholder={form.model_type === "image" && form.provider === "runninghub-ai-app" ? "https://www.runninghub.cn" : "https://api.example.com/v1"}
```

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

---

### Task 6: Add image-studio reference cap UX and backend-error clarity

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/image-studio-page.tsx`

The backend remains the source of truth: it rejects more reference images than `RUNNINGHUB_IMAGE_INPUT_NODES` exposes. The frontend constant below is only current-App UX copy for `2046794946094571522`, which currently exposes 2 `IMAGE` nodes; if the RunningHub App changes, update the backend node mapping and this copy together.

- [ ] **Step 1: Add a local constant and prevent selecting more references than current RunningHub app supports**

Near the top of `frontend/src/pages/platforms/xhs/image-studio-page.tsx`, after `const { TextArea } = Input;`, add:

```tsx
const RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT = 2;
```

Update `handlePickerSelect` reference branch:

```tsx
    if (pickerMode === "reference") {
      setReferenceImages((prev) => {
        if (prev.includes(url)) return prev;
        if (prev.length >= RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT) {
          setError(`当前 RunningHub 图生图工作流最多支持 ${RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT} 张参考图。`);
          return prev;
        }
        return [...prev, url];
      });
```

- [ ] **Step 2: Improve the reference image label**

Replace the label text block content from:

```tsx
参考图
```

To:

```tsx
参考图（当前 RunningHub 图生图工作流最多支持 2 张）
```

This is current-app-specific copy. If the backend later returns dynamic provider capability, replace this constant and copy with server-provided capability.

- [ ] **Step 3: Preserve backend error detail where available**

In `handleGenerate`, replace:

```tsx
    } catch {
      setError("AI 图片生成失败，请确认已配置图片生成模型。");
```

With:

```tsx
    } catch (err) {
      const detail = err instanceof Error ? err.message : "";
      setError(detail || "AI 图片生成失败，请确认已配置图片生成模型。");
```

If the project’s HTTP client throws Axios errors with response detail instead of `Error.message`, adapt this in implementation by importing `axios` or using the existing interceptor pattern. Keep the visible user message actionable.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

---

### Task 7: Backend route integration and persistence metadata

**Files:**
- Modify: `backend/app/api/ai.py`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Write metadata assertion in existing provider test**

In `test_ai_image_generate_uses_runninghub_provider_when_default_image_config_is_runninghub`, add assertions after `body = response.json()`:

```python
        assert body["asset"]["params"]["provider"] == "runninghub-ai-app"
        assert body["asset"]["params"]["reference_images"] == ["/api/files/media/ref.png"]
```

- [ ] **Step 2: Update asset params in `generate_image`**

In `backend/app/api/ai.py`, inside the `AiGeneratedAsset` creation in `generate_image`, replace:

```python
            params={"reference_images": payload.reference_images, "raw": result.get("raw")},
```

With:

```python
            params={
                "provider": model_config.provider,
                "reference_images": payload.reference_images,
                "raw": result.get("raw"),
            },
```

In `generate_cover`, replace:

```python
        params={"size": payload.size, "style": payload.style, "raw": result.get("raw")},
```

With:

```python
        params={"provider": model_config.provider, "size": payload.size, "style": payload.style, "raw": result.get("raw")},
```

- [ ] **Step 3: Run relevant backend tests**

Run:

```bash
py -m pytest tests/backend/test_api.py::test_ai_image_generate_uses_runninghub_provider_when_default_image_config_is_runninghub tests/backend/test_api.py::test_ai_image_routes_use_default_model_store_assets_and_enforce_scope -q
```

Expected: PASS.

---

### Task 8: Full verification

**Files:**
- No new source changes unless tests reveal a defect.

- [ ] **Step 1: Run backend AI/model tests**

Run:

```bash
py -m pytest tests/backend/test_api.py -q
```

Expected: PASS. If unrelated existing tests fail, capture the exact failing test names and output; do not hide failures.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Optional live RunningHub smoke test only after local tests pass**

Use the app UI, not hard-coded scripts, to store the user’s RunningHub API Key in encrypted `model_configs.encrypted_api_key`:

- Provider: `runninghub-ai-app`
- Model type: image
- Model name: `runninghub-image-g`
- Base URL: `https://www.runninghub.cn`
- Set as default image model

Then manually verify:

1. Generate with prompt only.
2. Generate with one reference image.
3. Generate with two reference images.
4. Attempt a third reference image and verify the UI blocks it with current workflow capacity copy.

Expected: generated assets appear in 图片工坊 and failures show actionable messages.

---

## Self-Review Checklist

- Spec coverage:
  - RunningHub as default image upstream: Tasks 3, 5, 8.
  - AI App, not workflow API: Tasks 1, 2.
  - Text-to-image and image-to-image node mappings: Tasks 1, 2.
  - Reference cap from exposed IMAGE nodes: Tasks 1, 6.
  - API Key encrypted and not in code: Tasks 5, 8.
  - Error handling and no fake success assets: Tasks 2, 7, 8.
- Placeholder scan: No TODO/TBD placeholders. One implementation note about Axios error shape is explicit and bounded.
- Type consistency:
  - Provider string: `runninghub-ai-app`.
  - Webapp IDs: `2046760522573418497`, `2046794946094571522`.
  - Node fields: `prompt`, `aspectRatio`, `resolution`, `image`.
  - Return shape: `{"url": str, "raw": dict}` matches existing `ImageAiClient` usage.

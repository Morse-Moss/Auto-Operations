from __future__ import annotations

import csv
import io
import ipaddress
import json
import re
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import FeishuIntegrationConfig, ModelConfig, Note, NoteAnalysisResult, NoteAsset, NoteExclusion
from backend.app.services.ai_service import OpenAICompatibleTextClient

ANALYSIS_STATUS_OPTIONS = ["待分析", "分析中", "已完成", "废弃", "已废弃"]
CONTENT_TYPE_OPTIONS = ["种草", "测评", "避坑", "教程", "合集/清单", "对比", "痛点共鸣", "案例故事", "经验分享", "观点输出", "记录日常"]
REUSABLE_MODEL_OPTIONS = [
    "问题驱动模型",
    "情绪驱动模型",
    "场景种草模型",
    "对比反差模型",
    "测评背书模型",
    "教程方法模型",
    "故事案例模型",
    "IP/热点借势模型",
]
REUSE_VALUE_OPTIONS = ["选题参考", "标题参考", "正文结构参考", "卖点表达参考", "可直接改写", "行业观察", "竞品参考", "废弃"]

SYSTEM_FIELD_NAMES = [
    "系统笔记ID",
    "平台笔记ID",
    "采集批次ID",
    "数据来源",
    "采集方式",
    "采集关键词",
    "关键词组",
    "笔记标题",
    "笔记正文",
    "作者",
    "原链接",
    "笔记类型",
    "笔记标签",
    "点赞数",
    "收藏数",
    "评论数",
    "分享数",
    "采集时间",
    "同步时间",
]

ANALYSIS_FIELD_NAMES = [
    "分析状态",
    "分析状态确认",
    "核心产品/服务",
    "产品/主题对象",
    "内容类型",
    "核心卖点/观点",
    "核心卖点/核心观点",
    "目标人群",
    "内容钩子",
    "封面类型",
    "标题类型",
    "笔记结构分析",
    "内容结构分析",
    "可复用模型",
    "内容利用方式",
    "复用价值",
    "搜索属性",
    "搜素属性",
    "评分",
    "评级",
    "分析备注",
]

FEISHU_FIELD_DEFINITIONS = [
    {"field_name": name, "type": "text"} for name in SYSTEM_FIELD_NAMES
] + [
    {"field_name": "分析状态", "type": "single_select", "options": ANALYSIS_STATUS_OPTIONS},
    {"field_name": "核心产品/服务", "type": "text"},
    {"field_name": "内容类型", "type": "single_select", "options": CONTENT_TYPE_OPTIONS},
    {"field_name": "核心卖点/观点", "type": "text"},
    {"field_name": "目标人群", "type": "text"},
    {"field_name": "内容钩子", "type": "text"},
    {"field_name": "封面", "type": "attachment"},
    {"field_name": "封面类型", "type": "text"},
    {"field_name": "标题类型", "type": "text"},
    {"field_name": "笔记结构分析", "type": "text"},
    {"field_name": "可复用模型", "type": "multi_select", "options": REUSABLE_MODEL_OPTIONS},
    {"field_name": "内容利用方式", "type": "multi_select", "options": REUSE_VALUE_OPTIONS},
    {"field_name": "搜索属性", "type": "single_select", "options": ["强搜索", "弱搜索", "泛流量"]},
    {"field_name": "评分", "type": "number"},
    {"field_name": "评级", "type": "text"},
    {"field_name": "分析备注", "type": "text"},
]

FIELD_ALIASES = {
    "核心产品/服务": ["产品/主题对象"],
    "核心卖点/观点": ["核心卖点/核心观点"],
    "内容钩子": ["封面/标题钩子"],
    "笔记结构分析": ["内容结构分析"],
    "内容利用方式": ["复用价值"],
    "搜索属性": ["搜素属性"],
    "分析状态": ["分析状态确认"],
    "笔记标签": ["标签/话题"],
}

FEISHU_FIELD_TYPE_MAP = {
    "text": 1,
    "number": 2,
    "single_select": 3,
    "multi_select": 4,
    "url": 15,
    "attachment": 17,
}
MAX_SYNC_ITEMS = 100
MAX_FEISHU_MEDIA_BYTES = 20 * 1024 * 1024
FEISHU_OPEN_API_BASE_URL = "https://open.feishu.cn/open-apis"


class FeishuIntegrationError(RuntimeError):
    pass


class FeishuBitableClient:
    def __init__(self, *, app_id: str, app_secret: str, bitable_app_token: str = "", table_id: str = "", timeout: int = 20):
        self.app_id = app_id
        self.app_secret = app_secret
        self.bitable_app_token = bitable_app_token
        self.table_id = table_id
        self.timeout = timeout
        self._tenant_access_token: str | None = None

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None, auth: bool = True) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self.get_tenant_access_token()}"
        response = requests.request(
            method,
            f"{FEISHU_OPEN_API_BASE_URL}{path}",
            headers=headers,
            params=params,
            json=json,
            timeout=self.timeout,
        )
        return self._parse_response(response)

    def _parse_response(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuIntegrationError(f"飞书接口返回非 JSON：HTTP {response.status_code}") from exc
        if response.status_code >= 400 or payload.get("code") not in (0, None):
            message = payload.get("msg") or payload.get("message") or f"HTTP {response.status_code}"
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            violations = error.get("permission_violations") if isinstance(error, dict) else None
            scopes = [str(item.get("scope")) for item in violations if isinstance(item, dict) and item.get("scope")] if isinstance(violations, list) else []
            if "Permission denied" in str(message):
                hint = "请确认飞书开放平台权限已发布生效，并开通云文档协作者权限（docs:permission.member:create 或 docs:permission.member），同时确认应用具备分享该多维表格的权限。"
                if scopes:
                    hint = f"{hint} 缺失权限：{', '.join(scopes)}。"
                message = f"{message}。{hint}"
            raise FeishuIntegrationError(f"飞书接口调用失败：{message}")
        return payload

    def get_tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        payload = self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            auth=False,
        )
        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuIntegrationError("飞书没有返回 tenant_access_token")
        self._tenant_access_token = str(token)
        return self._tenant_access_token

    def create_app(self, *, name: str, folder_token: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if folder_token:
            body["folder_token"] = folder_token
        payload = self._request("POST", "/bitable/v1/apps", json=body)
        return dict(payload.get("data", {}).get("app", payload.get("data", {})))

    def create_table(self, *, name: str) -> dict[str, Any]:
        payload = self._request("POST", f"/bitable/v1/apps/{self.bitable_app_token}/tables", json={"table": {"name": name}})
        return dict(payload.get("data", {}).get("table", payload.get("data", {})))

    def list_fields(self) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/fields")
        return list(payload.get("data", {}).get("items", []))

    def create_field(self, definition: dict[str, Any]) -> dict[str, Any]:
        body = _feishu_field_payload(definition)
        payload = self._request("POST", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/fields", json=body)
        return dict(payload.get("data", {}).get("field", payload.get("data", {})))

    def update_field(self, field_id: str, definition: dict[str, Any]) -> dict[str, Any]:
        body = _feishu_field_payload(definition)
        payload = self._request("PUT", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/fields/{field_id}", json=body)
        return dict(payload.get("data", {}).get("field", payload.get("data", {})))

    def list_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            payload = self._request("GET", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/records", params=params)
            data = payload.get("data", {})
            records.extend(list(data.get("items") or []))
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")
            if not page_token:
                return records

    def create_record(self, fields: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("POST", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/records", json={"fields": fields})
        return dict(payload.get("data", {}).get("record", payload.get("data", {})))

    def update_record(self, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("PUT", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/records/{record_id}", json={"fields": fields})
        return dict(payload.get("data", {}).get("record", payload.get("data", {})))

    def export_bitable_csv(self) -> bytes:
        body = {"file_extension": "csv", "token": self.bitable_app_token, "type": "bitable", "sub_id": self.table_id}
        payload = self._request("POST", "/drive/v1/export_tasks", json=body)
        ticket = str(payload.get("data", {}).get("ticket") or "")
        if not ticket:
            raise FeishuIntegrationError("飞书导出任务没有返回 ticket")
        file_token = ""
        for _ in range(30):
            status_payload = self._request("GET", f"/drive/v1/export_tasks/{ticket}", params={"token": self.bitable_app_token})
            data = status_payload.get("data", {})
            result = data.get("result") if isinstance(data.get("result"), dict) else data
            file_token = str(result.get("file_token") or "")
            if file_token:
                break
            time.sleep(2)
        if not file_token:
            raise FeishuIntegrationError("飞书 CSV 导出任务超时，请稍后重试")
        response = requests.get(
            f"{FEISHU_OPEN_API_BASE_URL}/drive/v1/export_tasks/file/{file_token}/download",
            headers={"Authorization": f"Bearer {self.get_tenant_access_token()}"},
            timeout=60,
        )
        response.raise_for_status()
        return response.content

    def upload_bitable_attachment(self, *, file_name: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        headers = {"Authorization": f"Bearer {self.get_tenant_access_token()}"}
        response = requests.post(
            f"{FEISHU_OPEN_API_BASE_URL}/drive/v1/medias/upload_all",
            headers=headers,
            data={
                "file_name": file_name,
                "parent_type": "bitable_file",
                "parent_node": self.bitable_app_token,
                "size": str(len(content)),
            },
            files={"file": (file_name, content, content_type)},
            timeout=self.timeout,
        )
        payload = self._parse_response(response)
        file_token = str(payload.get("data", {}).get("file_token") or "")
        if not file_token:
            raise FeishuIntegrationError("飞书附件上传成功但未返回 file_token")
        return file_token

    def add_bitable_permission_member(self, *, app_token: str, member_type: str, member_id: str, perm: str = "edit", notify_lark: bool = False) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/drive/v1/permissions/{app_token}/members",
            params={"type": "bitable"},
            json={"member_type": member_type, "member_id": member_id, "perm": perm},
        )
        data = payload.get("data", {})
        return {"is_all_success": True, "fail_members": [], "member": data.get("member", data)}


def extract_bitable_tokens(url: str) -> dict[str, str | None]:
    return {
        "bitable_app_token": _match(url, r"/base/([^/?#]+)"),
        "wiki_node_token": _match(url, r"/wiki/([^/?#]+)"),
        "table_id": _match(url, r"[?&]table=([^&#]+)"),
        "view_id": _match(url, r"[?&]view=([^&#]+)"),
    }


def _match(value: str, pattern: str) -> str | None:
    matched = re.search(pattern, value or "")
    return matched.group(1) if matched else None


def create_feishu_bootstrap_client_from_config(config: FeishuIntegrationConfig) -> FeishuBitableClient:
    if not config.enabled:
        raise FeishuIntegrationError("飞书集成未启用")
    if not config.app_id or not config.encrypted_app_secret:
        raise FeishuIntegrationError("飞书 App ID 或 App Secret 未配置")
    return FeishuBitableClient(app_id=config.app_id, app_secret=decrypt_text(config.encrypted_app_secret))


def create_feishu_client_from_config(config: FeishuIntegrationConfig) -> FeishuBitableClient:
    if not config.enabled:
        raise FeishuIntegrationError("飞书集成未启用")
    if not config.app_id or not config.encrypted_app_secret or not config.table_id:
        raise FeishuIntegrationError("飞书 App ID、App Secret 或目标数据表未配置")
    if not config.bitable_app_token:
        raise FeishuIntegrationError("飞书多维表格尚未创建，请先在设置页点击创建飞书分析表")
    return FeishuBitableClient(
        app_id=config.app_id,
        app_secret=decrypt_text(config.encrypted_app_secret),
        bitable_app_token=config.bitable_app_token,
        table_id=config.table_id,
    )


def grant_feishu_bitable_permission(client: Any, *, app_token: str, member_type: str, member_id: str, perm: str = "edit", notify_lark: bool = False) -> dict[str, Any]:
    member_type = member_type.strip()
    member_id = member_id.strip()
    perm = (perm or "edit").strip() or "edit"
    if not app_token:
        raise FeishuIntegrationError("飞书多维表格 app_token 缺失")
    if not member_type or not member_id:
        raise FeishuIntegrationError("飞书协作者类型或 ID 未配置")
    if member_type not in {"email", "openid", "openchat", "userid"}:
        raise FeishuIntegrationError("飞书协作者类型仅支持 email、openid、openchat、userid")
    if perm not in {"view", "edit"}:
        raise FeishuIntegrationError("飞书协作者权限仅支持 view 或 edit")
    result = client.add_bitable_permission_member(app_token=app_token, member_type=member_type, member_id=member_id, perm=perm, notify_lark=notify_lark)
    return {
        "status": "success" if result.get("is_all_success", True) else "partial_failed",
        "is_all_success": result.get("is_all_success", True),
        "fail_members": result.get("fail_members") or [],
        "member_type": member_type,
        "member_id": member_id,
        "perm": perm,
    }


def create_feishu_analysis_base(client: Any, *, base_name: str = "小红书内容分析总表", table_name: str = "小红书内容分析", folder_token: str = "") -> dict[str, Any]:
    app = client.create_app(name=base_name, folder_token=folder_token)
    app_token = str(app.get("app_token") or app.get("token") or app.get("appToken") or "")
    if not app_token:
        raise FeishuIntegrationError("飞书已返回结果，但没有 app_token")
    client.bitable_app_token = app_token
    table = client.create_table(name=table_name)
    table_id = str(table.get("table_id") or table.get("tableId") or "")
    if not table_id:
        raise FeishuIntegrationError("飞书已创建多维表格，但没有返回 table_id")
    client.table_id = table_id
    fields_result = ensure_feishu_fields(client)
    return {
        "status": "success",
        "app_token": app_token,
        "table_id": table_id,
        "bitable_url": f"https://www.feishu.cn/base/{app_token}?table={table_id}",
        "created_fields": fields_result.get("created_count", 0),
        "skipped_fields": fields_result.get("skipped_count", 0),
    }


def _normalize_option(option: Any) -> dict[str, Any]:
    if isinstance(option, dict):
        return dict(option)
    return {"name": str(option)}


def _feishu_field_payload(definition: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "field_name": definition["field_name"],
        "type": FEISHU_FIELD_TYPE_MAP.get(str(definition.get("type")), 1),
    }
    options = definition.get("options") or []
    if options:
        body["property"] = {"options": [_normalize_option(option) for option in options]}
    return body


def _field_options(field: dict[str, Any]) -> list[dict[str, Any]]:
    property_value = field.get("property") if isinstance(field.get("property"), dict) else {}
    options = property_value.get("options") if isinstance(property_value, dict) else []
    if not isinstance(options, list):
        return []
    return [_normalize_option(option) for option in options]


def _field_option_names(field: dict[str, Any]) -> set[str]:
    return {str(option["name"]) for option in _field_options(field) if option.get("name")}


def _field_id(field: dict[str, Any]) -> str:
    return str(field.get("field_id") or field.get("fieldId") or "")


def _field_type(field: dict[str, Any]) -> int | None:
    try:
        return int(field.get("type"))
    except (TypeError, ValueError):
        return None


def ensure_feishu_fields(client: Any) -> dict[str, Any]:
    existing = client.list_fields()
    existing_by_name = {str(field.get("field_name")): field for field in existing if field.get("field_name")}
    existing_names = set(existing_by_name)
    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[str] = []
    errors: list[str] = []
    for definition in FEISHU_FIELD_DEFINITIONS:
        field_name = definition["field_name"]
        aliases = FIELD_ALIASES.get(field_name, [])
        existing_name = field_name if field_name in existing_names else next((alias for alias in aliases if alias in existing_names), "")
        if existing_name:
            field = existing_by_name[existing_name]
            if field_name == "分析状态":
                options = definition.get("options") or []
                missing_options = [option for option in options if option not in _field_option_names(field)]
                field_id = _field_id(field)
                if missing_options:
                    missing_text = "、".join(str(option) for option in missing_options)
                    if existing_name != field_name:
                        errors.append(f"分析状态别名字段 {existing_name} 缺少选项：{missing_text}；请在飞书中人工补齐，或改用规范字段名 分析状态")
                    elif _field_type(field) != FEISHU_FIELD_TYPE_MAP["single_select"]:
                        errors.append("分析状态字段不是飞书单选字段，无法自动补齐选项：" + missing_text)
                    elif not field_id:
                        errors.append("分析状态字段缺少 field_id，无法自动补齐选项：" + missing_text)
                    elif not hasattr(client, "update_field"):
                        errors.append("飞书客户端不支持 update_field，无法自动补齐分析状态选项：" + missing_text)
                    else:
                        existing_options = _field_options(field)
                        update_definition = dict(definition)
                        update_definition["options"] = [*existing_options, *({"name": str(option)} for option in missing_options)]
                        updated.append(client.update_field(field_id, update_definition))
            skipped.append(field_name)
            continue
        created.append(client.create_field(definition))
        existing_names.add(field_name)
    return {
        "dry_run": False,
        "status": "failed" if errors else "ok",
        "created_count": len(created),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "fields": FEISHU_FIELD_DEFINITIONS,
    }


def note_to_feishu_fields(
    note: Note,
    *,
    batch_id: str = "",
    source: str = "小红书站内",
    method: str = "内容库同步",
    keyword: str = "",
    keyword_group: str = "",
    analysis: dict[str, Any] | None = None,
    cover_file_token: str = "",
) -> dict[str, Any]:
    raw = note.raw_json or {}
    tags = _note_tags(raw)
    note_url = str(raw.get("note_url") or raw.get("url") or raw.get("share_url") or f"https://www.xiaohongshu.com/explore/{note.note_id}")
    fields: dict[str, Any] = {
        "系统笔记ID": str(note.id),
        "平台笔记ID": note.note_id,
        "采集批次ID": batch_id,
        "数据来源": source,
        "采集方式": method,
        "采集关键词": keyword,
        "关键词组": keyword_group,
        "笔记标题": note.title,
        "笔记正文": note.content,
        "作者": note.author_name,
        "原链接": {"text": note.title or note.note_id, "link": note_url},
        "笔记类型": infer_note_type(note),
        "笔记标签": "、".join(tags),
        "点赞数": str(raw.get("liked_count") or raw.get("like_count") or raw.get("likes") or ""),
        "收藏数": str(raw.get("collected_count") or raw.get("collect_count") or raw.get("collects") or ""),
        "评论数": str(raw.get("comment_count") or raw.get("comments") or ""),
        "分享数": str(raw.get("share_count") or raw.get("shares") or ""),
        "采集时间": note.created_at.isoformat(),
        "同步时间": shanghai_now().isoformat(),
        "分析状态": "待分析",
    }
    analysis = analysis or {}
    if analysis:
        fields.update(
            {
                "内容类型": normalize_content_type(analysis.get("content_type")),
                "可复用模型": normalize_multi_select(analysis.get("reusable_models"), REUSABLE_MODEL_OPTIONS, fallback=["场景种草模型"]),
                "内容利用方式": normalize_multi_select(analysis.get("reuse_values"), REUSE_VALUE_OPTIONS, fallback=["选题参考"]),
                "搜索属性": normalize_search_attribute(analysis.get("search_attribute"), note),
            }
        )
    if cover_file_token:
        fields["封面"] = [{"file_token": cover_file_token}]
    return fields


def _note_tags(raw: dict[str, Any]) -> list[str]:
    for key in ("tags", "tag_list", "note_tags", "hash_tags"):
        value = raw.get(key)
        if isinstance(value, list):
            tags: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    tag = item.get("name") or item.get("tag_name") or item.get("title")
                else:
                    tag = item
                if str(tag or "").strip():
                    tags.append(str(tag).strip().lstrip("#"))
            return tags
        if isinstance(value, str) and value.strip():
            return [item.strip().lstrip("#") for item in re.split(r"[,，、\s]+", value) if item.strip()]
    return []


def _first_note_card(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    item = items[0] if items and isinstance(items[0], dict) else {}
    card = item.get("note_card") if isinstance(item.get("note_card"), dict) else {}
    return {"item": item, "card": card}


def infer_note_type(note: Note) -> str:
    raw = note.raw_json or {}
    nested = _first_note_card(raw)
    item = nested["item"]
    card = nested["card"]
    values = [raw.get("note_type"), raw.get("type"), raw.get("media_type"), raw.get("model_type"), item.get("model_type"), item.get("type"), card.get("type"), card.get("model_type")]
    text = " ".join(str(value or "").lower() for value in values)
    if "video" in text or "视频" in text or bool(card.get("video") or card.get("video_url") or card.get("video_addr")):
        return "视频"
    if "image" in text or "normal" in text or "note" in text or "图" in text or bool(card.get("image_list") or card.get("images") or _cover_url_from_raw(raw)):
        return "图文"
    return "未知"


def normalize_content_type(value: Any) -> str:
    text = _as_text(value)
    if not text:
        return "经验分享"
    if "避坑" in text or "避雷" in text or "踩坑" in text:
        return "避坑"
    if text in CONTENT_TYPE_OPTIONS:
        return text
    if "教程" in text or "攻略" in text or "方法" in text:
        return "教程"
    for option in CONTENT_TYPE_OPTIONS:
        if option in text:
            return option
    return "经验分享"


def normalize_multi_select(value: Any, options: list[str], *, fallback: list[str]) -> list[str]:
    raw_items = _as_text_list(value)
    items: list[str] = []
    for item in raw_items:
        if "废弃" in item:
            return ["废弃"]
        matched = item if item in options else next((option for option in options if option in item), "")
        if matched and matched not in items:
            items.append(matched)
        if len(items) >= 3:
            break
    return items or fallback


def infer_reusable_models(note: Note) -> list[str]:
    source = f"{note.title}\n{note.content}".lower()
    scored: list[tuple[str, int]] = []
    rules = [
        ("问题驱动模型", 30, ["痛点", "困扰", "问题", "怎么办", "担心", "焦虑", "踩坑", "避坑", "为什么", "如何"]),
        ("教程方法模型", 24, ["方法", "步骤", "技巧", "经验", "攻略", "教程", "清单", "流程", "一步步", "建议"]),
        ("测评背书模型", 20, ["体验", "测评", "测试", "数据", "反馈", "真实", "实测", "评价", "证明", "效果"]),
        ("对比反差模型", 16, ["前后", "变化", "对比", "反差", "差别", "不同", "原来", "现在", "提升", "变成"]),
        ("场景种草模型", 12, ["场景", "生活", "使用", "氛围", "家里", "日常", "入住", "小户型", "卧室", "厨房", "浴室", "客厅"]),
        ("情绪驱动模型", 10, ["共鸣", "治愈", "期待", "爽", "崩溃", "后悔", "喜欢", "惊喜", "焦虑", "松弛", "幸福"]),
        ("故事案例模型", 8, ["经历", "事件", "过程", "案例", "我家", "我曾", "那天", "后来"]),
        ("IP/热点借势模型", 6, ["爆火", "热点", "趋势", "明星", "品牌", "ip", "同款", "全网", "最近很火"]),
    ]
    for model, base_score, keywords in rules:
        keyword_hits = sum(1 for keyword in keywords if keyword in source)
        score = base_score + keyword_hits if keyword_hits else 0
        if score:
            scored.append((model, score))
    if not scored:
        return ["场景种草模型"]
    scored.sort(key=lambda item: (-item[1], REUSABLE_MODEL_OPTIONS.index(item[0])))
    return [model for model, _ in scored[:3]]


def normalize_search_attribute(value: Any, note: Note | None = None) -> str:
    text = _as_text(value)
    if text in {"强搜索", "弱搜索", "泛流量"}:
        return text
    if text:
        if "强" in text:
            return "强搜索"
        if "弱" in text:
            return "弱搜索"
        if "泛" in text:
            return "泛流量"
    if note is None:
        return ""
    source = f"{note.title}\n{note.content}".lower()
    strong_keywords = ["怎么", "如何", "教程", "攻略", "步骤", "尺寸", "价格", "避坑", "避雷", "解决", "怎么办", "清单", "方法"]
    weak_keywords = ["小户型", "装修", "设计", "方案", "推荐", "搭配", "收纳", "改造", "选购"]
    if any(keyword in source for keyword in strong_keywords):
        return "强搜索"
    if any(keyword in source for keyword in weak_keywords):
        return "弱搜索"
    return "泛流量"


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("AI pre-analysis result must be a JSON object")
    return parsed


def _default_text_model(db: Session, user_id: int) -> tuple[ModelConfig, str] | None:
    model_config = db.scalar(select(ModelConfig).where(ModelConfig.user_id == user_id, ModelConfig.model_type == "text", ModelConfig.is_default.is_(True)))
    if model_config is None:
        return None
    api_key = decrypt_text(model_config.encrypted_api_key) if model_config.encrypted_api_key else ""
    if not api_key:
        return None
    return model_config, api_key


def preanalyze_note_for_feishu(db: Session, *, user_id: int, note: Note) -> tuple[dict[str, Any], str]:
    fallback = {
        "content_type": "经验分享",
        "reusable_models": infer_reusable_models(note),
        "reuse_values": ["选题参考"],
        "search_attribute": normalize_search_attribute("", note),
    }
    model_context = _default_text_model(db, user_id)
    if model_context is None:
        return fallback, "未配置默认文本模型，已使用规则兜底预分析"
    model_config, api_key = model_context
    raw = note.raw_json or {}
    prompt = _feishu_preanalysis_prompt(note, _note_tags(raw))
    try:
        content = OpenAICompatibleTextClient().complete_json_prompt(
            model_config=model_config,
            api_key=api_key,
            system_prompt="你是小红书内容运营分析师。只输出合法 JSON，不输出解释。",
            user_prompt=prompt,
            temperature=0.1,
        )
        parsed = _extract_json_object(content)
        return {
            "content_type": normalize_content_type(parsed.get("content_type")),
            "reusable_models": normalize_multi_select(parsed.get("reusable_models"), REUSABLE_MODEL_OPTIONS, fallback=["场景种草模型"]),
            "reuse_values": normalize_multi_select(parsed.get("reuse_values"), REUSE_VALUE_OPTIONS, fallback=["选题参考"]),
            "search_attribute": normalize_search_attribute(parsed.get("search_attribute"), note),
        }, ""
    except Exception as exc:
        return fallback, f"AI 预分析失败，已使用规则兜底：{exc}"


def _feishu_preanalysis_prompt(note: Note, tags: list[str]) -> str:
    raw = note.raw_json or {}
    url = str(raw.get("note_url") or raw.get("url") or raw.get("share_url") or f"https://www.xiaohongshu.com/explore/{note.note_id}")
    return f"""
请根据小红书笔记信息做同步前预分析，输出 JSON：
{{
  "content_type": "种草|测评|避坑|教程|合集/清单|对比|痛点共鸣|案例故事|经验分享|观点输出|记录日常",
  "reusable_models": ["问题驱动模型|情绪驱动模型|场景种草模型|对比反差模型|测评背书模型|教程方法模型|故事案例模型|IP/热点借势模型"],
  "reuse_values": ["选题参考|标题参考|正文结构参考|卖点表达参考|可直接改写|行业观察|竞品参考|废弃"],
  "search_attribute": "强搜索|弱搜索|泛流量"
}}

内容类型规则：
- 避坑：核心是提醒风险、纠正错误、避免踩坑。即使包含步骤，只要核心是避坑，也输出避坑。
- 教程：核心是中性方法、步骤、流程，且不是以避坑纠错为主。
- 案例故事优先于教程；合集/清单优先于教程。
- 不允许输出“避坑教程”。

可复用模型规则：
可复用模型指内容背后的传播方式、吸引逻辑或说服机制，用于判断为什么这篇内容有效，不分析内容主题。
- 问题驱动模型：先提出问题、痛点、困扰，再推进内容。
- 情绪驱动模型：通过情绪、共鸣、期待、治愈、焦虑、爽感驱动阅读。
- 场景种草模型：通过生活场景、使用场景、氛围感激发向往或尝试欲。
- 对比反差模型：通过前后变化、认知差异、结果差异增强表达。
- 测评背书模型：通过体验、评价、测试、数据、真实反馈建立信任。
- 教程方法模型：通过步骤、方法、经验、技巧输出价值。
- 故事案例模型：通过经历、案例、事件推进表达。
- IP/热点借势模型：借助人物、品牌、热点、趋势获得关注。
判断要求：一篇内容可同时选择多个模型；优先判断真正驱动传播的模型，不要机械匹配关键词；不分析标题形式；不分析内容结构；不允许因为出现案例就直接判断故事案例模型；至少输出1项，最多输出3项；若多个模型同时存在，按影响强弱排序。

内容利用方式输出 1-3 个；如果输出“废弃”，必须只有“废弃”。
搜索属性：明确问题/方法/攻略/避坑/解决方案为强搜索；场景灵感/类目方案为弱搜索；情绪审美日常为泛流量。

标题：{note.title}
正文：{note.content[:5000]}
原链接：{url}
笔记标签：{'、'.join(tags)}
笔记类型：{infer_note_type(note)}
规则兜底可复用模型：{'、'.join(infer_reusable_models(note))}
""".strip()


def get_or_create_analysis_result(db: Session, *, user_id: int, note_id: int) -> NoteAnalysisResult:
    result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "feishu"))
    if result is None:
        result = NoteAnalysisResult(user_id=user_id, note_id=note_id, source="feishu")
        db.add(result)
        db.flush()
    return result


def apply_preanalysis_to_result(result: NoteAnalysisResult, analysis: dict[str, Any], warning: str = "", *, force_update: bool = False) -> None:
    content_type = normalize_content_type(analysis.get("content_type"))
    reusable_models = normalize_multi_select(analysis.get("reusable_models"), REUSABLE_MODEL_OPTIONS, fallback=["场景种草模型"])
    reuse_value = "、".join(normalize_multi_select(analysis.get("reuse_values"), REUSE_VALUE_OPTIONS, fallback=["选题参考"]))
    if force_update or not result.content_type:
        result.content_type = content_type
    if force_update or not result.reusable_models:
        result.reusable_models = reusable_models
    if force_update or not result.reuse_value:
        result.reuse_value = reuse_value
    search_attribute = normalize_search_attribute(analysis.get("search_attribute"), None)
    if force_update or not result.search_attribute:
        result.search_attribute = search_attribute or None
    if warning and warning not in (result.last_error or ""):
        result.last_error = warning


def _analysis_from_result(result: NoteAnalysisResult, note: Note) -> dict[str, Any]:
    return {
        "content_type": result.content_type or "经验分享",
        "reusable_models": result.reusable_models or ["场景种草模型"],
        "reuse_values": _as_text_list(result.reuse_value) or ["选题参考"],
        "search_attribute": result.search_attribute or normalize_search_attribute("", note),
    }


def _field_value(record_fields: dict[str, Any], name: str) -> Any:
    if name in record_fields:
        return record_fields.get(name)
    for alias in FIELD_ALIASES.get(name, []):
        if alias in record_fields:
            return record_fields.get(alias)
    return None


def _has_field_value(record_fields: dict[str, Any], name: str) -> bool:
    value = _field_value(record_fields, name)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True


def _record_fields_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
        if record_id:
            result[record_id] = fields
    return result


def existing_empty_only_fields(fields: dict[str, Any], existing_fields: dict[str, Any], *, overwrite_existing: bool = False) -> dict[str, Any]:
    if overwrite_existing:
        return dict(fields)
    protected = set(ANALYSIS_FIELD_NAMES)
    update_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if key in protected and _has_field_value(existing_fields, key):
            continue
        update_fields[key] = value
    return update_fields


def field_names_for_client(client: Any, *, raise_errors: bool = False) -> set[str]:
    try:
        return {str(field.get("field_name")) for field in client.list_fields() if field.get("field_name")}
    except Exception:
        if raise_errors:
            raise
        return set()


def resolve_field_aliases(fields: dict[str, Any], existing_field_names: set[str]) -> dict[str, Any]:
    if not existing_field_names:
        return fields
    resolved: dict[str, Any] = {}
    for key, value in fields.items():
        target = key
        if key not in existing_field_names:
            target = next((alias for alias in FIELD_ALIASES.get(key, []) if alias in existing_field_names), key)
        resolved[target] = value
    return resolved


def _image_url_from_item(item: Any) -> str:
    if isinstance(item, str) and item.strip():
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("url", "original", "default", "src", "file_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    info_list = item.get("info_list")
    if isinstance(info_list, list):
        for info in info_list:
            url = _image_url_from_item(info)
            if url:
                return url
    return ""


def _cover_url_from_raw(raw: dict[str, Any]) -> str:
    for key in ("cover", "cover_url", "image", "image_url", "thumbnail", "thumb_url"):
        value = raw.get(key)
        url = _image_url_from_item(value)
        if url:
            return url
    nested = _first_note_card(raw)
    for container in (raw, nested["card"], nested["item"]):
        for key in ("images", "image_list", "imgs"):
            value = container.get(key) if isinstance(container, dict) else None
            if isinstance(value, list):
                for item in value:
                    url = _image_url_from_item(item)
                    if url:
                        return url
    return ""


def cover_url_for_note(db: Session, note: Note) -> str:
    asset = db.scalar(select(NoteAsset).where(NoteAsset.note_id == note.id, NoteAsset.asset_type == "image").order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc()))
    if asset:
        return asset.local_path or asset.url or ""
    return _cover_url_from_raw(note.raw_json or {})


def _public_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("封面地址不是可下载的 HTTP 地址")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError("封面地址解析到非公网地址")
    return url


def _image_content_type(content: bytes, declared: str = "") -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if declared.startswith("image/"):
        return declared.split(";", 1)[0].strip()
    return "application/octet-stream"


def _image_extension(content_type: str) -> str:
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(content_type, ".bin")


def _resolve_local_media_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    media_path = Path(get_settings().storage_dir) / "media" / value.removeprefix("/api/files/media/")
    if media_path.is_file():
        return media_path
    return path


def _read_cover_bytes(ref: str) -> tuple[bytes, str]:
    value = (ref or "").strip()
    if not value:
        raise ValueError("没有可用封面")
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        response = requests.get(_public_http_url(value), timeout=20, allow_redirects=False)
        response.raise_for_status()
        content = response.content
        content_type = _image_content_type(content, response.headers.get("content-type", ""))
    else:
        path = _resolve_local_media_path(value)
        content = path.read_bytes()
        content_type = _image_content_type(content)
    if not content or len(content) > MAX_FEISHU_MEDIA_BYTES:
        raise ValueError("封面图片为空或超过 20MB")
    if not content_type.startswith("image/"):
        raise ValueError("封面文件不是图片")
    return content, content_type


def upload_note_cover_to_feishu(db: Session, *, note: Note, client: Any) -> tuple[str, str]:
    ref = cover_url_for_note(db, note)
    if not ref:
        return "", ""
    try:
        content, content_type = _read_cover_bytes(ref)
        file_name = f"xhs-note-{note.id}-cover{_image_extension(content_type)}"
        return client.upload_bitable_attachment(file_name=file_name, content=content, content_type=content_type), ""
    except Exception as exc:
        return "", f"封面上传失败：{exc}"


def _unique_note_ids(note_ids: list[int]) -> list[int]:
    return list(dict.fromkeys(note_ids))


def _excluded_note_ids_for_notes(db: Session, *, user_id: int, notes: list[Note]) -> set[int]:
    note_ids = [note.id for note in notes]
    platform_note_ids = [note.note_id for note in notes if note.platform == "xhs" and note.note_id]
    if not note_ids and not platform_note_ids:
        return set()
    exclusions = db.scalars(
        select(NoteExclusion).where(
            NoteExclusion.user_id == user_id,
            NoteExclusion.platform == "xhs",
            NoteExclusion.platform_note_id.in_(platform_note_ids),
        )
    ).all() if platform_note_ids else []
    excluded_platform_note_ids = {exclusion.platform_note_id for exclusion in exclusions}
    return {note.id for note in notes if note.platform == "xhs" and note.note_id in excluded_platform_note_ids}


def _skipped_excluded_record(note_id: int) -> dict[str, Any]:
    return {"note_id": note_id, "status": "skipped", "reason": "excluded"}


def _records_by_system_and_platform_id(records: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    by_system_id: dict[str, str] = {}
    by_platform_id: dict[str, str] = {}
    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
        if not record_id:
            continue
        system_id = fields.get("系统笔记ID")
        platform_id = fields.get("平台笔记ID")
        if system_id:
            by_system_id[str(system_id)] = record_id
        if platform_id:
            by_platform_id[str(platform_id)] = record_id
    return by_system_id, by_platform_id


def push_notes_to_feishu_dry_run(db: Session, *, user_id: int, note_ids: list[int], overwrite_existing: bool = False) -> dict[str, Any]:
    unique_ids = _unique_note_ids(note_ids)
    if len(unique_ids) > MAX_SYNC_ITEMS:
        return {"dry_run": True, "updated_count": 0, "failed_count": len(unique_ids), "errors": [f"每次最多同步 {MAX_SYNC_ITEMS} 条"], "records": []}
    notes = db.scalars(select(Note).where(Note.id.in_(unique_ids), Note.user_id == user_id)).all()
    by_id = {note.id: note for note in notes}
    excluded_note_ids = _excluded_note_ids_for_notes(db, user_id=user_id, notes=notes)
    records = []
    errors = []
    updated = 0
    now = shanghai_now()
    for note_id in unique_ids:
        note = by_id.get(note_id)
        if note is None:
            errors.append({"note_id": note_id, "error": "Note not found"})
            continue
        if note.id in excluded_note_ids:
            records.append(_skipped_excluded_record(note.id))
            continue
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        analysis, warning = preanalyze_note_for_feishu(db, user_id=user_id, note=note)
        apply_preanalysis_to_result(result, analysis, warning, force_update=overwrite_existing)
        fields = note_to_feishu_fields(note, analysis=_analysis_from_result(result, note))
        result.analysis_status = result.analysis_status or "待分析"
        result.push_status = "dry_run"
        result.last_pushed_at = now
        result.updated_at = now
        records.append({"note_id": note.id, "status": "dry_run", "fields": fields, "warning": warning})
        updated += 1
    db.commit()
    return {"dry_run": True, "updated_count": updated, "failed_count": len(errors), "errors": errors, "records": records}


def push_notes_to_feishu(db: Session, *, user_id: int, note_ids: list[int], client: Any, overwrite_existing: bool = False) -> dict[str, Any]:
    unique_ids = _unique_note_ids(note_ids)
    if len(unique_ids) > MAX_SYNC_ITEMS:
        return {"dry_run": False, "created_count": 0, "updated_count": 0, "failed_count": len(unique_ids), "errors": [f"每次最多同步 {MAX_SYNC_ITEMS} 条"], "records": []}
    notes = db.scalars(select(Note).where(Note.id.in_(unique_ids), Note.user_id == user_id)).all()
    by_id = {note.id: note for note in notes}
    excluded_note_ids = _excluded_note_ids_for_notes(db, user_id=user_id, notes=notes)
    preflight_records = []
    preflight_errors = []
    processable_ids = []
    for note_id in unique_ids:
        note = by_id.get(note_id)
        if note is None:
            preflight_errors.append({"note_id": note_id, "error": "Note not found"})
        elif note.id in excluded_note_ids:
            preflight_records.append(_skipped_excluded_record(note.id))
        else:
            processable_ids.append(note_id)
    if not processable_ids:
        return {"dry_run": False, "created_count": 0, "updated_count": 0, "failed_count": len(preflight_errors), "errors": preflight_errors, "records": preflight_records}
    fields_result = ensure_feishu_fields(client)
    if fields_result.get("status") == "failed":
        errors = fields_result.get("errors") or []
        message = "；".join(str(error) for error in errors) or "飞书字段补齐失败"
        raise FeishuIntegrationError(message)
    existing_records = client.list_records()
    existing_field_names = field_names_for_client(client)
    by_system_id, by_platform_id = _records_by_system_and_platform_id(existing_records)
    existing_fields_by_id = _record_fields_by_id(existing_records)
    created_count = 0
    updated_count = 0
    records = list(preflight_records)
    errors = list(preflight_errors)
    now = shanghai_now()
    for note_id in processable_ids:
        note = by_id.get(note_id)
        if note is None:
            errors.append({"note_id": note_id, "error": "Note not found"})
            continue
        if note.id in excluded_note_ids:
            records.append(_skipped_excluded_record(note.id))
            continue
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        analysis, warning = preanalyze_note_for_feishu(db, user_id=user_id, note=note)
        apply_preanalysis_to_result(result, analysis, warning, force_update=overwrite_existing)
        record_id = result.external_record_id or by_system_id.get(str(note.id)) or by_platform_id.get(note.note_id)
        existing_fields = existing_fields_by_id.get(record_id, {}) if record_id else {}
        cover_token = ""
        cover_warning = ""
        if overwrite_existing or not record_id or not _has_field_value(existing_fields, "封面"):
            cover_token, cover_warning = upload_note_cover_to_feishu(db, note=note, client=client)
        fields = resolve_field_aliases(note_to_feishu_fields(note, analysis=_analysis_from_result(result, note), cover_file_token=cover_token), existing_field_names)
        try:
            if record_id:
                update_fields = existing_empty_only_fields(fields, existing_fields, overwrite_existing=overwrite_existing)
                record = client.update_record(record_id, update_fields)
                status = "updated"
                updated_count += 1
            else:
                if result.analysis_status:
                    fields["分析状态"] = result.analysis_status
                record = client.create_record(fields)
                status = "created"
                created_count += 1
            result.external_record_id = str(record.get("record_id") or record_id or result.external_record_id or "") or None
            result.analysis_status = result.analysis_status or "待分析"
            result.push_status = "synced"
            result.last_pushed_at = now
            result.last_error = "；".join(item for item in [warning, cover_warning] if item)
            result.updated_at = now
            records.append({"note_id": note.id, "status": status, "record_id": result.external_record_id, "warning": result.last_error})
        except Exception as exc:
            result.push_status = "failed"
            result.last_error = str(exc)
            result.updated_at = now
            errors.append({"note_id": note.id, "error": str(exc)})
    db.commit()
    return {"dry_run": False, "created_count": created_count, "updated_count": updated_count, "failed_count": len(errors), "errors": errors, "records": records}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        text = value.get("text")
        if text is not None:
            return str(text).strip()
        return ""
    if isinstance(value, list):
        return "、".join(_as_text(item) for item in value if _as_text(item))
    return str(value).strip()


def normalize_score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        score = float(value)
    else:
        text = _as_text(value)
        if not text:
            return None
        matched = re.search(r"\d+(?:\.\d+)?", text)
        if not matched:
            return None
        score = float(matched.group(0))
    if score < 0 or score > 10:
        return None
    return score


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、\n]", value) if item.strip()]
    return []


def feishu_csv_to_records(content: bytes) -> list[dict[str, Any]]:
    if not content:
        return []
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("gb18030")
    reader = csv.DictReader(io.StringIO(text))
    records: list[dict[str, Any]] = []
    for row in reader:
        fields = {
            str(key).lstrip("﻿").strip(): str(value).strip()
            for key, value in row.items()
            if key is not None and str(key).lstrip("﻿").strip()
        }
        if any(fields.values()):
            records.append({"fields": fields})
    return records


def pull_feishu_analysis_records(db: Session, *, user_id: int, records: list[dict[str, Any]], note_ids: list[int] | None = None) -> dict[str, Any]:
    allowed_note_ids = set(_unique_note_ids(note_ids or []))
    updated = 0
    unmatched = 0
    skipped = 0
    errors = []
    now = shanghai_now()
    for record in records:
        fields = record.get("fields") if isinstance(record, dict) else None
        if not isinstance(fields, dict):
            errors.append({"error": "Invalid record fields"})
            continue
        raw_note_id = fields.get("系统笔记ID")
        try:
            note_id = int(str(raw_note_id))
        except Exception:
            unmatched += 1
            continue
        if allowed_note_ids and note_id not in allowed_note_ids:
            continue
        note = db.get(Note, note_id)
        if note is None or note.user_id != user_id:
            unmatched += 1
            continue
        if db.scalar(
            select(NoteExclusion.id).where(
                NoteExclusion.user_id == user_id,
                NoteExclusion.platform == note.platform,
                NoteExclusion.platform_note_id == note.note_id,
            )
        ) is not None:
            skipped += 1
            continue
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        result.external_record_id = _as_text(record.get("record_id") or result.external_record_id) or None
        result.analysis_status = _as_text(_field_value(fields, "分析状态")) or None
        result.subject_object = _as_text(_field_value(fields, "核心产品/服务"))
        result.content_type = normalize_content_type(_field_value(fields, "内容类型")) or None
        result.core_points = _as_text(_field_value(fields, "核心卖点/观点"))
        result.target_audience = _as_text(_field_value(fields, "目标人群"))
        result.title_hook = _as_text(_field_value(fields, "内容钩子"))
        result.content_structure = _as_text(_field_value(fields, "笔记结构分析"))
        result.reusable_models = normalize_multi_select(_field_value(fields, "可复用模型"), REUSABLE_MODEL_OPTIONS, fallback=[])
        result.reuse_value = "、".join(normalize_multi_select(_field_value(fields, "内容利用方式"), REUSE_VALUE_OPTIONS, fallback=[])) or None
        raw_search_attribute = _as_text(_field_value(fields, "搜索属性"))
        result.search_attribute = normalize_search_attribute(raw_search_attribute, note) if raw_search_attribute else None
        result.score = normalize_score(_field_value(fields, "评分"))
        result.rating = _as_text(_field_value(fields, "评级")) or None
        result.analysis_note = _as_text(_field_value(fields, "分析备注"))
        result.pull_status = "success"
        result.last_pulled_at = now
        result.last_error = ""
        result.raw_payload = fields
        result.updated_at = now
        updated += 1
    db.commit()
    return {"updated_count": updated, "unmatched_count": unmatched, "skipped_count": skipped, "failed_count": len(errors), "errors": errors}


def pull_feishu_analysis_records_from_client(db: Session, *, user_id: int, client: Any, note_ids: list[int] | None = None) -> dict[str, Any]:
    if note_ids and len(_unique_note_ids(note_ids)) > MAX_SYNC_ITEMS:
        return {"updated_count": 0, "unmatched_count": 0, "failed_count": len(note_ids), "errors": [f"每次最多回传 {MAX_SYNC_ITEMS} 条"]}
    if note_ids:
        records = client.list_records()
    else:
        records = feishu_csv_to_records(client.export_bitable_csv())
    return pull_feishu_analysis_records(db, user_id=user_id, records=records, note_ids=note_ids)

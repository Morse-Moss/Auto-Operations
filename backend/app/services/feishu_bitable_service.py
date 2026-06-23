from __future__ import annotations

import re
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import FeishuIntegrationConfig, Note, NoteAnalysisResult

ANALYSIS_STATUS_OPTIONS = ["待分析", "分析中", "已完成", "废弃"]
CONTENT_TYPE_OPTIONS = ["种草", "测评", "避坑", "教程", "合集/清单", "对比", "痛点共鸣", "案例故事"]
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
    "标签/话题",
    "点赞数",
    "收藏数",
    "评论数",
    "分享数",
    "采集时间",
    "同步时间",
]

ANALYSIS_FIELD_NAMES = [
    "分析状态",
    "产品/主题对象",
    "内容类型",
    "核心卖点/核心观点",
    "目标人群",
    "封面/标题钩子",
    "内容结构分析",
    "可复用模型",
    "复用价值",
    "分析备注",
]

FEISHU_FIELD_DEFINITIONS = [
    {"field_name": name, "type": "text"} for name in SYSTEM_FIELD_NAMES
] + [
    {"field_name": "分析状态", "type": "single_select", "options": ANALYSIS_STATUS_OPTIONS},
    {"field_name": "产品/主题对象", "type": "text"},
    {"field_name": "内容类型", "type": "single_select", "options": CONTENT_TYPE_OPTIONS},
    {"field_name": "核心卖点/核心观点", "type": "text"},
    {"field_name": "目标人群", "type": "text"},
    {"field_name": "封面/标题钩子", "type": "text"},
    {"field_name": "内容结构分析", "type": "text"},
    {"field_name": "可复用模型", "type": "multi_select", "options": REUSABLE_MODEL_OPTIONS},
    {"field_name": "复用价值", "type": "single_select", "options": REUSE_VALUE_OPTIONS},
    {"field_name": "分析备注", "type": "text"},
]

FEISHU_FIELD_TYPE_MAP = {
    "text": 1,
    "number": 2,
    "single_select": 3,
    "multi_select": 4,
}
MAX_SYNC_ITEMS = 100
FEISHU_OPEN_API_BASE_URL = "https://open.feishu.cn/open-apis"


class FeishuIntegrationError(RuntimeError):
    pass


class FeishuBitableClient:
    def __init__(self, *, app_id: str, app_secret: str, bitable_app_token: str, table_id: str, timeout: int = 20):
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
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuIntegrationError(f"飞书接口返回非 JSON：HTTP {response.status_code}") from exc
        if response.status_code >= 400 or payload.get("code") not in (0, None):
            message = payload.get("msg") or payload.get("message") or f"HTTP {response.status_code}"
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

    def list_fields(self) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/fields")
        return list(payload.get("data", {}).get("items", []))

    def create_field(self, definition: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "field_name": definition["field_name"],
            "type": FEISHU_FIELD_TYPE_MAP.get(str(definition.get("type")), 1),
        }
        options = definition.get("options") or []
        if options:
            body["property"] = {"options": [{"name": str(option)} for option in options]}
        payload = self._request("POST", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/fields", json=body)
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
            records.extend(list(data.get("items", [])))
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


def create_feishu_client_from_config(config: FeishuIntegrationConfig) -> FeishuBitableClient:
    if not config.enabled:
        raise FeishuIntegrationError("飞书集成未启用")
    if not config.app_id or not config.encrypted_app_secret or not config.table_id:
        raise FeishuIntegrationError("飞书 App ID、App Secret 或目标数据表未配置")
    if not config.bitable_app_token:
        raise FeishuIntegrationError("当前只支持飞书多维表格 base 链接，请在设置页填写 /base/ 开头的多维表格地址")
    return FeishuBitableClient(
        app_id=config.app_id,
        app_secret=decrypt_text(config.encrypted_app_secret),
        bitable_app_token=config.bitable_app_token,
        table_id=config.table_id,
    )


def ensure_feishu_fields(client: Any) -> dict[str, Any]:
    existing = client.list_fields()
    existing_names = {str(field.get("field_name")) for field in existing}
    created: list[dict[str, Any]] = []
    skipped: list[str] = []
    for definition in FEISHU_FIELD_DEFINITIONS:
        field_name = definition["field_name"]
        if field_name in existing_names:
            skipped.append(field_name)
            continue
        created.append(client.create_field(definition))
        existing_names.add(field_name)
    return {
        "dry_run": False,
        "status": "ok",
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
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
) -> dict[str, Any]:
    raw = note.raw_json or {}
    return {
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
        "原链接": str(raw.get("note_url") or raw.get("url") or raw.get("share_url") or f"https://www.xiaohongshu.com/explore/{note.note_id}"),
        "笔记类型": str(raw.get("note_type") or raw.get("type") or "未知"),
        "标签/话题": "、".join(str(item) for item in raw.get("tags", []) if item) if isinstance(raw.get("tags"), list) else "",
        "点赞数": str(raw.get("liked_count") or raw.get("like_count") or raw.get("likes") or ""),
        "收藏数": str(raw.get("collected_count") or raw.get("collect_count") or raw.get("collects") or ""),
        "评论数": str(raw.get("comment_count") or raw.get("comments") or ""),
        "分享数": str(raw.get("share_count") or raw.get("shares") or ""),
        "采集时间": note.created_at.isoformat(),
        "同步时间": shanghai_now().isoformat(),
        "分析状态": "待分析",
    }


def get_or_create_analysis_result(db: Session, *, user_id: int, note_id: int) -> NoteAnalysisResult:
    result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "feishu"))
    if result is None:
        result = NoteAnalysisResult(user_id=user_id, note_id=note_id, source="feishu")
        db.add(result)
        db.flush()
    return result


def _unique_note_ids(note_ids: list[int]) -> list[int]:
    return list(dict.fromkeys(note_ids))


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


def push_notes_to_feishu_dry_run(db: Session, *, user_id: int, note_ids: list[int]) -> dict[str, Any]:
    unique_ids = _unique_note_ids(note_ids)
    if len(unique_ids) > MAX_SYNC_ITEMS:
        return {"dry_run": True, "updated_count": 0, "failed_count": len(unique_ids), "errors": [f"每次最多同步 {MAX_SYNC_ITEMS} 条"], "records": []}
    notes = db.scalars(select(Note).where(Note.id.in_(unique_ids), Note.user_id == user_id)).all()
    by_id = {note.id: note for note in notes}
    records = []
    errors = []
    updated = 0
    now = shanghai_now()
    for note_id in unique_ids:
        note = by_id.get(note_id)
        if note is None:
            errors.append({"note_id": note_id, "error": "Note not found"})
            continue
        fields = note_to_feishu_fields(note)
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        result.analysis_status = result.analysis_status or "待分析"
        result.push_status = "dry_run"
        result.last_pushed_at = now
        result.last_error = ""
        result.updated_at = now
        records.append({"note_id": note.id, "status": "dry_run", "fields": fields})
        updated += 1
    db.commit()
    return {"dry_run": True, "updated_count": updated, "failed_count": len(errors), "errors": errors, "records": records}


def push_notes_to_feishu(db: Session, *, user_id: int, note_ids: list[int], client: Any) -> dict[str, Any]:
    unique_ids = _unique_note_ids(note_ids)
    if len(unique_ids) > MAX_SYNC_ITEMS:
        return {"dry_run": False, "created_count": 0, "updated_count": 0, "failed_count": len(unique_ids), "errors": [f"每次最多同步 {MAX_SYNC_ITEMS} 条"], "records": []}
    notes = db.scalars(select(Note).where(Note.id.in_(unique_ids), Note.user_id == user_id)).all()
    by_id = {note.id: note for note in notes}
    existing_records = client.list_records()
    by_system_id, by_platform_id = _records_by_system_and_platform_id(existing_records)
    created_count = 0
    updated_count = 0
    records = []
    errors = []
    now = shanghai_now()
    for note_id in unique_ids:
        note = by_id.get(note_id)
        if note is None:
            errors.append({"note_id": note_id, "error": "Note not found"})
            continue
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        fields = note_to_feishu_fields(note)
        record_id = result.external_record_id or by_system_id.get(str(note.id)) or by_platform_id.get(note.note_id)
        try:
            if record_id:
                update_fields = {key: value for key, value in fields.items() if key not in ANALYSIS_FIELD_NAMES}
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
            result.last_error = ""
            result.updated_at = now
            records.append({"note_id": note.id, "status": status, "record_id": result.external_record_id})
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
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item).strip())
    return str(value).strip()


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、\n]", value) if item.strip()]
    return []


def pull_feishu_analysis_records(db: Session, *, user_id: int, records: list[dict[str, Any]], note_ids: list[int] | None = None) -> dict[str, Any]:
    allowed_note_ids = set(_unique_note_ids(note_ids or []))
    updated = 0
    unmatched = 0
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
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        result.external_record_id = _as_text(record.get("record_id") or result.external_record_id) or None
        result.analysis_status = _as_text(fields.get("分析状态")) or None
        result.subject_object = _as_text(fields.get("产品/主题对象"))
        result.content_type = _as_text(fields.get("内容类型")) or None
        result.core_points = _as_text(fields.get("核心卖点/核心观点"))
        result.target_audience = _as_text(fields.get("目标人群"))
        result.title_hook = _as_text(fields.get("封面/标题钩子"))
        result.content_structure = _as_text(fields.get("内容结构分析"))
        result.reusable_models = _as_text_list(fields.get("可复用模型"))
        result.reuse_value = _as_text(fields.get("复用价值")) or None
        result.analysis_note = _as_text(fields.get("分析备注"))
        result.pull_status = "success"
        result.last_pulled_at = now
        result.last_error = ""
        result.raw_payload = fields
        result.updated_at = now
        updated += 1
    db.commit()
    return {"updated_count": updated, "unmatched_count": unmatched, "failed_count": len(errors), "errors": errors}


def pull_feishu_analysis_records_from_client(db: Session, *, user_id: int, client: Any, note_ids: list[int] | None = None) -> dict[str, Any]:
    if note_ids and len(_unique_note_ids(note_ids)) > MAX_SYNC_ITEMS:
        return {"updated_count": 0, "unmatched_count": 0, "failed_count": len(note_ids), "errors": [f"每次最多回传 {MAX_SYNC_ITEMS} 条"]}
    records = client.list_records()
    return pull_feishu_analysis_records(db, user_id=user_id, records=records, note_ids=note_ids)

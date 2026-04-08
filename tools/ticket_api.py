"""工单系统 API 调用工具

设置环境变量 MOCK_SERVICES=true 时使用模拟工单提交，无需真实接口。
"""

import json
import os
import random
import string
from datetime import datetime
from pathlib import Path

import httpx
from langchain_core.tools import tool


TICKET_API_URL = os.getenv("TICKET_API_URL", "http://localhost:8080/api/tickets")
TICKET_API_KEY = os.getenv("TICKET_API_KEY", "")
FALLBACK_DIR = os.getenv("SESSION_DIR", "./sessions")
MOCK_MODE = os.getenv("MOCK_SERVICES", "true").lower() in ("true", "1", "yes")

# 加载投诉 schema 用于必填要素校验
_SCHEMA_PATH = Path(__file__).parent.parent / "data" / "complaint_schemas.json"
_COMPLAINT_SCHEMAS: dict = {}
if _SCHEMA_PATH.exists():
    _COMPLAINT_SCHEMAS = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _generate_ticket_id() -> str:
    """生成模拟工单号：日期 + 5位随机数"""
    date_part = datetime.now().strftime("%Y%m%d")
    rand_part = "".join(random.choices(string.digits, k=5))
    return f"{date_part}-{rand_part}"


def _validate_required_elements(complaint_type: str, elements: dict) -> list[str]:
    """校验必填要素是否齐全，返回缺失要素标签列表。"""
    if not _COMPLAINT_SCHEMAS:
        return []
    schema = _COMPLAINT_SCHEMAS.get(complaint_type.upper(), _COMPLAINT_SCHEMAS.get("OTHER", {}))
    required = schema.get("required_elements", [])
    missing = []
    for elem in required:
        key = elem["key"]
        label = elem["label"]
        value = elements.get(key, "")
        if not value or str(value).strip() == "":
            missing.append(label)
    return missing


@tool
def submit_ticket(complaint_type: str, elements: dict, session_id: str = "") -> str:
    """提交投诉工单到业务系统。参数 complaint_type 为投诉类型代码，elements 为已收集的要素字典，
    session_id 为会话标识。返回 JSON 字符串，包含 success(bool), ticket_id(str|null)。"""
    # 必填要素校验：缺失时拒绝提交
    missing = _validate_required_elements(complaint_type, elements)
    if missing:
        missing_str = "、".join(missing)
        return json.dumps(
            {
                "success": False,
                "ticket_id": None,
                "error": f"工单提交被拒绝：以下必填要素尚未收集：{missing_str}。请先向用户逐一确认这些信息后再提交。",
            },
            ensure_ascii=False,
        )

    payload = {
        "complaint_type": complaint_type,
        "elements": elements,
        "session_id": session_id,
        "submitted_at": datetime.now().isoformat(),
    }

    if MOCK_MODE:
        # 模拟模式：生成工单号，保存到本地文件
        ticket_id = _generate_ticket_id()
        payload["ticket_id"] = ticket_id
        save_dir = Path(FALLBACK_DIR)
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / f"ticket_{ticket_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return json.dumps(
            {"success": True, "ticket_id": ticket_id, "saved_locally": True},
            ensure_ascii=False,
        )

    try:
        with httpx.Client(timeout=5.0) as client:
            headers = {}
            if TICKET_API_KEY:
                headers["Authorization"] = f"Bearer {TICKET_API_KEY}"
            response = client.post(TICKET_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return json.dumps(
                {"success": True, "ticket_id": data.get("ticket_id"), "saved_locally": False},
                ensure_ascii=False,
            )
    except Exception as e:
        fallback_path = Path(FALLBACK_DIR)
        fallback_path.mkdir(parents=True, exist_ok=True)
        filename = f"ticket_{session_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        (fallback_path / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return json.dumps(
            {"success": False, "ticket_id": None, "saved_locally": True, "error": str(e)},
            ensure_ascii=False,
        )

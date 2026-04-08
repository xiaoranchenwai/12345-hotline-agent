"""回复后处理守卫 — 强制 "每轮只问一个问题" 规则。

LLM 可能在一次回复中提出多个问题，违反投诉收集策略。
本模块在回复返回给用户之前做最后一道检查：
  - 如果检测到多个追问，只保留第一个问题
  - 保留问题之前的共情/确认文本
  - 返回被截断的问题列表，用于注入系统提醒
"""

import json
import re
from pathlib import Path

# 匹配中文问号或英文问号
_QUESTION_MARK = re.compile(r"[？?]")

# 加载投诉 schema，用于生成缺失要素提醒
_SCHEMA_PATH = Path(__file__).parent.parent / "data" / "complaint_schemas.json"
_COMPLAINT_SCHEMAS: dict = {}
if _SCHEMA_PATH.exists():
    _COMPLAINT_SCHEMAS = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def enforce_single_question(text: str) -> tuple[str, bool]:
    """如果回复中包含多个问题，只保留第一个。

    返回:
        (处理后的文本, 是否发生了截断)
    """
    marks = list(_QUESTION_MARK.finditer(text))

    if len(marks) <= 1:
        return text, False

    # 截取到第一个问号位置（包含问号本身）
    first_end = marks[0].end()
    truncated = text[:first_end].rstrip()

    return truncated, True


def build_element_reminder(messages: list[dict]) -> str | None:
    """根据对话历史识别投诉类型，返回一条系统提醒，
    列出该类型的所有必填要素，让 LLM 自行判断哪些已收集、哪些仍缺失。

    不尝试用关键词匹配判断"已收集/未收集"——LLM 比启发式规则
    更擅长理解"在我家这边"不是有效的详细地址。
    """
    if not _COMPLAINT_SCHEMAS:
        return (
            "系统提醒：上一轮回复中包含多个问题，已只保留第一个。"
            "请根据对话上下文判断哪些必填要素尚未有效收集，"
            "继续逐一追问，每轮只问一个问题。所有必填要素有效收集完毕前不要提交工单。"
        )

    # 拼接对话文本，用于关键词匹配投诉类型
    full_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") in ("user", "assistant")
    )

    # 识别投诉类型
    type_keywords = {
        "WATER_OUTAGE": ["停水"],
        "POWER_OUTAGE": ["停电"],
        "NOISE_COMPLAINT": ["噪音", "噪声", "扰民"],
        "ROAD_DAMAGE": ["道路", "路面", "坑洞", "护栏"],
        "GAS_ISSUE": ["燃气", "煤气", "天然气"],
    }

    complaint_type = None
    for ctype, keywords in type_keywords.items():
        if any(kw in full_text for kw in keywords):
            complaint_type = ctype
            break

    if not complaint_type or complaint_type not in _COMPLAINT_SCHEMAS:
        complaint_type = "OTHER"

    schema = _COMPLAINT_SCHEMAS[complaint_type]
    required = schema.get("required_elements", [])
    required_labels = "、".join(elem["label"] for elem in required)

    display_name = schema["display_name"]
    return (
        f"系统提醒：上一轮回复中包含多个问题，已只保留第一个。"
        f"当前投诉类型「{display_name}」的必填要素为：{required_labels}。"
        f"请根据对话上下文自行判断哪些要素已被用户有效提供"
        f"（注意：模糊回答如'在我家'不算有效地址），"
        f"继续逐一追问未有效收集的要素，每轮只问一个问题。"
        f"所有必填要素有效收集完毕前不要提交工单。"
    )

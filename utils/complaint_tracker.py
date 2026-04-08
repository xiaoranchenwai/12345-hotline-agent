"""投诉状态追踪器 — 解决多投诉交叉混淆问题。

在多轮对话中维护每个投诉的收集状态，
在每次 LLM 调用前注入结构化状态摘要，
让 LLM 始终清楚：当前在处理哪个投诉、各要素收集到了什么程度。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent / "data" / "complaint_schemas.json"
_COMPLAINT_SCHEMAS: dict = {}
if _SCHEMA_PATH.exists():
    _COMPLAINT_SCHEMAS = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))

# 投诉类型关键词，用于从用户消息中检测
_TYPE_KEYWORDS: dict[str, list[str]] = {
    "WATER_OUTAGE": ["停水", "没水", "断水"],
    "POWER_OUTAGE": ["停电", "没电", "断电"],
    "NOISE_COMPLAINT": ["噪音", "噪声", "扰民", "吵"],
    "ROAD_DAMAGE": ["道路", "路面", "坑洞", "护栏", "路坏"],
    "GAS_ISSUE": ["燃气", "煤气", "天然气", "停气"],
}


@dataclass
class ComplaintState:
    """单个投诉的状态"""
    complaint_type: str
    display_name: str
    required_keys: list[str]
    required_labels: list[str]
    collected: dict[str, str] = field(default_factory=dict)
    status: str = "collecting"  # collecting / submitted

    @property
    def missing_labels(self) -> list[str]:
        missing = []
        for key, label in zip(self.required_keys, self.required_labels):
            if key not in self.collected:
                missing.append(label)
        return missing

    @property
    def is_complete(self) -> bool:
        return all(k in self.collected for k in self.required_keys)


class ComplaintTracker:
    """跟踪会话中所有投诉的要素收集进度。

    用法：
        tracker = ComplaintTracker()

        # 每次用户发消息后，调用 update 分析
        tracker.update_from_user_message(user_msg)

        # 每次 LLM 回复后，调用 update 记录收集到的要素
        tracker.update_from_assistant(complaint_type, key, value)

        # 在发送给 LLM 之前，获取状态摘要注入消息
        summary = tracker.build_status_summary()
    """

    def __init__(self):
        self.complaints: list[ComplaintState] = []
        self.active_index: int = -1  # 当前活跃投诉的索引

    @property
    def active(self) -> ComplaintState | None:
        if 0 <= self.active_index < len(self.complaints):
            return self.complaints[self.active_index]
        return None

    def detect_complaint_type(self, text: str) -> str | None:
        """从文本中检测投诉类型"""
        for ctype, keywords in _TYPE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return ctype
        return None

    def _create_complaint(self, complaint_type: str) -> ComplaintState:
        schema = _COMPLAINT_SCHEMAS.get(complaint_type, _COMPLAINT_SCHEMAS.get("OTHER", {}))
        required = schema.get("required_elements", [])
        return ComplaintState(
            complaint_type=complaint_type,
            display_name=schema.get("display_name", complaint_type),
            required_keys=[e["key"] for e in required],
            required_labels=[e["label"] for e in required],
        )

    def update_from_user_message(self, text: str) -> str | None:
        """分析用户消息，检测是否有新投诉。

        返回: 新检测到的投诉类型，或 None
        """
        detected = self.detect_complaint_type(text)
        if detected is None:
            return None

        # 检查是否已有同类型的投诉
        for i, c in enumerate(self.complaints):
            if c.complaint_type == detected and c.status == "collecting":
                # 同类型且还在收集中，不创建新的
                return None

        # 新投诉
        new_complaint = self._create_complaint(detected)
        self.complaints.append(new_complaint)

        # 如果没有活跃投诉，或者当前活跃投诉已完成，切换到新投诉
        if self.active is None or self.active.status == "submitted":
            self.active_index = len(self.complaints) - 1

        return detected

    def record_element(self, complaint_type: str, key: str, value: str):
        """记录某个投诉收集到的要素"""
        for c in self.complaints:
            if c.complaint_type == complaint_type and c.status == "collecting":
                c.collected[key] = value
                return

    def mark_submitted(self, complaint_type: str):
        """标记某个投诉已提交"""
        for i, c in enumerate(self.complaints):
            if c.complaint_type == complaint_type and c.status == "collecting":
                c.status = "submitted"
                # 切换到下一个未完成的投诉
                if i == self.active_index:
                    self._switch_to_next_pending()
                return

    def _switch_to_next_pending(self):
        """切换到下一个待处理的投诉"""
        for i, c in enumerate(self.complaints):
            if c.status == "collecting":
                self.active_index = i
                return
        self.active_index = -1

    def build_status_summary(self) -> str | None:
        """构建结构化状态摘要，注入到 LLM 消息中。

        只展示投诉类型和所需要素清单，不追踪单个要素的收集状态。
        让 LLM 根据对话上下文自行判断哪些已收集、哪些还需追问。
        """
        if not self.complaints:
            return None

        lines = ["【投诉状态追踪】"]

        for i, c in enumerate(self.complaints):
            is_active = (i == self.active_index)
            marker = "→ 当前处理" if is_active else "  等待处理"
            if c.status == "submitted":
                marker = "  ✓ 已提交"

            lines.append(f"\n{marker}：{c.display_name}")

            if c.status == "submitted":
                continue

            # 只列出必填要素清单，不判断收集状态
            labels = "、".join(c.required_labels)
            lines.append(f"  必填要素：{labels}")

        # 行动指引
        active = self.active
        if active and active.status == "collecting":
            lines.append(
                f"\n请根据对话上下文判断「{active.display_name}」"
                f"的哪些必填要素已被用户有效提供、哪些仍需追问。"
                f"每轮只问一个问题。"
                f"已有效提供的要素不要重复询问。"
                f"所有必填要素有效收集完毕前不要提交工单。"
            )

        # 提醒其他待处理投诉
        pending = [c for c in self.complaints if c.status == "collecting" and c != active]
        if pending:
            names = "、".join(c.display_name for c in pending)
            lines.append(f"完成当前投诉后，还需处理：{names}")

        return "\n".join(lines)

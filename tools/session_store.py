import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class SessionStackManager:
    """管理会话中的多任务栈，持久化到文件系统"""

    def __init__(self, session_id: str, session_dir: str = "./sessions"):
        self.session_id = session_id
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / f"{session_id}.json"
        self.state = self._load_or_init()

    def _load_or_init(self) -> dict:
        if self.session_file.exists():
            return json.loads(self.session_file.read_text(encoding="utf-8"))
        return {
            "session_id": self.session_id,
            "active_task": None,
            "task_stack": [],
            "completed_tasks": [],
            "interrupt_depth": 0,
            "last_updated": datetime.now().isoformat(),
        }

    def _save(self):
        self.state["last_updated"] = datetime.now().isoformat()
        self.session_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def can_interrupt(self) -> bool:
        return self.state["interrupt_depth"] < 2

    def pause_active_and_push(self, new_task: dict) -> bool:
        """暂停当前任务，将新任务设为活跃（用于咨询/建议打断投诉）"""
        if not self.can_interrupt():
            return False
        if self.state["active_task"]:
            self.state["active_task"]["status"] = "PAUSED"
            self.state["task_stack"].append(self.state["active_task"])
        new_task["status"] = "ACTIVE"
        new_task["created_reason"] = "USER_INTERRUPT"
        self.state["active_task"] = new_task
        self.state["interrupt_depth"] += 1
        self._save()
        return True

    def queue_pending(self, new_task: dict) -> bool:
        """保持当前任务活跃，新投诉入队（用于投诉中新增投诉）"""
        if not self.can_interrupt():
            return False
        new_task["status"] = "PENDING"
        new_task["created_reason"] = "USER_INTERRUPT"
        self.state["task_stack"].append(new_task)
        self.state["interrupt_depth"] += 1
        self._save()
        return True

    def complete_active_and_resume(self, ticket_id: Optional[str] = None) -> Optional[dict]:
        """完成当前任务，从栈中恢复下一个"""
        if self.state["active_task"]:
            completed = self.state["active_task"]
            completed["status"] = "COMPLETED"
            if ticket_id:
                completed["ticket_id"] = ticket_id
            self.state["completed_tasks"].append(completed)
            self.state["active_task"] = None

        if self.state["task_stack"]:
            next_task = self.state["task_stack"].pop()
            next_task["status"] = "ACTIVE"
            self.state["active_task"] = next_task
            self.state["interrupt_depth"] = max(0, self.state["interrupt_depth"] - 1)
            self._save()
            return next_task

        self._save()
        return None

    def get_resume_transition(self, completed_task: dict, next_task: dict) -> str:
        """生成任务切换的自然过渡话术"""
        type_labels = {"INQUIRY": "咨询", "COMPLAINT": "投诉", "SUGGESTION": "建议"}
        next_label = type_labels.get(next_task.get("agent_type", ""), "问题")
        next_q = next_task.get("next_question", "")

        if completed_task.get("agent_type") == "INQUIRY":
            query = completed_task.get("query", "您咨询的问题")
            return f"好的，以上是关于\u201c{query}\u201d的解答。我们继续刚才的{next_label}——{next_q}"

        if completed_task.get("agent_type") == "COMPLAINT":
            tid = completed_task.get("ticket_id", "处理中")
            name = completed_task.get("display_name", "投诉")
            return f"{name}已为您登记（工单号：{tid}）。接下来我们处理{next_label}的问题——{next_q}"

        c_label = type_labels.get(completed_task.get("agent_type", ""), "问题")
        return f"好的，{c_label}已处理完毕。我们继续——{next_q}"

    def get_summary(self) -> str:
        """生成所有已完成任务的汇总"""
        tasks = self.state["completed_tasks"]
        if not tasks:
            return ""
        lines = [f"您本次共处理了 {len(tasks)} 项事务："]
        for i, t in enumerate(tasks, 1):
            name = t.get("display_name", t.get("agent_type", "事务"))
            tid = t.get("ticket_id")
            if tid:
                lines.append(f"  {i}. {name}（工单号：{tid}）")
            else:
                lines.append(f"  {i}. {name}（已完成）")
        return "\n".join(lines)

import json
import pytest
from pathlib import Path
from tools.session_store import SessionStackManager


@pytest.fixture
def tmp_session_dir(tmp_path):
    return str(tmp_path / "sessions")


@pytest.fixture
def manager(tmp_session_dir):
    return SessionStackManager("test-session-001", session_dir=tmp_session_dir)


def test_init_creates_empty_state(manager):
    assert manager.state["session_id"] == "test-session-001"
    assert manager.state["active_task"] is None
    assert manager.state["task_stack"] == []
    assert manager.state["completed_tasks"] == []
    assert manager.state["interrupt_depth"] == 0


def test_can_interrupt_initially_true(manager):
    assert manager.can_interrupt() is True


def test_pause_active_and_push_sets_new_task_active(manager):
    manager.state["active_task"] = {
        "task_id": "complaint-001",
        "agent_type": "COMPLAINT",
        "complaint_type": "WATER_OUTAGE",
        "collected": {"address": "XX路88号"},
        "missing": ["start_time"],
        "next_question": "请问什么时间开始停水？",
        "status": "ACTIVE",
    }

    new_task = {
        "task_id": "inquiry-001",
        "agent_type": "INQUIRY",
        "query": "临时供水怎么申请",
    }
    result = manager.pause_active_and_push(new_task)

    assert result is True
    assert manager.state["active_task"]["task_id"] == "inquiry-001"
    assert manager.state["active_task"]["status"] == "ACTIVE"
    assert len(manager.state["task_stack"]) == 1
    assert manager.state["task_stack"][0]["status"] == "PAUSED"
    assert manager.state["interrupt_depth"] == 1


def test_queue_pending_keeps_current_active(manager):
    manager.state["active_task"] = {
        "task_id": "complaint-001",
        "agent_type": "COMPLAINT",
        "status": "ACTIVE",
    }
    new_complaint = {
        "task_id": "complaint-002",
        "agent_type": "COMPLAINT",
        "complaint_type": "FACILITY_DAMAGE",
    }
    result = manager.queue_pending(new_complaint)

    assert result is True
    assert manager.state["active_task"]["task_id"] == "complaint-001"
    assert manager.state["active_task"]["status"] == "ACTIVE"
    assert manager.state["task_stack"][0]["task_id"] == "complaint-002"
    assert manager.state["task_stack"][0]["status"] == "PENDING"


def test_complete_active_and_resume_returns_next_task(manager):
    manager.state["active_task"] = {
        "task_id": "inquiry-001",
        "agent_type": "INQUIRY",
        "status": "ACTIVE",
    }
    manager.state["task_stack"] = [
        {
            "task_id": "complaint-001",
            "agent_type": "COMPLAINT",
            "status": "PAUSED",
            "next_question": "请问什么时间？",
        }
    ]
    manager.state["interrupt_depth"] = 1

    next_task = manager.complete_active_and_resume(ticket_id=None)

    assert next_task is not None
    assert next_task["task_id"] == "complaint-001"
    assert next_task["status"] == "ACTIVE"
    assert len(manager.state["completed_tasks"]) == 1
    assert manager.state["interrupt_depth"] == 0


def test_complete_active_returns_none_when_stack_empty(manager):
    manager.state["active_task"] = {
        "task_id": "complaint-001",
        "agent_type": "COMPLAINT",
        "status": "ACTIVE",
    }
    next_task = manager.complete_active_and_resume(ticket_id="T-001")
    assert next_task is None
    assert len(manager.state["completed_tasks"]) == 1
    assert manager.state["completed_tasks"][0]["ticket_id"] == "T-001"


def test_interrupt_depth_limit(manager):
    manager.state["interrupt_depth"] = 2
    assert manager.can_interrupt() is False

    result = manager.pause_active_and_push({"task_id": "x", "agent_type": "INQUIRY"})
    assert result is False


def test_persistence(tmp_session_dir):
    m1 = SessionStackManager("persist-test", session_dir=tmp_session_dir)
    m1.state["active_task"] = {"task_id": "t1", "agent_type": "COMPLAINT", "status": "ACTIVE"}
    m1._save()

    m2 = SessionStackManager("persist-test", session_dir=tmp_session_dir)
    assert m2.state["active_task"]["task_id"] == "t1"


def test_get_resume_transition_inquiry(manager):
    completed = {"agent_type": "INQUIRY", "query": "临时供水申请"}
    next_task = {"agent_type": "COMPLAINT", "next_question": "请问停水什么时间开始？"}
    text = manager.get_resume_transition(completed, next_task)
    assert "临时供水申请" in text
    assert "请问停水什么时间开始？" in text


def test_get_summary(manager):
    manager.state["completed_tasks"] = [
        {"agent_type": "COMPLAINT", "display_name": "停水投诉", "ticket_id": "A001"},
        {"agent_type": "COMPLAINT", "display_name": "停电投诉", "ticket_id": "A002"},
    ]
    summary = manager.get_summary()
    assert "A001" in summary
    assert "A002" in summary

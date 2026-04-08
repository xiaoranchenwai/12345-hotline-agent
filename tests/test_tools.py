import json
import pytest
from unittest.mock import patch, MagicMock
from tools.knowledge_base import query_knowledge_base, _mock_query
from tools.ticket_api import submit_ticket


# ---------------------------------------------------------------------------
# 知识库 - 模拟模式测试
# ---------------------------------------------------------------------------

def test_mock_kb_hit():
    """模拟知识库命中关键词时返回 found=True"""
    result = _mock_query("办理营业执照需要什么材料")
    assert result["found"] is True
    assert "身份证" in result["answer"]


def test_mock_kb_miss():
    """模拟知识库未命中时返回 found=False"""
    result = _mock_query("量子力学原理")
    assert result["found"] is False


# ---------------------------------------------------------------------------
# 知识库 - 真实接口模式测试（patch MOCK_MODE=False）
# ---------------------------------------------------------------------------

def test_query_knowledge_base_real_mode():
    """MOCK_MODE=False 时走 httpx 真实调用"""
    with patch("tools.knowledge_base.MOCK_MODE", False), \
         patch("tools.knowledge_base.httpx") as mock_httpx:
        mock_response = MagicMock()
        mock_response.json.return_value = {"found": True, "answer": "带身份证即可", "source": "kb"}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        result = query_knowledge_base.invoke({"query": "营业执照"})
        parsed = json.loads(result)
        assert parsed["found"] is True
        assert "身份证" in parsed["answer"]


def test_query_knowledge_base_timeout_fallback():
    """MOCK_MODE=False 超时时返回 source=timeout"""
    with patch("tools.knowledge_base.MOCK_MODE", False), \
         patch("tools.knowledge_base.httpx") as mock_httpx:
        import httpx as real_httpx
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = real_httpx.TimeoutException("timeout")
        mock_httpx.Client.return_value = mock_client
        mock_httpx.TimeoutException = real_httpx.TimeoutException

        result = query_knowledge_base.invoke({"query": "test"})
        parsed = json.loads(result)
        assert parsed["found"] is False
        assert parsed["source"] == "timeout"


# ---------------------------------------------------------------------------
# 工单 - 模拟模式测试
# ---------------------------------------------------------------------------

_FULL_WATER_ELEMENTS = {
    "address": "XX路88号",
    "start_time": "2026-04-07 09:00",
    "reason": "不明原因",
}


def test_submit_ticket_mock_mode(tmp_path):
    """MOCK_MODE=True 时生成模拟工单号并保存到本地"""
    with patch("tools.ticket_api.MOCK_MODE", True), \
         patch("tools.ticket_api.FALLBACK_DIR", str(tmp_path)):
        result = submit_ticket.invoke({
            "complaint_type": "WATER_OUTAGE",
            "elements": _FULL_WATER_ELEMENTS,
            "session_id": "mock-001",
        })
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["ticket_id"] is not None
        assert len(parsed["ticket_id"]) > 0
        # 文件应被保存
        saved = list(tmp_path.glob("ticket_*.json"))
        assert len(saved) == 1


def test_submit_ticket_rejected_when_missing_elements():
    """必填要素缺失时拒绝提交"""
    result = submit_ticket.invoke({
        "complaint_type": "WATER_OUTAGE",
        "elements": {"address": "XX路88号"},  # 缺少 start_time 和 reason
        "session_id": "test-reject",
    })
    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "停水开始时间" in parsed["error"]
    assert "停水原因" in parsed["error"]


# ---------------------------------------------------------------------------
# 工单 - 真实接口模式测试
# ---------------------------------------------------------------------------

def test_submit_ticket_real_mode():
    """MOCK_MODE=False 时走 httpx 真实调用"""
    with patch("tools.ticket_api.MOCK_MODE", False), \
         patch("tools.ticket_api.httpx") as mock_httpx:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ticket_id": "20240115-00234", "status": "created"}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        result = submit_ticket.invoke({
            "complaint_type": "WATER_OUTAGE",
            "elements": _FULL_WATER_ELEMENTS,
            "session_id": "test-001",
        })
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["ticket_id"] == "20240115-00234"


def test_submit_ticket_failure_saves_locally(tmp_path):
    """MOCK_MODE=False 接口失败时降级保存到本地"""
    with patch("tools.ticket_api.MOCK_MODE", False), \
         patch("tools.ticket_api.httpx") as mock_httpx:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception("connection refused")
        mock_httpx.Client.return_value = mock_client

        with patch("tools.ticket_api.FALLBACK_DIR", str(tmp_path)):
            result = submit_ticket.invoke({
                "complaint_type": "WATER_OUTAGE",
                "elements": _FULL_WATER_ELEMENTS,
                "session_id": "test-002",
            })
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert parsed["saved_locally"] is True
            saved_files = list(tmp_path.glob("*.json"))
            assert len(saved_files) == 1

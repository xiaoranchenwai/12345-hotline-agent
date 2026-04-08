"""utils/response_guard.py 单元测试"""

from utils.response_guard import build_element_reminder, enforce_single_question


class TestEnforceSingleQuestion:
    """enforce_single_question 测试"""

    def test_no_question_returns_as_is(self):
        text = "好的，我已经记录了您的信息。"
        result, truncated = enforce_single_question(text)
        assert result == text
        assert truncated is False

    def test_single_question_returns_as_is(self):
        text = "非常抱歉听到您遇到了停水问题。请问您的详细地址是？"
        result, truncated = enforce_single_question(text)
        assert result == text
        assert truncated is False

    def test_multiple_questions_keeps_first_only(self):
        text = (
            "您好，很抱歉听到您这边停水了。"
            "请问您能提供停水的具体地址吗？"
            "停水发生的时间是什么时候？"
            "是否有其他异常情况？"
        )
        result, truncated = enforce_single_question(text)
        assert truncated is True
        assert result.count("？") == 1
        assert "具体地址" in result
        assert "时间" not in result

    def test_preserves_empathy_before_question(self):
        text = "非常理解您的困扰，我们一定认真处理。请问具体地址是？另外什么时候开始的？"
        result, truncated = enforce_single_question(text)
        assert truncated is True
        assert "理解您的困扰" in result
        assert "具体地址" in result
        assert "什么时候" not in result

    def test_english_question_marks(self):
        text = "What is the address? When did it start? Any other issues?"
        result, truncated = enforce_single_question(text)
        assert truncated is True
        assert result.count("?") == 1
        assert "address" in result
        assert "start" not in result

    def test_mixed_question_marks(self):
        text = "请问地址是？What time?"
        result, truncated = enforce_single_question(text)
        assert truncated is True
        assert "地址" in result
        assert "time" not in result

    def test_empty_string(self):
        result, truncated = enforce_single_question("")
        assert result == ""
        assert truncated is False

    def test_multiline_multiple_questions(self):
        text = "您好！\n请问停水地址是哪里？\n大概从什么时候开始停水的？\n有没有其他异常？"
        result, truncated = enforce_single_question(text)
        assert truncated is True
        assert result.count("？") == 1
        assert "地址" in result
        assert "什么时候" not in result


class TestBuildElementReminder:
    """build_element_reminder 测试"""

    def test_water_outage_lists_all_required(self):
        """停水投诉应列出所有必填要素，让 LLM 自行判断"""
        messages = [
            {"role": "user", "content": "我家停水了"},
            {"role": "assistant", "content": "请问您的详细地址是？"},
        ]
        reminder = build_element_reminder(messages)
        assert reminder is not None
        assert "停水投诉" in reminder
        assert "详细地址" in reminder
        assert "停水开始时间" in reminder
        assert "停水原因" in reminder

    def test_water_outage_still_lists_all_after_partial_collection(self):
        """即使部分要素已收集，提醒仍列出全部，由 LLM 判断有效性"""
        messages = [
            {"role": "user", "content": "我家停水了"},
            {"role": "assistant", "content": "请问您的详细地址是？"},
            {"role": "user", "content": "光谷金融港A16栋"},
        ]
        reminder = build_element_reminder(messages)
        # 全部必填要素都应列出
        assert "详细地址" in reminder
        assert "停水开始时间" in reminder
        assert "停水原因" in reminder

    def test_noise_complaint_detection(self):
        messages = [
            {"role": "user", "content": "楼上噪音太大了"},
            {"role": "assistant", "content": "请问噪音来源是哪里？"},
        ]
        reminder = build_element_reminder(messages)
        assert "噪音扰民" in reminder
        assert "噪音来源位置" in reminder

    def test_includes_no_submit_instruction(self):
        messages = [
            {"role": "user", "content": "停水了"},
            {"role": "assistant", "content": "地址在哪？"},
        ]
        reminder = build_element_reminder(messages)
        assert "不要提交工单" in reminder

    def test_includes_vague_answer_hint(self):
        """提醒应包含模糊回答的示例提示"""
        messages = [
            {"role": "user", "content": "停水了"},
            {"role": "assistant", "content": "地址在哪？"},
        ]
        reminder = build_element_reminder(messages)
        assert "模糊回答" in reminder

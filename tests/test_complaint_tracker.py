"""utils/complaint_tracker.py 单元测试

覆盖场景：
1. 地址模糊时的状态追踪
2. 停水过程中插入停电投诉
"""

from utils.complaint_tracker import ComplaintTracker


class TestComplaintDetection:
    """投诉类型检测"""

    def test_detect_water_outage(self):
        tracker = ComplaintTracker()
        assert tracker.detect_complaint_type("我家停水了") == "WATER_OUTAGE"

    def test_detect_power_outage(self):
        tracker = ComplaintTracker()
        assert tracker.detect_complaint_type("现在也没电了") == "POWER_OUTAGE"

    def test_detect_noise(self):
        tracker = ComplaintTracker()
        assert tracker.detect_complaint_type("楼上太吵了") == "NOISE_COMPLAINT"

    def test_no_complaint(self):
        tracker = ComplaintTracker()
        assert tracker.detect_complaint_type("你好") is None


class TestSingleComplaint:
    """单个投诉的状态追踪"""

    def test_new_complaint_becomes_active(self):
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        assert len(tracker.complaints) == 1
        assert tracker.active is not None
        assert tracker.active.complaint_type == "WATER_OUTAGE"

    def test_missing_labels_initially_all(self):
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        missing = tracker.active.missing_labels
        assert "详细地址" in missing
        assert "停水开始时间" in missing
        assert "停水原因" in missing

    def test_record_element_reduces_missing(self):
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.record_element("WATER_OUTAGE", "address", "光谷金融港A16栋")
        missing = tracker.active.missing_labels
        assert "详细地址" not in missing
        assert "停水开始时间" in missing

    def test_is_complete_when_all_collected(self):
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.record_element("WATER_OUTAGE", "address", "光谷金融港A16栋")
        tracker.record_element("WATER_OUTAGE", "start_time", "今早9点")
        tracker.record_element("WATER_OUTAGE", "reason", "不清楚")
        assert tracker.active.is_complete is True

    def test_duplicate_complaint_type_not_created(self):
        """同类型投诉还在收集中时，不会重复创建"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.update_from_user_message("停水好久了")
        assert len(tracker.complaints) == 1


class TestVagueAddress:
    """场景1：地址模糊时的状态摘要"""

    def test_summary_lists_all_required_elements(self):
        """摘要应列出所有必填要素，让 LLM 自行判断哪些已收集"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        summary = tracker.build_status_summary()
        assert "详细地址" in summary
        assert "停水开始时间" in summary
        assert "停水原因" in summary

    def test_summary_tells_llm_to_judge(self):
        """摘要应指示 LLM 根据对话上下文自行判断"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        summary = tracker.build_status_summary()
        assert "已有效提供" in summary or "有效提供" in summary


class TestMultiComplaintInterrupt:
    """场景2：停水过程中插入停电投诉"""

    def test_new_complaint_added_during_collection(self):
        """停水还在收集中，用户提到停电，应创建第二个投诉"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.record_element("WATER_OUTAGE", "address", "光谷金融港A16栋")

        # 用户中途提到停电
        result = tracker.update_from_user_message("现在也没电了")
        assert result == "POWER_OUTAGE"
        assert len(tracker.complaints) == 2

    def test_active_stays_on_first_complaint(self):
        """新投诉加入后，当前活跃投诉不切换（先完成当前的）"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.update_from_user_message("现在也没电了")
        # 停水还在收集中，应该仍是活跃投诉
        assert tracker.active.complaint_type == "WATER_OUTAGE"

    def test_switch_to_pending_after_submit(self):
        """停水提交后，自动切换到停电"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.update_from_user_message("现在也没电了")

        tracker.mark_submitted("WATER_OUTAGE")
        assert tracker.active is not None
        assert tracker.active.complaint_type == "POWER_OUTAGE"

    def test_summary_shows_both_complaints(self):
        """摘要应同时显示两个投诉的状态"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.update_from_user_message("现在也没电了")

        summary = tracker.build_status_summary()
        assert "停水投诉" in summary
        assert "停电投诉" in summary
        assert "当前处理" in summary
        assert "等待处理" in summary

    def test_summary_after_first_submitted(self):
        """停水提交后，摘要应显示停水已完成、停电变为当前"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.update_from_user_message("现在也没电了")
        tracker.mark_submitted("WATER_OUTAGE")

        summary = tracker.build_status_summary()
        assert "已提交" in summary
        assert "当前处理" in summary
        assert "停电投诉" in summary

    def test_summary_shows_pending_reminder(self):
        """有等待投诉时，摘要应提醒处理完当前后还有其他"""
        tracker = ComplaintTracker()
        tracker.update_from_user_message("我家停水了")
        tracker.update_from_user_message("现在也没电了")

        summary = tracker.build_status_summary()
        assert "还需处理" in summary

    def test_no_summary_when_no_complaints(self):
        tracker = ComplaintTracker()
        assert tracker.build_status_summary() is None

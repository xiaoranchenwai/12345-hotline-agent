"""知识库 API 调用工具 - 封装为 LangChain tool 可用的同步函数

设置环境变量 MOCK_SERVICES=true 时使用内置模拟数据，无需真实接口。
"""

import json
import os

import httpx
from langchain_core.tools import tool


KNOWLEDGE_BASE_URL = os.getenv("KNOWLEDGE_BASE_URL", "http://localhost:8080/api/query")
KNOWLEDGE_BASE_TOKEN = os.getenv("KNOWLEDGE_BASE_TOKEN", "")
MOCK_MODE = os.getenv("MOCK_SERVICES", "true").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# 模拟知识库数据
# ---------------------------------------------------------------------------
_MOCK_KB = {
    "营业执照": {
        "answer": "办理营业执照需要以下材料：\n1. 身份证原件及复印件\n2. 经营场所证明（租赁合同或房产证）\n3. 1寸照片2张\n4. 《企业名称预先核准通知书》\n办理地点：各区行政服务中心市场监管窗口，工作日 9:00-17:00。",
        "source": "市市场监督管理局",
    },
    "社保": {
        "answer": "社保查询方式：\n1. 登录当地人社局官网或APP\n2. 携带身份证到社保经办窗口查询\n3. 拨打 12333 人社服务热线\n缴费标准以当年度公布为准。",
        "source": "市人力资源和社会保障局",
    },
    "居住证": {
        "answer": "居住证办理流程：\n1. 居住登记满半年\n2. 携带身份证、居住证明到居住地派出所申请\n3. 15个工作日内领取\n所需材料：身份证、住房证明（租赁合同等）、近期照片。",
        "source": "市公安局",
    },
    "停水": {
        "answer": "临时停水期间您可以：\n1. 关注当地供水公司公众号获取恢复时间\n2. 拨打供水热线 96116 查询\n3. 申请临时供水：携带身份证到所在街道办事处提交申请\n紧急用水可联系社区协调临时水源。",
        "source": "市供水集团",
    },
    "停电": {
        "answer": "停电相关信息：\n1. 查询计划停电：关注供电公司公众号或拨打 95598\n2. 报修故障停电：拨打 95598\n3. 停电补偿：非计划停电超过24小时可申请补偿\n紧急情况请拨打 119。",
        "source": "市供电公司",
    },
    "公积金": {
        "answer": "公积金提取流程：\n1. 登录公积金管理中心官网或APP\n2. 选择提取类型（购房、租房、还贷等）\n3. 上传相关材料\n4. 审核通过后3个工作日到账\n咨询热线：12329。",
        "source": "市住房公积金管理中心",
    },
    "垃圾分类": {
        "answer": "垃圾分类标准：\n1. 可回收物（蓝桶）：纸张、塑料、金属、玻璃\n2. 有害垃圾（红桶）：电池、灯管、药品\n3. 厨余垃圾（绿桶）：剩菜剩饭、果皮\n4. 其他垃圾（灰桶）：以上之外的生活垃圾\n违规投放可处50-200元罚款。",
        "source": "市城市管理局",
    },
}


def _mock_query(query: str) -> dict:
    """在模拟数据中按关键词匹配"""
    for keyword, item in _MOCK_KB.items():
        if keyword in query:
            return {"found": True, "answer": item["answer"], "source": item["source"]}
    # 未匹配到，返回兜底
    return {
        "found": False,
        "answer": None,
        "source": "mock_no_match",
    }


@tool
def query_knowledge_base(query: str, category: str = "") -> str:
    """调用政务知识库接口检索答案。参数 query 为用户的咨询问题关键词，category 可选分类过滤。
    返回 JSON 字符串，包含 found(bool), answer(str|null), source(str)。"""
    if MOCK_MODE:
        return json.dumps(_mock_query(query), ensure_ascii=False)

    try:
        with httpx.Client(timeout=3.0) as client:
            headers = {}
            if KNOWLEDGE_BASE_TOKEN:
                headers["Authorization"] = f"Bearer {KNOWLEDGE_BASE_TOKEN}"
            response = client.post(
                KNOWLEDGE_BASE_URL,
                json={"query": query, "category": category or None},
                headers=headers,
            )
            response.raise_for_status()
            return json.dumps(response.json(), ensure_ascii=False)
    except httpx.TimeoutException:
        return json.dumps({"found": False, "answer": None, "source": "timeout"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"found": False, "answer": None, "source": f"error: {str(e)}"}, ensure_ascii=False)

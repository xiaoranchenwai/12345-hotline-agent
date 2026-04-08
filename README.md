# 12345-hotline-agent

12345 政务服务热线智能客服系统 —— 基于 **DeepAgents / LangGraph** 框架的多智能体客服系统，通过意图分类将市民诉求路由至投诉、咨询、建议等子智能体进行处理。

## 功能特性

- **多智能体协作** — Supervisor → Sub-agent 路由架构，自动识别用户意图并分派至对应子智能体
- **投诉要素采集** — 支持 6 类投诉场景（停水、停电、噪音扰民、道路损坏、燃气问题、其他），按 schema 结构化采集必填要素
- **多投诉处理** — 支持同一会话中处理多个投诉，任务栈管理与中断深度控制
- **知识库查询** — 政策法规知识库检索，支持 mock/real 双模式
- **工单提交** — 自动校验必填要素后提交工单，失败时本地持久化兜底
- **多端接入** — CLI / FastAPI API / Gradio Web UI 三种接入方式

## 架构

```
用户输入 (CLI / FastAPI / Gradio)
    ↓
Supervisor Agent (意图分类)
    ↓
    ├── 投诉子智能体 → 要素采集 → 工单提交
    ├── 咨询子智能体 → 知识库查询 → 回复
    ├── 建议子智能体 → 归纳总结 → 温馨回复
    └── 要素提取子智能体 → 信息校验
```

## 快速开始

### 环境要求

- Python >= 3.11

### 安装

```bash
pip install -e .
```

### 配置

复制 `.env.example` 为 `.env` 并修改：

```bash
# LLM 服务配置
LLM_BASE_URL=http://your-llm-server/v1
LLM_MODEL_NAME=your-model
LLM_API_KEY=your-key

# Mock 模式（离线开发）
MOCK_SERVICES=true
```

### 运行

```bash
# 命令行单轮对话
python main.py --message "我家停水了"

# 命令行交互模式
python main.py --interactive

# FastAPI 服务
python main.py --serve --host 0.0.0.0 --port 8080

# Gradio Web UI
python main.py --gradio --host 0.0.0.0 --port 8080
```

## 项目结构

```
├── main.py                  # 入口文件
├── AGENTS.md                # Supervisor 系统提示词
├── agents/                  # 子智能体定义
│   ├── complaint/           # 投诉处理
│   ├── inquiry/             # 咨询处理
│   ├── suggestion/          # 建议处理
│   └── element_extraction/  # 要素提取
├── skills/                  # 可复用技能定义
├── tools/                   # 工具函数
│   ├── knowledge_base.py    # 知识库查询
│   ├── ticket_api.py        # 工单提交
│   └── session_store.py     # 会话状态管理
├── utils/                   # 辅助模块
│   ├── complaint_tracker.py # 投诉状态追踪
│   └── response_guard.py    # 回复后处理守卫
├── data/                    # 配置数据
│   ├── complaint_schemas.json
│   └── intent_keywords.json
└── tests/                   # 测试
```

## 测试

```bash
pytest tests/ -v
```

## License

MIT

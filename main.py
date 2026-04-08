"""12345 热线智能客服系统入口 - CLI + FastAPI Web API"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from rich.console import Console
from rich.panel import Panel

from tools.knowledge_base import query_knowledge_base
from tools.ticket_api import submit_ticket
from utils.complaint_tracker import ComplaintTracker
from utils.response_guard import enforce_single_question

load_dotenv(dotenv_path='/home/zhengxin/Documents/workspace/12345-hotline-agent/.env')

console = Console()

BASE_DIR = Path(__file__).parent
SESSION_DIR = os.getenv("SESSION_DIR", str(BASE_DIR / "sessions"))


def create_model():
    """创建 LLM 实例（兼容 OpenAI API 格式的本地模型）"""
    return init_chat_model(
        model=os.getenv("LLM_MODEL_NAME", "qwen"),
        model_provider="openai",
        temperature=0,
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:8000/v1"),
        api_key=os.getenv("LLM_API_KEY", "none"),
        timeout=30,
    )


def _read_agent_prompt(relative_path: str) -> str:
    """读取 AGENTS.md 文件内容作为 system_prompt"""
    return (BASE_DIR / relative_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# SubAgent 规格定义（deepagents 要求 dict 格式，包含 name/description/system_prompt）
# ---------------------------------------------------------------------------

def _element_extraction_subagent_spec() -> dict:
    """要素提取子智能体规格"""
    return {
        "name": "element_extraction_agent",
        "description": "分析对话历史，逐一核查投诉要素是否已收集，输出结构化 JSON 报告（collected/missing/ambiguous/next_question）。仅做分析，不与用户对话。",
        "system_prompt": _read_agent_prompt("agents/element_extraction/AGENTS.md"),
        "skills": [str(BASE_DIR / "skills" / "complaint-type-mapping")],
        "tools": [],
    }


def _inquiry_subagent_spec() -> dict:
    """咨询子智能体规格"""
    return {
        "name": "inquiry_agent",
        "description": "处理政策法规、办事流程等咨询类问题，优先调用知识库接口获取权威答案，无结果时使用大模型知识兜底并附免责声明。",
        "system_prompt": _read_agent_prompt("agents/inquiry/AGENTS.md"),
        "skills": [str(BASE_DIR / "skills" / "knowledge-base-query")],
        "tools": [query_knowledge_base],
    }


def _suggestion_subagent_spec() -> dict:
    """建议子智能体规格"""
    return {
        "name": "suggestion_agent",
        "description": "接收市民对城市治理、公共服务的改进建议，进行要点提炼和分类，给予积极有温度的回应。",
        "system_prompt": _read_agent_prompt("agents/suggestion/AGENTS.md"),
        "skills": [str(BASE_DIR / "skills" / "warm-response-generation")],
        "tools": [],
    }


def _complaint_subagent_spec() -> dict:
    """投诉子智能体规格（内含要素提取子智能体）"""
    return {
        "name": "complaint_agent",
        "description": "处理市民投诉，识别投诉类型，逐步收集必填要素，收集完毕后提交工单。支持停水、停电、噪音、道路损坏、燃气等投诉类型。",
        "system_prompt": _read_agent_prompt("agents/complaint/AGENTS.md"),
        "skills": [
            str(BASE_DIR / "skills" / "complaint-type-mapping"),
            str(BASE_DIR / "skills" / "empathy-response"),
            str(BASE_DIR / "skills" / "ticket-submission"),
        ],
        "tools": [query_knowledge_base, submit_ticket],
    }


def create_supervisor_agent():
    """创建主智能体（Supervisor）- 意图分类 + 路由调度"""
    model = create_model()

    return create_deep_agent(
        model=model,
        memory=[str(BASE_DIR / "AGENTS.md")],
        skills=[
            str(BASE_DIR / "skills" / "intent-classification"),
            str(BASE_DIR / "skills" / "fallback-handling"),
            str(BASE_DIR / "skills" / "context-switch"),
            str(BASE_DIR / "skills" / "multi-complaint"),
        ],
        tools=[query_knowledge_base, submit_ticket],
        subagents=[
            _complaint_subagent_spec(),
            _inquiry_subagent_spec(),
            _suggestion_subagent_spec(),
        ],
        backend=FilesystemBackend(root_dir=SESSION_DIR),
    )


def run_cli():
    """命令行交互模式"""
    parser = argparse.ArgumentParser(
        description="12345 热线智能客服系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --message "我家停水了"
  python main.py --interactive
  python main.py --serve
        """,
    )
    parser.add_argument("--message", type=str, help="单次消息模式")
    parser.add_argument("--interactive", action="store_false", help="交互式对话模式")
    parser.add_argument("--serve", action="store_true", help="启动 Web API 服务")
    parser.add_argument("--gradio", action="store_true", help="启动 Gradio 对话界面")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")

    args = parser.parse_args()

    if args.serve:
        import uvicorn
        uvicorn.run(create_web_app(), host=args.host, port=args.port)
        return

    if args.gradio:
        from gradio_app import build_app
        build_app().launch(server_name=args.host, server_port=args.port, share=False)
        return

    console.print(Panel("12345 热线智能客服系统", style="bold blue"))
    console.print("[dim]正在初始化智能体...[/dim]")
    agent = create_supervisor_agent()
    console.print("[green]初始化完成！[/green]\n")

    if args.message:
        _process_single(agent, args.message)
    else:
        _run_interactive(agent)


def _process_single(agent, message: str):
    """处理单条消息"""
    console.print(f"[bold cyan]用户:[/bold cyan] {message}")
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": message}]})
        answer = result["messages"][-1]
        content = answer.content if hasattr(answer, "content") else str(answer)
        content, _ = enforce_single_question(content)
        console.print(Panel(f"[bold green]客服:[/bold green]\n\n{content}", border_style="green"))
    except Exception as e:
        console.print(Panel(f"[bold red]错误:[/bold red] {str(e)}", border_style="red"))
        sys.exit(1)


def _run_interactive(agent):
    """交互式多轮对话"""
    console.print("[dim]输入 'quit' 或 'exit' 退出对话[/dim]\n")
    messages = []
    tracker = ComplaintTracker()

    while True:
        try:
            user_input = console.input("[bold cyan]用户> [/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            console.print("\n[dim]感谢使用 12345 热线智能客服，祝您生活愉快！[/dim]")
            break

        if not user_input.strip():
            continue

        # 检测新投诉
        tracker.update_from_user_message(user_input)

        # 构建带状态摘要的消息列表
        invoke_messages = list(messages)
        invoke_messages.append({"role": "user", "content": user_input})
        status_summary = tracker.build_status_summary()
        if status_summary:
            invoke_messages.append({"role": "system", "content": status_summary})

        try:
            result = agent.invoke({"messages": invoke_messages})
            answer = result["messages"][-1]
            content = answer.content if hasattr(answer, "content") else str(answer)
            content, _ = enforce_single_question(content)
            console.print(f"\n[bold green]客服>[/bold green] {content}\n")
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": content})
        except Exception as e:
            console.print(f"\n[bold red]系统错误:[/bold red] {str(e)}\n")
            console.print("[dim]非常抱歉，系统遇到了一些问题。请稍后再试或拨打人工热线 12345。[/dim]\n")


def create_web_app():
    """创建 FastAPI 应用"""
    from fastapi import FastAPI
    from pydantic import BaseModel

    web_app = FastAPI(title="12345 热线智能客服 API", version="0.1.0")

    _sessions: dict = {}

    class ChatRequest(BaseModel):
        session_id: str = ""
        message: str

    class ChatResponse(BaseModel):
        session_id: str
        reply: str
        intent: str = ""
        error: str = ""

    def _get_or_create_session(session_id: str):
        if session_id not in _sessions:
            _sessions[session_id] = {
                "agent": create_supervisor_agent(),
                "messages": [],
                "tracker": ComplaintTracker(),
            }
        return _sessions[session_id]

    @web_app.post("/api/chat", response_model=ChatResponse)
    def chat(req: ChatRequest):
        session_id = req.session_id or str(uuid.uuid4())
        session = _get_or_create_session(session_id)
        agent = session["agent"]
        messages = session["messages"]
        tracker: ComplaintTracker = session["tracker"]

        tracker.update_from_user_message(req.message)

        invoke_messages = list(messages)
        invoke_messages.append({"role": "user", "content": req.message})
        status_summary = tracker.build_status_summary()
        if status_summary:
            invoke_messages.append({"role": "system", "content": status_summary})

        try:
            result = agent.invoke({"messages": invoke_messages})
            answer = result["messages"][-1]
            content = answer.content if hasattr(answer, "content") else str(answer)
            content, _ = enforce_single_question(content)
            messages.append({"role": "user", "content": req.message})
            messages.append({"role": "assistant", "content": content})
            return ChatResponse(session_id=session_id, reply=content)
        except Exception as e:
            return ChatResponse(
                session_id=session_id,
                reply="非常抱歉，当前系统正在维护中，请稍后再试或直接拨打人工热线 12345。",
                error=str(e),
            )

    @web_app.get("/health")
    def health():
        return {"status": "ok"}

    return web_app


# Support `uvicorn main:app`
app = None

def __getattr__(name):
    if name == "app":
        global app
        if app is None:
            app = create_web_app()
        return app
    raise AttributeError(name)


if __name__ == "__main__":
    run_cli()

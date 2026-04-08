"""12345 热线智能客服 - Gradio 对话界面"""

import os
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

from main import create_supervisor_agent
from utils.complaint_tracker import ComplaintTracker
from utils.response_guard import enforce_single_question

load_dotenv(dotenv_path='/home/zhengxin/Documents/workspace/12345-hotline-agent/.env')

# 每个会话独立持有 agent 和消息历史
_session_agents: dict = {}


def _get_or_create_agent(session_hash: str):
    """按会话获取或创建 agent 实例"""
    if session_hash not in _session_agents:
        _session_agents[session_hash] = {
            "agent": create_supervisor_agent(),
            "messages": [],
            "tracker": ComplaintTracker(),
        }
    return _session_agents[session_hash]


def chat(user_message: str, history: list, request: gr.Request):
    """Gradio 聊天回调 — 支持多轮对话"""
    if not user_message.strip():
        return "", history

    session_hash = request.session_hash or "default"
    session = _get_or_create_agent(session_hash)

    tracker: ComplaintTracker = session["tracker"]

    # 检测用户消息中是否有新投诉
    tracker.update_from_user_message(user_message)

    # 注入状态摘要
    status_summary = tracker.build_status_summary()
    invoke_messages = list(session["messages"])
    invoke_messages.append({"role": "user", "content": user_message})
    if status_summary:
        invoke_messages.append({"role": "system", "content": status_summary})

    try:
        result = session["agent"].invoke({"messages": invoke_messages})
        answer = result["messages"][-1]
        reply = answer.content if hasattr(answer, "content") else str(answer)
        reply, _ = enforce_single_question(reply)
    except Exception as e:
        reply = f"非常抱歉，系统遇到了一些问题（{type(e).__name__}）。请稍后再试或拨打人工热线 12345。"

    session["messages"].append({"role": "user", "content": user_message})
    session["messages"].append({"role": "assistant", "content": reply})
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    return "", history


def clear_session(request: gr.Request):
    """清空当前会话"""
    session_hash = request.session_hash or "default"
    _session_agents.pop(session_hash, None)
    return [], ""


EXAMPLES = [
    "我家从昨晚开始停水了",
    "办理营业执照需要哪些材料？",
    "建议在XX公园增加健身器材",
    "我们小区噪音太大了，施工到半夜",
    "路面有个大坑洞，很危险",
]


def build_app() -> gr.Blocks:
    """构建 Gradio 界面"""
    with gr.Blocks(
        title="12345 热线智能客服",
        theme=gr.themes.Soft(),
        css="""
        .header { text-align: center; padding: 10px; }
        .disclaimer { font-size: 12px; color: #888; text-align: center; }
        """,
    ) as app:
        gr.HTML(
            """
            <div class="header">
                <h1>12345 政务服务热线智能客服</h1>
                <p>支持投诉、咨询、建议三类诉求，多轮对话自动引导</p>
            </div>
            """
        )

        chatbot = gr.Chatbot(
            label="对话记录",
            height=500,
            placeholder="请输入您的诉求，例如：我家停水了...",
            
        )

        with gr.Row():
            msg = gr.Textbox(
                label="输入消息",
                placeholder="请描述您的问题...",
                scale=8,
                show_label=False,
            )
            send_btn = gr.Button("发送", variant="primary", scale=1)

        with gr.Row():
            clear_btn = gr.Button("清空对话", variant="secondary")
            gr.Examples(
                examples=EXAMPLES,
                inputs=msg,
                label="快捷输入示例",
            )

        gr.HTML('<p class="disclaimer">本系统为 AI 辅助客服，回答仅供参考，请以官方最新规定为准。</p>')

        # 事件绑定
        msg.submit(chat, inputs=[msg, chatbot], outputs=[msg, chatbot])
        send_btn.click(chat, inputs=[msg, chatbot], outputs=[msg, chatbot])
        clear_btn.click(clear_session, outputs=[chatbot, msg])

    return app


if __name__ == "__main__":
    app = build_app()
    app.launch(
        server_name=os.getenv("GRADIO_HOST", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_PORT", "7861")),
        share=False,
    )

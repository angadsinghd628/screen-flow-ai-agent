"""
LangGraph 核心状态机 + 智能检索流式接口。

图结构：trim_history → call_vlm → END

流式接口 stream_graph：
  - 用 memory_retriever 从全部历史中检索相关消息
  - 最近 N 轮完整保留 + 早期相关消息召回
  - 直接调用 ChatDoubaoVL.stream() 获取逐 token 输出
"""
from typing import AsyncIterator, Optional, List

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from agent.state import AgentState
from agent.llm_client import ChatDoubaoVL, build_text_message, build_multimodal_message
from config import RECENT_ROUNDS

# 系统提示词
SYSTEM_PROMPT = (
    "你是一个实用的桌面 AI 助手，用户可能发送文字、截图或两者结合。"
    "请仔细分析所有输入内容，给出详细、完整、有深度的回答。"
    "如果是代码问题，请解释原理并给出代码示例；"
    "如果是图表或数据，请详细解读趋势和关键信息；"
    "如果是报错信息，请分析原因并提供具体解决步骤；"
    "如果用户只是提问，请充分展开回答，不要过于简短。"
    "回答风格：专业但不啰嗦，结构清晰，善用 Markdown 排版。"
)


# ============================================================
# Node Functions
# ============================================================

def trim_history_node(state: AgentState) -> dict:
    """
    历史裁剪节点：只保留最近 N 轮（条数限制，不做 Token 检查）。
    Token 层面的控制由 stream_graph 中的智能检索负责。
    """
    messages = list(state["messages"])
    max_turns = state.get("max_turns", 10)
    max_messages = max_turns * 2

    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    return {"messages": messages}


def call_vlm_node(state: AgentState) -> dict:
    """非流式调用 VLM（graph.invoke 备用）。"""
    messages = state["messages"]
    if not messages:
        return {"messages": [AIMessage(content="没有收到任何输入。")]}

    llm = ChatDoubaoVL()
    all_messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
    response = llm.invoke(all_messages)
    return {"messages": [response]}


# ============================================================
# Graph Construction
# ============================================================

def build_graph() -> StateGraph:
    """编译 LangGraph，使用 MemorySaver 按 thread_id 持久化状态。"""
    workflow = StateGraph(AgentState)
    workflow.add_node("trim_history", trim_history_node)
    workflow.add_node("call_vlm", call_vlm_node)
    workflow.set_entry_point("trim_history")
    workflow.add_edge("trim_history", "call_vlm")
    workflow.add_edge("call_vlm", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# ============================================================
# Streaming Interface — 智能检索 + 流式输出
# ============================================================

async def stream_graph(
    graph: StateGraph,
    messages: List[BaseMessage],
    user_text: str,
    image_base64_list: Optional[List[str]] = None,
    max_turns: int = 10,
) -> AsyncIterator[str]:
    """
    流式执行：智能检索相关历史 → 拼装上下文 → 逐 token 输出。

    混合策略：
    - 最近 RECENT_ROUNDS 轮完整保留
    - 从更早历史中检索最多 MAX_RETRIEVED_MESSAGES 条相关消息
    - 移除 Token 硬上限，靠检索条数控制上下文大小

    Args:
        graph: 编译好的 LangGraph
        messages: 全部对话历史（可能很长）
        user_text: 本轮用户文本
        image_base64_list: 本轮截图的 base64 列表
        max_turns: 最大保留轮数（备份）

    Yields:
        逐 token 文本片段。
    """
    # 1. 构建本轮输入消息
    if image_base64_list:
        input_msg = build_multimodal_message(user_text, image_base64_list=image_base64_list)
    elif user_text and user_text.strip():
        input_msg = build_text_message(user_text)
    else:
        input_msg = HumanMessage(content="请描述当前看到的内容。")

    # 2. 上下文：只保留最近 N 轮（快速，不调 AI 判断）
    if messages:
        recent_count = RECENT_ROUNDS * 2
        relevant = list(messages[-recent_count:]) if len(messages) > recent_count else list(messages)
    else:
        relevant = []

    # 3. 拼装：系统提示 + 检索到的相关历史 + 本轮新消息
    all_messages = [SystemMessage(content=SYSTEM_PROMPT)] + relevant + [input_msg]

    # 4. 直接流式调用 ChatDoubaoVL
    llm = ChatDoubaoVL()
    for chunk in llm.stream(all_messages):
        if chunk.content:
            content = chunk.content
            if isinstance(content, str):
                yield content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and content:
                        block_type = block.get("type", "")
                        if "text" in block_type:
                            yield block.get("text", "")

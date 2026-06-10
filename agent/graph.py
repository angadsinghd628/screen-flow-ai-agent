"""
LangGraph 核心状态机 + 流式接口。

图结构：trim_history → call_vlm → END
  - trim_history: 裁剪过长的对话历史
  - call_vlm: 非流式调用 VLM（用于 graph.invoke）

流式接口 stream_graph：
  - 手动执行 trim_history 逻辑
  - 直接调用 ChatDoubaoVL.stream() 获取逐 token 输出
  - 保证流式结果实时显示
"""
from typing import AsyncIterator, Optional, List

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from agent.state import AgentState
from agent.llm_client import ChatDoubaoVL, build_text_message, build_multimodal_message
from config import MAX_TOKEN_ESTIMATE
from utils.token_counter import is_over_token_limit, strip_images_from_message

# 系统提示词：详细、实用地回答用户问题
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
    历史上下文裁剪节点。
    """
    messages = list(state["messages"])
    max_turns = state.get("max_turns", 10)
    max_messages = max_turns * 2

    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    if is_over_token_limit(messages, MAX_TOKEN_ESTIMATE):
        num_strip = max(0, len(messages) - 4)
        for i in range(num_strip):
            messages[i] = strip_images_from_message(messages[i])

    while is_over_token_limit(messages, MAX_TOKEN_ESTIMATE) and len(messages) > 2:
        messages = messages[2:]

    return {"messages": messages}


def call_vlm_node(state: AgentState) -> dict:
    """
    非流式调用 VLM（graph.invoke 用，保留在图中确保完整性）。
    """
    messages = state["messages"]
    if not messages:
        return {"messages": [AIMessage(content="没有收到任何输入。")]}

    llm = ChatDoubaoVL()
    # 添加系统提示词，要求精简回答
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
# Streaming Interface — 真正的逐 token 流式输出
# ============================================================

async def stream_graph(
    graph: StateGraph,
    messages: List[BaseMessage],
    user_text: str,
    image_base64_list: Optional[List[str]] = None,
    max_turns: int = 10,
) -> AsyncIterator[str]:
    """
    流式执行：取历史消息 → trim → 直接 ChatDoubaoVL.stream() 逐 token 输出。

    Args:
        graph: 编译好的 LangGraph（保留，用于未来扩）
        messages: 已有的对话历史
        user_text: 本轮用户文本
        image_base64_list: 本轮截图的 base64 列表，None/空 表示纯文本
        max_turns: 最大保留轮数

    Yields:
        逐 token 文本片段。
    """
    # 1. 构建本轮输入消息（支持多图）
    if image_base64_list:
        input_msg = build_multimodal_message(user_text, image_base64_list=image_base64_list)
    elif user_text and user_text.strip():
        input_msg = build_text_message(user_text)
    else:
        input_msg = HumanMessage(content="请描述当前看到的内容。")

    # 2. 合并历史消息，添加系统提示词要求精简
    all_messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages) + [input_msg]

    # 3. Trim 历史（保护 system prompt 不被裁剪）
    max_msgs = max_turns * 2 + 1  # +1 给 system prompt
    if len(all_messages) > max_msgs:
        # 保留 system prompt (index 0) + 最近的消息
        all_messages = [all_messages[0]] + all_messages[-(max_msgs - 1):]

    if is_over_token_limit(all_messages, MAX_TOKEN_ESTIMATE):
        # 从 index 1 开始剥离旧图片（跳过 system prompt）
        num_strip = max(0, len(all_messages) - 4)
        for i in range(1, min(num_strip + 1, len(all_messages))):
            all_messages[i] = strip_images_from_message(all_messages[i])

    while is_over_token_limit(all_messages, MAX_TOKEN_ESTIMATE) and len(all_messages) > 3:
        # 移除 index 1,2（保留 system prompt）
        all_messages = [all_messages[0]] + all_messages[3:]

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

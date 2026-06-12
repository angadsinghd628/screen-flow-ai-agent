"""
智能记忆检索 — AI 判断是否需要 + 关键词召回相关消息。

策略：
  1. AI 判断当前问题是否需要检索历史（轻量 yes/no 调用）
  2. 需要 → 关键词召回早期相关消息 + 最近 N 轮
  3. 不需要 → 只带最近 N 轮
"""
import re
from typing import List, Optional
from langchain_core.messages import BaseMessage, HumanMessage

# 中文停用词
_STOP_WORDS = set(
    "的 了 是 吗 呢 啊 吧 呀 哦 嗯 哈 嘛 呗 啦 呐 噢 嘿 哇 呵 嘻 "
    "什么 这个 那个 哪个 一个 一下 一些 怎么 怎样 怎么样 为什么 "
    "帮我 请 可以 能不能 能否 可不 会不会 "
    "在 有 和 与 或 但 而 且 虽然 因为 所以 如果 就 都 也 还 要 把 被 让 给 对 从 到 向 跟 同 比 为 除了 不只".split()
)


def keyword_rewrite(query: str) -> List[str]:
    """
    从用户输入中提取关键词（中英文 + 数字）。
    """
    if not query:
        return []

    keywords = []

    # 英文单词
    eng_words = re.findall(r'[a-zA-Z]{2,}', query)
    keywords.extend(w.lower() for w in eng_words)

    # 中文 2-4 字 n-gram
    chinese_chars = re.findall(r'[一-鿿]', query)
    for n in (4, 3, 2):
        for i in range(len(chinese_chars) - n + 1):
            word = ''.join(chinese_chars[i:i + n])
            if word not in _STOP_WORDS and word not in keywords:
                keywords.append(word)

    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result[:20]


def _extract_text(msg: BaseMessage) -> str:
    """从消息中提取纯文本内容。"""
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return " ".join(texts)
    return ""


def _score_message(msg: BaseMessage, keywords: List[str]) -> float:
    """BM25 简化版：关键词命中得分 / 文档长度归一化。"""
    text = _extract_text(msg)
    if not text or not keywords:
        return 0.0

    text_lower = text.lower()
    score = 0.0
    for kw in keywords:
        count = text_lower.count(kw)
        if count > 0:
            score += 1.0 + min(count - 1, 3) * 0.3

    doc_len = len(text)
    if doc_len > 100:
        score = score * (1.0 / max(1, doc_len / 200))
    return score


# ============================================================
# AI 判断是否需要检索
# ============================================================

_RETRIEVAL_DECISION_PROMPT = (
    "你是一个上下文判断助手。用户正在与AI进行多轮对话。"
    "请判断用户的这条新消息是否需要查看之前的对话历史才能正确回答。"
    "只回答 YES 或 NO，不要输出任何其他内容。\n\n"
    "需要检索历史的情况：\n"
    "- 用户引用了之前讨论过的话题、代码、报错等\n"
    "- 用户说'刚才那个'、'继续'、'回到xxx'\n"
    "- 需要了解之前的对话背景才能理解问题\n\n"
    "不需要检索的情况：\n"
    "- 一个全新的独立问题\n"
    "- 简单问候\n"
    "- 完全不相干的新话题\n\n"
    "最近对话内容：\n"
    "{context}\n\n"
    "用户新消息：{query}\n\n"
    "需要检索历史吗？(YES/NO):"
)

# 缓存最后一次的决策结果（同一 query 不重复调用 AI）
_last_decision: dict = {"query": "", "result": False}


def ai_should_retrieve(query: str, recent_context: str = "",
                       model_name: Optional[str] = None) -> bool:
    """
    让 AI 判断是否需要检索历史上下文。

    用最轻量的模型做 yes/no 判断，耗时约 0.5-1 秒。

    Args:
        query: 用户当前输入
        recent_context: 最近的对话摘要（用于判断）
        model_name: 指定模型名，默认用 mini

    Returns:
        True 需要检索，False 不需要
    """
    global _last_decision

    if not query or not query.strip():
        return False

    # 简单问候直接跳过，不上 AI
    q = query.strip()
    if q in {"你好", "hi", "hello", "嘿", "嗨", "早上好", "晚上好", "下午好"}:
        return False
    if len(q) <= 3:
        return False

    # 命中缓存（同一 query 不重复调 AI）
    if q == _last_decision["query"]:
        return _last_decision["result"]

    # 明显引用过去的触发词 → 直接检索，不用问 AI
    obvious_triggers = ["刚才那个", "上面那个", "前面那个", "回到刚才", "还记得上次"]
    for t in obvious_triggers:
        if t in q:
            _last_decision = {"query": q, "result": True}
            return True

    try:
        # 用轻量模型做决策
        from agent.llm_client import ChatDoubaoVL
        from langchain_core.messages import SystemMessage

        prompt = _RETRIEVAL_DECISION_PROMPT.format(
            context=recent_context or "（尚无对话历史）",
            query=q,
        )

        llm = ChatDoubaoVL(model_name=model_name or "doubao-seed-2-0-mini-260428")
        response = llm.invoke([SystemMessage(content=prompt)])
        answer = response.content.strip().upper() if hasattr(response, 'content') else ""

        result = "YES" in answer
        _last_decision = {"query": q, "result": result}
        return result

    except Exception as e:
        # API 调用失败（无网络/Key过期等）→ 回退到本地判断
        err = str(e)
        if "401" in err or "AuthenticationError" in err or "Unauthorized" in err:
            # API Key 问题 → 用关键词判断
            pass
        # 其他错误也回退
        keywords = keyword_rewrite(query)
        # 有关键词且不像是全新话题 → 尝试检索
        return len(keywords) >= 3


def needs_retrieval(query: str, recent_context: str = "") -> bool:
    """
    判断是否需要检索 — 现在由 AI 决定（别名，向后兼容）。
    """
    return ai_should_retrieve(query, recent_context)


# ============================================================
# 检索主函数
# ============================================================

def retrieve_relevant(
    query: str,
    all_messages: List[BaseMessage],
    top_k: int = 6,
    recent_rounds: int = 3,
) -> List[BaseMessage]:
    """
    从历史消息中检索与 query 最相关的消息。

    混合策略：
    - 最近 `recent_rounds` 轮完整保留
    - 更早的消息中按关键词相关性检索 top_k 条
    - 返回结果按时间顺序排列
    """
    if not all_messages:
        return []

    total = len(all_messages)
    recent_count = recent_rounds * 2

    if total <= recent_count:
        return list(all_messages)

    recent_msgs = list(all_messages[-recent_count:])
    older_msgs = list(all_messages[:-recent_count])

    keywords = keyword_rewrite(query)
    if not keywords or not older_msgs:
        return recent_msgs

    scored = []
    for i, msg in enumerate(older_msgs):
        s = _score_message(msg, keywords)
        if s > 0:
            scored.append((s, i, msg))

    scored.sort(key=lambda x: x[0], reverse=True)
    retrieved = scored[:top_k]
    retrieved.sort(key=lambda x: x[1])

    result = [m for _, _, m in retrieved] + recent_msgs

    seen_ids = set()
    final = []
    for m in result:
        mid = id(m)
        if mid not in seen_ids:
            seen_ids.add(mid)
            final.append(m)

    return final

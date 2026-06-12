"""
智能记忆检索 — 本地关键词提取 + 相关消息召回。

策略：
  1. 从用户输入中提取关键词（中英文 + 数字）
  2. 遍历全部历史消息，对每条消息计算关键词命中得分
  3. 返回得分最高的 top-K 条消息
"""
import re
from typing import List
from langchain_core.messages import BaseMessage

# 中文停用词
_STOP_WORDS = set(
    "的 了 是 吗 呢 啊 吧 呀 哦 嗯 哈 嘛 呗 啦 呐 噢 嘿 哇 呵 嘻 "
    "什么 这个 那个 哪个 一个 一下 一些 怎么 怎样 怎么样 为什么 "
    "帮我 请 可以 能不能 能否 可不 会不会 "
    "在 有 和 与 或 但 而 且 虽然 因为 所以 如果 就 都 也 还 要 把 被 让 给 对 从 到 向 跟 同 比 为 除了 不只".split()
)

# 最少关键词长度（避免太短的词）
_MIN_KEYWORD_LEN = 2


def keyword_rewrite(query: str) -> List[str]:
    """
    从用户输入中提取关键词。

    策略：
    - 中文：提取 2-4 字连续片段，过滤停用词
    - 英文：提取完整单词
    - 数字：保留
    """
    if not query:
        return []

    keywords = []

    # 1. 提取英文单词（连续字母串）
    eng_words = re.findall(r'[a-zA-Z]{2,}', query)
    keywords.extend(w.lower() for w in eng_words)

    # 2. 提取中文词（2-4字 n-gram）
    chinese_chars = re.findall(r'[一-鿿]', query)
    for n in (4, 3, 2):
        for i in range(len(chinese_chars) - n + 1):
            word = ''.join(chinese_chars[i:i + n])
            if word not in _STOP_WORDS and word not in keywords:
                keywords.append(word)

    # 3. 去重 + 限制数量
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)

    # 限制关键词数量，避免太宽泛的搜索
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
    """
    对消息计算关键词命中得分。
    使用 BM25 简化版：关键词命中次数 / 文档长度归一化。
    """
    text = _extract_text(msg)
    if not text or not keywords:
        return 0.0

    text_lower = text.lower()
    score = 0.0
    for kw in keywords:
        count = text_lower.count(kw)
        if count > 0:
            # 每个命中关键词 +1 基础分，多次命中给额外加分
            score += 1.0 + min(count - 1, 3) * 0.3

    # 长度归一化（避免长消息天然占优）
    doc_len = len(text)
    if doc_len > 100:
        score = score * (1.0 / max(1, doc_len / 200))

    return score


# 需要检索上下文的触发词（用户提到过去的对话）
_RETRIEVAL_TRIGGERS = [
    "刚才", "刚刚", "之前", "前面", "上次", "上一次",
    "那个", "哪个", "那些", "之前的",
    "继续", "接着", "回到", "回过来", "返回",
    "还记得", "之前说", "你之前",
    "再", "再问", "再说",
    "前面那个", "上面那个", "刚刚那个",
]


def needs_retrieval(query: str) -> bool:
    """
    判断当前 query 是否需要检索历史上下文。

    不需要检索的情况：
    - 简单问候（你好、早上好...）
    - 全新的独立问题（不引用过去内容）
    - 纯截图描述请求
    """
    if not query or not query.strip():
        return False

    q = query.strip().lower()

    # 不检索：简单问候
    greetings = {"你好", "hi", "hello", "嘿", "嗨", "早上好", "晚上好", "下午好"}
    if q in greetings or len(q) <= 3:
        return False

    # 触发词 → 需要检索
    for trigger in _RETRIEVAL_TRIGGERS:
        if trigger in q:
            return True

    # 关键词太少（≤2 个有效词）→ 可能是新话题，不检索
    keywords = keyword_rewrite(query)
    if len(keywords) <= 2:
        return False

    # 默认检索（有一定信息量的 query 都检索，开销很小）
    return True


def retrieve_relevant(
    query: str,
    all_messages: List[BaseMessage],
    top_k: int = 6,
    recent_rounds: int = 3,
) -> List[BaseMessage]:
    """
    从历史消息中检索与 query 最相关的消息。

    混合策略：
    - 最近 `recent_rounds` 轮（recent_rounds*2 条）完整保留
    - 更早的消息中按关键词相关性检索 top_k 条
    - 返回结果按时间顺序排列

    Args:
        query: 用户当前输入
        all_messages: 全部历史消息
        top_k: 检索返回的最大消息数
        recent_rounds: 完整保留的最近轮数

    Returns:
        筛选后的消息列表（按时间顺序）
    """
    if not all_messages:
        return []

    total = len(all_messages)
    recent_count = recent_rounds * 2  # 每轮 1Q+1A

    # 最近 N 轮完整保留
    if total <= recent_count:
        return list(all_messages)

    recent_msgs = list(all_messages[-recent_count:])
    older_msgs = list(all_messages[:-recent_count])

    # 没有关键词 → 只返回最近的消息
    keywords = keyword_rewrite(query)
    if not keywords or not older_msgs:
        return recent_msgs

    # 对更早的消息评分
    scored = []
    for i, msg in enumerate(older_msgs):
        s = _score_message(msg, keywords)
        if s > 0:
            scored.append((s, i, msg))

    # 按得分降序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 取 top_k，按原始时间顺序排列
    retrieved = scored[:top_k]
    retrieved.sort(key=lambda x: x[1])  # 按原始索引排序

    result = [m for _, _, m in retrieved] + recent_msgs

    # 避免重复
    seen_ids = set()
    final = []
    for m in result:
        mid = id(m)
        if mid not in seen_ids:
            seen_ids.add(mid)
            final.append(m)

    return final

"""
豆包 VL 自定义 LangChain ChatModel — 封装火山引擎方舟 Ark SDK (responses API)。

该模块创建了一个自定义的 BaseChatModel 子类 ChatDoubaoVL，
使豆包 VL 的 responses.create API 可以无缝集成到 LangGraph 的流式管道中。

消息格式转换：
  LangChain (OpenAI-style)  →  Ark (responses-style)
  ─────────────────────────────────────────────────
  {"type": "text", ...}      →  {"type": "input_text", "text": ...}
  {"type": "image_url", ...} →  {"type": "input_image", "image_url": ...}
"""
import base64
from typing import Any, Iterator, List, Mapping, Optional, Sequence, Union

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel, generate_from_stream
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    AIMessageChunk,
    SystemMessage,
    ChatMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field, PrivateAttr

from volcenginesdkarkruntime import Ark

from config import ARK_API_KEY, ARK_BASE_URL, DOUBAO_MODEL_NAME, MAX_OUTPUT_TOKENS


class ChatDoubaoVL(BaseChatModel):
    """
    豆包 VL 多模态大模型 LangChain 封装。

    使用火山引擎方舟 Ark SDK 的 responses.create API，
    支持文本 + 图片多模态输入和流式输出。

    用法:
        llm = ChatDoubaoVL()
        messages = [HumanMessage(content=[
            {"type": "text", "text": "这是什么?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
        ])]
        response = llm.invoke(messages)          # 非流式
        async for chunk in llm.astream(messages): # 流式
            print(chunk.content)
    """

    model_name: str = Field(default="")
    api_key: str = Field(default="")
    base_url: str = Field(default=ARK_BASE_URL)
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=MAX_OUTPUT_TOKENS)

    _client: Ark = PrivateAttr()

    def __init__(self, **kwargs):
        # 动态读取 API Key（支持运行时修改）
        from config import ARK_API_KEY, DOUBAO_MODEL_NAME
        if "api_key" not in kwargs:
            kwargs["api_key"] = ARK_API_KEY
        if "model_name" not in kwargs:
            kwargs["model_name"] = DOUBAO_MODEL_NAME
        super().__init__(**kwargs)
        self._create_client()

    def _create_client(self):
        """（重新）创建 Ark 客户端。API Key 变更后可调用。"""
        self._client = Ark(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def reload_api_key(self, new_key: str):
        """更新 API Key 并重建客户端。"""
        self.api_key = new_key
        self._create_client()

    # ============================================================
    # LangChain 要求的属性
    # ============================================================

    @property
    def _llm_type(self) -> str:
        return "doubao-vl"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "model_name": self.model_name,
            "base_url": self.base_url,
        }

    # ============================================================
    # 非流式生成
    # ============================================================

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> ChatResult:
        """非流式调用 Ark responses.create。"""
        ark_input = self._convert_messages_to_ark(messages)

        response = self._client.responses.create(
            model=self.model_name,
            input=ark_input,
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )

        # 从 Response 对象中提取输出文本
        text = ""
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "content") and item.content:
                    for part in item.content:
                        if hasattr(part, "text") and part.text:
                            text += part.text

        message = AIMessage(content=text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    # ============================================================
    # 流式生成
    # ============================================================

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> Iterator[ChatGenerationChunk]:
        """流式调用 Ark responses.create(stream=True)。"""
        ark_input = self._convert_messages_to_ark(messages)

        stream = self._client.responses.create(
            model=self.model_name,
            input=ark_input,
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            stream=True,
        )

        for event in stream:
            # response.output_text.delta — 逐 token 文本输出
            if hasattr(event, "type") and event.type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    chunk = ChatGenerationChunk(message=AIMessageChunk(content=delta))
                    if run_manager:
                        run_manager.on_llm_new_token(delta, chunk=chunk)
                    yield chunk

    # ============================================================
    # LangChain → Ark 消息格式转换
    # ============================================================

    def _convert_messages_to_ark(self, messages: List[BaseMessage]) -> List[dict]:
        """
        将 LangChain 消息列表转换为 Ark responses.create 的 input 格式。

        LangChain 多模态格式 (OpenAI-style):
            HumanMessage(content=[
                {"type": "text", "text": "你好"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
            ])

        Ark responses 格式:
            [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "你好"},
                    {"type": "input_image", "image_url": "data:image/jpeg;base64,...", "detail": "auto"},
                ]
            }]
        """
        ark_input = []

        for msg in messages:
            role = self._get_ark_role(msg)
            content = self._convert_content_to_ark(msg.content)
            if content is not None:
                ark_input.append({"role": role, "content": content})

        return ark_input

    def _get_ark_role(self, message: BaseMessage) -> str:
        """将 LangChain 消息类型映射为 Ark role。"""
        if isinstance(message, HumanMessage):
            return "user"
        elif isinstance(message, AIMessage):
            return "assistant"
        elif isinstance(message, SystemMessage):
            return "system"
        elif isinstance(message, ChatMessage):
            return message.role
        return "user"

    def _convert_content_to_ark(
        self, content: Union[str, List[dict]]
    ) -> Optional[Union[str, List[dict]]]:
        """
        将 LangChain 消息内容转换为 Ark 内容格式。

        str → 保持为 str (Ark 也支持纯文本字符串内容)
        list → 逐个 block 转换:
            "text"       → "input_text"
            "image_url"  → "input_image"
        """
        if isinstance(content, str):
            return content

        if not isinstance(content, list):
            return str(content)

        ark_content = []
        for block in content:
            if not isinstance(block, dict):
                continue

            block_type = block.get("type", "")

            if block_type == "text":
                ark_content.append({
                    "type": "input_text",
                    "text": block.get("text", ""),
                })

            elif block_type == "image_url":
                image_url_data = block.get("image_url", {})
                url = ""
                if isinstance(image_url_data, dict):
                    url = image_url_data.get("url", "")
                elif isinstance(image_url_data, str):
                    url = image_url_data

                ark_content.append({
                    "type": "input_image",
                    "image_url": url,
                    "detail": "auto",
                })

            # 忽略不认识的 block type

        if not ark_content:
            return None

        return ark_content


# ============================================================
# 便捷工厂函数
# ============================================================

def create_llm(streaming: bool = False) -> ChatDoubaoVL:
    """
    创建 ChatDoubaoVL 实例。

    注意: ChatDoubaoVL 不通过 streaming 参数区分模式。
    非流式使用 llm.invoke()，流式使用 llm.stream() / llm.astream()。
    streaming 参数仅用于向后兼容，实际创建的是同一对象。
    """
    return ChatDoubaoVL()


def build_multimodal_message(text: str, image_base64: str) -> HumanMessage:
    """
    构建包含文本和图片的多模态 HumanMessage（LangChain 格式）。

    Args:
        text: 用户输入的文本提示词（可为空字符串）。
        image_base64: 图片 Base64 编码（不含 data URI 前缀）。

    Returns:
        包含多模态内容列表的 HumanMessage。
    """
    content: List[dict] = []

    if text and text.strip():
        content.append({
            "type": "text",
            "text": text.strip(),
        })

    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
            },
        })

    if not content:
        content.append({
            "type": "text",
            "text": "请描述这张图片的内容。",
        })

    return HumanMessage(content=content)


def build_text_message(text: str) -> HumanMessage:
    """构建纯文本的 HumanMessage（无图片）。"""
    return HumanMessage(content=text.strip())

"""
AIRAG 全局配置文件
"""
import os

from utils.api_key_manager import get_api_key, get_model

# ============================================================
# 快捷键
# ============================================================
DEFAULT_HOTKEY = "ctrl+d"
TOGGLE_HOTKEY = "ctrl+h"

# ============================================================
# 网络代理（访问火山引擎 API 需要）
# ============================================================
HTTP_PROXY = "http://127.0.0.1:7890"   # 改成你的代理地址，不需要则留空 ""

# ============================================================
# 豆包 VL API 配置 (火山引擎方舟)
# ============================================================
# 优先读取本地配置文件，其次环境变量，最后用占位符
ARK_API_KEY = get_api_key() or os.environ.get("ARK_API_KEY", "")
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_MODEL_NAME = get_model() or os.environ.get("DOUBAO_MODEL_NAME", "doubao-seed-2-0-lite-260428")

# ============================================================
# 上下文限制
# ============================================================
MAX_TURNS = 5                 # 最多保留 5 轮对话（纯文本）
MAX_MESSAGES = MAX_TURNS * 2  # 最多保留 10 条消息
MAX_TOKEN_ESTIMATE = 8000     # 总 token 上限
# MAX_OUTPUT_TOKENS 已移除，不限制模型输出长度，靠 system prompt 控制精简度

# ============================================================
# 图片处理配置
# ============================================================
MAX_IMAGE_WIDTH = 1920        # 压缩最大宽度
MAX_IMAGE_HEIGHT = 1080       # 压缩最大高度
JPEG_QUALITY = 85             # JPEG 压缩质量 (1-100)
MAX_IMAGE_BASE64_KEEP_TURNS = 0  # JSON 中不保留图片 base64（只存文本）

# ============================================================
# 上下文持久化
# ============================================================
CONTEXT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "context_history.json")

# ============================================================
# UI 配置
# ============================================================
# 截图遮罩
MASK_OPACITY = 0.3            # 遮罩层透明度
HANDLE_SIZE = 8               # 锚点大小(像素)
HANDLE_HIT_RADIUS = 10        # 锚点点击检测半径

# 结果窗口
RESULT_WINDOW_WIDTH = 500     # 默认宽度
RESULT_WINDOW_HEIGHT = 400    # 默认高度
RESULT_WINDOW_OPACITY = 0.92  # 窗口不透明度
RESULT_FONT_SIZE = 13         # 字体大小
RESULT_BG_COLOR = "rgba(30, 30, 30, 0.92)"  # 深色半透明背景
RESULT_TEXT_COLOR = "#e0e0e0"  # 文字颜色

# 输入窗口
INPUT_WINDOW_WIDTH = 420
INPUT_WINDOW_HEIGHT = 160

"""
AIRAG — 智能截图解析悬浮窗工具 主入口

流程：
  1. 后台监听 Ctrl+D 快捷键 (keyboard 库 → 后台线程)
  2. 弹出全屏截图遮罩 → 用户选择区域 → 截图并发射信号
  3. 弹出追问输入框 → 用户可选输入问题
  4. 图片压缩 + Base64 → LangGraph 流式调用豆包 VL API
  5. 流式结果逐字显示在可拖动的透明悬浮窗上
  6. 保存/加载对话上下文到 JSON，支持多轮对话 + 历史裁剪

系统托盘图标提供：
  - 手动截图入口（右键菜单）
  - 程序状态指示
  - 退出程序
"""
import sys
import asyncio
import traceback
from typing import Optional, List

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QThread, QRect
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from pynput import keyboard as pynput_keyboard
from langchain_core.messages import BaseMessage, AIMessage

from config import DEFAULT_HOTKEY, TOGGLE_HOTKEY, CONTEXT_FILE, MAX_MESSAGES, HTTP_PROXY
from utils.image_tool import qimage_to_pil, pil_to_base64, compress_image
from utils.context_store import load_context, save_context
from utils.api_key_manager import get_api_key, set_api_key
from agent.graph import build_graph, stream_graph
from agent.llm_client import build_multimodal_message
from gui.capture_window import CaptureWindow
from gui.result_window import ResultWindow


# ============================================================
# Streaming Worker — QThread 中运行 asyncio 流式调用
# ============================================================

class StreamWorker(QThread):
    token_received = pyqtSignal(str)
    stream_finished = pyqtSignal()
    stream_error = pyqtSignal(str)

    def __init__(self, graph, messages: List[BaseMessage],
                 user_text: str, image_base64_list: Optional[List[str]],
                 max_turns: int, parent=None):
        super().__init__(parent)
        self._graph = graph
        self._messages = messages
        self._user_text = user_text
        self._image_base64_list = image_base64_list or []
        self._max_turns = max_turns

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _stream():
                async for token in stream_graph(
                    graph=self._graph,
                    messages=self._messages,
                    user_text=self._user_text,
                    image_base64_list=self._image_base64_list,
                    max_turns=self._max_turns,
                ):
                    self.token_received.emit(token)

            loop.run_until_complete(_stream())
            self.stream_finished.emit()
        except Exception as e:
            traceback.print_exc()
            self.stream_error.emit(str(e))
        finally:
            loop.close()


# ============================================================
# Main Agent Controller
# ============================================================

class ScreenAIAgent(QObject):
    """主控制器，管理截图→AI→展示的全流程。"""

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._thread_id = "default"
        self._hotkey_registered = False

        # 对话历史
        self._messages: List[BaseMessage] = load_context(CONTEXT_FILE)
        print(f"[AIRAG] 已加载 {len(self._messages)} 条历史消息")

        # LangGraph
        self._graph = build_graph()
        print("[AIRAG] LangGraph 状态机已就绪")

        # UI 组件 — ResultWindow 常驻显示
        self._result_window = ResultWindow()
        self._result_window.follow_up_requested.connect(self._on_follow_up)
        self._result_window.show()
        self._stream_worker: Optional[StreamWorker] = None
        self._capture_win: Optional[CaptureWindow] = None

        # 本轮输入追踪
        self._last_user_text = ""
        self._last_image_b64_list: List[str] = []
        self._last_capture_rect: Optional[QRect] = None

        # 系统托盘
        self._setup_tray()

        # 注册快捷键
        self._register_hotkey()

        # 延迟启动 API Key 检查（等 QApplication 事件循环就绪）
        QTimer.singleShot(500, self._check_api_key)

    # ============================================================
    # System Tray
    # ============================================================

    def _setup_tray(self):
        """创建系统托盘图标和右键菜单。"""
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("AIRAG 截图助手\nCtrl+D 截图  Ctrl+H 显隐")

        # 使用一个简单的内置图标（没有外部图标文件）
        pixmap = self._create_tray_icon_pixmap()
        icon = QIcon(pixmap)
        self._tray.setIcon(icon)
        self._tray.setVisible(True)

        # 右键菜单
        menu = QMenu()

        capture_action = QAction("📷 立即截图 (Ctrl+D)")
        capture_action.triggered.connect(self._start_capture_flow)
        menu.addAction(capture_action)

        menu.addSeparator()

        apikey_action = QAction("🔑 修改 API Key")
        apikey_action.triggered.connect(self._change_api_key)
        menu.addAction(apikey_action)

        clear_action = QAction("🗑️ 清空对话历史")
        clear_action.triggered.connect(self._clear_history)
        menu.addAction(clear_action)

        menu.addSeparator()

        quit_action = QAction("❌ 退出")
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)

        # 双击托盘图标也可截图
        self._tray.activated.connect(self._on_tray_activated)

        # 启动气泡提示
        self._tray.showMessage(
            "AIRAG 截图助手",
            f"已启动！\n{DEFAULT_HOTKEY.upper()} 截图发送\n{TOGGLE_HOTKEY.upper()} 隐藏/显示\n直接输入文字即可对话",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _create_tray_icon_pixmap(self):
        """创建简单的系统托盘图标（纯色方块 + 字母 A）。"""
        from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap, QPen, QBrush
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景圆
        painter.setBrush(QBrush(QColor(60, 120, 220)))
        painter.setPen(QPen(QColor(40, 80, 180), 2))
        painter.drawRoundedRect(2, 2, 28, 28, 8, 8)

        # 文字 A
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 16, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(2, 2, 28, 28, Qt.AlignmentFlag.AlignCenter, "A")

        painter.end()
        return pixmap

    def _on_tray_activated(self, reason):
        """双击托盘图标触发截图。"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._start_capture_flow()

    def _quit_app(self):
        """退出程序。"""
        print("[AIRAG] 正在退出...")
        save_context(self._messages, CONTEXT_FILE)
        try:
            if hasattr(self, '_hotkey_listener') and self._hotkey_listener:
                self._hotkey_listener.stop()
        except Exception:
            pass
        self._tray.hide()
        self._app.quit()

    # ============================================================
    # Hotkey
    # ============================================================

    def _register_hotkey(self):
        """注册全局快捷键 Ctrl+D（截图）和 Ctrl+F（显隐）— 跨平台 pynput。"""
        try:
            # pynput 热键映射：<ctrl>+d, <ctrl>+f
            hotkeys = {
                '<ctrl>+d': self._on_hotkey_triggered,
                '<ctrl>+f': self._on_hotkey_toggle,
            }
            self._hotkey_listener = pynput_keyboard.GlobalHotKeys(
                hotkeys, suppress=False)  # suppress=False 让 Ctrl+Z 等正常传递
            self._hotkey_listener.start()  # 非阻塞，后台线程运行
            self._hotkey_registered = True
            print(f"[AIRAG] [OK] 快捷键注册成功 (pynput)")
            print(f"         Ctrl+D — 截图发送")
            print(f"         Ctrl+F — 隐藏/显示窗口")
        except Exception as e:
            self._hotkey_registered = False
            self._hotkey_listener = None
            print(f"[AIRAG] [WARN] 快捷键注册失败: {e}")
            print(f"         pynput 在 Linux 上通常无需管理员权限。")
            print(f"         你也可以通过系统托盘的右键菜单手动截图。")
            self._tray.setToolTip(
                "AIRAG 截图助手\n⚠ 热键未注册\n右键托盘图标手动截图"
            )

    def _on_hotkey_triggered(self, key=None):
        """
        Ctrl+D 回调 — 在 pynput 后台线程中运行。
        QTimer.singleShot(0, ...) 安全切回主线程。
        """
        QTimer.singleShot(0, self._start_capture_flow)

    def _on_hotkey_toggle(self, key=None):
        """
        Ctrl+F 回调 — 切换 ResultWindow 显隐。
        """
        QTimer.singleShot(0, self._toggle_window)

    def _toggle_window(self):
        """切换常驻窗口的显示/隐藏（主线程）。"""
        if self._result_window.isVisible():
            self._result_window.hide()
        else:
            self._result_window.show()
            self._result_window.raise_()

    # ============================================================
    # Step 1: Capture
    # ============================================================

    def _start_capture_flow(self):
        """打开全屏截图遮罩（主线程）。"""
        # 避免重复打开截图窗口
        if self._capture_win is not None and self._capture_win.isVisible():
            return

        self._capture_win = CaptureWindow()
        self._capture_win.captured.connect(self._on_image_captured)
        self._capture_win.showFullScreen()

    def _on_image_captured(self, images: list):
        """多框截图完成 → 全部压缩存入 ResultWindow 缩略图区。"""
        self._capture_win = None

        if not images:
            return

        # 用第一个截图的矩形定位窗口
        _, first_rect = images[0]
        self._last_capture_rect = first_rect

        # 每张图压缩 → Base64 → 添加到缩略图
        for img, _ in images:
            pil_img = qimage_to_pil(img)
            pil_img = compress_image(pil_img)
            image_base64 = pil_to_base64(pil_img)
            self._result_window.add_image_thumbnail(image_base64, img)

        # 窗口保持可见
        if not self._result_window.isVisible():
            self._result_window.show()
        self._result_window.raise_()

    # ============================================================
    # Step 2: AI Stream
    # ============================================================

    def _run_ai_stream(self, user_text: str, image_base64_list: Optional[List[str]] = None):
        """启动 AI 流式处理。支持多图列表。"""
        if image_base64_list is None:
            image_base64_list = []

        has_image = len(image_base64_list) > 0

        # 只有新截图时才重新定位窗口
        if has_image and self._last_capture_rect and not self._last_capture_rect.isEmpty():
            self._result_window.position_near_rect(self._last_capture_rect)
        elif has_image:
            self._result_window._position_bottom_right()

        # 在已有内容后追加用户问题标题
        if user_text.strip():
            img_count = len(image_base64_list)
            if img_count > 1:
                icon = f"🖼️×{img_count}"
            elif img_count == 1:
                icon = "🖼️"
            else:
                icon = "💬"
            existing = self._result_window.get_content()
            separator = "\n\n---\n\n" if existing.strip() else ""
            self._result_window.set_content(
                existing + separator +
                f"**{icon} 你：** {user_text}\n\n"
            )

        self._result_window.start_loading("⏳ AI 正在思考")
        self._result_window.show()
        self._result_window.raise_()

        self._stream_worker = StreamWorker(
            graph=self._graph,
            messages=list(self._messages),
            user_text=user_text,
            image_base64_list=image_base64_list,
            max_turns=10,
        )
        self._stream_worker.token_received.connect(self._on_token_received)
        self._stream_worker.stream_finished.connect(self._on_stream_finished)
        self._stream_worker.stream_error.connect(self._on_stream_error)
        self._stream_worker.start()

    def _on_token_received(self, token: str):
        if self._result_window:
            self._result_window.append_text(token)

    def _on_follow_up(self, text: str):
        """用户点击发送 — 收集所有待发送图片一起提交。"""
        if not text.strip() and not self._result_window.get_pending_images():
            return
        self._last_user_text = text
        # 收集所有待发送图片
        self._last_image_b64_list = self._result_window.get_pending_images()
        self._result_window.clear_pending_images()
        # 清空输入框
        self._result_window.clear_input()
        self._run_ai_stream(text, image_base64_list=self._last_image_b64_list)

    def _on_stream_finished(self):
        full_response = ""
        if self._result_window:
            self._result_window.stop_loading()
            full_response = self._result_window.get_content()

        print(f"[AIRAG] 流式输出完成 ({len(full_response)} 字符)")

        # 保存上下文（支持多图）
        if self._last_user_text or self._last_image_b64_list:
            user_msg = build_multimodal_message(
                self._last_user_text or "请描述图片内容",
                image_base64_list=self._last_image_b64_list,
            )
            self._messages.append(user_msg)

        if full_response.strip():
            ai_msg = AIMessage(content=full_response.strip())
            self._messages.append(ai_msg)

        if len(self._messages) > MAX_MESSAGES:
            self._messages = self._messages[-MAX_MESSAGES:]

        save_context(self._messages, CONTEXT_FILE)
        print(f"[AIRAG] 上下文已保存 ({len(self._messages)} 条消息)")

        self._stream_worker = None
        self._last_image_b64_list = []

    def _on_stream_error(self, error_msg: str):
        print(f"[AIRAG] 流式错误: {error_msg}")
        if self._result_window:
            self._result_window.stop_loading()
            self._result_window.append_text(
                f"\n\n❌ **请求失败**: {error_msg}\n\n"
                f"请检查 API Key 和网络连接。"
            )
        self._stream_worker = None

    # ============================================================
    # History
    # ============================================================

    def _clear_history(self):
        """清空对话历史（窗口保持显示）。"""
        self._messages = []
        save_context(self._messages, CONTEXT_FILE)
        print("[AIRAG] 对话历史已清空")
        self._result_window.clear_content()
        self._tray.showMessage(
            "AIRAG",
            "对话历史已清空",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _check_api_key(self):
        """启动时检查 API Key，没有则弹出设置框。"""
        key = get_api_key()
        if not key:
            self._tray.showMessage(
                "AIRAG",
                "未检测到 API Key，请设置后使用",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            QTimer.singleShot(1000, self._change_api_key)

    def _change_api_key(self):
        """弹出 API Key 设置弹窗。"""
        from gui.api_key_dialog import ApiKeyDialog
        dlg = ApiKeyDialog()
        if dlg.exec() == ApiKeyDialog.DialogCode.Accepted:
            # 重新加载 config 中的 API Key
            import config
            config.ARK_API_KEY = get_api_key()
            print("[AIRAG] API Key 已更新")
            self._tray.showMessage(
                "AIRAG",
                "API Key 已保存",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )


# ============================================================
# Entry Point
# ============================================================

def main():
    try:
        print()
        print("=" * 58)
        print("   AIRAG - AI Screenshot Assistant")
        print("=" * 58)
        print(f"   {DEFAULT_HOTKEY.upper()} — 截图发送")
        print(f"   {TOGGLE_HOTKEY.upper()} — 隐藏/显示窗口")
        print(f"   直接输入文字即可与 AI 对话")
        print(f"   Model:      doubao-seed-2-0-lite-260428")
        print(f"   Context:    max {MAX_MESSAGES} messages")
        print("=" * 58)
        print("   [*] Check system tray (bottom-right) for icon")
        print("   [*] Right-click tray icon to capture manually")
        print("   [*] Run as Administrator if hotkey fails")
        print("=" * 58)
    except UnicodeEncodeError:
        pass  # Windows console GBK encoding doesn't support emoji
    print()

    # 设置网络代理（火山引擎 API 需要）
    if HTTP_PROXY:
        import os
        os.environ["HTTP_PROXY"] = HTTP_PROXY
        os.environ["HTTPS_PROXY"] = HTTP_PROXY
        print(f"   Proxy:      {HTTP_PROXY}")
    print()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 检查是否支持系统托盘
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[AIRAG] [WARN] 系统托盘不可用，请确保桌面环境支持。")

    agent = ScreenAIAgent(app)

    try:
        sys.exit(app.exec())
    finally:
        try:
            if hasattr(agent, '_hotkey_listener') and agent._hotkey_listener:
                agent._hotkey_listener.stop()
        except Exception:
            pass
        print("[AIRAG] 已退出。")


if __name__ == "__main__":
    main()

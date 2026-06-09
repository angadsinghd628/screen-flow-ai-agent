"""
透明悬浮结果窗 — 流式显示 AI 回复，支持 Markdown、拖动、缩放。

特性：
  - 无边框、置顶、半透明背景
  - 鼠标按住标题栏拖动窗口
  - 鼠标拖拽边缘/角落缩放窗口
  - 呼吸灯加载动画（等待 AI 回复时）
  - 右键菜单：清空/复制/关闭
"""
import re
from PyQt6.QtCore import Qt, QPoint, QSize, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QAction,
    QTextCursor, QMouseEvent, QCursor,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QLabel, QMenu, QLineEdit,
)

from config import (
    RESULT_WINDOW_WIDTH, RESULT_WINDOW_HEIGHT,
    RESULT_WINDOW_OPACITY, RESULT_FONT_SIZE,
)

# 边缘检测距离（像素）
EDGE_MARGIN = 8
# 最小窗口尺寸
MIN_WIDTH = 300
MIN_HEIGHT = 200


class ResultWindow(QWidget):
    """
    透明、可拖动、可缩放、置顶的悬浮结果窗。
    底部带有追问输入框，支持连续纯文本追问。
    """
    # 信号：用户在追问框输入文字并发送
    follow_up_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buffer = ""

        # ---- 拖动/缩放状态 ----
        self._drag_pos = QPoint()          # 拖动起始偏移
        self._dragging = False             # 是否在拖动窗口
        self._resizing = False             # 是否在缩放窗口
        self._resize_edge = ""             # 缩放边缘方向: n, s, e, w, ne, nw, se, sw
        self._resize_start_geo: QRect | None = None  # 缩放前窗口几何
        self._resize_start_pos: QPoint | None = None  # 缩放起始鼠标全局坐标

        # ---- 加载动画 ----
        self._loading = False
        self._loading_dots = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._tick_loading)
        self._loading_base_text = ""

        self._setup_ui()

    # ============================================================
    # UI Setup
    # ============================================================

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowOpacity(RESULT_WINDOW_OPACITY)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(RESULT_WINDOW_WIDTH, RESULT_WINDOW_HEIGHT)
        self._position_bottom_right()

        # 深色半透明背景
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 35, 235))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # 启用鼠标追踪（边缘检测需要）
        self.setMouseTracking(True)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # ---- 标题栏 ----
        title_bar = QHBoxLayout()
        title_bar.setSpacing(6)

        self._title_label = QLabel("🤖 AI 解析结果")
        self._title_label.setFont(QFont("Microsoft YaHei", 11))
        self._title_label.setStyleSheet("color: #88aaff; font-weight: bold;")
        title_bar.addWidget(self._title_label)
        title_bar.addStretch()

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a40; color: #ccc; border: none;
                border-radius: 4px; padding: 3px 10px; font-size: 11px;
            }
            QPushButton:hover { background: #555; }
        """)
        self._clear_btn.clicked.connect(self.clear_content)
        title_bar.addWidget(self._clear_btn)

        # 推后台按钮
        min_btn = QPushButton("—")
        min_btn.setFixedSize(24, 24)
        min_btn.setToolTip("隐藏到后台（Ctrl+D 可重新截图）")
        min_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a40; color: #ccc; border: none;
                border-radius: 12px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background: #555; color: white; }
        """)
        min_btn.clicked.connect(self.hide)
        title_bar.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b; color: white; border: none;
                border-radius: 12px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #e74c3c; }
        """)
        close_btn.clicked.connect(self.hide)
        title_bar.addWidget(close_btn)

        layout.addLayout(title_bar)

        # ---- 内容显示区 ----
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setFont(QFont("Microsoft YaHei", RESULT_FONT_SIZE))
        self._text_view.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                color: #e0e0e0;
                border: 1px solid #3a3a45;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #3a5a8c;
            }
        """)
        self._text_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self._text_view, stretch=1)

        # ---- 底部追问输入区 ----
        ask_layout = QHBoxLayout()
        ask_layout.setSpacing(6)

        self._ask_input = QLineEdit()
        self._ask_input.setPlaceholderText("💬 输入追问内容，Enter 发送...")
        self._ask_input.setFont(QFont("Microsoft YaHei", 11))
        self._ask_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a35;
                color: #e0e0e0;
                border: 1px solid #4a4a55;
                border-radius: 5px;
                padding: 6px 10px;
            }
            QLineEdit:focus { border-color: #4a8af4; }
        """)
        self._ask_input.returnPressed.connect(self._send_follow_up)
        ask_layout.addWidget(self._ask_input, stretch=1)

        send_btn = QPushButton("发送")
        send_btn.setStyleSheet("""
            QPushButton {
                background: #2b5db8; color: white; border: none;
                border-radius: 5px; padding: 6px 14px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #3a6fd8; }
        """)
        send_btn.clicked.connect(self._send_follow_up)
        ask_layout.addWidget(send_btn)

        layout.addLayout(ask_layout)

    # ============================================================
    # Positioning
    # ============================================================

    def _position_bottom_right(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            x = available.right() - self.width() - 20
            y = available.bottom() - self.height() - 40
            self.move(x, y)

    def position_near_rect(self, rect: QRect):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        gap = 16
        win_w = self.width()
        win_h = self.height()

        x = rect.right() + gap
        y = rect.top()

        if x + win_w > available.right():
            x = rect.left() - win_w - gap
        if x < available.left():
            x = rect.left()
            y = rect.bottom() + gap

        if y + win_h > available.bottom():
            y = available.bottom() - win_h - gap
        if y < available.top():
            y = available.top() + gap

        self.move(x, y)

    # ============================================================
    # Loading Animation（呼吸灯）
    # ============================================================

    def start_loading(self, base_text: str = "⏳ AI 正在思考"):
        """启动加载动画。"""
        self._loading = True
        self._loading_dots = 0
        self._loading_base_text = base_text
        self._update_loading_display()
        self._loading_timer.start(400)  # 每 400ms 切换

    def stop_loading(self):
        """停止加载动画。"""
        self._loading = False
        self._loading_timer.stop()
        self._title_label.setText("🤖 AI 解析结果")

    def _tick_loading(self):
        """加载动画的每个 tick。"""
        self._loading_dots = (self._loading_dots + 1) % 4
        self._update_loading_display()

    def _update_loading_display(self):
        """更新加载动画显示。"""
        dots = " ·" * self._loading_dots
        if self._loading_dots == 0:
            dots = ""
        self._title_label.setText(f"{self._loading_base_text}{dots}")

        # 内容区：在已有内容下方追加加载动画
        pulse = ["○", "◔", "◑", "◕"][self._loading_dots]
        loading_html = (
            f"<div style='text-align:center; padding:20px 0;'>"
            f"<span style='font-size:28px; color:#4a8af4;'>{pulse}</span><br>"
            f"<span style='color:#8899aa; font-size:13px;'>{self._loading_base_text}{dots}</span>"
            f"</div>"
        )

        if self._buffer.strip():
            # 已有内容 + 后面加加载动画
            self._text_view.setHtml(
                self._render_markdown(self._buffer) + loading_html
            )
        else:
            self._text_view.setHtml(loading_html)

    # ============================================================
    # Content API
    # ============================================================

    def append_text(self, text: str):
        """追加流式文本。首次调用时自动停止加载动画并保留已有内容。"""
        if self._loading:
            self.stop_loading()
            # 保留已有内容（如用户问题），不清空 buffer

        self._buffer += text
        self._text_view.setHtml(self._render_markdown(self._buffer))
        cursor = self._text_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text_view.setTextCursor(cursor)

    def set_content(self, text: str):
        self._buffer = text
        self._text_view.setHtml(self._render_markdown(text))

    def clear_content(self):
        self._buffer = ""
        self._text_view.clear()

    def get_content(self) -> str:
        return self._buffer

    # ---- 追问 ----

    def get_input_text(self) -> str:
        """获取底部追问输入框当前文本。"""
        return self._ask_input.text().strip()

    def clear_input(self):
        """清空底部追问输入框。"""
        self._ask_input.clear()

    def _send_follow_up(self):
        """用户按 Enter 或点击发送按钮时触发。"""
        text = self._ask_input.text().strip()
        if text:
            self._ask_input.clear()
            self.follow_up_requested.emit(text)

    # ============================================================
    # Markdown → HTML
    # ============================================================

    def _render_markdown(self, text: str) -> str:
        """将 Markdown 转换为 HTML，支持表格。"""
        html = text

        # 0. 先处理表格（在转义 HTML 之前，因为我们要插入真正的 HTML 标签）
        html = self._render_tables(html)

        # 1. 转义 HTML 特殊字符（保护已处理的表格 HTML）
        html = self._escape_except_tags(html)

        # 2. 代码块 ```...```
        html = re.sub(
            r'```(\w*)\n(.*?)```',
            r'<pre style="background:#1e1e2a;padding:10px;border-radius:4px;overflow-x:auto;"><code>\2</code></pre>',
            html, flags=re.DOTALL)
        # 行内代码 `...`
        html = re.sub(
            r'`([^`]+)`',
            r'<code style="background:#2a2a35;padding:1px 4px;border-radius:3px;color:#f0c070;">\1</code>',
            html)
        # 标题
        html = re.sub(r'^### (.+)$', r'<h3 style="color:#88aaff;margin:8px 0;">\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2 style="color:#88ccff;margin:10px 0;">\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1 style="color:#aaddff;margin:12px 0;">\1</h1>', html, flags=re.MULTILINE)
        # 粗体 / 斜体
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
        # 列表
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        # 水平线
        html = re.sub(r'^---$', r'<hr style="border:0;border-top:1px solid #444;">', html, flags=re.MULTILINE)
        html = html.replace("\n\n", "<br><br>")

        return f"""
        <div style="font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                    font-size: {RESULT_FONT_SIZE}px; line-height: 1.6; color: #e0e0e0;">
            {html}
        </div>
        """

    def _render_tables(self, text: str) -> str:
        """将 Markdown 表格转换为 HTML 表格。"""
        lines = text.split("\n")
        result = []
        table_buffer = []
        in_table = False

        def flush_table():
            """将缓存的表格行转换为 HTML。"""
            nonlocal table_buffer
            if not table_buffer:
                return

            # 过滤：至少要有 separator 行（|---...|）才算是表格
            has_separator = any(
                re.match(r'^\|[\s\-:]+\|', row) for row in table_buffer
            )
            if not has_separator or len(table_buffer) < 2:
                result.extend(table_buffer)
                table_buffer = []
                return

            html_parts = ['<table style="border-collapse:collapse;width:100%;margin:10px 0;">']

            header_done = False
            for row in table_buffer:
                # Separator 行 → 标记 header 结束
                if re.match(r'^\|[\s\-:]+\|', row):
                    header_done = True
                    continue

                cells = [c.strip() for c in row.split("|")[1:-1]]
                if not cells:
                    continue

                if not header_done:
                    # 表头
                    html_parts.append("<tr>")
                    for c in cells:
                        html_parts.append(
                            f'<th style="border:1px solid #3a4a5a;padding:6px 12px;'
                            f'background:#2a3a50;color:#aaccff;text-align:left;">{c}</th>'
                        )
                    html_parts.append("</tr>")
                else:
                    # 表体
                    html_parts.append("<tr>")
                    for c in cells:
                        html_parts.append(
                            f'<td style="border:1px solid #3a3a45;padding:5px 10px;'
                            f'vertical-align:top;">{c}</td>'
                        )
                    html_parts.append("</tr>")

            html_parts.append("</table>")
            result.append("".join(html_parts))
            table_buffer = []

        for line in lines:
            is_table_row = bool(re.match(r'^\|.+\|$', line.strip()))

            if is_table_row:
                if not in_table:
                    in_table = True
                table_buffer.append(line)
            else:
                if in_table:
                    flush_table()
                    in_table = False
                result.append(line)

        # 处理末尾的表格
        if in_table:
            flush_table()

        return "\n".join(result)

    def _escape_except_tags(self, text: str) -> str:
        """转义 HTML 特殊字符，但保留已有的 HTML 标签。"""
        # 保护已存在的 HTML 标签
        protected = []
        def _save(m):
            protected.append(m.group(0))
            return f"\x00PROTECT{len(protected) - 1}\x00"

        # 保护所有 HTML 标签
        text = re.sub(r'<[^>]+>', _save, text)

        # 转义剩余文本中的特殊字符
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")

        # 还原保护的 HTML 标签
        for i, tag in enumerate(protected):
            text = text.replace(f"\x00PROTECT{i}\x00", tag)

        return text

    # ============================================================
    # Mouse Events — 拖动 + 缩放 + 边缘检测
    # ============================================================

    def _get_resize_edge(self, pos: QPoint) -> str:
        """检测鼠标在窗口的哪个边缘/角落，返回方向字符串。"""
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()

        on_left = x <= EDGE_MARGIN
        on_right = x >= w - EDGE_MARGIN
        on_top = y <= EDGE_MARGIN
        on_bottom = y >= h - EDGE_MARGIN

        if on_top and on_left:
            return "nw"
        if on_top and on_right:
            return "ne"
        if on_bottom and on_left:
            return "sw"
        if on_bottom and on_right:
            return "se"
        if on_top:
            return "n"
        if on_bottom:
            return "s"
        if on_left:
            return "w"
        if on_right:
            return "e"
        return ""

    def _cursor_for_edge(self, edge: str) -> QCursor:
        """根据边缘方向返回对应的光标。"""
        cursors = {
            "n": Qt.CursorShape.SizeVerCursor,
            "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor,
            "w": Qt.CursorShape.SizeHorCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor,
            "sw": Qt.CursorShape.SizeBDiagCursor,
            "nw": Qt.CursorShape.SizeFDiagCursor,
            "se": Qt.CursorShape.SizeFDiagCursor,
        }
        return QCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position().toPoint()
        edge = self._get_resize_edge(pos)

        if edge:
            # 开始缩放
            self._resizing = True
            self._resize_edge = edge
            self._resize_start_geo = self.geometry()
            self._resize_start_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            # 开始拖动
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        gpos = event.globalPosition().toPoint()

        if self._resizing:
            # 缩放窗口
            self._do_resize(gpos)
            event.accept()
        elif self._dragging:
            # 拖动窗口
            new_pos = gpos - self._drag_pos
            self.move(new_pos)
            event.accept()
        else:
            # 仅移动鼠标 — 更新光标提示
            edge = self._get_resize_edge(pos)
            if edge:
                self.setCursor(self._cursor_for_edge(edge))
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._resizing = False
            self._resize_edge = ""
            self._resize_start_geo = None
            self._resize_start_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _do_resize(self, gpos: QPoint):
        """根据当前缩放方向和鼠标位置调整窗口几何。"""
        if not self._resize_start_geo or not self._resize_start_pos:
            return

        dx = gpos.x() - self._resize_start_pos.x()
        dy = gpos.y() - self._resize_start_pos.y()
        geo = QRect(self._resize_start_geo)
        edge = self._resize_edge

        if "e" in edge:
            geo.setRight(max(geo.left() + MIN_WIDTH, geo.right() + dx))
        if "w" in edge:
            geo.setLeft(min(geo.right() - MIN_WIDTH, geo.left() + dx))
        if "s" in edge:
            geo.setBottom(max(geo.top() + MIN_HEIGHT, geo.bottom() + dy))
        if "n" in edge:
            geo.setTop(min(geo.bottom() - MIN_HEIGHT, geo.top() + dy))

        self.setGeometry(geo)

    # ============================================================
    # Context Menu
    # ============================================================

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a32; color: #e0e0e0;
                border: 1px solid #444; padding: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #3a5a8c; }
        """)

        clear_action = QAction("清空内容", self)
        clear_action.triggered.connect(self.clear_content)
        menu.addAction(clear_action)

        copy_action = QAction("复制全部", self)
        copy_action.triggered.connect(lambda: _get_clipboard().setText(self._buffer))
        menu.addAction(copy_action)

        menu.addSeparator()

        hide_action = QAction("关闭窗口", self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        menu.exec(event.globalPos())


def _get_clipboard():
    from PyQt6.QtWidgets import QApplication
    return QApplication.clipboard()

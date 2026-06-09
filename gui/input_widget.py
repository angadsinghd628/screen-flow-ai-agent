"""
快捷输入窗口 — 截图完成后弹出，用户可追加提问或直接跳过。
支持多行输入，Enter 确认，Escape 跳过。
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QLabel,
)

from config import INPUT_WINDOW_WIDTH, INPUT_WINDOW_HEIGHT


class InputDialog(QDialog):
    """
    截图后的追问输入弹窗。

    用法:
        dlg = InputDialog()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            user_text = dlg.get_text()
    """
    confirmed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("AI 截图助手")
        self.setFixedSize(INPUT_WINDOW_WIDTH, INPUT_WINDOW_HEIGHT)

        # 无边框 + 置顶
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # 半透明深色背景
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(40, 40, 45, 240))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 标题
        title = QLabel("✏️ 追问（可选）- 直接 Enter 发送图片给 AI")
        title.setFont(QFont("Microsoft YaHei", 11))
        title.setStyleSheet("color: #c8c8c8;")
        layout.addWidget(title)

        # 多行输入框
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("输入你的问题，例如：这段代码是什么意思？帮我翻译截图内容...")
        self._text_edit.setFont(QFont("Microsoft YaHei", 11))
        self._text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a30;
                color: #e8e8e8;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 8px;
            }
            QTextEdit:focus {
                border-color: #4a8af4;
            }
        """)
        self._text_edit.setMaximumHeight(60)
        layout.addWidget(self._text_edit)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._skip_btn = QPushButton("跳过 (Esc)")
        self._skip_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a40;
                color: #aaa;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 6px 18px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4a4a50;
                color: #ddd;
            }
        """)
        self._skip_btn.clicked.connect(self._on_skip)

        self._confirm_btn = QPushButton("确认发送 (Enter)")
        self._confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #2b5db8;
                color: white;
                border: 1px solid #3a6fd8;
                border-radius: 5px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a6fd8;
            }
        """)
        self._confirm_btn.clicked.connect(self._on_confirm)

        btn_layout.addStretch()
        btn_layout.addWidget(self._skip_btn)
        btn_layout.addWidget(self._confirm_btn)
        layout.addLayout(btn_layout)

        # 让输入框获取焦点
        self._text_edit.setFocus()

        # 居中在屏幕上
        self._center_on_screen()

    def _center_on_screen(self):
        """将窗口放在屏幕中央偏上。"""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - self.width()) // 2 + screen_geo.x()
            y = (screen_geo.height() - self.height()) // 3 + screen_geo.y()
            self.move(x, y)

    def _on_confirm(self):
        """确认并返回输入文本。"""
        self.confirmed.emit(self.get_text())
        self.accept()

    def _on_skip(self):
        """跳过，不输入文本。"""
        self.confirmed.emit("")
        self.accept()

    def get_text(self) -> str:
        """获取用户输入文本。"""
        return self._text_edit.toPlainText().strip()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            # 如果是 Shift+Enter 则换行
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._text_edit.insertPlainText("\n")
            else:
                self._on_confirm()
        elif key == Qt.Key.Key_Escape:
            self._on_skip()
        else:
            super().keyPressEvent(event)

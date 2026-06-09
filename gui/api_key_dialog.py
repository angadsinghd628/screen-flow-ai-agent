"""
API Key 输入弹窗 — 首次使用或修改 API Key 时弹出。
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QPalette
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QHBoxLayout,
    QPushButton, QLabel,
)

from utils.api_key_manager import get_api_key, set_api_key, get_model


class ApiKeyDialog(QDialog):
    """
    API Key 设置弹窗。

    用法:
        dlg = ApiKeyDialog()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            print("API Key 已保存")
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("AIRAG - API Key 设置")
        self.setFixedSize(440, 180)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # 深色背景
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(35, 35, 42, 245))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(10)

        # 标题
        title = QLabel("请输入火山引擎方舟 API Key")
        title.setFont(QFont("Microsoft YaHei", 12))
        title.setStyleSheet("color: #aaccff; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("API Key 将保存在程序目录下，下次启动自动加载。")
        desc.setFont(QFont("Microsoft YaHei", 10))
        desc.setStyleSheet("color: #8899aa;")
        layout.addWidget(desc)

        # 输入框
        current_key = get_api_key()
        self._input = QLineEdit()
        self._input.setPlaceholderText("粘贴你的 API Key（例如：c774d2b6-xxxx-xxxx-xxxx-xxxxxxxxxxxx）")
        self._input.setEchoMode(QLineEdit.EchoMode.Password)
        self._input.setFont(QFont("Consolas", 11))
        self._input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e28;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border-color: #4a8af4; }
        """)
        if current_key:
            self._input.setText(current_key)
        layout.addWidget(self._input)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        skip_btn = QPushButton("取消")
        skip_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a40; color: #aaa; border: 1px solid #555;
                border-radius: 5px; padding: 7px 20px; font-size: 12px;
            }
            QPushButton:hover { background: #4a4a50; color: #ddd; }
        """)
        skip_btn.clicked.connect(self.reject)
        btn_layout.addWidget(skip_btn)

        btn_layout.addStretch()

        save_btn = QPushButton("保存并继续")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #2b5db8; color: white; border: none;
                border-radius: 5px; padding: 7px 20px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #3a6fd8; }
        """)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _on_save(self):
        key = self._input.text().strip()
        if key:
            set_api_key(key)
            self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._on_save()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

"""
截图遮罩窗口 — 全屏半透明覆盖层，支持拖拽选择区域、8 锚点拉伸调整。

核心设计：
  - WA_TranslucentBackground = True，窗口真正透明
  - 先画全屏暗色遮罩，再"挖空"选中区域显示原屏幕画面
  - 用户可以透过遮罩看到屏幕内容

状态机：IDLE → SELECTING → ADJUSTING → CONFIRMED
"""
from enum import Enum, auto
from typing import Optional
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont,
    QPixmap, QImage,
)
from PyQt6.QtWidgets import QWidget, QApplication

from config import MASK_OPACITY, HANDLE_SIZE, HANDLE_HIT_RADIUS


class CaptureState(Enum):
    IDLE = auto()
    SELECTING = auto()
    ADJUSTING = auto()
    CONFIRMED = auto()


class HandlePosition(Enum):
    TOP_LEFT = auto()
    TOP = auto()
    TOP_RIGHT = auto()
    RIGHT = auto()
    BOTTOM_RIGHT = auto()
    BOTTOM = auto()
    BOTTOM_LEFT = auto()
    LEFT = auto()


class CaptureWindow(QWidget):
    """
    全屏透明截图遮罩窗口。

    - 创建时捕获全屏截图作为背景层
    - 在背景上画半透明暗色遮罩
    - 选区区域"挖空"显示清晰的背景
    - 8 个锚点支持拖拽调整选区大小
    """
    captured = pyqtSignal(QImage, QRect)

    def __init__(self):
        super().__init__()

        # 关键：无边框 + 置顶 + 透明背景
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 状态机
        self._state = CaptureState.IDLE

        # 选择区域坐标
        self._start_pos = QPoint()
        self._end_pos = QPoint()

        # 锚点拖拽
        self._active_handle: Optional[HandlePosition] = None
        self._drag_anchor = QPoint()
        self._drag_start_rect = QRect()

        # 全屏背景快照
        self._bg_pixmap: Optional[QPixmap] = None

    def showFullScreen(self):
        """捕获全屏快照，然后全屏显示。"""
        screen = QApplication.primaryScreen()
        if screen:
            self._bg_pixmap = screen.grabWindow(0)
        super().showFullScreen()

    # ============================================================
    # Paint — 三层绘制：背景图 → 遮罩 → 挖空选区
    # ============================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        full_rect = QRect(0, 0, w, h)

        # ---- Layer 1: 完整背景图（透过透明窗口看到屏幕） ----
        if self._bg_pixmap:
            painter.drawPixmap(full_rect, self._bg_pixmap, full_rect)

        # ---- Layer 2: 暗色遮罩（alpha 通道 = 半透明覆盖） ----
        mask_alpha = int(255 * MASK_OPACITY)
        mask_color = QColor(0, 0, 0, mask_alpha)
        painter.fillRect(full_rect, mask_color)

        r = self._get_normalized_rect()

        # ---- Layer 3: 挖空选区 — 用背景图覆盖遮罩层 ----
        if not r.isEmpty() and self._bg_pixmap:
            # 在选区位置重新画背景图（覆盖遮罩，形成"挖空"效果）
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawPixmap(r, self._bg_pixmap, r)

        # ---- 选区边框 ----
        if not r.isEmpty():
            # 亮蓝色实线边框，更显眼
            pen = QPen(QColor(30, 144, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)

            # 外发光效果（白色半透明宽边框）
            glow_pen = QPen(QColor(255, 255, 255, 80), 4)
            painter.setPen(glow_pen)
            painter.drawRect(r)

            # ---- 尺寸标签 ----
            size_text = f"{r.width()} × {r.height()}"
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Microsoft YaHei", 11, QFont.Weight.Bold)
            painter.setFont(font)

            # 标签放在选框上方或下方
            label_y = r.top() - 26
            if label_y < 10:
                label_y = r.bottom() + 8
            text_rect = QRect(r.left(), label_y, r.width(), 22)
            painter.fillRect(
                text_rect.adjusted(-8, -2, 8, 2),
                QColor(30, 144, 255, 200),
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, size_text)

            # ---- 锚点 ----
            if self._state in (CaptureState.ADJUSTING, CaptureState.CONFIRMED):
                self._draw_handles(painter, r)

        # ---- 顶部提示文字 ----
        if self._state == CaptureState.IDLE:
            hint_font = QFont("Microsoft YaHei", 16, QFont.Weight.Bold)
            painter.setFont(hint_font)

            # 文字阴影
            painter.setPen(QColor(0, 0, 0, 160))
            shadow_rect = QRect(1, 51, w, 30)
            painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter,
                             "🖱️ 拖拽鼠标框选截图区域")

            # 文字本体
            painter.setPen(QColor(255, 255, 255, 230))
            hint_rect = QRect(0, 50, w, 30)
            painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter,
                             "🖱️ 拖拽鼠标框选截图区域")

            hint2_font = QFont("Microsoft YaHei", 12)
            painter.setFont(hint2_font)
            painter.setPen(QColor(255, 255, 255, 180))
            hint2_rect = QRect(0, 80, w, 24)
            painter.drawText(hint2_rect, Qt.AlignmentFlag.AlignCenter,
                             "Enter 确认  |  Esc 取消  |  直接 Enter = 全屏截图")

        elif self._state == CaptureState.ADJUSTING:
            hint_font = QFont("Microsoft YaHei", 12)
            painter.setFont(hint_font)
            painter.setPen(QColor(255, 255, 255, 200))
            hint_rect = QRect(0, h - 50, w, 24)
            painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter,
                             "拖拽蓝色锚点调整选区  |  Enter 确认  |  Esc 取消")

        painter.end()

    def _draw_handles(self, painter: QPainter, rect: QRect):
        """绘制 8 个锚点 — 蓝色实心方块 + 白色边框。"""
        s = HANDLE_SIZE
        half = s // 2
        positions = self._get_handle_points(rect)

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(QBrush(QColor(30, 144, 255)))

        for pos in positions.values():
            painter.drawRect(QRect(pos.x() - half, pos.y() - half, s, s))

    def _get_handle_points(self, rect: QRect) -> dict:
        return {
            HandlePosition.TOP_LEFT: rect.topLeft(),
            HandlePosition.TOP: QPoint(rect.center().x(), rect.top()),
            HandlePosition.TOP_RIGHT: rect.topRight(),
            HandlePosition.RIGHT: QPoint(rect.right(), rect.center().y()),
            HandlePosition.BOTTOM_RIGHT: rect.bottomRight(),
            HandlePosition.BOTTOM: QPoint(rect.center().x(), rect.bottom()),
            HandlePosition.BOTTOM_LEFT: rect.bottomLeft(),
            HandlePosition.LEFT: QPoint(rect.left(), rect.center().y()),
        }

    # ============================================================
    # Mouse Events
    # ============================================================

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()

        if self._state == CaptureState.IDLE:
            self._state = CaptureState.SELECTING
            self._start_pos = pos
            self._end_pos = pos
            self.update()

        elif self._state == CaptureState.ADJUSTING:
            r = self._get_normalized_rect()
            handle = self._get_handle_at(pos, r)
            if handle is not None:
                self._active_handle = handle
                self._drag_anchor = pos
                self._drag_start_rect = QRect(r)
                self._update_cursor_for_handle(handle)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        if self._state == CaptureState.SELECTING:
            self._end_pos = pos
            self.update()

        elif self._state == CaptureState.ADJUSTING:
            if self._active_handle is not None:
                dx = pos.x() - self._drag_anchor.x()
                dy = pos.y() - self._drag_anchor.y()
                new_rect = self._resize_rect(self._drag_start_rect, self._active_handle, dx, dy)
                self._start_pos = new_rect.topLeft()
                self._end_pos = new_rect.bottomRight()
                self.update()
            else:
                r = self._get_normalized_rect()
                handle = self._get_handle_at(pos, r)
                if handle is not None:
                    self._update_cursor_for_handle(handle)
                else:
                    self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._state == CaptureState.SELECTING:
            r = self._get_normalized_rect()
            if r.width() > 10 and r.height() > 10:
                self._state = CaptureState.ADJUSTING
            else:
                # 框选太小，重置
                self._state = CaptureState.IDLE
                self._start_pos = QPoint()
                self._end_pos = QPoint()
            self.update()

        elif self._state == CaptureState.ADJUSTING and self._active_handle is not None:
            self._active_handle = None
            self._drag_anchor = QPoint()
            self._drag_start_rect = QRect()
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()

    def mouseDoubleClickEvent(self, event):
        self.capture_screen()

    # ============================================================
    # Keyboard
    # ============================================================

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.capture_screen()
        elif key == Qt.Key.Key_Escape:
            self.close()

    # ============================================================
    # Logic
    # ============================================================

    def _get_normalized_rect(self) -> QRect:
        return QRect(self._start_pos, self._end_pos).normalized()

    def _get_handle_at(self, pos: QPoint, rect: QRect) -> Optional[HandlePosition]:
        if rect.isEmpty():
            return None
        radius = HANDLE_HIT_RADIUS
        for h_pos, h_p in self._get_handle_points(rect).items():
            if abs(pos.x() - h_p.x()) <= radius and abs(pos.y() - h_p.y()) <= radius:
                return h_pos
        return None

    def _update_cursor_for_handle(self, handle: HandlePosition):
        cursors = {
            HandlePosition.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.TOP: Qt.CursorShape.SizeVerCursor,
            HandlePosition.BOTTOM: Qt.CursorShape.SizeVerCursor,
            HandlePosition.LEFT: Qt.CursorShape.SizeHorCursor,
            HandlePosition.RIGHT: Qt.CursorShape.SizeHorCursor,
        }
        self.setCursor(cursors.get(handle, Qt.CursorShape.CrossCursor))

    def _resize_rect(self, rect: QRect, handle: HandlePosition, dx: int, dy: int) -> QRect:
        r = QRect(rect)
        if handle in (HandlePosition.TOP_LEFT, HandlePosition.LEFT, HandlePosition.BOTTOM_LEFT):
            r.setLeft(r.left() + dx)
        if handle in (HandlePosition.TOP_LEFT, HandlePosition.TOP, HandlePosition.TOP_RIGHT):
            r.setTop(r.top() + dy)
        if handle in (HandlePosition.TOP_RIGHT, HandlePosition.RIGHT, HandlePosition.BOTTOM_RIGHT):
            r.setRight(r.right() + dx)
        if handle in (HandlePosition.BOTTOM_LEFT, HandlePosition.BOTTOM, HandlePosition.BOTTOM_RIGHT):
            r.setBottom(r.bottom() + dy)

        if r.width() < 20:
            if handle in (HandlePosition.TOP_LEFT, HandlePosition.LEFT, HandlePosition.BOTTOM_LEFT):
                r.setLeft(r.right() - 20)
            else:
                r.setRight(r.left() + 20)
        if r.height() < 20:
            if handle in (HandlePosition.TOP_LEFT, HandlePosition.TOP, HandlePosition.TOP_RIGHT):
                r.setTop(r.bottom() - 20)
            else:
                r.setBottom(r.top() + 20)

        return r.intersected(self.rect())

    def _get_selected_rect(self) -> QRect:
        r = self._get_normalized_rect()
        if r.isEmpty():
            return self.rect()
        return r

    def capture_screen(self):
        """隐藏遮罩 → 截取屏幕指定区域 → 发射信号。"""
        self._state = CaptureState.CONFIRMED
        self.hide()

        # 等一帧让窗口完全隐藏
        QApplication.processEvents()

        screen = QApplication.primaryScreen()
        if screen is None:
            self.close()
            return

        target_rect = self._get_selected_rect()
        pixmap = screen.grabWindow(
            0,
            target_rect.x(),
            target_rect.y(),
            target_rect.width(),
            target_rect.height(),
        )

        image = pixmap.toImage()
        self.captured.emit(image, target_rect)
        self.close()

"""
截图遮罩窗口 — 全屏半透明覆盖层，支持连续多框捕获。

核心设计：
  - Ctrl+D 进入，可在同一屏幕连续画多个框
  - Enter 确认当前框 → 框变为绿色标记，继续捕获下一个
  - Ctrl+Z 撤销上一个已确认的框
  - Esc 发射所有已确认框并退出
  - 直接 Enter（无选区）= 全屏截图，立即发射并退出
"""
from enum import Enum, auto
from typing import Optional, List, Tuple
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
    全屏透明截图遮罩窗口 — 连续多框模式。

    - 创建时捕获全屏截图作为背景层
    - 拖拽画蓝色框（编辑中），Enter 确认后变绿色（已确认）
    - Ctrl+Z 撤销最后一个已确认框
    - Esc 发射所有已确认框的截图
    """
    # 信号：发射 (图片, 矩形) 列表
    captured = pyqtSignal(list)

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 状态机
        self._state = CaptureState.IDLE

        # 当前编辑中的选区
        self._start_pos = QPoint()
        self._end_pos = QPoint()

        # 锚点拖拽
        self._active_handle: Optional[HandlePosition] = None
        self._drag_anchor = QPoint()
        self._drag_start_rect = QRect()

        # ===== 多框支持 =====
        # 已确认的选区列表：[(rect, pixmap), ...]
        self._confirmed: List[Tuple[QRect, QPixmap]] = []

        # 全屏背景快照
        self._bg_pixmap: Optional[QPixmap] = None

    def showFullScreen(self):
        """捕获全屏快照，然后全屏显示。"""
        screen = QApplication.primaryScreen()
        if screen:
            self._bg_pixmap = screen.grabWindow(0)
        self._confirmed = []
        self._state = CaptureState.IDLE
        self._start_pos = QPoint()
        self._end_pos = QPoint()
        super().showFullScreen()

    # ============================================================
    # Paint
    # ============================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        full_rect = QRect(0, 0, w, h)

        # Layer 1: 背景图
        if self._bg_pixmap:
            painter.drawPixmap(full_rect, self._bg_pixmap, full_rect)

        # Layer 2: 暗色遮罩
        mask_alpha = int(255 * MASK_OPACITY)
        painter.fillRect(full_rect, QColor(0, 0, 0, mask_alpha))

        # ---- 已确认的框（绿色挖空 + 编号） ----
        for i, (rect, pm) in enumerate(self._confirmed):
            if self._bg_pixmap and not rect.isEmpty():
                # 挖空
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                painter.drawPixmap(rect, self._bg_pixmap, rect)

                # 绿色边框
                pen = QPen(QColor(0, 200, 80), 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)

                # 编号标签
                label = str(i + 1)
                label_size = 24
                lx = rect.left() + 4
                ly = rect.top() + 4
                painter.fillRect(
                    QRect(lx - 2, ly - 2, label_size, label_size),
                    QColor(0, 180, 60, 220),
                )
                painter.setPen(QColor(255, 255, 255))
                font = QFont("Microsoft YaHei", 12, QFont.Weight.Bold)
                painter.setFont(font)
                painter.drawText(QRect(lx, ly, label_size - 4, label_size - 4),
                                 Qt.AlignmentFlag.AlignCenter, label)

        # ---- 当前编辑中的框（蓝色） ----
        r = self._get_normalized_rect()
        if not r.isEmpty() and self._bg_pixmap:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawPixmap(r, self._bg_pixmap, r)

            # 蓝色边框
            pen = QPen(QColor(30, 144, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)

            # 外发光
            glow_pen = QPen(QColor(255, 255, 255, 80), 4)
            painter.setPen(glow_pen)
            painter.drawRect(r)

            # 尺寸标签
            size_text = f"{r.width()} × {r.height()}"
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)
            painter.setFont(font)
            label_y = r.top() - 24
            if label_y < 4:
                label_y = r.bottom() + 4
            text_rect = QRect(r.left(), label_y, r.width(), 20)
            painter.fillRect(text_rect.adjusted(-6, -2, 6, 2), QColor(30, 144, 255, 200))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, size_text)

            # 锚点
            if self._state == CaptureState.ADJUSTING:
                self._draw_handles(painter, r)

        # ---- 提示文字 ----
        count = len(self._confirmed)
        if self._state == CaptureState.IDLE and count == 0:
            # 初始提示
            hint_font = QFont("Microsoft YaHei", 16, QFont.Weight.Bold)
            painter.setFont(hint_font)
            painter.setPen(QColor(0, 0, 0, 160))
            painter.drawText(QRect(1, 51, w, 30), Qt.AlignmentFlag.AlignCenter,
                             "🖱️ 拖拽鼠标框选截图区域")
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(QRect(0, 50, w, 30), Qt.AlignmentFlag.AlignCenter,
                             "🖱️ 拖拽鼠标框选截图区域")

            hint2_font = QFont("Microsoft YaHei", 12)
            painter.setFont(hint2_font)
            painter.setPen(QColor(255, 255, 255, 180))
            painter.drawText(QRect(0, 80, w, 24), Qt.AlignmentFlag.AlignCenter,
                             "Enter 确认当前框  |  Ctrl+Z 撤销  |  Esc 完成")
        else:
            # 状态栏
            status_parts = []
            if count > 0:
                status_parts.append(f"✅ 已选 {count} 个区域")
            if self._state == CaptureState.ADJUSTING:
                status_parts.append("拖拽锚点调整")
            elif self._state == CaptureState.SELECTING:
                status_parts.append("正在拖拽选区...")
            else:
                status_parts.append("拖拽画新框")
            status_parts.append("Enter 确认当前框")
            status_parts.append("Ctrl+Z 撤销")
            status_parts.append("Esc 完成")

            status_text = "  |  ".join(status_parts)
            status_font = QFont("Microsoft YaHei", 11)
            painter.setFont(status_font)

            # 底部半透明状态栏
            bar_y = h - 40
            painter.fillRect(QRect(0, bar_y, w, 40), QColor(0, 0, 0, 180))
            painter.setPen(QColor(200, 220, 255))
            painter.drawText(QRect(0, bar_y, w, 40), Qt.AlignmentFlag.AlignCenter, status_text)

        painter.end()

    def _draw_handles(self, painter: QPainter, rect: QRect):
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

        if self._state in (CaptureState.IDLE, CaptureState.SELECTING):
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
                new_rect = self._resize_rect(
                    self._drag_start_rect, self._active_handle, dx, dy)
                self._start_pos = new_rect.topLeft()
                self._end_pos = new_rect.bottomRight()
                self.update()
            else:
                r = self._get_normalized_rect()
                handle = self._get_handle_at(pos, r)
                if handle:
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
                self._state = CaptureState.IDLE
                self._start_pos = QPoint()
                self._end_pos = QPoint()
            self.update()

        elif self._state == CaptureState.ADJUSTING and self._active_handle is not None:
            self._active_handle = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()

    # ============================================================
    # Keyboard
    # ============================================================

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+Z → 撤销
        if key == Qt.Key.Key_Z and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self._undo_last()
            return

        # Enter → 确认当前框
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm_current()
            return

        # Esc → 发射所有并退出
        if key == Qt.Key.Key_Escape:
            self._finish_and_exit()
            return

    # ============================================================
    # Logic
    # ============================================================

    def _confirm_current(self):
        """确认当前编辑框，加入已确认列表，重置准备下一个。"""
        r = self._get_normalized_rect()

        if r.isEmpty() or r.width() <= 10 or r.height() <= 10:
            # 无选区 → 全屏截图
            r = QRect(0, 0, self.width(), self.height())
            self._confirmed.append((r, self._bg_pixmap.copy(r) if self._bg_pixmap else QPixmap()))
            self._finish_and_exit()
            return

        # 截取当前区域的小缩略图
        thumb = self._bg_pixmap.copy(r) if self._bg_pixmap else QPixmap()
        self._confirmed.append((r, thumb))

        # 重置状态
        self._state = CaptureState.IDLE
        self._start_pos = QPoint()
        self._end_pos = QPoint()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _undo_last(self):
        """撤销最后一个已确认框。"""
        if self._confirmed:
            self._confirmed.pop()
            self.update()

    def _finish_and_exit(self):
        """截取所有已确认区域，发射信号，退出。"""
        self.hide()
        QApplication.processEvents()

        screen = QApplication.primaryScreen()
        if screen is None:
            self.close()
            return

        results = []
        for rect, _ in self._confirmed:
            pixmap = screen.grabWindow(
                0, rect.x(), rect.y(), rect.width(), rect.height())
            results.append((pixmap.toImage(), rect))

        # 无已确认框 → 返回空列表
        self.captured.emit(results)
        self.close()

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

"""
截图遮罩窗口 — 全屏半透明，拖拽松手即自动确认选区，可连续画多框。

- Ctrl+D 进入，拖拽画框，松手自动确认变绿
- 继续拖拽画下一个框
- Ctrl+Z 撤销上一个框
- Enter 发射所有已确认框（列表），关闭
- Esc 取消，不发射，关闭
"""
from typing import Optional, List, Tuple
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont,
    QPixmap, QImage,
)
from PyQt6.QtWidgets import QWidget, QApplication

from config import MASK_OPACITY, HANDLE_SIZE, HANDLE_HIT_RADIUS


class CaptureState:
    IDLE = 0
    SELECTING = 1
    ADJUSTING = 2


class CaptureWindow(QWidget):
    """
    连续多框截图遮罩。

    - 拖拽画框 → 松手自动确认（变绿标号）
    - 已确认框可点中锚点调整
    - Ctrl+Z 撤销最后一个已确认框
    - Enter → 发射所有已确认框截图列表
    - Esc → 取消关闭
    """
    captured = pyqtSignal(list)  # list of (QImage, QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._state = CaptureState.IDLE

        # 当前编辑中的选区
        self._start = QPoint()
        self._end = QPoint()
        self._active_handle = -1
        self._drag_anchor = QPoint()
        self._drag_start_rect = QRect()

        # 已确认的选区
        self._confirmed: List[Tuple[QRect, QPixmap]] = []

        self._bg: Optional[QPixmap] = None

    # ============================================================
    # Lifecycle
    # ============================================================

    def showFullScreen(self):
        screen = QApplication.primaryScreen()
        if screen:
            self._bg = screen.grabWindow(0)
        self._confirmed = []
        self._state = CaptureState.IDLE
        self._start = QPoint()
        self._end = QPoint()
        self._active_handle = -1
        super().showFullScreen()
        self.activateWindow()
        self.raise_()

    # ============================================================
    # Paint
    # ============================================================

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        full = QRect(0, 0, w, h)

        # 背景
        if self._bg:
            p.drawPixmap(full, self._bg, full)
        p.fillRect(full, QColor(0, 0, 0, int(255 * MASK_OPACITY)))

        # ---- 已确认框（绿色） ----
        for i, (rect, _) in enumerate(self._confirmed):
            if not rect.isEmpty() and self._bg:
                p.drawPixmap(rect, self._bg, rect)
                p.setPen(QPen(QColor(0, 200, 80), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect)

                # 编号标签
                label = str(i + 1)
                sz = 22
                lx, ly = rect.left() + 3, rect.top() + 3
                p.fillRect(QRect(lx - 1, ly - 1, sz, sz), QColor(0, 180, 60, 230))
                p.setPen(QColor(255, 255, 255))
                p.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
                p.drawText(QRect(lx, ly, sz - 2, sz - 2),
                            Qt.AlignmentFlag.AlignCenter, label)

        # ---- 当前编辑框（蓝色） ----
        r = self._normalized()
        if not r.isEmpty() and self._bg:
            p.drawPixmap(r, self._bg, r)
            p.setPen(QPen(QColor(30, 144, 255), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            p.setPen(QPen(QColor(255, 255, 255, 80), 4))
            p.drawRect(r)
            # 尺寸
            txt = f"{r.width()} × {r.height()}"
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
            ly = r.top() - 24
            if ly < 4:
                ly = r.bottom() + 4
            tr = QRect(r.left(), ly, r.width(), 20)
            p.fillRect(tr.adjusted(-6, -2, 6, 2), QColor(30, 144, 255, 200))
            p.drawText(tr, Qt.AlignmentFlag.AlignCenter, txt)
            # 锚点
            self._draw_handles(p, r)

        # ---- 提示栏 ----
        count = len(self._confirmed)
        bar_y = h - 40
        p.fillRect(QRect(0, bar_y, w, 40), QColor(0, 0, 0, 180))

        if count == 0 and self._state == CaptureState.IDLE:
            hint = "🖱️ 拖拽画框（松手自动确认）  |  Enter 全部放入对话框  |  Esc 取消"
        elif self._state == CaptureState.SELECTING:
            hint = "松手确认当前框  |  Enter 全部放入对话框  |  Esc 取消"
        else:
            parts = [f"✅ 已确认 {count} 个区域"]
            if self._state == CaptureState.IDLE:
                parts.append("继续拖拽画新框")
            parts.append("Ctrl+Z 撤销")
            parts.append("Enter 全部放入对话框")
            parts.append("Esc 取消")
            hint = "  |  ".join(parts)

        p.setFont(QFont("Microsoft YaHei", 11))
        p.setPen(QColor(200, 220, 255))
        p.drawText(QRect(0, bar_y, w, 40), Qt.AlignmentFlag.AlignCenter, hint)

        p.end()

    def _draw_handles(self, p, r):
        s = HANDLE_SIZE
        pts = {
            0: r.topLeft(), 1: QPoint(r.center().x(), r.top()),
            2: r.topRight(), 3: QPoint(r.right(), r.center().y()),
            4: r.bottomRight(), 5: QPoint(r.center().x(), r.bottom()),
            6: r.bottomLeft(), 7: QPoint(r.left(), r.center().y()),
        }
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(QBrush(QColor(30, 144, 255)))
        for pt in pts.values():
            p.drawRect(QRect(pt.x() - s // 2, pt.y() - s // 2, s, s))

    def _normalized(self):
        return QRect(self._start, self._end).normalized()

    def _handle_at(self, pos):
        r = self._normalized()
        if r.isEmpty():
            return -1
        pts = {
            0: r.topLeft(), 1: QPoint(r.center().x(), r.top()),
            2: r.topRight(), 3: QPoint(r.right(), r.center().y()),
            4: r.bottomRight(), 5: QPoint(r.center().x(), r.bottom()),
            6: r.bottomLeft(), 7: QPoint(r.left(), r.center().y()),
        }
        for h_idx, pt in pts.items():
            if abs(pos.x() - pt.x()) <= HANDLE_HIT_RADIUS and abs(pos.y() - pt.y()) <= HANDLE_HIT_RADIUS:
                return h_idx
        return -1

    _cursors = {
        0: Qt.CursorShape.SizeFDiagCursor, 4: Qt.CursorShape.SizeFDiagCursor,
        2: Qt.CursorShape.SizeBDiagCursor, 6: Qt.CursorShape.SizeBDiagCursor,
        1: Qt.CursorShape.SizeVerCursor, 5: Qt.CursorShape.SizeVerCursor,
        3: Qt.CursorShape.SizeHorCursor, 7: Qt.CursorShape.SizeHorCursor,
    }

    # ============================================================
    # Mouse — 松手自动确认
    # ============================================================

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        self._active_handle = -1

        # 检查是否点在已确认框的锚点上（用于调整已确认框）
        if self._state == CaptureState.IDLE:
            for idx, (rect, _) in enumerate(self._confirmed):
                h = self._handle_on_rect(pos, rect)
                if h >= 0:
                    self._active_handle = h
                    self._editing_confirmed_idx = idx
                    self._drag_anchor = pos
                    self._drag_start_rect = QRect(rect)
                    self._state = CaptureState.ADJUSTING
                    self.setCursor(self._cursors.get(h, Qt.CursorShape.CrossCursor))
                    return

        # 开始新选区
        self._state = CaptureState.SELECTING
        self._start = pos
        self._end = pos
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._state == CaptureState.SELECTING:
            self._end = pos
            self.update()
        elif self._state == CaptureState.ADJUSTING:
            if self._active_handle >= 0 and hasattr(self, '_editing_confirmed_idx'):
                dx = pos.x() - self._drag_anchor.x()
                dy = pos.y() - self._drag_anchor.y()
                nr = self._resize(self._drag_start_rect, self._active_handle, dx, dy)
                rects = list(self._confirmed)
                idx = self._editing_confirmed_idx
                rects[idx] = (nr, rects[idx][1])
                self._confirmed = rects
                self.update()
            else:
                r = self._normalized()
                h = self._handle_at(pos)
                self.setCursor(self._cursors.get(h, Qt.CursorShape.CrossCursor) if h >= 0 else Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return

        if self._state == CaptureState.SELECTING:
            r = self._normalized()
            if r.width() > 10 and r.height() > 10:
                # 松手 → 自动确认
                thumb = self._bg.copy(r) if self._bg else QPixmap()
                self._confirmed.append((r, thumb))
            # 重置，准备下一个框
            self._state = CaptureState.IDLE
            self._start = QPoint()
            self._end = QPoint()
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()

        elif self._state == CaptureState.ADJUSTING:
            self._active_handle = -1
            if hasattr(self, '_editing_confirmed_idx'):
                del self._editing_confirmed_idx
            self._state = CaptureState.IDLE
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()

    def _handle_on_rect(self, pos, rect):
        """检查 pos 是否在某已确认框的锚点上。"""
        pts = {
            0: rect.topLeft(), 1: QPoint(rect.center().x(), rect.top()),
            2: rect.topRight(), 3: QPoint(rect.right(), rect.center().y()),
            4: rect.bottomRight(), 5: QPoint(rect.center().x(), rect.bottom()),
            6: rect.bottomLeft(), 7: QPoint(rect.left(), rect.center().y()),
        }
        for h_idx, pt in pts.items():
            if abs(pos.x() - pt.x()) <= HANDLE_HIT_RADIUS and abs(pos.y() - pt.y()) <= HANDLE_HIT_RADIUS:
                return h_idx
        return -1

    def _resize(self, rect, handle, dx, dy):
        r = QRect(rect)
        if handle in (0, 6, 7):
            r.setLeft(r.left() + dx)
        if handle in (0, 1, 2):
            r.setTop(r.top() + dy)
        if handle in (2, 3, 4):
            r.setRight(r.right() + dx)
        if handle in (4, 5, 6):
            r.setBottom(r.bottom() + dy)
        if r.width() < 20:
            if handle in (0, 6, 7):
                r.setLeft(r.right() - 20)
            else:
                r.setRight(r.left() + 20)
        if r.height() < 20:
            if handle in (0, 1, 2):
                r.setTop(r.bottom() - 20)
            else:
                r.setBottom(r.top() + 20)
        return r.intersected(self.rect())

    # ============================================================
    # Keyboard
    # ============================================================

    def keyPressEvent(self, e):
        # Ctrl+Z → 撤销
        if e.key() == Qt.Key.Key_Z and (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self._confirmed:
                self._confirmed.pop()
                self.update()
            return

        # Enter → 发射所有已确认框
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._emit_all()
            return

        # Esc → 取消
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def _emit_all(self):
        """截取所有已确认框，发射 list of (QImage, QRect)，关闭。"""
        if not self._confirmed:
            self.close()
            return

        self.hide()
        QApplication.processEvents()

        screen = QApplication.primaryScreen()
        if screen is None:
            self.close()
            return

        results = []
        for rect, _ in self._confirmed:
            pix = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
            results.append((pix.toImage(), rect))

        self.captured.emit(results)
        self.close()

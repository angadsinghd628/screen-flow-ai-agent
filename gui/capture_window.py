"""
截图遮罩窗口 — 全屏半透明覆盖层，单次拖拽选一个区域。

- Ctrl+D 进入，拖拽画框，8 锚点调整
- Enter 确认截图 → 发射信号并关闭
- Esc 取消 → 不截图关闭
"""
from typing import Optional
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


class HandlePosition:
    TL, T, TR, R, BR, B, BL, L = range(8)


HANDLE_NAMES = {
    0: 'TL', 1: 'T', 2: 'TR', 3: 'R',
    4: 'BR', 5: 'B', 6: 'BL', 7: 'L',
}


class CaptureWindow(QWidget):
    """
    全屏截图遮罩 — 单个矩形选区。
    Enter 确认 → 发射 captured(image, rect) 信号。
    Esc 取消 → 关闭不发射。
    """
    captured = pyqtSignal(QImage, QRect)

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
        self._start = QPoint()
        self._end = QPoint()
        self._active_handle = -1
        self._drag_anchor = QPoint()
        self._drag_start_rect = QRect()
        self._bg: Optional[QPixmap] = None

    def showFullScreen(self):
        screen = QApplication.primaryScreen()
        if screen:
            self._bg = screen.grabWindow(0)
        self._state = CaptureState.IDLE
        self._start = QPoint()
        self._end = QPoint()
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

        r = self._rect()
        if not r.isEmpty() and self._bg:
            # 挖空
            p.drawPixmap(r, self._bg, r)
            # 蓝色边框
            p.setPen(QPen(QColor(30, 144, 255), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            # 发光
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
            if self._state == CaptureState.ADJUSTING:
                self._draw_handles(p, r)

        # 提示
        p.setFont(QFont("Microsoft YaHei", 14 if self._state == CaptureState.IDLE else 11,
                        QFont.Weight.Bold if self._state == CaptureState.IDLE else QFont.Weight.Normal))
        if self._state == CaptureState.IDLE:
            p.setPen(QColor(0, 0, 0, 160))
            p.drawText(QRect(1, 51, w, 30), Qt.AlignmentFlag.AlignCenter, "🖱️ 拖拽鼠标框选截图区域")
            p.setPen(QColor(255, 255, 255, 230))
            p.drawText(QRect(0, 50, w, 30), Qt.AlignmentFlag.AlignCenter, "🖱️ 拖拽鼠标框选截图区域")
            p.setFont(QFont("Microsoft YaHei", 12))
            p.setPen(QColor(255, 255, 255, 180))
            p.drawText(QRect(0, 80, w, 24), Qt.AlignmentFlag.AlignCenter,
                        "Enter 确认放入对话框  |  Esc 取消")
        else:
            bar_y = h - 40
            p.fillRect(QRect(0, bar_y, w, 40), QColor(0, 0, 0, 180))
            p.setPen(QColor(200, 220, 255))
            p.drawText(QRect(0, bar_y, w, 40), Qt.AlignmentFlag.AlignCenter,
                        "拖拽锚点调整  |  Enter 确认  |  Esc 取消")
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
            p.drawRect(QRect(pt.x() - s//2, pt.y() - s//2, s, s))

    def _rect(self):
        return QRect(self._start, self._end).normalized()

    def _handle_at(self, pos):
        r = self._rect()
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
    # Mouse
    # ============================================================

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        if self._state in (CaptureState.IDLE, CaptureState.SELECTING):
            self._state = CaptureState.SELECTING
            self._start = pos
            self._end = pos
            self.update()
        elif self._state == CaptureState.ADJUSTING:
            h = self._handle_at(pos)
            if h >= 0:
                self._active_handle = h
                self._drag_anchor = pos
                self._drag_start_rect = QRect(self._rect())
                self.setCursor(self._cursors.get(h, Qt.CursorShape.CrossCursor))

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._state == CaptureState.SELECTING:
            self._end = pos
            self.update()
        elif self._state == CaptureState.ADJUSTING:
            if self._active_handle >= 0:
                dx = pos.x() - self._drag_anchor.x()
                dy = pos.y() - self._drag_anchor.y()
                nr = self._resize(self._drag_start_rect, self._active_handle, dx, dy)
                self._start = nr.topLeft()
                self._end = nr.bottomRight()
                self.update()
            else:
                h = self._handle_at(pos)
                if h >= 0:
                    self.setCursor(self._cursors.get(h, Qt.CursorShape.CrossCursor))
                else:
                    self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == CaptureState.SELECTING:
            r = self._rect()
            if r.width() > 10 and r.height() > 10:
                self._state = CaptureState.ADJUSTING
            else:
                self._state = CaptureState.IDLE
                self._start = QPoint()
                self._end = QPoint()
            self.update()
        elif self._state == CaptureState.ADJUSTING and self._active_handle >= 0:
            self._active_handle = -1
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()

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
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._capture()
        elif e.key() == Qt.Key.Key_Escape:
            self.close()

    def _capture(self):
        r = self._rect()
        if r.isEmpty() or r.width() <= 10 or r.height() <= 10:
            return  # 没画框，忽略
        self.hide()
        QApplication.processEvents()
        screen = QApplication.primaryScreen()
        if screen:
            pix = screen.grabWindow(0, r.x(), r.y(), r.width(), r.height())
            self.captured.emit(pix.toImage(), r)
        self.close()

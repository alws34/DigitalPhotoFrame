from PySide6 import QtWidgets, QtGui, QtCore
from typing import Optional

class ImageCanvas(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qimage: Optional[QtGui.QImage] = None
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        # Black background by default
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)

    @QtCore.Slot(QtGui.QImage)
    def set_qimage(self, qimage: QtGui.QImage) -> None:
        self._qimage = qimage
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QtCore.Qt.black)

        if self._qimage is None or self._qimage.isNull():
            return

        iw = self._qimage.width()
        ih = self._qimage.height()
        ww = self.width()
        wh = self.height()
        if iw <= 0 or ih <= 0 or ww <= 0 or wh <= 0:
            return

        image_ar = iw / float(ih)
        widget_ar = ww / float(wh)

        # "Fit Center" logic (contain)
        if widget_ar > image_ar:
            new_h = int(round(iw / widget_ar))
            new_h = min(new_h, ih)
            y = max(0, (ih - new_h) // 2)
            src = QtCore.QRect(0, y, iw, new_h)
        else:
            new_w = int(round(ih * widget_ar))
            new_w = min(new_w, iw)
            x = max(0, (iw - new_w) // 2)
            src = QtCore.QRect(x, 0, new_w, ih)

        painter.drawImage(self.rect(), self._qimage, src)

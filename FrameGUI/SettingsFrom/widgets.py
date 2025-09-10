from __future__ import annotations
from PySide6 import QtCore, QtGui, QtWidgets
from typing import List

# ---------- Sparkline ----------
class Sparkline(QtWidgets.QWidget):
    def __init__(self, parent=None, maxlen=60):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self._maxlen = maxlen
        self._data: List[float] = []

    @QtCore.Slot(float)
    def push(self, v: float):
        try: v = float(v)
        except: return
        self._data.append(v)
        if len(self._data) > self._maxlen:
            self._data = self._data[-self._maxlen:]
        self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        r = self.rect().adjusted(0,0,-1,-1)
        p.fillRect(r, QtGui.QColor("#ffffff"))
        p.setPen(QtGui.QPen(QtGui.QColor("#e0e0e0")))
        p.drawRect(r)

        if len(self._data) < 2: return
        vals = self._data
        vmin, vmax = 0.0, 100.0 #min(vals), max(vals)
        rng = (vmax - vmin) or 1.0

        left, top, right, bottom = r.left()+6, r.top()+6, r.right()-6, r.bottom()-6
        w = right - left
        h = bottom - top

        pts = []
        for i,v in enumerate(vals):
            x = left + (i * w / max(1, len(vals)-1))
            y = bottom - ((v - vmin) / rng) * h
            pts.append(QtCore.QPointF(x,y))

        # area
        area = [QtCore.QPointF(pts[0].x(), bottom)] + pts + [QtCore.QPointF(pts[-1].x(), bottom)]
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#e8f2ff"))
        p.drawPolygon(QtGui.QPolygonF(area))

        # line
        p.setPen(QtGui.QPen(QtGui.QColor("#1976d2"), 2))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPolyline(QtGui.QPolygonF(pts))

        # last point dot
        p.setBrush(QtGui.QColor("#1e88e5"))
        p.drawEllipse(pts[-1], 2.5, 2.5)

# ---------- On-screen keyboard ----------
class OnScreenKeyboard(QtWidgets.QWidget):
    keyPressed = QtCore.Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.caps = False
        self.shift = False
        self.symbols = False
        self._repeat = QtCore.QTimer(self, interval=50)
        self._repeat.timeout.connect(self._repeat_backspace)
        self._backspace_down = False
        self._build()

    def _build(self):
        layout = QtWidgets.QGridLayout(self); layout.setSpacing(4)
        self._rows_letters = [
            ["`","1","2","3","4","5","6","7","8","9","0","-","=","Backspace"],
            ["Tab","q","w","e","r","t","y","u","i","o","p","[","]","\\"],
            ["Caps","a","s","d","f","g","h","j","k","l",";","'","Enter"],
            ["Shift","z","x","c","v","b","n","m",",",".","/","Shift"],
            ["123/#","Space","Left","Right"]
        ]
        self._rows_symbols = [
            ["~","!","@","#","$","%","^","&","*","(",")","_","+","Backspace"],
            ["Tab","q","w","e","r","t","y","u","i","o","p","{","}","|"],
            ["Caps","a","s","d","f","g","h","j","k","l",":","\"","Enter"],
            ["Shift","z","x","c","v","b","n","m","<",">","?","Shift"],
            ["ABC","Space","Left","Right"]
        ]
        self._layout = layout
        self._refresh_keys()

    def _refresh_keys(self):
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w: w.deleteLater()
        rows = self._rows_symbols if self.symbols else self._rows_letters
        def add(row, col, text, cs=1):
            b = QtWidgets.QPushButton(self._display(text))
            b.setFixedHeight(36)
            b.pressed.connect(lambda t=text: self._on_press(t))
            if text == "Backspace":
                b.pressed.connect(self._start_repeat)
                b.released.connect(self._stop_repeat)
            self._layout.addWidget(b, row, col, 1, cs)
        c=0
        for k in rows[0]:
            add(0, c, k, 2 if k=="Backspace" else 1); c += 2 if k=="Backspace" else 1
        c=0
        for k in rows[1]:
            add(1, c, k, 2 if k=="Tab" else 1); c += 2 if k=="Tab" else 1
        c=0
        for k in rows[2]:
            add(2, c, k, 2 if k in ("Caps","Enter") else 1); c += 2 if k in ("Caps","Enter") else 1
        c=0
        for k in rows[3]:
            add(3, c, k, 2 if k=="Shift" else 1); c += 2 if k=="Shift" else 1
        # bottom row
        add(4,0, rows[4][0], 2)
        add(4,2, rows[4][1], 10)
        add(4,12, rows[4][2])
        add(4,13, rows[4][3])

    def _display(self, label):
        if label in ("Space","Enter","Tab","Backspace","Left","Right","Caps","Shift","123/#","ABC"):
            return label
        ch = label
        if not self.symbols:
            ch = ch.upper() if (self.shift ^ self.caps) else ch.lower()
        return ch

    def _start_repeat(self):
        self._backspace_down = True
        QtCore.QTimer.singleShot(250, lambda: self._repeat.start() if self._backspace_down else None)

    def _stop_repeat(self):
        self._backspace_down = False
        self._repeat.stop()

    def _repeat_backspace(self):
        if self._backspace_down:
            self.keyPressed.emit("Backspace")

    def _on_press(self, label):
        if label in ("123/#","ABC"):
            self.symbols = not self.symbols; self.shift = False; self._refresh_keys(); return
        if label == "Caps":
            self.caps = not self.caps; self._refresh_keys(); return
        if label == "Shift":
            self.shift = not self.shift; self._refresh_keys(); return
        self.keyPressed.emit(self._display(label))
        if label not in ("Caps","Shift") and self.shift:
            self.shift = False; self._refresh_keys()

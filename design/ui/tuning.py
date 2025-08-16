from collections import deque

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from singleton import VariaveisGlobais


class TrendWidget(QWidget):
    def __init__(self, tag, max_points=600, parent=None):
        super().__init__(parent)
        self.tag = tag
        self.max_points = max_points
        self.setMinimumHeight(220)
        self.setStyleSheet("background-color: black;")

        self.buf_pv = deque(maxlen=max_points)
        self.buf_sp = deque(maxlen=max_points)
        self.buf_mv = deque(maxlen=max_points)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sample)
        self.timer.start(200)

    def sample(self):
        vg = VariaveisGlobais()
        self.buf_pv.append(float(vg.get(f"{self.tag}.pv", 0)))
        self.buf_sp.append(float(vg.get(f"{self.tag}.sp", 0)))
        self.buf_mv.append(float(vg.get(f"{self.tag}.mv", 0)))
        self.update()

    def _map(self, val, h, top=10, bottom=10):
        usable = h - (top + bottom)
        val = max(0.0, min(100.0, val))
        return int(top + (100.0 - val) * (usable / 100.0))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("black"))

        w, h = self.width(), self.height()

        def draw(buf, color):
            if len(buf) < 2:
                return
            p.setPen(QPen(color, 2))
            step = max(1.0, w / float(self.max_points))
            x_right = w - 1
            prev = None
            for i, val in enumerate(reversed(buf)):
                x = int(x_right - i * step)
                y = self._map(val, h)
                if prev and x >= 0:
                    p.drawLine(prev[0], prev[1], x, y)
                prev = (x, y)

        draw(self.buf_pv, QColor(0, 255, 255))  # ciano
        draw(self.buf_sp, QColor(255, 0, 255))  # magenta
        draw(self.buf_mv, QColor(255, 255, 0))  # amarelo


class TuningDialog(QDialog):
    def __init__(self, tag, parent=None):
        super().__init__(parent)
        self.tag = tag
        self.vg = VariaveisGlobais()

        self.setWindowTitle(f"Tuning - {tag}")
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: black; color: #00FF00;")

        # ---- Edição rápida de PV / SP / MV ----
        self.edPV = QDoubleSpinBox()
        self.edPV.setRange(-1e9, 1e9)
        self.edPV.setStyleSheet("background:#111; color:#00FF00;")
        self.edSP = QDoubleSpinBox()
        self.edSP.setRange(-1e9, 1e9)
        self.edSP.setStyleSheet("background:#111; color:#00FF00;")
        self.edMV = QDoubleSpinBox()
        self.edMV.setRange(0, 100)
        self.edMV.setStyleSheet("background:#111; color:#00FF00;")

        self.btnApplyVals = QPushButton("Aplicar PV/SP/MV")
        self.btnApplyVals.setStyleSheet("background:#222; color:#00FF00;")
        self.btnApplyVals.clicked.connect(self.apply_values)
        # Empurre este botão para a área de botões inferior

        top_layout = QGridLayout()

        top_layout.addWidget(QLabel("Set PV"), 3, 0)
        top_layout.addWidget(self.edPV, 3, 1)
        top_layout.addWidget(QLabel("Set SP"), 3, 2)
        top_layout.addWidget(self.edSP, 3, 3)
        top_layout.addWidget(QLabel("Set MV"), 3, 4)
        top_layout.addWidget(self.edMV, 3, 5)

        font_val = QFont("Consolas", 11)

        def mk_label(txt):
            l = QLabel(txt)
            l.setStyleSheet("color:#00FF00;")
            l.setFont(QFont("Arial", 10, QFont.Bold))
            return l

        def mk_val():
            l = QLabel("0.00")
            l.setFont(font_val)
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            l.setStyleSheet("background:#111; color:#00FF00; padding:3px;")
            return l

        self.lblPV = mk_val()
        self.lblSP = mk_val()
        self.lblMV = mk_val()

        self.spnKp = QDoubleSpinBox()
        self.spnKi = QDoubleSpinBox()
        self.spnKd = QDoubleSpinBox()
        for spn in (self.spnKp, self.spnKi, self.spnKd):
            spn.setRange(-1e9, 1e9)
            spn.setDecimals(7)
            spn.setStyleSheet("background:#111; color:#00FF00;")

        self.cmbMode = QComboBox()
        self.cmbMode.addItems(["MAN", "AUT", "CAS", "PRD"])
        self.cmbMode.setStyleSheet("background:#111; color:#00FF00;")
        self.chkSPT = QCheckBox("SP Tracking (em MAN)")
        self.chkSPT.setStyleSheet("color:#00FF00;")
        top_layout.addWidget(self.chkSPT, 2, 4, 1, 2)  # onde couber melhor no grid

        self.lblAlarm = QLabel("OK")
        self.lblAlarm.setAlignment(Qt.AlignCenter)
        self.lblAlarm.setStyleSheet("background:#111; color:#00FF00;")

        top_layout.addWidget(mk_label("PV"), 0, 0)
        top_layout.addWidget(self.lblPV, 0, 1)
        top_layout.addWidget(mk_label("SP"), 0, 2)
        top_layout.addWidget(self.lblSP, 0, 3)
        top_layout.addWidget(mk_label("MV"), 0, 4)
        top_layout.addWidget(self.lblMV, 0, 5)

        top_layout.addWidget(mk_label("Kp"), 1, 0)
        top_layout.addWidget(self.spnKp, 1, 1)
        top_layout.addWidget(mk_label("Ki"), 1, 2)
        top_layout.addWidget(self.spnKi, 1, 3)
        top_layout.addWidget(mk_label("Kd"), 1, 4)
        top_layout.addWidget(self.spnKd, 1, 5)

        top_layout.addWidget(mk_label("Mode"), 2, 0)
        top_layout.addWidget(self.cmbMode, 2, 1)
        top_layout.addWidget(mk_label("ALARME"), 2, 2)
        top_layout.addWidget(self.lblAlarm, 2, 3, 1, 3)

        self.trend = TrendWidget(tag)

        btns = QHBoxLayout()
        btn_apply = QPushButton("Aplicar")
        btn_apply.clicked.connect(self.apply)
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        for b in (btn_apply, btn_close):
            b.setStyleSheet("background:#222; color:#00FF00;")
        btns.insertWidget(0, self.btnApplyVals)
        btns.addStretch()
        btns.addWidget(btn_apply)
        btns.addWidget(btn_close)
        layout = QVBoxLayout(self)
        layout.addLayout(top_layout)
        layout.addWidget(self.trend)
        layout.addLayout(btns)

        self.timer_ui = QTimer(self)
        self.timer_ui.timeout.connect(self.update_values)
        self.timer_ui.start(200)
        self.load_initial()

    def load_initial(self):
        conf = self.vg.get(f"{self.tag}.controle", {}) or {}
        self.spnKp.setValue(conf.get("Kp", 1.0))
        self.spnKi.setValue(conf.get("Ki", 0.0))
        self.spnKd.setValue(conf.get("Kd", 0.0))
        self.cmbMode.setCurrentText(self.vg.get(f"{self.tag}.modo", "MAN"))
        self.chkSPT.setChecked(conf.get("sp_tracking", False))  # <<< novo

    def update_values(self):
        pv = self.vg.get(f"{self.tag}.pv", 0)
        sp = self.vg.get(f"{self.tag}.sp", 0)
        mv = self.vg.get(f"{self.tag}.mv", 0)
        self.lblPV.setText(f"{pv:.2f}")
        self.lblSP.setText(f"{sp:.2f}")
        self.lblMV.setText(f"{mv:.2f}")

    def apply(self):
        conf = self.vg.get(f"{self.tag}.controle", {}) or {}
        conf["Kp"] = self.spnKp.value()
        conf["Ki"] = self.spnKi.value()
        conf["Kd"] = self.spnKd.value()
        conf["sp_tracking"] = self.chkSPT.isChecked()  # <<< novo
        self.vg.set(f"{self.tag}.controle", conf)
        self.vg.set(f"{self.tag}.modo", self.cmbMode.currentText())

    def _limits(self):
        conf = self.vg.get(f"{self.tag}.controle", {}) or {}
        pv_min = conf.get("pv_min", 0.0)
        pv_max = conf.get("pv_max", 100.0)
        if pv_min > pv_max:
            pv_min, pv_max = pv_max, pv_min
        return pv_min, pv_max

    def update_values(self):
        pv = self.vg.get(f"{self.tag}.pv", 0)
        sp = self.vg.get(f"{self.tag}.sp", 0)
        mv = self.vg.get(f"{self.tag}.mv", 0)
        self.lblPV.setText(f"{pv:.2f}")
        self.lblSP.setText(f"{sp:.2f}")
        self.lblMV.setText(f"{mv:.2f}")

        # refletir nos spinboxes também
        self.edPV.setValue(pv)
        self.edSP.setValue(sp)
        self.edMV.setValue(mv)

        # habilitar/desabilitar conforme modo
        m = self.vg.get(f"{self.tag}.modo", "MAN")
        # PV sempre editável (simulação / injeção), mas clipado por limites
        self.edPV.setEnabled(True)
        # SP: AUT/PRD habilita; CAS desabilita (slave); MAN opcionalmente habilitado p/ pré-ajuste
        self.edSP.setEnabled(m in ("MAN", "AUT", "PRD"))
        # MV: só MAN
        self.edMV.setEnabled(m == "MAN")

    def apply_values(self):
        pv_min, pv_max = self._limits()
        # usa as APIs com regra
        self.vg.set_pv(self.tag, self.edPV.value())
        self.vg.set_sp(self.tag, self.edSP.value())  # CAS manual será ignorado
        self.vg.set_mv(self.tag, self.edMV.value())  # só MAN efetiva

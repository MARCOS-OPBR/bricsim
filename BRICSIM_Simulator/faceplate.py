import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QFrame, QMenu, QAction, QDialog, QLineEdit, QPushButton,QMessageBox
)
from PyQt5.QtCore import Qt, QPointF, QTimer
from PyQt5.QtGui import QFont, QPainter, QColor, QPolygonF, QPen

from singleton import VariaveisGlobais


# ------------------------------
# Utilitários visuais
# ------------------------------

class ValueInputDialog(QDialog):
    """Janela para entrada de valores numéricos (campo preto, texto verde)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alterar valor")
        self.setModal(True)
        self.setFixedSize(250, 120)

        layout = QVBoxLayout(self)

        self.input = QLineEdit(self)
        self.input.clear()
        self.input.setFixedHeight(40)
        self.input.setStyleSheet(
            "background-color: black; color: #00FF00; font-size: 16px; padding: 4px;"
        )
        self.input.setFont(QFont("Microsoft Sans Serif", 14))
        layout.addWidget(self.input)

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)

        layout.addWidget(btn_ok)
        layout.addWidget(btn_cancel)

    def get_value(self):
        return self.input.text()


class LampWidget(QWidget):
    """Lâmpada de estado para variáveis digitais."""
    def __init__(self, diameter=26):
        super().__init__()
        self.state = None  # None=indef, False=OFF, True=ON
        self.setFixedSize(diameter + 8, diameter + 8)
        self._diameter = diameter

    def set_state(self, s):
        self.state = s
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        d = self._diameter
        x = (self.width() - d) // 2
        y = (self.height() - d) // 2

        # cor por estado
        if self.state is True:
            color = QColor("#00C853")  # verde ON
        elif self.state is False:
            color = QColor("#D50000")  # vermelho OFF
        else:
            color = QColor("#9E9E9E")  # cinza indefinido

        painter.setBrush(color)
        painter.setPen(QPen(QColor("#222"), 2))
        painter.drawEllipse(x, y, d, d)


class LevelIndicator(QWidget):
    """Indicador vertical com barra PV, SP e MV (analógico)."""
    def __init__(self, pv=30, sp=60, mv=40, mlo=None, mhi=None):
        super().__init__()
        self.pv = pv
        self.sp = sp
        self.mv = mv
        self.mlo = mlo
        self.mhi = mhi
        self.setMinimumSize(80, 150)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        margin = 20

        painter.fillRect(self.rect(), QColor("black"))

        # Barra PV central
        bar_width = 20
        bar_x = int(width / 2 - bar_width / 2)
        bar_y = margin
        bar_height = height - 2 * margin
        painter.setPen(QPen(QColor("white"), 1))
        painter.setBrush(QColor(0, 174, 239, 80))
        painter.drawRect(bar_x, bar_y, bar_width, bar_height)

        def percent_to_y(percent):
            return margin + ((100 - percent) / 100.0) * (height - 2 * margin)

        # SP seta amarela à esquerda
        sp_y = percent_to_y(self.sp)
        sp_triangle = QPolygonF([
            QPointF(bar_x - 8, sp_y - 5),
            QPointF(bar_x, sp_y),
            QPointF(bar_x - 8, sp_y + 5)
        ])
        painter.setBrush(QColor("yellow"))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(sp_triangle)

        # MV seta vermelha à direita
        mv_y = percent_to_y(self.mv)
        mv_triangle = QPolygonF([
            QPointF(bar_x + bar_width + 8, mv_y - 5),
            QPointF(bar_x + bar_width, mv_y),
            QPointF(bar_x + bar_width + 8, mv_y + 5)
        ])
        painter.setBrush(QColor("red"))
        painter.drawPolygon(mv_triangle)

        # Barra de escala à direita
        line_x = int(width * 0.85)
        pen_scale = QPen(QColor("#00AEEF"), 2)
        painter.setPen(pen_scale)
        painter.drawLine(line_x, margin, line_x, height - margin)

        # Batentes
        painter.setPen(QPen(QColor("#003366"), 2))
        if self.mlo is not None:
            mlo_y = percent_to_y(self.mlo)
            painter.drawLine(int(line_x - 10), int(mlo_y), int(line_x + 10), int(mlo_y))
        if self.mhi is not None:
            mhi_y = percent_to_y(self.mhi)
            painter.drawLine(int(line_x - 10), int(mhi_y), int(line_x + 10), int(mhi_y))

        # Texto 0 e 100
        painter.setPen(QColor("#00AEEF"))
        font = QFont("Arial", 8)
        painter.setFont(font)
        painter.drawText(line_x + 5, height - margin + 10, "0")
        painter.drawText(line_x + 5, margin - 2, "100")


# ------------------------------
# Faceplate base
# ------------------------------

class BaseFaceplate(QWidget):
    """Base comum para faceplates, com cabeçalho e modo."""
    def __init__(self, tag_name: str):
        super().__init__()
        self.tag_name = tag_name
        self.vg = VariaveisGlobais()
        self.mode = self.vg.get(f"{self.tag_name}.modo", "MAN")
        self.setWindowTitle(f"Faceplate - {self.tag_name}")
        self.setStyleSheet("background-color: #FFFDEB;")

    def create_header(self, main_layout):
        header = QLabel(self.tag_name)
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Arial", 10, QFont.Bold))
        header.setStyleSheet("background-color: #00AEEF; color: black; padding: 4px;")
        main_layout.addWidget(header)

    def create_value_frame(self, name, value, clickable=False):
        frame = QFrame()
        frame.setStyleSheet("background-color: black; border: 1px solid #333;")
        frame.setFixedHeight(50)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 5, 10, 5)

        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("color: #00FF00;")
        lbl_name.setFont(QFont("Arial", 9))

        lbl_value = QLabel(value)
        lbl_value.setStyleSheet("color: #00FF00;")
        lbl_value.setFont(QFont("Arial", 9))

        layout.addWidget(lbl_name)
        layout.addWidget(lbl_value)

        if name == "PV":
            self.pv_label = lbl_value
            self.mode_label = QLabel(self.mode)
            self.mode_label.setStyleSheet("color: #00FF00;")
            self.mode_label.setFont(QFont("Arial", 9))
            self.mode_label.setAlignment(Qt.AlignCenter)
            self.mode_label.setToolTip("Clique para alterar o modo")
            self.mode_label.mousePressEvent = self._change_mode_menu
            layout.addWidget(self.mode_label)
        elif name == "SP":
            self.sp_label = lbl_value
        elif name == "MV":
            self.mv_label = lbl_value

        if clickable:
            lbl_value.mousePressEvent = lambda e, n=name: self.value_clicked(n)

        layout.addStretch()
        return frame

    # sobrescritos nas subclasses
    def value_clicked(self, name):  # noqa: ARG002
        pass

    # menu e setter de modo (com regra de CAS)
    def _change_mode_menu(self, event):
        menu = QMenu(self)
        for mode in ["MAN", "AUT", "CAS", "PRD"]:
            action = QAction(mode, self)
            action.triggered.connect(lambda checked, m=mode: self.set_mode(m))
            menu.addAction(action)
        menu.exec_(event.globalPos())

    def set_mode(self, mode):
        self.mode = mode
        self.mode_label.setText(mode)
        self.vg.set(f"{self.tag_name}.modo", mode)


# ------------------------------
# Faceplate ANALÓGICO
# ------------------------------

class AnalogFaceplate(BaseFaceplate):
    def __init__(self, tag_name="P1001"):
        super().__init__(tag_name)
        self.resize(200, 700)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        self.create_header(main_layout)

        # PV, SP, MV
        self.pv_frame = self.create_value_frame("PV", "0.00")
        self.sp_frame = self.create_value_frame("SP", "0.00", clickable=True)
        self.mv_frame = self.create_value_frame("MV", "0.00", clickable=True)
        main_layout.addWidget(self.pv_frame)
        main_layout.addWidget(self.sp_frame)
        main_layout.addWidget(self.mv_frame)

        # Indicador vertical
        bar_layout = QHBoxLayout()
        bar_layout.addStretch()
        self.level_indicator = LevelIndicator()
        bar_layout.addWidget(self.level_indicator)
        bar_layout.addStretch()
        main_layout.addLayout(bar_layout)

        self.setLayout(main_layout)

        # Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_values)
        self.timer.start(500)
        self.update_values()

    def value_clicked(self, name):
        if name == "SP" and self.mode == "AUT":
            dialog = ValueInputDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                try:
                    val = float(dialog.get_value())
                except ValueError:
                    return
                self.vg.set(f"{self.tag_name}.sp", val)
        elif name == "MV" and self.mode == "MAN":
            dialog = ValueInputDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                try:
                    val = float(dialog.get_value())
                except ValueError:
                    return
                self.vg.set(f"{self.tag_name}.mv", val)

    def update_values(self):
        pv = float(self.vg.get(f"{self.tag_name}.pv", 0) or 0)
        sp = float(self.vg.get(f"{self.tag_name}.sp", 0) or 0)
        mv = float(self.vg.get(f"{self.tag_name}.mv", 0) or 0)

        self.pv_label.setText(f"{pv:.2f}")
        self.sp_label.setText(f"{sp:.2f}")
        self.mv_label.setText(f"{mv:.2f}")

        self.level_indicator.pv = pv
        self.level_indicator.sp = sp
        self.level_indicator.mv = mv
        self.level_indicator.update()


# ------------------------------
# Faceplate DIGITAL (novo)
# ------------------------------

# =========================
# Faceplate DIGITAL (mínimo)
# =========================
class DigitalFaceplate(QWidget):
    """ON/OFF com lâmpada e botões; respeita MAN/AUT."""
    def __init__(self, tag_name="DI001"):
        super().__init__()
        self.tag_name = tag_name
        self.vg = VariaveisGlobais()
        self.mode = self.vg.get(f"{self.tag_name}.modo", "MAN")
        self.setWindowTitle(f"Faceplate (DIG) - {self.tag_name}")
        self.resize(220, 300)
        self.setStyleSheet("background-color:#FFFDEB;")

        lay = QVBoxLayout(self); lay.setContentsMargins(6,6,6,6); lay.setSpacing(6)

        head = QLabel(self.tag_name); head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet("background:#00AEEF; color:black; padding:4px;")
        head.setFont(QFont("Arial", 10, QFont.Bold))
        lay.addWidget(head)

        # PV + Modo
        row_pv = QHBoxLayout()
        self.lbl_pv = QLabel("PV: ?"); self.lbl_pv.setStyleSheet("color:#0F0; background:black; padding:6px;")
        row_pv.addWidget(self.lbl_pv, 1)
        self.lbl_mode = QLabel(self.mode); self.lbl_mode.setStyleSheet("color:#0F0; background:black; padding:6px;")
        self.lbl_mode.setAlignment(Qt.AlignCenter)
        self.lbl_mode.mousePressEvent = self._menu_modo
        row_pv.addWidget(self.lbl_mode)
        lay.addLayout(row_pv)

        # SP (AUT)
        row_sp = QHBoxLayout()
        self.lbl_sp = QLabel("SP: ?"); self.lbl_sp.setStyleSheet("color:#0F0; background:black; padding:6px;")
        row_sp.addWidget(self.lbl_sp, 1)
        self.bt_sp_on = QPushButton("SP ON"); self.bt_sp_off = QPushButton("SP OFF")
        self.bt_sp_on.clicked.connect(lambda: self._write("sp", True))
        self.bt_sp_off.clicked.connect(lambda: self._write("sp", False))
        row_sp.addWidget(self.bt_sp_on); row_sp.addWidget(self.bt_sp_off)
        lay.addLayout(row_sp)

        # MV (MAN)
        row_mv = QHBoxLayout()
        self.lbl_mv = QLabel("MV: ?"); self.lbl_mv.setStyleSheet("color:#0F0; background:black; padding:6px;")
        row_mv.addWidget(self.lbl_mv, 1)
        self.bt_mv_on = QPushButton("MV ON"); self.bt_mv_off = QPushButton("MV OFF")
        self.bt_mv_on.clicked.connect(lambda: self._write("mv", True))
        self.bt_mv_off.clicked.connect(lambda: self._write("mv", False))
        row_mv.addWidget(self.bt_mv_on); row_mv.addWidget(self.bt_mv_off)
        lay.addLayout(row_mv)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(400)
        self._tick()

    def _menu_modo(self, ev):
        from PyQt5.QtWidgets import QMenu, QAction, QMessageBox
        menu = QMenu(self)
        for m in ["MAN","AUT","CAS","PRD"]:
            ac = QAction(m, self); ac.triggered.connect(lambda chk, mm=m: self._set_mode(mm))
            menu.addAction(ac)
        menu.exec_(ev.globalPos())

    def _set_mode(self, mode):
        if mode == "CAS":
            ctrl = self.vg.get(f"{self.tag_name}.controle", {})
            if not ctrl.get("fonte_cascata"):
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Modo indisponível",
                                    f"Sem 'fonte_cascata' em {self.tag_name}.")
                return
        self.mode = mode
        self.lbl_mode.setText(mode)
        self.vg.set(f"{self.tag_name}.modo", mode)
        self._tick()

    def _write(self, field, val):
        if field == "sp" and self.mode != "AUT": return
        if field == "mv" and self.mode != "MAN": return
        self.vg.set(f"{self.tag_name}.{field}", 1 if val else 0)

    def _b(self, key, default=0):
        v = self.vg.get(key, default)
        if isinstance(v, str) and v.isdigit(): v = int(v)
        return bool(v)

    def _tick(self):
        pv = self._b(f"{self.tag_name}.pv", 0)
        sp = self._b(f"{self.tag_name}.sp", 0)
        mv = self._b(f"{self.tag_name}.mv", 0)
        self.lbl_pv.setText("PV: ON" if pv else "PV: OFF")
        self.lbl_sp.setText("SP: ON" if sp else "SP: OFF")
        self.lbl_mv.setText("MV: ON" if mv else "MV: OFF")
        man = (self.mode == "MAN"); aut = (self.mode == "AUT")
        self.bt_mv_on.setEnabled(man); self.bt_mv_off.setEnabled(man)
        self.bt_sp_on.setEnabled(aut); self.bt_sp_off.setEnabled(aut)


# =========================
# Faceplate DIGITAL (status PV0..PV5)
# =========================
from PyQt5.QtWidgets import QTabWidget, QPlainTextEdit  # (garante imports básicos já existentes)

class DigitalStatusFaceplate(QWidget):
    """
    Layout:
      ┌────────────────────────┐  cabeçalho azul com TAG
      │        <TAG>           │
      └────────────────────────┘
      ┌────────────────────────┐  painel preto
      │ [ PV0 ]                │  até 6 “botões” (QPushButton) creme
      │ [ PV1 ]                │  cada um mostra rótulo de acordo com valor 0/1
      │ [ PV2 ]                │  invisível se não for usado
      │ [ PV3 ]                │
      │ [ PV4 ]                │
      │ [ PV5 ]                │
      └────────────────────────┘
    Config via singleton:
      vg[f"{tag}.tipo"] = "DIG"
      vg[f"{tag}.digi.map"] =
         {
           "PV0": {"text0": "DESLIGADO", "text1": "LIGADO", "visible": True},
           "PV1": {"text0": "",          "text1": "ALARME", "visible": False},
           ...
         }
    Valores lidos/escritos em:
      vg[f"{tag}.PV{i}"] ∈ {0,1}
    """
    def __init__(self, tag_name="DI001"):
        super().__init__()
        self._flash_active = set()  # índices de PV piscando por 1s
        self.tag_name = tag_name
        self.vg = VariaveisGlobais()

        self.setWindowTitle(f"Faceplate (DIG) - {self.tag_name}")
        self.resize(230, 520)
        self.setStyleSheet("background:#FFFDEB;")

        root = QVBoxLayout(self); root.setContentsMargins(6, 6, 6, 6); root.setSpacing(6)

        # Cabeçalho azul
        head = QLabel(self.tag_name)
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet("background:#00AEEF; color:black; padding:6px; font-weight:600;")
        head.setFont(QFont("Arial", 10))
        root.addWidget(head)
       


        # Painel preto
        panel = QFrame(); panel.setStyleSheet("background:black; border:1px solid #111;")
        v = QVBoxLayout(panel); v.setContentsMargins(20, 18, 20, 18); v.setSpacing(18)
        root.addWidget(panel, 1)

        # Preparar 6 “cards” creme
        self.rows = []
        for i in range(15):
            btn = QPushButton(f"PV{i}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(56)
            btn.setStyleSheet(
                "QPushButton{background:#FFF8E1; color:#666; border-radius:6px; font-size:14px;}"
                "QPushButton:pressed{ padding-top:7px; padding-left:7px; }"
            )
            btn.clicked.connect(lambda _=False, idx=i: self._toggle(idx))
            v.addWidget(btn)
            self.rows.append(btn)

        # Timer de atualização
        self._t = QTimer(self); self._t.timeout.connect(self._tick); self._t.start(300)
        self._tick()

    # ----- helpers -----
    def _flash(self, idx: int, ms: int = 1000):
        self._flash_active.add(idx)
        QTimer.singleShot(ms, lambda: (self._flash_active.discard(idx), self._tick()))

    def _get_map(self):
        m = self.vg.get(f"{self.tag_name}.digi.map", {}) or {}
        for i in range(6):
            key = f"PV{i}"
            if key not in m:
                m[key] = {"text0": f"PV{i}", "text1": f"PV{i}", "visible": False}
            m[key].setdefault("pulse", True if i in (0,1) else False)
            m[key].setdefault("confirm", False)
        return m

    def _bget(self, key, default=0):
        v = self.vg.get(key, default)
        if isinstance(v, str) and v.isdigit(): v = int(v)
        return 1 if bool(v) else 0

    def _pulse(self, key, ms=800):
        self.vg.set(key, 1)
        QTimer.singleShot(ms, lambda: self.vg.set(key, 0))
        
    def _confirm(self, msg: str) -> bool:
        ans = QMessageBox.question(self, "Confirmação", msg,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return ans == QMessageBox.Yes

    def _toggle(self, i):
        tag = self.tag_name
        m = self._get_map()
        cfg = m.get(f"PV{i}", {}) or {}
        pulse_mode = bool(cfg.get("pulse", True if i in (0, 1) else False))
        need_confirm = bool(cfg.get("confirm", False))

        # texto para confirmação
        text0 = cfg.get("text0", f"PV{i}")
        text1 = cfg.get("text1", f"PV{i}")
        cur = self._bget(f"{tag}.PV{i}", 0)

        # Confirmação
        if need_confirm:
            if pulse_mode:
                if not self._confirm(f'Deseja acionar o Botão "{text0}"?'):
                    return
            else:
                txt_dest = text0 if cur else text1
                if not self._confirm(f'Deseja mudar para ("{txt_dest}")?'):
                    return

        if pulse_mode:
            # Pulso direto no próprio PV
            self._pulse(f"{tag}.PV{i}", ms=800)
            self._flash(i, 300)
        else:
            # Alternância direta
            novo = 0 if cur else 1
            self.vg.set(f"{tag}.PV{i}", novo)
            self._flash(i, 300)






    def _tick(self):
        m = self._get_map()
        for i, btn in enumerate(self.rows):
            cfg = m.get(f"PV{i}", {"text0": f"PV{i}", "text1": f"PV{i}", "visible": False})
            visible = bool(cfg.get("visible", False))
            btn.setVisible(visible)
            if not visible:
                btn.hide()
                continue
            btn.show()

            val = self._bget(f"{self.tag_name}.PV{i}", 0)
            text0 = cfg.get("text0", f"PV{i}")
            text1 = cfg.get("text1", text0 or f"PV{i}")
            btn.setText(text1 if val else text0)
            # Cores padrão (ou as do seu map color0/color1, se já usa)
            bg0 = (cfg.get("color0") or "#FFF8E1")
            bg1 = (cfg.get("color1") or "#E8FFE8")
            fg0 = "#666"; br0 = "1px solid #DDD"
            fg1 = "#0A0"; br1 = "2px solid #0A0"

            # Estilos normais por valor
            style_on  = f"QPushButton{{background:{bg1}; color:{fg1}; border:{br1}; border-radius:6px; font-weight:600; padding:6px;}}"
            style_off = f"QPushButton{{background:{bg0}; color:{fg0}; border:{br0}; border-radius:6px; padding:6px;}}"
            pressed   = "QPushButton:pressed{opacity:0.95;}"

            # --- FLASH de 1s tem prioridade visual ---
            if i in getattr(self, "_flash_active", set()):
                # cores de flash (pode personalizar)
                flash_on  = "#C8E6C9"   # verde claro (Ligar)
                flash_off = "#FFCDD2"   # vermelho claro (Desligar)
                flash_bg  = flash_on if i == 0 else flash_off
                btn.setStyleSheet(f"QPushButton{{background:{flash_bg}; color:#000; border:2px solid #666; border-radius:6px; padding:6px;}}{pressed}")
            else:
                btn.setStyleSheet((style_on if val else style_off) + pressed)

           



# =========================
# Factory: abre analógico ou digital
# =========================
def open_faceplate(tag_name: str) -> QWidget:
    vg = VariaveisGlobais()
    tipo = str(vg.get(f"{tag_name}.tipo", "ANA") or "ANA").upper()
    if tipo.startswith("D"):
        # assegura estrutura padrão
        if vg.get(f"{tag_name}.digi.map", None) is None:
            vg.set(
                f"{tag_name}.digi.map",
                {
                    "PV0": {"text0": "DESLIGADO", "text1": "LIGADO", "visible": True},
                    "PV1": {"text0": "",          "text1": "ALARME", "visible": False},
                    "PV2": {"text0": "MANUAL",    "text1": "AUTOMÁTICO", "visible": False},
                    "PV3": {"text0": "CAMPO",     "text1": "CCI", "visible": False},
                    "PV4": {"text0": "PV4",       "text1": "PV4", "visible": False},
                    "PV5": {"text0": "PV5",       "text1": "PV5", "visible": False},
                }
            )
        return DigitalStatusFaceplate(tag_name)
    # analógico padrão já existente
    return AnalogFaceplate(tag_name)

# ------------------------------
# Execução direta p/ teste rápido
# ------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Exemplo: defina tipo e valores iniciais
    vg = VariaveisGlobais()
    # Comentário: troque para "DIG" para testar o digital
    vg.set("X1001.tipo", "DIG")
    vg.set("X1001.pv", 1)
    vg.set("X1001.sp", 0)
    vg.set("X1001.mv", 0)
    vg.set("X1001.modo", "MAN")

    vg.set("P1001.tipo", "ANA")
    vg.set("P1001.pv", 35.0)
    vg.set("P1001.sp", 60.0)
    vg.set("P1001.mv", 40.0)
    vg.set("P1001.modo", "AUT")

    # Abra um para ver
    w = open_faceplate("PI001")  # ou "P1001"
    w.show()

    sys.exit(app.exec_())

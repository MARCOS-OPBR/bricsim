# trends.py
# Janela de tendências (trends) com múltiplas escalas por "TAG|cor|escala"
# Requisitos: PyQt5, pyqtgraph. Lê valores do singleton.VariaveisGlobais

from collections import deque

import pyqtgraph as pg
from PyQt5 import QtCore, QtGui, QtWidgets
from singleton import VariaveisGlobais

# -----------------------
# Helpers de cor e TAG
# -----------------------


def parse_color(s: str) -> QtGui.QColor:
    if not s:
        return pg.mkColor("#00AEEF")
    try:
        return pg.mkColor(s.strip())
    except Exception:
        return pg.mkColor("#00AEEF")


def normalize_tag(tag: str) -> str:
    t = (tag or "").strip()
    if not t:
        return ""
    return t if ("." in t) else f"{t}.pv"


# -----------------------
# TrendWindow
# -----------------------
class TrendWindow(QtWidgets.QDialog):
    """
    Janela de tendências com múltiplas escalas.
    Adição por linha no formato: TAG|cor|escala
      - TAG: nome da variável (usa TAG.pv se não tiver sufixo)
      - cor: #RRGGBB, nomes ("red"), ou vazio para automático
      - escala: nome do eixo (ex.: "°C", "m", "bar", "%") –
                pens com o MESMO texto compartilham o mesmo eixo.
                Se vazio, usa a escala primária (esquerda).
    """

    def __init__(
        self,
        parent=None,
        titulo: str = "Tendências",
        max_points: int = 600,
        dt_ms: int = 500,
    ):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(1000, 520)
        self._vg = VariaveisGlobais()
        self._dt_ms = int(dt_ms)
        self._max_points = int(max_points)

        # Plot principal
        self.plot = pg.PlotWidget()
        self.plot.setBackground("k")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.getAxis("left").setPen(pg.mkPen("#8ecae6"))
        self.plot.getAxis("bottom").setPen(pg.mkPen("#8ecae6"))
        self.plot.getAxis("left").setTextPen(pg.mkPen("#8ecae6"))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen("#8ecae6"))
        self.plot.setLabel("bottom", "tempo", units="tics")

        # Layout superior: input e botões
        self.in_line = QtWidgets.QLineEdit()
        self.in_line.setPlaceholderText(
            "Ex.: TI001|#ffcc00|°C  ou  LC001|red|m  (deixe cor/escala vazios se quiser)"
        )
        self.btn_add = QtWidgets.QPushButton("Adicionar pena")
        self.btn_clear = QtWidgets.QPushButton("Limpar tudo")

        top_row = QtWidgets.QHBoxLayout()
        top_row.addWidget(self.in_line)
        top_row.addWidget(self.btn_add)
        top_row.addWidget(self.btn_clear)

        # Lista de penas
        self.list_pens = QtWidgets.QListWidget()
        self.list_pens.setSelectionMode(self.list_pens.ExtendedSelection)
        self.btn_remove = QtWidgets.QPushButton("Remover selecionadas")

        right_col = QtWidgets.QVBoxLayout()
        right_col.addWidget(self.list_pens)
        right_col.addWidget(self.btn_remove)

        central = QtWidgets.QHBoxLayout()
        central.addWidget(self.plot, 3)
        side = QtWidgets.QWidget()
        side.setLayout(right_col)
        side.setFixedWidth(280)
        central.addWidget(side, 0)

        # Rodapé: opções
        self.chk_autoscale = QtWidgets.QCheckBox("Autoescala ao vivo")
        self.chk_autoscale.setChecked(True)
        self.spin_history = QtWidgets.QSpinBox()
        self.spin_history.setRange(60, 20000)
        self.spin_history.setValue(self._max_points)
        self.spin_history.setPrefix("História: ")
        self.spin_history.setSuffix(" pts")

        foot = QtWidgets.QHBoxLayout()
        foot.addWidget(self.chk_autoscale)
        foot.addStretch(1)
        foot.addWidget(self.spin_history)

        # Layout principal
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addLayout(central)
        layout.addLayout(foot)

        # Eixos adicionais (escala -> (AxisItem, ViewBox))
        self._axes = {}  # escala:str -> (axisItem, viewBox)
        self._axis_right_offset = 0

        # Dados: lista de dicts {tag, axis, curve, color, buffer}
        self._pens = []
        self._t = 0

        # Timer
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(self._dt_ms)

        # Conexões
        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.spin_history.valueChanged.connect(self._on_history_changed)

        # Escala primária (esquerda) fica implícita no PlotWidget
        self.plot.setLabel("left", "escala primária")

    # -----------------------
    # Eixos múltiplos
    # -----------------------
    def _ensure_axis(self, escala: str):
        """Garante um eixo para a escala; retorna viewbox e axisItem.
        escala == '' ou None usa o eixo primário (esquerda)."""
        esc = (escala or "").strip()
        if esc == "":
            return self.plot.getViewBox(), self.plot.getAxis("left")

        if esc in self._axes:
            return self._axes[esc]

        # cria novo eixo à direita com offset
        axis = pg.AxisItem("right")
        axis.setPen(pg.mkPen("#8ecae6"))
        axis.setTextPen(pg.mkPen("#8ecae6"))
        axis.setLabel(esc)
        self._axis_right_offset += 50
        axis.setZValue(100)
        # pega o layout do PlotItem, compatível com versões que expõem como método ou atributo
        plot_item = self.plot.getPlotItem()
        layout_obj = (
            plot_item.layout
            if not callable(getattr(plot_item, "layout", None))
            else plot_item.layout()
        )
        # coloca o eixo na coluna direita (3). A coluna 2 costuma ser a do right axis padrão.
        layout_obj.addItem(axis, 2, 3)

        axis.setFixedWidth(60)
        axis.setStyle(tickLength=6)

        # novo ViewBox para essa escala, linkado no X
        vb = pg.ViewBox()
        vb.setBackgroundColor(None)
        self.plot.scene().addItem(vb)
        axis.linkToView(vb)
        vb.setXLink(self.plot)

        # posiciona o vb por cima do plot
        vb.setGeometry(self.plot.getViewBox().sceneBoundingRect())
        vb.linkedViewChanged(self.plot.getViewBox(), vb.XAxis)

        # quando o plot principal muda de tamanho, acompanha
        def _update_views():
            vb.setGeometry(self.plot.getViewBox().sceneBoundingRect())
            vb.linkedViewChanged(self.plot.getViewBox(), vb.XAxis)

        self.plot.getViewBox().sigResized.connect(_update_views)

        self._axes[esc] = (vb, axis)
        return vb, axis

    # -----------------------
    # Pens
    # -----------------------
    def _add_pen(self, tag: str, color: str = "", escala: str = ""):
        tagn = normalize_tag(tag)
        if not tagn:
            return
        vb, axis = self._ensure_axis(escala)
        curve = pg.PlotCurveItem(pen=pg.mkPen(parse_color(color), width=2))
        vb.addItem(curve)
        item = {
            "tag": tagn,
            "color": color,
            "axis": (escala or "").strip(),
            "curve": curve,
            "data": deque(maxlen=self._max_points),
        }
        self._pens.append(item)
        self.list_pens.addItem(
            f"{tagn} | {color or 'auto'} | {item['axis'] or 'primária'}"
        )
        self._pens.append(item)
        self.list_pens.addItem(
            f"{tagn} | {color or 'auto'} | {item['axis'] or 'primária'}"
        )

        # <<< novo: pré-carrega histórico
        self._bootstrap_history(item)

    def _on_add_clicked(self):
        text = self.in_line.text().strip()
        if not text:
            return
        # Permite várias linhas separadas por \n
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("|")]
            tag = parts[0] if len(parts) > 0 else ""
            cor = parts[1] if len(parts) > 1 else ""
            escala = parts[2] if len(parts) > 2 else ""
            self._add_pen(tag, cor, escala)
        self.in_line.clear()

    def clear_all(self):
        for p in self._pens:
            try:
                p["curve"].getViewBox().removeItem(p["curve"])
            except Exception:
                pass
        self._pens.clear()
        self.list_pens.clear()

    def remove_selected(self):
        rows = sorted({i.row() for i in self.list_pens.selectedIndexes()}, reverse=True)
        for r in rows:
            try:
                p = self._pens.pop(r)
                p["curve"].getViewBox().removeItem(p["curve"])
                self.list_pens.takeItem(r)
            except Exception:
                pass

    def _on_history_changed(self, v: int):
        self._max_points = int(v)
        for p in self._pens:
            old = p["data"]
            dq = deque(old, maxlen=self._max_points)
            p["data"] = dq

    # -----------------------
    # Atualização
    # -----------------------
    def _on_tick(self):
        self._t += 1
        for p in self._pens:
            y = self._vg.get(p["tag"], None)
            if y is None:
                # tenta PV se tag veio sem sufixo em algum lugar
                base = p["tag"].split(".pv")[0]
                y = self._vg.get(f"{base}.pv", 0.0)
            p["data"].append((self._t, float(y)))
            xs = [pt[0] for pt in p["data"]]
            ys = [pt[1] for pt in p["data"]]
            p["curve"].setData(xs, ys)

        if self.chk_autoscale.isChecked():
            # autoscale de cada eixo separadamente
            self.plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=True)
            # eixo primário
            self.plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
            for vb, axis in self._axes.values():
                vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)

    def _bootstrap_history(self, p):
        """Preenche p['data'] com histórico antes do primeiro tick."""
        N = self._max_points
        data = []

        # 1) tenta usar vg.hist(tag, N) se existir
        hist_vals = None
        try:
            hist_vals = self._vg.hist(p["tag"], N)
        except Exception:
            hist_vals = None

        if hist_vals:
            # assume lista do mais antigo -> mais novo
            vals = list(hist_vals)[-N:]
            start_x = self._t - len(vals)
            for i, v in enumerate(vals):
                data.append((start_x + i, float(v)))
        else:
            # 2) reconstrói com passado(tag, k)
            last = self._vg.get(p["tag"], 0.0)
            seq = []
            # pega até N amostras antigas (k = N..1)
            for k in range(min(N, 1000), 0, -1):
                try:
                    v = self._vg.passado(p["tag"], k, last)
                except Exception:
                    v = last
                seq.append(float(v))
            start_x = self._t - len(seq)
            for i, v in enumerate(seq):
                data.append((start_x + i, v))

        for pt in data:
            p["data"].append(pt)

        # desenha já com o histórico
        xs = [x for x, _ in p["data"]]
        ys = [y for _, y in p["data"]]
        p["curve"].setData(xs, ys)


# -----------------------
# Função utilitária
# -----------------------


def open_trends(parent=None, titulo="Tendências", presets=None):
    """Abre a janela de tendências.
    presets: lista de strings "TAG|cor|escala" para adicionar ao abrir.
    """
    dlg = TrendWindow(parent=parent, titulo=titulo)
    if presets:
        for line in presets:
            parts = [p.strip() for p in line.split("|")]
            tag = parts[0] if len(parts) > 0 else ""
            cor = parts[1] if len(parts) > 1 else ""
            escala = parts[2] if len(parts) > 2 else ""
            dlg._add_pen(tag, cor, escala)
    dlg.show()
    return dlg


# Execução direta para teste manual
if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = TrendWindow(titulo="Tendências - Demo")
    # exemplos iniciais
    w._add_pen("TI001", "#ffcc00", "°C")
    w._add_pen("LC001", "#00ff88", "m")
    w._add_pen("PC001", "#ffa0a0", "bar")
    w._add_pen("FC001", "#a0c4ff", "m³/s")
    w.show()
    sys.exit(app.exec_())

import sip
from canvas import SvgCanvas, SvgObjectItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsTextItem,
    QHBoxLayout,
    QMainWindow,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from ribbon import Ribbon
from sidebar import Sidebar
from toolbar_status import StatusBar

# from shortcuts import configurar_atalhos


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BRICSIM Designer- Novo Documento.tbr")
        self.setGeometry(100, 100, 1600, 900)
        self.setWindowIcon(QIcon("bricsim.ico"))

        # Elementos principais
        self.canvas = SvgCanvas(self)
        self.ribbon = Ribbon(self)
        self.canvas.set_area_util(1920, 1080, QColor("#c0c0c0"))
        self.sidebar = Sidebar(self)
        self.status_bar = QStatusBar()
        self.custom_status_widget = StatusBar()
        self.status_bar.addPermanentWidget(self.custom_status_widget, stretch=1)
        self.canvas.mode_changed.connect(self.ribbon.atualizar_estilo_visual)
        self.canvas.texto_selecionado.connect(
            self.ribbon.atualizar_estilo_texto_selecionado
        )
        self.documento_modificado = False

        self._init_ui()
        # configurar_atalhos(self, self.canvas)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Adiciona Ribbon na parte superior
        layout.addWidget(self.ribbon)

        # Layout central com Sidebar e Canvas
        mid_layout = QHBoxLayout()
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(0)
        mid_layout.addWidget(self.sidebar)
        mid_layout.addWidget(self.canvas, stretch=1)

        layout.addLayout(mid_layout)

        # Barra de status
        self.setStatusBar(self.status_bar)

    def atualizar_titulo(self, nome_arquivo=None):
        if nome_arquivo:
            self.setWindowTitle(f"BRICSim Designer - {nome_arquivo}")
        else:
            self.setWindowTitle("BRICSim Designer")

    def marcar_modificado(self, modificado: bool):
        self.documento_modificado = modificado
        nome = "Novo Documento.tbr"
        if modificado:
            self.setWindowTitle(f"* BRICSim Designer - {nome}")
        else:
            self.setWindowTitle(f"BRICSim Designer - {nome}")

    def set_modo(self, modo):
        self.canvas.set_mode(modo)
        self.ribbon.atualizar_estilo_visual(modo)

    def atualizar_estilo_ativo(self):
        itens = self.canvas.scene.selectedItems()
        if not itens:
            self.ribbon.atualizar_estilo_visual(None)
            return

        for item in itens:
            if hasattr(item, "handle_start"):  # linha
                self.ribbon.atualizar_estilo_visual("linha")
                return
            elif isinstance(item, QGraphicsTextItem):
                self.ribbon.atualizar_estilo_visual("texto")
                self.ribbon.atualizar_estilo_texto_selecionado(item)
                return
            elif isinstance(item, SvgObjectItem):  # reconhece SVGs
                self.ribbon.atualizar_estilo_visual("linha")
                return

        self.ribbon.atualizar_estilo_visual(None)

    def keyPressEvent(self, event):
        if sip.isdeleted(self):
            return
        if event.key() == Qt.Key_Escape:
            # Desfoca todos os objetos da cena
            self.canvas.scene.clearSelection()
            self.canvas.scene.clearFocus()
            self.canvas.clearFocus()
            self.canvas.set_mode("selecionar")
            return

        super().keyPressEvent(event)


if __name__ == "__main__":
    import sys

    from splash import SplashScreen

    app = QApplication(sys.argv)

    splash = SplashScreen("Logo.PNG")

    def abrir_janela_principal():
        window = MainWindow()
        window.show()

    splash.show_with_fade(abrir_janela_principal)
    sys.exit(app.exec_())

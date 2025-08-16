import json
import os
import sys

from canvas_simulator import (
    LogicaCentralDialog,
    SimuladorCanvas,
    TouchAreaItem,
    VariaveisCentralDialog,
)
from functions import (
    _montar_cena,
    carregar_modelo,
    carregar_simulacao,
    salvar_modelo,
    salvar_simulacao,
)
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

base_path = os.path.dirname(__file__)


class SimuladorMain(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BRICSSIM Simulador")
        self.resize(1200, 800)
        self.modo_modelo = True
        # --- estado da simulação ---
        self.simulacao_rodando = False
        self.simulacao_pausada = False

        # aplica visibilidade inicial dos botões

        # ===== Painel Superior =====
        self.top_bar = QWidget()
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 5, 10, 5)
        top_layout.setSpacing(20)

        # ===== Sidebar e Tabs =====
        self.sidebar = QListWidget()
        self.tab_widget = QTabWidget()
        self.sidebar.setMaximumWidth(150)
        self.sidebar.currentRowChanged.connect(self.trocar_aba_sidebar)
        self.sidebar.setDragDropMode(QListWidget.InternalMove)  # permitir reordenação
        self.sidebar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sidebar.customContextMenuRequested.connect(self.menu_sidebar)

        # ===== Botões ===
        self.btn_iniciar = QPushButton("SIMULAÇÃO")
        self.btn_iniciar.setIcon(QIcon(os.path.join(base_path, "icons", "play.svg")))
        self.btn_iniciar.setIconSize(QSize(32, 32))
        self.btn_pausar = QPushButton("PAUSAR")
        self.btn_pausar.setIcon(QIcon(os.path.join(base_path, "icons", "pause.svg")))
        self.btn_pausar.setIconSize(QSize(32, 32))
        self.btn_parar = QPushButton("PARAR")
        self.btn_parar.setIcon(QIcon(os.path.join(base_path, "icons", "stop.svg")))
        self.btn_parar.setIconSize(QSize(32, 32))
        self.btn_salvar = QPushButton("SALVAR SIM")
        self.btn_salvar.setIcon(QIcon(os.path.join(base_path, "icons", "save.svg")))
        self.btn_salvar.setIconSize(QSize(32, 32))
        self.btn_abrir_sim = QPushButton("ABRIR SIM")
        self.btn_abrir_sim.setIcon(
            QIcon(os.path.join(base_path, "icons", "open_s.svg"))
        )
        self.btn_abrir_sim.setIconSize(QSize(32, 32))
        self.btn_abrir_mod = QPushButton("ABRIR MOD")
        self.btn_abrir_mod.setIcon(
            QIcon(os.path.join(base_path, "icons", "open_m.svg"))
        )
        self.btn_abrir_mod.setIconSize(QSize(32, 32))
        self.btn_abrir_des = QPushButton("ABRIR DESIGNER")
        self.btn_abrir_des.setIcon(
            QIcon(os.path.join(base_path, "icons", "open_d.svg"))
        )
        self.btn_abrir_des.setIconSize(QSize(32, 32))
        self.btn_salvar_mod = QPushButton("SALVAR MOD")
        self.btn_salvar_mod.setIcon(
            QIcon(os.path.join(base_path, "icons", "save_m.svg"))
        )
        self.btn_salvar_mod.setIconSize(QSize(32, 32))
        self.btn_modo = QPushButton("MODELO")
        self.btn_modo.setIcon(QIcon(os.path.join(base_path, "icons", "gear.svg")))
        self.btn_modo.setIconSize(QSize(32, 32))
        self.btn_area_toque = QPushButton("Área de Toque")
        # >>> NOVO: botões pedidos
        self.btn_add_var_dig = QPushButton("Var. Digital")
        self.btn_central_vars = QPushButton("Central de Variáveis")
        self.btn_central_log = QPushButton("Central de Lógica")
        self.btn_tela_cheia = QPushButton("TELA CHEIA")
        self.btn_tela_cheia.setVisible(False)  # começa oculto

        top_layout.addWidget(self.btn_iniciar)
        top_layout.addWidget(self.btn_pausar)
        top_layout.addWidget(self.btn_parar)
        top_layout.addSpacing(50)
        top_layout.addWidget(self.btn_salvar)
        top_layout.addWidget(self.btn_abrir_sim)
        top_layout.addWidget(self.btn_abrir_mod)
        top_layout.addWidget(self.btn_abrir_des)
        top_layout.addWidget(self.btn_tela_cheia)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_area_toque)
        # >>> NOVO: posiciona logo ao lado do botão de touch_area
        top_layout.addWidget(self.btn_add_var_dig)
        top_layout.addWidget(self.btn_central_vars)
        top_layout.addWidget(self.btn_central_log)
        top_layout.addWidget(self.btn_salvar_mod)
        top_layout.addWidget(self.btn_modo)

        # ===== Rodapé =====
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.coord_label = QLabel("X: ---  Y: ---")
        self.modo_label = QLabel("Modo: VISUALIZAÇÃO")
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Digite um comando e pressione Enter")
        status_bar.addWidget(self.coord_label)
        status_bar.addWidget(self.modo_label)
        status_bar.addPermanentWidget(self.cmd_input, 1)

        # ===== Layout Principal =====
        main_split = QHBoxLayout()
        main_split.setContentsMargins(0, 0, 0, 0)
        main_split.setSpacing(0)
        main_split.addWidget(self.sidebar)
        main_split.addWidget(self.tab_widget)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.top_bar)
        central_layout.addLayout(main_split)

        self.setCentralWidget(central_widget)

        # ===== Conexões =====
        self.btn_iniciar.clicked.connect(self.iniciar_simulacao)
        self.btn_pausar.clicked.connect(self.pausar_simulacao)
        self.btn_parar.clicked.connect(self.parar_simulacao)
        self.btn_salvar.clicked.connect(lambda: salvar_simulacao(self))
        self.btn_abrir_sim.clicked.connect(lambda: carregar_simulacao(self))
        self.btn_abrir_mod.clicked.connect(lambda: carregar_modelo(self))
        self.btn_salvar_mod.clicked.connect(lambda: salvar_modelo(self))
        self.btn_abrir_des.clicked.connect(self.carregar_design)
        self.btn_tela_cheia.clicked.connect(self.ativar_tela_cheia)
        self.btn_modo.clicked.connect(self.alternar_modo)
        self.btn_area_toque.clicked.connect(lambda: self._criar_area_toque())
        self.btn_add_var_dig.clicked.connect(self._inserir_variavel_digital_modelo)
        self.btn_central_vars.clicked.connect(self._abrir_central_variaveis)
        self.btn_central_log.clicked.connect(self._abrir_central_logica)

        self.atualizar_botoes()

    def _criar_area_toque(self):
        canvas = self.tab_widget.currentWidget()
        if canvas and hasattr(canvas, "adicionar_area_toque"):
            canvas.adicionar_area_toque()
        else:
            print("⚠ Nenhuma tela aberta para adicionar área de toque")
            self.atualizar_botoes()

    # ===== Navegação =====
    def trocar_aba_sidebar(self, row):
        if row >= 0:
            self.tab_widget.setCurrentIndex(row)

    def trocar_item_sidebar(self, index):
        if index >= 0:
            self.sidebar.setCurrentRow(index)

    def menu_sidebar(self, pos):
        item = self.sidebar.itemAt(pos)
        if item:
            menu = QMenu(self)
            remover_acao = menu.addAction("Remover Tela")
            acao = menu.exec_(self.sidebar.mapToGlobal(pos))
            if acao == remover_acao:
                index = self.sidebar.row(item)
                self.sidebar.takeItem(index)
                self.tab_widget.removeTab(index)

    # ===== Carregar TBR como nova aba =====
    def carregar_design(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Carregar Design", "", "Tela BRICSSIM (*.tbr)"
        )
        if not caminho:
            return

        nome_tela = os.path.splitext(os.path.basename(caminho))[0]
        novo_canvas = SimuladorCanvas(self, main_window=self)

        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)

        _montar_cena(novo_canvas, dados, carregar_valores=False)

        self.tab_widget.addTab(novo_canvas, nome_tela)
        self.sidebar.addItem(nome_tela)
        self.sidebar.setCurrentRow(self.tab_widget.count() - 1)
        # garante flags corretas para o modo atual
        if hasattr(novo_canvas, "aplicar_flags_por_modo"):
            novo_canvas.aplicar_flags_por_modo()

    # ===== Modo e botões =====
    def alternar_modo(self):
        self.modo_modelo = not self.modo_modelo

        # atualiza rótulo/botão
        if self.modo_modelo:
            self.btn_modo.setText("MODO MODELO")
            self.btn_modo.setIcon(QIcon(os.path.join(base_path, "icons", "gear.svg")))
            self.modo_label.setText("Modo: MODELO")
            # exibe a tag nos textos
            for i in range(self.tab_widget.count()):
                canvas = self.tab_widget.widget(i)
                for var in getattr(canvas, "variaveis", []):
                    var.setPlainText(getattr(var, "tag", ""))
        else:
            self.btn_modo.setText("SIMULAÇÃO")
            self.btn_modo.setIcon(
                QIcon(os.path.join(base_path, "icons", "keyboard.svg"))
            )
            self.modo_label.setText("SIMULAÇÃO")

        # aplica flags em TODOS os canvases existentes
        for i in range(self.tab_widget.count()):
            canvas = self.tab_widget.widget(i)
            if hasattr(canvas, "aplicar_flags_por_modo"):
                canvas.aplicar_flags_por_modo()

        self.atualizar_botoes()

    def atualizar_botoes(self):
        # visibilidade por modo
        self.sidebar.setVisible(self.modo_modelo)
        self.btn_tela_cheia.setVisible(not self.modo_modelo)
        self.btn_salvar_mod.setVisible(self.modo_modelo)
        self.btn_salvar.setVisible(self.modo_modelo)
        self.btn_abrir_des.setVisible(self.modo_modelo)
        self.btn_abrir_mod.setVisible(self.modo_modelo)
        self.btn_abrir_sim.setVisible(self.modo_modelo)
        self.btn_area_toque.setVisible(self.modo_modelo)

        # grupo de execução (só no modo simulação)
        if self.modo_modelo:
            self.btn_iniciar.setVisible(False)
            self.btn_pausar.setVisible(False)
            self.btn_parar.setVisible(False)
            return

        # estamos em modo simulação
        if not self.simulacao_rodando and not self.simulacao_pausada:
            # parado
            self.btn_iniciar.setText("INICIAR")
            self.btn_iniciar.setVisible(True)
            self.btn_pausar.setVisible(False)
            self.btn_parar.setVisible(False)
        elif self.simulacao_rodando and not self.simulacao_pausada:
            # rodando
            self.btn_iniciar.setVisible(False)
            self.btn_pausar.setVisible(True)
            self.btn_parar.setVisible(True)
        else:
            # pausado
            self.btn_iniciar.setText("RETOMAR")
            self.btn_iniciar.setVisible(True)
            self.btn_pausar.setVisible(False)
            self.btn_parar.setVisible(True)

        self.btn_abrir_des.setVisible(self.modo_modelo)
        self.btn_abrir_mod.setVisible(self.modo_modelo)
        self.btn_abrir_sim.setVisible(self.modo_modelo)
        self.btn_area_toque.setVisible(self.modo_modelo)
        self.btn_central_log.setVisible(self.modo_modelo)
        self.btn_central_vars.setVisible(self.modo_modelo)

    def dropEvent(self, event):
        super(QListWidget, self.sidebar).dropEvent(event)
        self.sincronizar_ordem_abas()

    def sincronizar_ordem_abas(self):
        nova_ordem = [self.sidebar.item(i).text() for i in range(self.sidebar.count())]
        widgets = []
        for nome in nova_ordem:
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == nome:
                    widgets.append(self.tab_widget.widget(i))
                    break
        self.tab_widget.clear()
        for nome, widget in zip(nova_ordem, widgets):
            self.tab_widget.addTab(widget, nome)

    # ===== Simulação =====
    def iniciar_simulacao(self):
        print("Iniciar Simulação")

        from singleton import VariaveisGlobais

        vg = VariaveisGlobais()

        canvas = self.tab_widget.currentWidget()
        if not canvas:
            return

        # (opcional) garantir histórico para .pv/.sp/.mv das variáveis que estão na tela
        if hasattr(canvas, "variaveis"):
            for var in canvas.variaveis:
                for sufixo in (".pv", ".sp", ".mv"):
                    chave = f"{var.tag}{sufixo}"
                    if len(vg.hist(chave)) == 0:
                        vg.set(chave, 0)

        # liga a simulação
        canvas.simulacao_rodando = True

        # >>> RELIGA OS TIMERS SE ESTIVEREM PARADOS <<<
        if hasattr(canvas, "timer_controle") and not canvas.timer_controle.isActive():
            canvas.timer_controle.start(200)  # mesma cadência definida no canvas
        if hasattr(canvas, "timer_interface") and not canvas.timer_interface.isActive():
            canvas.timer_interface.start(1000)  # mesma cadência definida no canvas

    def pausar_simulacao(self):
        print("Pausar Simulação")
        canvas = self.tab_widget.currentWidget()
        if canvas:
            canvas.simulacao_rodando = False

    def parar_simulacao(self):
        print("Parar Simulação")
        canvas = self.tab_widget.currentWidget()
        if not canvas:
            return

        canvas.simulacao_rodando = False

        if hasattr(canvas, "timer_controle") and canvas.timer_controle.isActive():
            canvas.timer_controle.stop()
        if hasattr(canvas, "timer_interface") and canvas.timer_interface.isActive():
            canvas.timer_interface.stop()

        from singleton import VariaveisGlobais

        VariaveisGlobais().diagnostico()

    def ativar_tela_cheia(self):
        self.showFullScreen()
        self.top_bar.setVisible(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.showNormal()
            self.top_bar.setVisible(True)
        super().keyPressEvent(event)

    # >>> NOVO: insere rapidamente uma variável digital padrão
    def _inserir_variavel_digital_modelo(self):
        canvas = self.tab_widget.currentWidget()
        if not canvas:
            print("⚠ Nenhuma tela aberta")
            return
        canvas.inserir_variavel_digital_modelo()

    # >>> NOVO: abre a Central de Variáveis (abas Analógicas/Digitais)
    def _abrir_central_variaveis(self):
        canvas = self.tab_widget.currentWidget()
        if not canvas:
            return
        self._dlg_vars = VariaveisCentralDialog(canvas, parent=self)
        self._dlg_vars.show()

    # >>> NOVO: abre a Central de Lógica (lista → Grafcet)
    def _abrir_central_logica(self):
        self._dlg_log = LogicaCentralDialog(parent=self)
        self._dlg_log.show()

    def atualizar_botoes(self):
        # mantém sua lógica e adiciona visibilidade no modo
        self.sidebar.setVisible(self.modo_modelo)
        # ...
        self.btn_area_toque.setVisible(self.modo_modelo)
        # >>> NOVO:
        self.btn_add_var_dig.setVisible(self.modo_modelo)
        self.btn_central_vars.setVisible(self.modo_modelo)
        self.btn_central_log.setVisible(self.modo_modelo)
        # ...


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = SimuladorMain()
    w.show()
    sys.exit(app.exec_())

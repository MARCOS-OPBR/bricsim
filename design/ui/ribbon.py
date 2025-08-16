# ribbon.py
from canvas import EditableLine, EditablePolyline
from functions import (
    abrir_novo_documento,
    alterar_cor_contorno,
    alterar_cor_preenchimento,
    alterar_espessura_contorno,
    alterar_tipo_linha,
    alternar_handles,
    aplicar_formatacao_texto,
    ativar_desenho_caminho,
    ativar_desenho_linha,
    ativar_desenho_texto,
    ativar_modo_selecionar,
    carregar_projeto,
    escalar_item_selecionado,
    exportar_imagem,
    importar_imagem,
    imprimir_imagem,
    salvar_projeto,
)
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFontComboBox,
    QGraphicsTextItem,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedLayout,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from resources import icon_path


def create_tool_button(icon_filename, tooltip):
    btn = QToolButton()
    btn.setIcon(QIcon(icon_path(icon_filename)))
    btn.setIconSize(QSize(16, 16))
    btn.setToolTip(tooltip)
    btn.setAutoRaise(True)
    return btn


class Ribbon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # ✅ Inicializa grupos de estilo ANTES das abas
        self.grupo_estilo_linha = self._criar_estilo_linha()
        self.grupo_estilo_texto = self._criar_estilo_texto()

        # ✅ Agora pode criar as abas
        self.tabs.addTab(self._aba_arquivo(), "Arquivo")
        self.tabs.addTab(self._aba_editar(), "Editar")
        self.tabs.addTab(self._aba_desenhar(), "Desenhar")
        self.tabs.addTab(self._aba_inserir(), "Inserir")
        self.tabs.addTab(self._aba_exibir(), "Exibir")
        self.tabs.addTab(self._aba_revisar(), "Revisar")
        self.tabs.addTab(self._aba_preferencias(), "Preferências")
        self.tabs.addTab(self._aba_tools(), "Tools")

        layout.addWidget(self.tabs)

        # Começa com o grupo de texto escondido:
        self.grupo_estilo_texto.hide()

        self.setLayout(layout)

    # Cada aba abaixo só adiciona os grupos com botões (sem conexão funcional ainda)

    def _aba_arquivo(self):
        aba = QWidget()
        layout = QHBoxLayout()

        grupo = QGroupBox("Projeto")
        g_layout = QGridLayout()

        btn_novo = create_tool_button("new.svg", "Nova Tela")
        btn_novo.clicked.connect(lambda: abrir_novo_documento(self.main_window))

        btn_abrir = create_tool_button("open.svg", "Abrir Tela")
        btn_abrir.clicked.connect(lambda: carregar_projeto(self.main_window))

        btn_salvar = create_tool_button("save.svg", "Salvar Tela")
        btn_salvar.clicked.connect(lambda: salvar_projeto(self.main_window))

        btn_importar = create_tool_button("import.svg", "Importar")
        btn_exportar = create_tool_button("export.svg", "Exportar")
        btn_imprimir = create_tool_button("print.svg", "Imprimir")
        btn_importar.clicked.connect(lambda: importar_imagem(self.main_window))
        btn_exportar.clicked.connect(lambda: exportar_imagem(self.main_window))
        btn_imprimir.clicked.connect(lambda: imprimir_imagem(self.main_window))

        g_layout.addWidget(btn_novo, 0, 0)
        g_layout.addWidget(btn_abrir, 0, 1)
        g_layout.addWidget(btn_salvar, 0, 2)
        g_layout.addWidget(btn_importar, 0, 3)
        g_layout.addWidget(btn_exportar, 0, 4)
        g_layout.addWidget(btn_imprimir, 0, 5)
        grupo.setLayout(g_layout)

        layout.addWidget(grupo)
        aba.setLayout(layout)
        return aba

    def _aba_editar(self):
        aba = QWidget()
        layout = QHBoxLayout()

        # Grupo 1: Comandos
        comandos = QGroupBox("Comandos")
        g1 = QGridLayout()

        btn_undo = create_tool_button("undo.svg", "Desfazer (CTRL+Z)")
        btn_undo.clicked.connect(self.main_window.canvas._desfazer)

        btn_redo = create_tool_button("redo.svg", "Refazer (CTRL+Y)")
        btn_redo.clicked.connect(self.main_window.canvas._refazer)

        btn_copy = create_tool_button("copy.svg", "Copiar (CTRL+C)")
        btn_copy.clicked.connect(self.main_window.canvas._copiar_itens)

        btn_paste = create_tool_button("paste.svg", "Colar (CTRL+V)")
        btn_paste.clicked.connect(self.main_window.canvas._colar_itens)

        btn_cut = create_tool_button("cut.svg", "Cortar (CTRL+X)")
        btn_cut.clicked.connect(self.main_window.canvas._cortar_itens)

        btn_delete = create_tool_button("delete.svg", "Excluir (DEL)")
        btn_delete.clicked.connect(
            lambda: [
                main_window.canvas.scene.removeItem(i)
                for i in main_window.canvas.scene.selectedItems()
            ]
        )

        g1.addWidget(btn_undo, 0, 0)
        g1.addWidget(btn_redo, 0, 1)
        g1.addWidget(btn_copy, 1, 0)
        g1.addWidget(btn_paste, 1, 1)
        g1.addWidget(btn_cut, 2, 0)
        g1.addWidget(btn_delete, 2, 1)
        comandos.setLayout(g1)
        aba.setLayout(layout)

        # Grupo 2: Seleção
        selecao = QGroupBox("Seleção")
        g2 = QGridLayout()

        btn_select = create_tool_button("select.svg", "Selecionar(Espaço)")
        btn_select.clicked.connect(lambda: ativar_modo_selecionar(self.main_window))
        g2.addWidget(btn_select, 0, 0)

        btn_select_all = create_tool_button(
            "select_all.svg", "Selecionar Tudo (Ctrl+A)"
        )
        btn_select_all.clicked.connect(self.main_window.canvas._selecionar_tudo)

        btn_inverter = create_tool_button(
            "invert.svg", "Inverter Seleção (Ctrl+Shift+A)"
        )
        btn_inverter.clicked.connect(self.main_window.canvas._inverter_selecao)

        g2.addWidget(btn_select_all, 0, 1)
        g2.addWidget(btn_inverter, 0, 2)
        selecao.setLayout(g2)

        # Grupo 3: Alinhamento
        alinhamento = QGroupBox("Alinhamento")
        g3 = QGridLayout()
        btn_align_left = create_tool_button("align_left.svg", "Alinhar à Esquerda")
        btn_align_left.clicked.connect(
            lambda: self.main_window.canvas._alinhar_objetos("esquerda")
        )

        btn_align_center = create_tool_button("align_center.svg", "Centralizar")
        btn_align_center.clicked.connect(
            lambda: self.main_window.canvas._alinhar_objetos("centro")
        )

        btn_align_right = create_tool_button("align_right.svg", "Alinhar à Direita")
        btn_align_right.clicked.connect(
            lambda: self.main_window.canvas._alinhar_objetos("direita")
        )

        g3.addWidget(btn_align_left, 0, 0)
        g3.addWidget(btn_align_center, 0, 1)
        g3.addWidget(btn_align_right, 0, 2)

        btn_align_top = create_tool_button("align_top.svg", "Alinhar ao Topo")
        btn_align_top.clicked.connect(
            lambda: self.main_window.canvas._alinhar_objetos("topo")
        )

        btn_align_middle = create_tool_button("align_middle.svg", "Alinhar ao Meio")
        btn_align_middle.clicked.connect(
            lambda: self.main_window.canvas._alinhar_objetos("meio")
        )

        btn_align_bottom = create_tool_button("align_bottom.svg", "Alinhar à Base")
        btn_align_bottom.clicked.connect(
            lambda: self.main_window.canvas._alinhar_objetos("base")
        )

        g3.addWidget(btn_align_top, 1, 0)
        g3.addWidget(btn_align_middle, 1, 1)
        g3.addWidget(btn_align_bottom, 1, 2)

        alinhamento.setLayout(g3)

        # Grupo 4: Ordem
        ordem = QGroupBox("Ordem")
        g4 = QGridLayout()

        btn_trazer_frente = create_tool_button("bring_front.svg", "Trazer para Frente")
        btn_enviar_tras = create_tool_button("send_back.svg", "Enviar para Trás")
        btn_avancar = create_tool_button("forward.svg", "Avançar")
        btn_recuar = create_tool_button("backward.svg", "Recuar")

        btn_trazer_frente.clicked.connect(
            lambda: self.main_window.canvas.trazer_para_frente()
        )
        btn_enviar_tras.clicked.connect(
            lambda: self.main_window.canvas.enviar_para_tras()
        )
        btn_avancar.clicked.connect(lambda: self.main_window.canvas.avancar_z())
        btn_recuar.clicked.connect(lambda: self.main_window.canvas.recuar_z())

        g4.addWidget(btn_trazer_frente, 0, 0)
        g4.addWidget(btn_avancar, 0, 1)
        g4.addWidget(btn_recuar, 1, 0)
        g4.addWidget(btn_enviar_tras, 1, 1)
        ordem.setLayout(g4)

        # Grupo 5: Dimensão
        dimensao = QGroupBox("Dimensão")
        g5 = QGridLayout()
        btn_escalar = create_tool_button("scale.svg", "Escalar")
        btn_escalar.clicked.connect(lambda: escalar_item_selecionado(self.main_window))
        g5.addWidget(btn_escalar, 0, 0)

        btn_rot_horario = create_tool_button(
            "rotate_hour.svg", "Rotacionar Sentido Horário"
        )
        btn_rot_antihorario = create_tool_button(
            "rotate_anti.svg", "Rotacionar Sentido Anti-Horário"
        )
        btn_flip_h = create_tool_button("flip_horizontal.svg", "Espelhar Horizontal")
        btn_flip_v = create_tool_button("flip_vertical.svg", "Espelhar Vertical")

        btn_rot_horario.clicked.connect(
            lambda: self.main_window.canvas.rotacionar_selecionados(90)
        )
        btn_rot_antihorario.clicked.connect(
            lambda: self.main_window.canvas.rotacionar_selecionados(-90)
        )
        btn_flip_h.clicked.connect(
            lambda: self.main_window.canvas.espelhar_horizontal()
        )
        btn_flip_v.clicked.connect(lambda: self.main_window.canvas.espelhar_vertical())

        g5.addWidget(btn_rot_horario, 0, 1)
        g5.addWidget(btn_rot_antihorario, 0, 2)
        g5.addWidget(btn_flip_h, 1, 0)
        g5.addWidget(btn_flip_v, 1, 1)
        dimensao.setLayout(g5)

        # Adiciona todos os grupos ao layout da aba
        layout.addWidget(comandos)
        layout.addWidget(selecao)
        layout.addWidget(alinhamento)
        layout.addWidget(ordem)
        layout.addWidget(dimensao)
        aba.setLayout(layout)
        return aba

    def _aba_desenhar(self):
        aba = QWidget()
        layout = QHBoxLayout()

        grupo_formas = QGroupBox("Formas")
        g1 = QGridLayout()

        btn_linha = create_tool_button("line.svg", "Desenhar Linha")
        btn_linha.clicked.connect(lambda: ativar_desenho_linha(self.main_window))
        g1.addWidget(btn_linha, 0, 0)

        btn_texto = create_tool_button("A.svg", "Desenhar Linha")
        btn_texto.clicked.connect(lambda: ativar_desenho_texto(self.main_window))
        g1.addWidget(btn_texto, 2, 1)

        g1.addWidget(create_tool_button("table.svg", "Tabela"), 1, 1)

        # Após btn_linha:
        btn_conector = create_tool_button("connect.svg", "Desenhar Caminho")
        btn_conector.clicked.connect(lambda: ativar_desenho_caminho(self.main_window))
        g1.addWidget(btn_conector, 1, 0)

        grupo_formas.setLayout(g1)

        layout.addWidget(grupo_formas)
        aba.setLayout(layout)

        # Frame 2: Estilo de Desenho
        self.stack_estilo = QStackedLayout()
        self.stack_estilo.addWidget(self.grupo_estilo_linha)  # index 0
        self.stack_estilo.addWidget(self.grupo_estilo_texto)  # index 1

        # Adiciona tudo ao layout da aba
        layout.addWidget(grupo_formas)
        layout.addWidget(self.grupo_estilo_linha)
        layout.addLayout(self.stack_estilo)
        return aba

    def _aba_inserir(self):
        aba = QWidget()
        layout = QHBoxLayout()

        grupo_isa = QGroupBox("OBjetos e Variaveis")
        g = QVBoxLayout()
        btn_svg = create_tool_button("valve.svg", "Inserir SVG com TAG")
        btn_svg.setIconSize(QSize(48, 48))  # Tamanho do ícone
        btn_svg.setFixedSize(64, 64)  # Tamanho do botão (inclui margem)
        btn_svg.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn_svg.clicked.connect(lambda: self.main_window.canvas.importar_svg())
        g.addWidget(btn_svg)
        grupo_isa.setLayout(g)
        btn_variavel = create_tool_button("variable.svg", "Inserir Variável")
        btn_variavel.setIconSize(QSize(48, 48))
        btn_variavel.setFixedSize(64, 64)
        btn_variavel.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn_variavel.clicked.connect(
            lambda: self.main_window.canvas.ativar_modo_inserir_variavel()
        )
        g.addWidget(btn_variavel)

        layout.addWidget(grupo_isa)
        aba.setLayout(layout)
        return aba

    def _aba_exibir(self):
        aba = QWidget()
        layout = QHBoxLayout()

        # Grupo: Elementos Visuais
        grupo_visual = QGroupBox("Elementos Visuais")
        g = QVBoxLayout()
        layout_grid = QHBoxLayout()

        btn_grid = QToolButton()
        btn_grid.setText("Grade")
        btn_grid.setCheckable(True)
        btn_grid.setToolTip("Exibir Grade")
        btn_grid.clicked.connect(
            lambda checked: self.main_window.canvas.set_grid_visible(checked)
        )
        layout_grid.addWidget(btn_grid)

        label_spacing = QLabel("Tamanho:")
        layout_grid.addWidget(label_spacing)

        spin_grid = QSpinBox()
        spin_grid.setRange(10, 200)
        spin_grid.setValue(25)
        spin_grid.setToolTip("Espaçamento entre os pontos do grid")
        spin_grid.valueChanged.connect(
            lambda val: self.main_window.canvas.set_grid_spacing(val)
        )
        layout_grid.addWidget(spin_grid)

        btn_snap = QToolButton()
        btn_snap.setText("Atrair a Grade")
        btn_snap.setCheckable(True)
        btn_snap.setToolTip("Snap to Grid")
        btn_snap.clicked.connect(
            lambda checked: self.main_window.canvas.set_snap_to_grid(checked)
        )
        g.addWidget(btn_snap)

        g.addLayout(layout_grid)
        g.addWidget(create_tool_button("ruler.svg", "Régua"))

        btn_handles = QToolButton()
        btn_handles.setIcon(QIcon(icon_path("handles.svg")))
        btn_handles.setIconSize(QSize(24, 24))
        btn_handles.setToolTip("Exibir Handles")
        btn_handles.setCheckable(True)
        btn_handles.setChecked(True)
        btn_handles.clicked.connect(
            lambda checked: alternar_handles(self.main_window, checked)
        )
        g.addWidget(btn_handles)

        grupo_visual.setLayout(g)
        layout.addWidget(grupo_visual)

        # Grupo: Zoom
        grupo_zoom = QGroupBox("Zoom")
        z = QGridLayout()

        btn_mais = create_tool_button("zoom_in.svg", "Zoom +")
        btn_mais.clicked.connect(lambda: self.main_window.canvas.zoom_mais())
        z.addWidget(btn_mais, 0, 0)

        btn_menos = create_tool_button("zoom_out.svg", "Zoom -")
        btn_menos.clicked.connect(lambda: self.main_window.canvas.zoom_menos())
        z.addWidget(btn_menos, 0, 1)

        btn_ajustar = create_tool_button("fit.svg", "Ajustar à Tela")
        btn_ajustar.clicked.connect(lambda: self.main_window.canvas.ajustar_a_tela())
        z.addWidget(btn_ajustar, 0, 2)

        btn_janela = create_tool_button("zoom_rect.svg", "Zoom por Janela")
        btn_janela.clicked.connect(
            lambda: self.main_window.canvas.iniciar_zoom_por_janela()
        )
        z.addWidget(btn_janela, 0, 3)

        grupo_zoom.setLayout(z)
        layout.addWidget(grupo_zoom)

        aba.setLayout(layout)
        return aba

    def _aba_revisar(self):
        aba = QWidget()
        layout = QHBoxLayout()
        grupo_valida = QGroupBox("Validação")
        g = QVBoxLayout()
        g.addWidget(create_tool_button("check.svg", "Verificar objetos"))
        grupo_valida.setLayout(g)
        layout.addWidget(grupo_valida)
        aba.setLayout(layout)
        return aba

    def _aba_preferencias(self):
        aba = QWidget()
        layout = QHBoxLayout()
        grupo_tema = QGroupBox("Aparência")
        g = QVBoxLayout()
        g.addWidget(create_tool_button("theme.svg", "Tema Escuro/Claro"))
        g.addWidget(create_tool_button("settings.svg", "Configurações de Interface"))
        grupo_tema.setLayout(g)
        layout.addWidget(grupo_tema)
        aba.setLayout(layout)
        return aba

    def _aba_tools(self):
        aba = QWidget()
        layout = QHBoxLayout()
        grupo_tools = QGroupBox("Integração")
        g = QVBoxLayout()
        g.addWidget(create_tool_button("model.svg", "Abrir no Modelador"))
        g.addWidget(create_tool_button("simulate.svg", "Executar no Simulador"))
        grupo_tools.setLayout(g)
        layout.addWidget(grupo_tools)
        aba.setLayout(layout)
        return aba

    def abrir_seletor_cor_texto(self):
        cor = QColorDialog.getColor()
        if cor.isValid():
            aplicar_formatacao_texto(self.main_window, cor=cor)

    def atualizar_estilo_visual(self, modo):
        if modo == "texto":
            self.grupo_estilo_texto.show()
            self.grupo_estilo_linha.hide()
            self.stack_estilo.setCurrentIndex(1)
        elif modo == "linha" or "caminho":
            self.grupo_estilo_texto.hide()
            self.grupo_estilo_linha.show()
            self.stack_estilo.setCurrentIndex(0)
        else:
            self.grupo_estilo_texto.hide()
            self.grupo_estilo_linha.hide()

    def atualizar_estilo_texto_selecionado(self, item: QGraphicsTextItem):
        font = item.font()
        self.combo_fonte.setCurrentFont(font)
        self.combo_tamanho.setCurrentText(str(font.pointSize()))
        # Atualiza botões checkáveis
        self.btn_negrito.setChecked(font.bold())
        self.btn_italico.setChecked(font.italic())
        self.btn_sublinhado.setChecked(font.underline())

    def _criar_estilo_linha(self):
        grupo_estilo = QGroupBox("Estilo")
        g2 = QGridLayout()
        # Cor de contorno
        g2.addWidget(QLabel("Cor de Contorno:"), 0, 0)
        btn_cor_contorno = QPushButton("Cor de Contorno")
        btn_cor_contorno.clicked.connect(lambda: alterar_cor_contorno(self.main_window))

        g2.addWidget(btn_cor_contorno, 1, 0)

        # Tipo de contorno
        g2.addWidget(QLabel("Tipo de Contorno:"), 0, 1)
        tipo_linha = QComboBox()
        tipo_linha.currentTextChanged.connect(
            lambda estilo: alterar_tipo_linha(self.main_window, estilo)
        )

        tipo_linha.addItems(["Contínuo", "Tracejado", "Pontilhado", "Traço-Ponto"])
        tipo_linha.setToolTip("Tipo de Linha")
        g2.addWidget(tipo_linha, 1, 1)

        # Espessura Linha
        g2.addWidget(QLabel("Espessura:"), 0, 2)
        combo_espessura = QComboBox()
        combo_espessura.setToolTip("Espessura do Contorno")
        valores_decimais = [f"{i/10:.1f}" for i in range(1, 10)]
        valores_inteiros = [str(i) for i in range(1, 21)]
        valores = valores_decimais + valores_inteiros

        combo_espessura.addItems(valores)
        combo_espessura.setCurrentText("2")  # valor padrão: 2

        combo_espessura.currentIndexChanged.connect(
            lambda index: alterar_espessura_contorno(
                self.main_window, float(combo_espessura.currentText())
            )
        )
        g2.addWidget(combo_espessura, 1, 2)

        # Extremidade inicial
        g2.addWidget(QLabel("Extremidade Inicial:"), 2, 0)
        extremidade_ini = QComboBox()
        estilos_seta = ["Nenhuma", "Seta", "Seta Aberta", "Círculo", "Quadrado"]
        extremidade_ini.addItems(estilos_seta)
        extremidade_ini.setToolTip("Extremidade Inicial")

        # Extremidade final
        g2.addWidget(QLabel("Extremidade Final:"), 2, 1)
        extremidade_fim = QComboBox()
        extremidade_fim.addItems(estilos_seta)
        extremidade_fim.setToolTip("Extremidade Final")
        extremidade_ini.currentTextChanged.connect(
            lambda estilo: self._aplicar_extremidade("inicio", estilo)
        )
        extremidade_fim.currentTextChanged.connect(
            lambda estilo: self._aplicar_extremidade("fim", estilo)
        )

        self.extremidade_ini = extremidade_ini
        self.extremidade_fim = extremidade_fim
        # TAMANHO DAS SETAS

        g2.addWidget(QLabel("Tamanho da Extremidade:"), 2, 3)
        combo_tamanho_ext = QComboBox()
        combo_tamanho_ext.addItems([str(i) for i in range(4, 100, 2)])
        combo_tamanho_ext.setCurrentText("12")
        g2.addWidget(combo_tamanho_ext, 3, 3)
        self.combo_tamanho_ext = combo_tamanho_ext
        self.combo_tamanho_ext.currentTextChanged.connect(
            self._atualizar_tamanho_extremidade
        )
        self.tamanho_extremidade = 12

        # Cor de preenchimento
        g2.addWidget(QLabel("Cor de Preenchimento:"), 2, 2)
        btn_cor_preench = QPushButton("Cor de Preenchimento")
        btn_cor_preench.clicked.connect(
            lambda: alterar_cor_preenchimento(self.main_window)
        )
        g2.addWidget(btn_cor_preench, 3, 2)
        grupo_estilo.setLayout(g2)
        extremidade_ini.currentTextChanged.connect(
            lambda estilo: self._aplicar_extremidade("inicio", estilo)
        )
        extremidade_fim.currentTextChanged.connect(
            lambda estilo: self._aplicar_extremidade("fim", estilo)
        )
        self.extremidade_ini = extremidade_ini
        self.extremidade_fim = extremidade_fim
        g2.addWidget(extremidade_ini, 3, 0)
        g2.addWidget(extremidade_fim, 3, 1)
        return grupo_estilo

    def _aplicar_extremidade(self, qual, estilo):
        for item in self.main_window.canvas.scene.selectedItems():
            if isinstance(item, EditableLine):
                if qual == "inicio":
                    item.estilo_ini = estilo
                elif qual == "fim":
                    item.estilo_fim = estilo
                item.update_line()
            elif isinstance(item, EditablePolyline):
                if qual == "inicio":
                    item.estilo_ini = estilo
                elif qual == "fim":
                    item.estilo_fim = estilo
                (
                    item.update_line()
                    if isinstance(item, EditableLine)
                    else item.update_extremidades()
                )

    def _criar_estilo_texto(self):
        grupo = QGroupBox("Texto")
        layout = QVBoxLayout()

        # Linha 1: Fonte + Tamanho
        linha1 = QHBoxLayout()
        self.combo_fonte = QFontComboBox()
        self.combo_fonte.setCurrentFont(QFont("Microsoft Sans Serif"))

        self.combo_tamanho = QComboBox()
        self.combo_tamanho.addItems([str(t) for t in range(8, 97, 2)])
        self.combo_tamanho.setCurrentText("12")

        linha1.addWidget(self.combo_fonte)
        linha1.addWidget(self.combo_tamanho)

        # Linha 2: Negrito, Itálico, Sublinhado, Cor
        linha2 = QHBoxLayout()
        self.btn_negrito = QToolButton()
        self.btn_negrito.setIcon(QIcon("icons/bold.svg"))
        self.btn_negrito.setCheckable(True)

        self.btn_italico = QToolButton()
        self.btn_italico.setIcon(QIcon("icons/italic.svg"))
        self.btn_italico.setCheckable(True)

        self.btn_sublinhado = QToolButton()
        self.btn_sublinhado.setIcon(QIcon("icons/underline.svg"))
        self.btn_sublinhado.setCheckable(True)

        self.btn_cor = QPushButton("Cor")
        self.btn_cor.clicked.connect(self.abrir_seletor_cor_texto)

        linha2.addWidget(self.btn_negrito)
        linha2.addWidget(self.btn_italico)
        linha2.addWidget(self.btn_sublinhado)
        linha2.addWidget(self.btn_cor)

        # Ligações
        self.btn_negrito.clicked.connect(
            lambda _: aplicar_formatacao_texto(
                self.main_window, negrito=self.btn_negrito.isChecked()
            )
        )
        self.btn_italico.clicked.connect(
            lambda _: aplicar_formatacao_texto(
                self.main_window, italico=self.btn_italico.isChecked()
            )
        )
        self.btn_sublinhado.clicked.connect(
            lambda _: aplicar_formatacao_texto(
                self.main_window, sublinhado=self.btn_sublinhado.isChecked()
            )
        )
        self.combo_fonte.currentFontChanged.connect(
            lambda font: aplicar_formatacao_texto(self.main_window, fonte=font.family())
        )
        self.combo_tamanho.currentTextChanged.connect(
            lambda size: aplicar_formatacao_texto(self.main_window, tamanho=int(size))
        )

        layout.addLayout(linha1)
        layout.addLayout(linha2)
        grupo.setLayout(layout)

        return grupo

    def atualizar_estilo_linha_selecionado(self, item):
        pen = None
        if hasattr(item, "pen"):
            pen = item.pen() if callable(item.pen) else item.pen
        elif hasattr(item, "path_items") and item.path_items:
            pen = item.path_items[0].pen()

        if pen:
            estilo = {
                Qt.SolidLine: "Contínuo",
                Qt.DashLine: "Tracejado",
                Qt.DotLine: "Pontilhado",
                Qt.DashDotLine: "Traço-Ponto",
            }.get(pen.style(), "Contínuo")

            espessura = str(pen.width())

            # Atualiza os combos da aba Estilo
            for i in range(self.combo_espessura.count()):
                if self.combo_espessura.itemText(i) == espessura:
                    self.combo_espessura.setCurrentIndex(i)
                    break

            self.tipo_linha.setCurrentText(estilo)

    def _atualizar_tamanho_extremidade(self, valor):
        try:
            self.tamanho_extremidade = int(valor)
            for item in self.main_window.canvas.scene.selectedItems():
                if isinstance(item, EditableLine):
                    item.update_line()
                elif isinstance(item, EditablePolyline):
                    item.update_extremidades()

        except ValueError:
            pass


##############################################################################################################################

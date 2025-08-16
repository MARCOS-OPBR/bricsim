from PyQt5.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class PropriedadesDialog(QDialog):
    def __init__(self, objeto=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Propriedades")
        self.resize(400, 300)

        layout = QVBoxLayout(self)
        abas = QTabWidget()
        layout.addWidget(abas)

        if objeto is None:
            abas.addTab(self._aba_tela(), "Tela")
        else:
            abas.addTab(self._aba_estilo(objeto), "Estilo")
            abas.addTab(self._aba_modificadores(objeto), "Modificadores")

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

    def _aba_tela(self):
        aba = QWidget()
        form = QFormLayout(aba)

        self.tipo_input = QComboBox()
        self.tipo_input.addItems(["Tela", "Faceplate"])

        self.largura_input = QLineEdit("1280")
        self.altura_input = QLineEdit("720")

        self.bg_color_btn = QPushButton("Escolher cor")
        self.bg_color_btn.clicked.connect(self._selecionar_cor_fundo)

        form.addRow("Tipo:", self.tipo_input)
        form.addRow("Largura:", self.largura_input)
        form.addRow("Altura:", self.altura_input)
        form.addRow("Plano de fundo:", self.bg_color_btn)

        return aba

    def _aba_estilo(self, objeto):
        aba = QWidget()
        form = QFormLayout(aba)

        self.fonte_input = QLineEdit("Microsoft Sans Serif")
        self.tamanho_input = QLineEdit("12")
        self.cor_texto_btn = QPushButton("Escolher cor")
        self.cor_texto_btn.clicked.connect(self._selecionar_cor_texto)

        form.addRow("Fonte:", self.fonte_input)
        form.addRow("Tamanho:", self.tamanho_input)
        form.addRow("Cor do texto:", self.cor_texto_btn)

        return aba

    def _aba_modificadores(self, objeto):
        aba = QWidget()
        form = QFormLayout(aba)

        self.tipo_mod = QComboBox()
        self.tipo_mod.addItems(["fill", "piscar", "texto", "cor do texto"])

        self.expr_input = QLineEdit("variavel > 2.0")
        self.valor_a = QLineEdit("valor A (ex: #ff0000)")
        self.valor_b = QLineEdit("valor B (ex: #00ff00)")

        form.addRow("Tipo de Modificador:", self.tipo_mod)
        form.addRow("Expressão lógica:", self.expr_input)
        form.addRow("Valor A:", self.valor_a)
        form.addRow("Valor B:", self.valor_b)

        return aba

    def _selecionar_cor_fundo(self):
        cor = QColorDialog.getColor()
        if cor.isValid():
            self.bg_color_btn.setStyleSheet(f"background-color: {cor.name()}")

    def _selecionar_cor_texto(self):
        cor = QColorDialog.getColor()
        if cor.isValid():
            self.cor_texto_btn.setStyleSheet(f"background-color: {cor.name()}")


class VariableDialog(QDialog):
    def __init__(self, parent=None, tag="", casas=2, digitos=4):
        super().__init__(parent)
        self.setWindowTitle("Configurar Variável")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.tag_edit = QLineEdit(tag)
        form.addRow("TAG de referência:", self.tag_edit)

        self.casas_spin = QSpinBox()
        self.casas_spin.setRange(0, 6)
        self.casas_spin.setValue(casas)
        form.addRow("Casas decimais:", self.casas_spin)

        self.digitos_spin = QSpinBox()
        self.digitos_spin.setRange(1, 12)
        self.digitos_spin.setValue(digitos)
        form.addRow("Dígitos:", self.digitos_spin)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        return {
            "tag": self.tag_edit.text(),
            "casas": self.casas_spin.value(),
            "digitos": self.digitos_spin.value(),
        }

# toolbar_status.py
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit
from PyQt5.QtCore import Qt, pyqtSignal

class StatusBar(QWidget):
    # Sinal emitido quando o usuário digita um comando
    comando_executado = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(12)

        # 📍 Coordenadas (exibidas em tempo real)
        self.coords_label = QLabel("X: ---  Y: ---")
        self.coords_label.setMinimumWidth(120)

        # 🧭 Modo atual
        self.modo_label = QLabel("Modo: SELEÇÃO")
        self.modo_label.setMinimumWidth(150)

        # 💬 Barra de Comando
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Digite um comando e pressione Enter")
        self.cmd_input.returnPressed.connect(self.executar_comando)

        # Adiciona ao layout
        layout.addWidget(self.coords_label)
        layout.addWidget(self.modo_label)
        layout.addWidget(self.cmd_input, stretch=1)

        self.setLayout(layout)

    def atualizar_coords(self, x, y):
        self.coords_label.setText(f"X: {int(x)}  Y: {int(y)}")

    def definir_modo(self, texto):
        self.modo_label.setText(f"Modo: {texto.upper()}")

    def executar_comando(self):
        texto = self.cmd_input.text().strip()
        if texto:
            self.comando_executado.emit(texto)
            self.cmd_input.clear()
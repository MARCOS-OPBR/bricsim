from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QLabel, QListWidget, QTextEdit, QSizePolicy

class Sidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        # 🔹 Parte 1: Biblioteca de símbolos
        self.biblioteca_box = QGroupBox("Biblioteca")
        biblioteca_layout = QVBoxLayout()
        biblioteca_layout.addWidget(QLabel("ISA 5.1"))  # Placeholder
        biblioteca_layout.addWidget(QListWidget())       # Futuro: lista de símbolos
        self.biblioteca_box.setLayout(biblioteca_layout)

        # 🔹 Parte 2: Árvore de Navegação
        self.arvore_box = QGroupBox("Navegação")
        arvore_layout = QVBoxLayout()
        arvore_layout.addWidget(QLabel("Tela atual: Forno L-2B"))  # Placeholder
        arvore_layout.addWidget(QTextEdit())                       # Futuro: QTreeView
        self.arvore_box.setLayout(arvore_layout)

        # Adiciona os dois quadros ao layout principal
        layout.addWidget(self.biblioteca_box, stretch=2)
        layout.addWidget(self.arvore_box, stretch=3)

        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setMinimumWidth(220)
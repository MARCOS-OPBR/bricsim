# functions.py (DESIGN)
from canvas import (
    EditableLine,
    EditablePolyline,
    EditableTextItem,
    EditableVariable,
    SvgObjectItem,
)
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
from PyQt5.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from svg.path import Arc, CubicBezier, Line, QuadraticBezier, parse_path


class NovoDocumentoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo Documento")
        self.setMinimumWidth(350)

        # Campos
        self.nome_tela = QLineEdit()
        self.unidade = QLineEdit()
        self.resolucao = QComboBox()
        self.resolucao.addItems(["1920 x 1080", "1280 x 720", "Personalizada"])
        self.cor_fundo = QPushButton("Escolher Cor")
        self.cor_selecionada = QColor("#ffffff")
        self.cor_fundo.clicked.connect(self.abrir_seletor_cor)
        self.grade_checkbox = QCheckBox("Exibir Grade")

        # Botões
        self.botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Nome da Tela:"))
        layout.addWidget(self.nome_tela)
        layout.addWidget(QLabel("Unidade da Planta:"))
        layout.addWidget(self.unidade)
        layout.addWidget(QLabel("Resolução:"))
        layout.addWidget(self.resolucao)
        layout.addWidget(QLabel("Cor de Fundo:"))
        layout.addWidget(self.cor_fundo)
        layout.addWidget(self.grade_checkbox)
        layout.addWidget(self.botoes)
        self.setLayout(layout)

    def abrir_seletor_cor(self):
        cor = QColorDialog.getColor(initial=self.cor_selecionada, parent=self)
        if cor.isValid():
            self.cor_selecionada = cor
            self.cor_fundo.setStyleSheet(f"background-color: " + cor.name())


# ✅ Função fora da classe — isso que o Ribbon vai importar


def abrir_novo_documento(main_window):
    dialog = NovoDocumentoDialog(main_window)
    if dialog.exec_():
        nome = dialog.nome_tela.text()
        planta = dialog.unidade.text()
        resolucao = dialog.resolucao.currentText()
        cor_fundo = dialog.cor_selecionada
        grade = dialog.grade_checkbox.isChecked()

        # Limpa o canvas
        main_window.canvas.scene.clear()

        # Atualiza o título da janela
        main_window.atualizar_titulo(f"{nome}.tbr")

        # Atualiza fundo do canvas
        main_window.canvas.setBackgroundBrush(cor_fundo)

        # Atualiza resolução (se quiser mudar tamanho do canvas)
        if "x" in resolucao:
            w, h = map(int, resolucao.split("x"))
            main_window.canvas.set_area_util(w, h, cor_fundo)
        else:
            main_window.canvas.set_area_util(1920, 1080, cor_fundo)
            from PyQt5.QtWidgets import QColorDialog
    main_window.canvas.set_grid_visible(grade)  # usa a checkbox "Exibir grade"


def alternar_handles(main_window, visivel: bool):
    scene = main_window.canvas.scene

    for item in scene.items():
        if hasattr(item, "handle_start"):
            item.handle_start.setVisible(visivel)
        if hasattr(item, "handle_end"):
            item.handle_end.setVisible(visivel)


def aplicar_formatacao_texto(
    main_window,
    fonte=None,
    tamanho=None,
    negrito=None,
    italico=None,
    sublinhado=None,
    cor=None,
):
    scene = main_window.canvas.scene
    for item in scene.selectedItems():
        if isinstance(item, QGraphicsTextItem):
            font = item.font()
            if fonte:
                font.setFamily(fonte)
            if tamanho:
                font.setPointSize(tamanho)
            if negrito is not None:
                font.setBold(negrito)
            if italico is not None:
                font.setItalic(italico)
            if sublinhado is not None:
                font.setUnderline(sublinhado)
            item.setFont(font)
            if cor:
                item.setDefaultTextColor(cor)


def ativar_desenho_linha(main_window):
    main_window.canvas.set_mode("linha")


def ativar_desenho_texto(main_window):
    if hasattr(main_window, "canvas"):
        main_window.canvas.set_mode("texto")

    if hasattr(main_window, "ribbon"):
        main_window.ribbon.atualizar_estilo_visual("texto")


def aplicar_formatacao_texto(
    main_window,
    fonte=None,
    tamanho=None,
    negrito=None,
    italico=None,
    sublinhado=None,
    cor=None,
):
    canvas = main_window.canvas
    for item in canvas.scene.selectedItems():
        if isinstance(item, QGraphicsTextItem):
            font = item.font()

            if fonte:
                font.setFamily(fonte)
            if tamanho:
                font.setPointSize(tamanho)
            if negrito is not None:
                font.setBold(negrito)
            if italico is not None:
                font.setItalic(italico)
            if sublinhado is not None:
                font.setUnderline(sublinhado)

            item.setFont(font)

            if cor:
                item.setDefaultTextColor(cor)


def ativar_modo_selecionar(main_window):
    main_window.canvas.set_mode("selecionar")


import json


def salvar_projeto(main_window):
    path, _ = QFileDialog.getSaveFileName(
        main_window, "Salvar Projeto", "", "Projeto BRICSim (*.tbr)"
    )
    if not path:
        return
    # Encontra o item da área útil com zValue -10
    for item in main_window.canvas.scene.items():
        if isinstance(item, QGraphicsRectItem) and item.zValue() == -10000:
            cor_fundo = item.brush().color().name()
            break
    else:
        cor_fundo = "#ff00ff"

    data = {
        "canvas_size": [
            main_window.canvas.area_largura,
            main_window.canvas.area_altura,
        ],
        "items": [],
        "cor_fundo": cor_fundo,
    }
    id_map = {}  # salva objetos com ID

    for item in main_window.canvas.scene.items():
        obj_id = id(item)

        if isinstance(item, EditableLine):
            data["items"].append(item.to_dict())
            id_map[obj_id] = item

        elif isinstance(item, EditablePolyline):
            data["items"].append(item.to_dict())
            id_map[obj_id] = item
        elif isinstance(item, EditableVariable):
            data["items"].append(item.to_dict())
            id_map[obj_id] = item

        elif isinstance(item, EditableTextItem):
            font = item.font()
            data["items"].append(
                {
                    "type": "text",
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "content": item.toPlainText(),
                    "font": font.family(),
                    "size": font.pointSize(),
                    "bold": font.bold(),
                    "italic": font.italic(),
                    "underline": font.underline(),
                    "color": item.defaultTextColor().name(),
                    "z": item.zValue(),
                    "scale_x": item.transform().m11(),
                    "scale_y": item.transform().m22(),
                    "id": obj_id,
                }
            )
            id_map[obj_id] = item

        elif isinstance(item, SvgObjectItem):
            d_paths = []
            for child in item.childItems():
                if isinstance(child, QGraphicsPathItem):
                    d = child.data(1)
                    if not d:
                        continue
                    stroke = child.pen().color().name()
                    stroke_width = child.pen().widthF()
                    fill = (
                        child.brush().color().name()
                        if child.brush().style() != Qt.NoBrush
                        else "none"
                    )

                    d_paths.append(
                        {
                            "d": d,
                            "stroke": stroke,
                            "stroke_width": stroke_width,
                            "fill": fill,
                        }
                    )

            data["items"].append(
                {
                    "type": "svg",
                    "tag": item.data(0),
                    "paths": d_paths,
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "z": item.zValue(),
                    "scale_x": item.transform().m11(),
                    "scale_y": item.transform().m22(),
                    "rotation": item.rotation(),
                    "shear_x": item.transform().m12(),
                    "shear_y": item.transform().m21(),
                    "id": obj_id,
                }
            )
            id_map[obj_id] = item

        elif isinstance(item, QGraphicsItemGroup):
            filhos_ids = [id(child) for child in item.childItems()]
            data["items"].append(
                {
                    "type": "grupo",
                    "filhos_ids": filhos_ids,
                    "z": item.zValue(),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "id": obj_id,
                }
            )
            id_map[obj_id] = item

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    main_window.atualizar_titulo(path.split("/")[-1])
    # Após salvar com sucesso:
    if hasattr(main_window, "marcar_modificado"):
        main_window.marcar_modificado(False)


def carregar_projeto(main_window):
    path, _ = QFileDialog.getOpenFileName(
        main_window, "Abrir Projeto", "", "Projeto BRICSim (*.tbr *mbr)"
    )
    if not path:
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    main_window.canvas.scene.clear()

    largura, altura = data.get("canvas_size", [1920, 1080])
    cor_fundo = QColor(data.get("cor_fundo", "#ffffff"))
    main_window.canvas.set_area_util(largura, altura, cor_fundo)

    id_map = {}
    pendentes = []

    for item_data in data["items"]:
        if item_data["type"] == "linha":
            line = EditableLine.from_dict(item_data)
            t = QTransform()
            main_window.canvas.scene.addItem(line)
            id_map[item_data["id"]] = line

        elif item_data["type"] == "text":
            from canvas import EditableTextItem

            texto = EditableTextItem(item_data["content"])
            texto.setPos(QPointF(item_data.get("x", 0), item_data.get("y", 0)))
            t = QTransform()
            t.scale(item_data.get("scale_x", 1.0), item_data.get("scale_y", 1.0))
            texto.setRotation(item_data.get("rotation", 0))
            texto.setTransform(t)
            fonte = QFont(item_data["font"], item_data["size"])
            fonte.setBold(item_data.get("bold", False))
            fonte.setItalic(item_data.get("italic", False))
            fonte.setUnderline(item_data.get("underline", False))
            texto.setFont(fonte)
            texto.setDefaultTextColor(QColor(item_data["color"]))
            texto.setZValue(item_data.get("z", 0))
            main_window.canvas.scene.addItem(texto)
            id_map[item_data["id"]] = texto

        elif item_data["type"] == "caminho":
            poly = EditablePolyline.from_dict(item_data)
            main_window.canvas.scene.addItem(poly)
            id_map[item_data["id"]] = poly

        elif item_data["type"] == "svg":
            from canvas import SvgObjectItem

            svg_item = SvgObjectItem(item_data.get("tag", "SVG"))
            svg_item.setZValue(item_data.get("z", 0))
            svg_item.setPos(QPointF(item_data.get("x", 0), item_data.get("y", 0)))
            svg_item.setRotation(item_data.get("rotation", 0))
            t = QTransform()
            t.scale(item_data.get("scale_x", 1.0), item_data.get("scale_y", 1.0))
            svg_item.setTransform(t)

            for path_dict in item_data["paths"]:
                d = path_dict["d"]
                qt_path = QPainterPath()
                svg_path_obj = parse_path(d)
                first = True

                for seg in svg_path_obj:
                    start = QPointF(seg.start.real, seg.start.imag)
                    end = QPointF(seg.end.real, seg.end.imag)

                    if first:
                        qt_path.moveTo(start)
                        first = False

                    if isinstance(seg, Line):
                        qt_path.lineTo(end)
                    elif isinstance(seg, CubicBezier):
                        qt_path.cubicTo(
                            QPointF(seg.control1.real, seg.control1.imag),
                            QPointF(seg.control2.real, seg.control2.imag),
                            end,
                        )
                    elif isinstance(seg, QuadraticBezier):
                        qt_path.quadTo(
                            QPointF(seg.control.real, seg.control.imag),
                            end,
                        )
                    elif isinstance(seg, Arc):
                        qt_path.lineTo(end)

                path_item = QGraphicsPathItem(qt_path)
                path_item.setData(1, d)  # reatribui o d original
                path_item.setPen(
                    QPen(QColor(path_dict["stroke"]), path_dict["stroke_width"])
                )
                path_item.setBrush(
                    QBrush(QColor(path_dict["fill"]))
                    if path_dict["fill"] != "none"
                    else QBrush(Qt.transparent)
                )
                svg_item.add_path(path_item)

            main_window.canvas.scene.addItem(svg_item)
            id_map[item_data["id"]] = svg_item

        elif item_data["type"] == "grupo":
            pendentes.append(item_data)
        elif item_data["type"] == "variavel":
            var = EditableVariable.from_dict(item_data)
            main_window.canvas.scene.addItem(var)
            id_map[item_data["id"]] = var

    restantes = pendentes[:]
    while restantes:
        progresso = False
        for grupo_data in restantes[:]:
            filhos_ok = all(fid in id_map for fid in grupo_data["filhos_ids"])
            if filhos_ok:
                grupo = main_window.canvas.scene.createItemGroup(
                    [id_map[fid] for fid in grupo_data["filhos_ids"]]
                )
                grupo.setZValue(grupo_data.get("z", 0))
                grupo.setFlags(
                    QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                )
                grupo.setPos(QPointF(grupo_data.get("x", 0), grupo_data.get("y", 0)))
                gid = grupo_data.get("id", id(grupo))
                id_map[gid] = grupo
                restantes.remove(grupo_data)
                progresso = True
        if not progresso:
            print(
                "⚠️ Alguns grupos não puderam ser reconstruídos (ciclo ou falta de dependência)"
            )
            break

    main_window.atualizar_titulo(path.split("/")[-1])


def importar_imagem(main_window):
    caminho, _ = QFileDialog.getOpenFileName(
        None, "Importar Imagem", "", "Imagens (*.png *.jpg *.bmp *.gif)"
    )
    if caminho:
        canvas = main_window.canvas
        canvas.imagem_a_importar = caminho
        canvas.set_mode("inserir_imagem")


import copy

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QFont, QTransform
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGraphicsItemGroup,
    QGraphicsTextItem,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


def escalar_item_selecionado(main_window):
    scene = main_window.canvas.scene
    itens = scene.selectedItems()
    if not itens:
        QMessageBox.information(main_window, "Escala", "Nenhum item selecionado.")
        return

    # Salva o estado inicial de transformacoes e posicoes
    estado_original = {}
    for item in itens:
        estado_original[item] = {
            "transform": QTransform(item.transform()),
            "font_size": (
                item.font().pointSizeF()
                if isinstance(item, QGraphicsTextItem)
                else None
            ),
            "p1": item.handle_start.pos() if hasattr(item, "handle_start") else None,
            "p2": item.handle_end.pos() if hasattr(item, "handle_end") else None,
        }

    class DialogEscala(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Escalar Objeto")
            layout = QVBoxLayout()

            self.proporcional = QCheckBox("Manter proporção")
            self.proporcional.setChecked(True)
            layout.addWidget(self.proporcional)

            self.escala_x = QDoubleSpinBox()
            self.escala_y = QDoubleSpinBox()
            for spin in (self.escala_x, self.escala_y):
                spin.setDecimals(2)
                spin.setRange(0.1, 10.0)
                spin.setSingleStep(0.1)
                spin.setValue(1.0)
            layout.addWidget(QLabel("Escala X:"))
            layout.addWidget(self.escala_x)
            layout.addWidget(QLabel("Escala Y:"))
            layout.addWidget(self.escala_y)

            self.reset_btn = QPushButton("Resetar")
            self.reset_btn.clicked.connect(self.resetar)
            layout.addWidget(self.reset_btn)

            self.botoes = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            )
            layout.addWidget(self.botoes)
            self.setLayout(layout)

            self.botoes.accepted.connect(self.accept)
            self.botoes.rejected.connect(self.reject)
            self.escala_x.valueChanged.connect(self._sync_y_if_proporcional)
            self.escala_y.valueChanged.connect(self._sync_x_if_proporcional)

        def _sync_y_if_proporcional(self, val):
            if self.proporcional.isChecked():
                self.escala_y.blockSignals(True)
                self.escala_y.setValue(val)
                self.escala_y.blockSignals(False)

        def _sync_x_if_proporcional(self, val):
            if self.proporcional.isChecked():
                self.escala_x.blockSignals(True)
                self.escala_x.setValue(val)
                self.escala_x.blockSignals(False)

        def resetar(self):
            self.escala_x.setValue(1.0)
            self.escala_y.setValue(1.0)
            restaurar_estado_original()

    def restaurar_estado_original():
        for item in itens:
            estado = estado_original[item]
            item.setTransform(estado["transform"])
            if hasattr(item, "handle_start") and hasattr(item, "handle_end"):
                item.handle_start.setPos(estado["p1"])
                item.handle_end.setPos(estado["p2"])
                item.update_line()
            elif (
                isinstance(item, QGraphicsTextItem) and estado["font_size"] is not None
            ):
                fonte = item.font()
                fonte.setPointSizeF(estado["font_size"])
                item.setFont(fonte)

    def aplicar_preview():
        restaurar_estado_original()
        sx = dialog.escala_x.value()
        sy = dialog.escala_y.value()
        for item in itens:
            if hasattr(item, "handle_start") and hasattr(item, "handle_end"):
                centro = item.boundingRect().center()
                p1 = item.handle_start.pos()
                p2 = item.handle_end.pos()
                novo_p1 = centro + (p1 - centro) * sx
                novo_p2 = centro + (p2 - centro) * sy
                item.handle_start.setPos(novo_p1)
                item.handle_end.setPos(novo_p2)
                item.update_line()

            elif isinstance(item, QGraphicsTextItem):
                fonte = item.font()
                novo_tamanho = max(1, round(fonte.pointSizeF() * sx))
                fonte.setPointSize(novo_tamanho)
                item.setFont(fonte)

            elif isinstance(item, QGraphicsItemGroup):
                t = QTransform()
                t.scale(sx, sy)
                item.setTransform(t, True)

            elif hasattr(item, "path_items"):
                for p in item.path_items:
                    t = QTransform()
                    t.scale(sx, sy)
                    p.setTransform(t, True)

            else:
                t = QTransform()
                t.scale(sx, sy)
                item.setTransform(t, True)

    dialog = DialogEscala(main_window)
    dialog.escala_x.valueChanged.connect(aplicar_preview)
    dialog.escala_y.valueChanged.connect(aplicar_preview)

    if not dialog.exec_():
        restaurar_estado_original()
        return

    main_window.canvas._registrar_estado()
    main_window.canvas._salvar_estado()


def exportar_imagem(main_window):
    caminho, _ = QFileDialog.getSaveFileName(
        main_window, "Exportar como Imagem", "", "Imagem PNG (*.png)"
    )
    if not caminho:
        return
    if not caminho.endswith(".png"):
        caminho += ".png"

    scene = main_window.canvas.scene
    rect = scene.sceneRect()

    imagem = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32)
    imagem.fill(Qt.transparent)

    painter = QPainter(imagem)
    scene.render(painter, QRectF(imagem.rect()), rect)
    painter.end()

    imagem.save(caminho, "PNG")


def imprimir_imagem(main_window):
    printer = QPrinter(QPrinter.HighResolution)
    printer.setFullPage(True)

    dialog = QPrintDialog(printer, main_window)
    if dialog.exec_() == QPrintDialog.Accepted:
        painter = QPainter(printer)
        scene = main_window.canvas.scene
        rect = scene.sceneRect()
        scene.render(painter, printer.pageRect(), rect)
        painter.end()


def ativar_desenho_caminho(main_window):
    if hasattr(main_window, "canvas"):
        main_window.canvas.set_mode("caminho")


def alterar_tipo_linha(main_window, estilo):
    estilos = {
        "Contínuo": Qt.SolidLine,
        "Tracejado": Qt.DashLine,
        "Pontilhado": Qt.DotLine,
        "Traço-Ponto": Qt.DashDotLine,
    }

    tipo = estilos.get(estilo, Qt.SolidLine)

    canvas = main_window.canvas
    for item in canvas.scene.selectedItems():
        if hasattr(item, "apply_pen"):
            # Caso item tenha pen diretamente
            if hasattr(item, "pen"):
                pen = item.pen() if callable(item.pen) else item.pen
            # Caso seja um grupo SVG com path_items
            elif hasattr(item, "path_items") and item.path_items:
                pen = item.path_items[0].pen()
            else:
                continue  # pula se não tem como obter pen

            pen.setStyle(tipo)
            item.apply_pen(pen)


def alterar_espessura_contorno(main_window, valor):
    canvas = main_window.canvas
    for item in canvas.scene.selectedItems():
        if hasattr(item, "apply_pen"):
            # Caso seja um item com pen direto
            if hasattr(item, "pen"):
                pen = item.pen() if callable(item.pen) else item.pen
                pen.setWidthF(valor)
                item.apply_pen(pen)

            # Caso seja um grupo SVG com sub-itens
            elif hasattr(item, "path_items") and item.path_items:
                pen = item.path_items[0].pen()
                pen.setWidthF(valor)
                item.apply_pen(pen)


def alterar_cor_contorno(main_window):
    cor = QColorDialog.getColor()
    if not cor.isValid():
        return

    canvas = main_window.canvas
    for item in canvas.scene.selectedItems():
        if hasattr(item, "apply_pen"):
            pen = item.pen() if callable(item.pen) else item.pen
            pen.setColor(cor)
            item.apply_pen(pen)


def alterar_cor_preenchimento(main_window):
    scene = main_window.canvas.scene
    selecionados = scene.selectedItems()

    if not selecionados:
        return

    cor = QColorDialog.getColor(parent=main_window)
    if not cor.isValid():
        return

    for item in selecionados:
        if hasattr(item, "apply_brush"):
            item.apply_brush(QBrush(cor))
        elif hasattr(item, "setBrush"):
            item.setBrush(QBrush(cor))  # fallback direto

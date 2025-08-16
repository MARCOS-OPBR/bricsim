
from PyQt5.QtWidgets import (
    QApplication, QGraphicsView, QGraphicsScene,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsRectItem,
    QGraphicsItem,QGraphicsTextItem,QGraphicsPixmapItem
    ,QGraphicsItemGroup,QInputDialog,QFileDialog,QGraphicsPathItem,QMenu,QShortcut, QMessageBox,
    QGraphicsPolygonItem)

from PyQt5.QtCore import Qt, QPointF, QRectF,pyqtSignal,QLine,QLineF, QTimer
from PyQt5.QtGui import (QPen, QColor, QPainter, QKeySequence,QFont,QPixmap, QBrush,QPainterPath,
        QTransform, QPolygonF)
from PyQt5.QtSvg import QGraphicsSvgItem
import math, json
import sip
import svg.path
from xml.dom import minidom
import xml.etree.ElementTree as ET
from svg.path import parse_path
from svg.path import Line, CubicBezier, QuadraticBezier, Arc
from dialogs import PropriedadesDialog  # se ainda não tiver







class SnapMovableItem():
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            scene = self.scene()
            parent = scene.parent() if scene else None
            if parent and getattr(parent, "snap_to_grid", False):
                spacing = parent.grid_spacing
                x = round(value.x() / spacing) * spacing
                y = round(value.y() / spacing) * spacing
                return QPointF(x, y)
        return super().itemChange(change, value)

class SnapPixmapItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, parent=None):
        super().__init__(pixmap, parent)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable
        )
        self.setCursor(Qt.SizeAllCursor)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            scene = self.scene()
            parent = scene.parent() if scene else None
            if parent and getattr(parent, "snap_to_grid", False):
                spacing = parent.grid_spacing
                x = round(value.x() / spacing) * spacing
                y = round(value.y() / spacing) * spacing
                return QPointF(x, y)
        return super().itemChange(change, value)


class Handle(QGraphicsEllipseItem):
    def __init__(self, x, y, parent=None):
        super().__init__(-4, -4, 8, 8, parent)
        self.setBrush(QColor("blue"))
        self.setPen(QPen(Qt.NoPen))
        self._bloqueado = False
        
        # ⚙️ Flags de interação:
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIgnoresParentOpacity, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.SizeAllCursor)

        self.setZValue(1)  # garantir que fique acima da linha
        self.setPos(x, y)

    def itemChange(self, change, value):
        if not self.isEnabled():
            return super().itemChange(change, value)

        if getattr(self, "_bloqueado", False):
             return super().itemChange(change, value)
        if change == self.ItemPositionChange and self.parentItem():
            parent = self.parentItem()

            # Verifica se o pai já tem os handles definidos
            if not (hasattr(parent, "handle_start") and hasattr(parent, "handle_end")):
                return super().itemChange(change, value)

            scene = self.scene()
            modifiers = QApplication.keyboardModifiers()

            # SNAP TO GRID (antes do Snap Handle)
            if getattr(scene.parent(), "snap_to_grid", False):
                spacing = scene.parent().grid_spacing
                snapped = QPointF(
                    round(value.x() / spacing) * spacing,
                    round(value.y() / spacing) * spacing
                )
                x = round(value.x() / spacing) * spacing
                y = round(value.y() / spacing) * spacing
                value = QPointF(x, y)
                # Só altera se for diferente (evita travamento)
                if snapped != self.pos():
                    value = snapped

            # SNAP TO HANDLE
            if hasattr(scene, "get_snap_point"):
                value = scene.get_snap_point(value)

            # SHIFT: trava ângulo
            if modifiers & Qt.ShiftModifier:
                other = parent.handle_end if self is parent.handle_start else parent.handle_start
                delta = value - other.pos()
                angle = math.atan2(delta.y(), delta.x())
                snapped_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(delta.x(), delta.y())
                dx = length * math.cos(snapped_angle)
                dy = length * math.sin(snapped_angle)
                value = other.pos() + QPointF(dx, dy)

            parent.update_line()

        return super().itemChange(change, value)



class EditableLine(QGraphicsLineItem):
    def __init__(self, start, end):
        super().__init__()
        self._construindo = True
        self._carregando=False
        self.setPen(QPen(Qt.black, 2))
        self.setFlag(self.ItemIsSelectable)
        self.setZValue(+1)

        self.handle_start = Handle(start.x(), start.y(), parent=self)
        self.handle_end = Handle(end.x(), end.y(), parent=self)
        self.handle_start._bloqueado = True
        self.handle_end._bloqueado = True
        self.estilo_ini = "aberta"
        self.estilo_fim = "aberta"
        self.setas=[]
        self.tamanho_extremidade=12
        self.show_handles = True  # por padrão no Designer


        self.handle_start.setVisible(False)
        self.handle_end.setVisible(False)

        self._construindo = False
        self.handle_start._bloqueado = False
        self.handle_end._bloqueado = False

    def to_dict(self):
        ribbon = self._get_ribbon()
        tamanho_ext = getattr(ribbon, "tamanho_extremidade", None) if ribbon else None
        return {
            "type": "linha",
            "x1": self.line().p1().x(),
            "y1": self.line().p1().y(),
            "x2": self.line().p2().x(),
            "y2": self.line().p2().y(),
            "color": self.pen().color().name(),
            "width": self.pen().widthF(),
            "style": self.pen().style(),
            "estilo_ini": self.estilo_ini,
            "estilo_fim": self.estilo_fim,
            "tamanho_extremidade": tamanho_ext,
            "z": self.zValue(),
            "rotation": self.rotation(),
            "scale_x": self.transform().m11(),
            "scale_y": self.transform().m22(),
            "id": id(self)
        }
    @classmethod

    def from_dict(cls, data):
        linha=cls.__new__(cls)
        linha._carregando=True
        p1 = QPointF(data["x1"], data["y1"])
        p2 = QPointF(data["x2"], data["y2"])
        linha = cls(p1, p2)

        pen = QPen(QColor(data["color"]))
        pen.setWidthF(data["width"])
        pen.setStyle(data["style"])
        linha.setPen(pen)

        linha.setZValue(data.get("z", 0))
        linha.estilo_ini = data.get("estilo_ini", "aberta")
        linha.estilo_fim = data.get("estilo_fim", "aberta")
        tamanho_ext = data.get("tamanho_extremidade", None)
        linha.x1=data.get("x1",0)
        linha.x2=data.get("x2",0)
        linha.y1=data.get("1",0)
        linha.y2=data.get("y2",0)
        t = QTransform()
        t.scale(data.get("scale_x", 1.0), data.get("scale_y", 1.0))
        t.rotate(data.get("rotation", 0))
        linha.setTransform(t)

        QTimer.singleShot(0, lambda: linha.update_line(tamanho_override=tamanho_ext))

        linha._carregando = False
        return linha

    def mouseDoubleClickEvent(self, event):
        self.setSelected(True)  # Força visibilidade dos handles
        super().mouseDoubleClickEvent(event)

    def _get_ribbon(self):
        parent = self.scene().views()[0].parent() if self.scene().views() else None
        while parent:
            if hasattr(parent, "ribbon"):
                return parent.ribbon
            parent = parent.parent()
        return None

    def update_line(self, tamanho_override=None):
        if self.show_handles:
            if getattr(self, "_construindo", False):
                return

            p1 = self.handle_start.pos()
            p2 = self.handle_end.pos()
            self.setLine(QLineF(p1, p2))

            # Remove extremidades anteriores
            for item in getattr(self, "_setas", []):
                if item and item.scene():
                    item.scene().removeItem(item)
            self._setas = []

            direcao = p2 - p1
            # 🔹 Se estiver carregando, não bloqueia pelo tamanho zero
            if not getattr(self, "_carregando", False):
                if direcao.manhattanLength() == 0 or not self.scene():
                    return

            direcao_normalizada = direcao / (direcao.manhattanLength() or 1)

            # 🔁 Interpreta estilos e tipo (fechada ou aberta)
            estilo_ini = self.estilo_ini.replace(" Aberta", "")
            tipo_ini = "aberta" if "Aberta" in self.estilo_ini else "fechada"

            estilo_fim = self.estilo_fim.replace(" Aberta", "")
            tipo_fim = "aberta" if "Aberta" in self.estilo_fim else "fechada"

            # 🔹 Tamanho: override > Ribbon > padrão
            if tamanho_override is not None:
                tamanho = tamanho_override
            else:
                ribbon = self._get_ribbon()
                tamanho = getattr(ribbon, "tamanho_extremidade", 12) if ribbon else 12

            if estilo_ini != "Nenhuma":
                forma_ini = criar_extremidade(p1, -direcao_normalizada, estilo_ini,
                                            tamanho=tamanho, cor=self.pen().color(), tipo=tipo_ini)
                if forma_ini:
                    forma_ini.setZValue(self.zValue() + 1)
                    self.scene().addItem(forma_ini)
                    self._setas.append(forma_ini)

            if estilo_fim != "Nenhuma":
                forma_fim = criar_extremidade(p2, direcao_normalizada, estilo_fim,
                                            tamanho=tamanho, cor=self.pen().color(), tipo=tipo_fim)
                if forma_fim:
                    forma_fim.setZValue(self.zValue() + 1)
                    self.scene().addItem(forma_fim)
                    self._setas.append(forma_fim)


    def itemChange(self, change, value):
        # Quando o item é removido da cena, apaga as setas associadas
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene() is None:
            for seta in getattr(self, "_setas", []):
                if seta and seta.scene():
                    seta.scene().removeItem(seta)
            self._setas = []
        return super().itemChange(change, value)



    def setSelected(self, selected):
        super().setSelected(selected)
        self.handle_start.setVisible(selected)
        self.handle_end.setVisible(selected)

    def apply_pen(self, pen: QPen):
        if self.show_handles:
            self.setPen(pen)

    



class EditablePolyline(QGraphicsItemGroup):
    def __init__(self, start_point_or_list, parent=None):
        super().__init__(parent)
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable)
        self.setZValue(+1)
        self._carregando=False
        self.points = []
        self.lines = []
        self.handles = []
        self.mode="caminho"
        self.pen = QPen(Qt.black, 2)
        self.estilo_ini = "Nenhuma"
        self.estilo_fim = "Nenhuma"
        self._extremidades = []
        self.show_handles = True
        if isinstance(start_point_or_list, list):
            pontos = start_point_or_list
        else:
            pontos = [start_point_or_list]

        for pt in pontos:
            self.points.append(pt)
            self._adicionar_handle(pt)

    def to_dict(self):
        pontos = [[p.x(), p.y()] for p in self.points]
        t = self.transform()
        ribbon = self._get_ribbon()
        tamanho_ext = getattr(ribbon, "tamanho_extremidade", None) if ribbon else None
        return {
            "type": "caminho",
            "z": self.zValue(),
            "color": self.pen.color().name(),
            "width": self.pen.widthF(),
            "style": self.pen.style(),
            "scale_x": t.m11(),
            "scale_y": t.m22(),
            "x": self.pos().x(),
            "y": self.pos().y(),
            "pontos": [[p.x() + self.pos().x(), p.y() + self.pos().y()] for p in self.points],
            "estilo_ini": self.estilo_ini,
            "estilo_fim": self.estilo_fim,
            "rotation": self.rotation(),
            "scale_x": self.transform().m11(),
            "scale_y": self.transform().m22(),
            "tamanho_extremidade": tamanho_ext,
            "id": id(self)
        }
    @classmethod
    def from_dict(cls, data):
        poly=cls.__new__(cls)
        poly._carregando=True
        x0 = data.get("x", 0)
        y0 = data.get("y", 0)
        pontos = [QPointF(p[0] - x0, p[1] - y0) for p in data["pontos"]]
        poly = cls([])
        poly.setZValue(data.get("z", 0))
        t = QTransform()
        t.scale(data.get("scale_x", 1.0), data.get("scale_y", 1.0))
        poly.setTransform(t)
        poly.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
        for pt in pontos:
            poly.add_point(pt)
        pen = QPen(QColor(data["color"]))
        pen.setWidthF(data["width"])
        pen.setStyle(data["style"])
        poly.setPen(pen)
        poly.estilo_ini = data.get("estilo_ini", "Nenhuma")
        poly.estilo_fim = data.get("estilo_fim", "Nenhuma")
        tamanho_ext = data.get("tamanho_extremidade", None)
        t = QTransform()
        t.scale(data.get("scale_x", 1.0), data.get("scale_y", 1.0))
        t.rotate(data.get("rotation", 0))
        poly.setTransform(t)

        QTimer.singleShot(0, lambda: poly.update_extremidades(tamanho_override=tamanho_ext))
        poly._carregando=True
        return poly


    def _get_ribbon(self):
        parent = self.scene().views()[0].parent() if self.scene().views() else None
        while parent:
            if hasattr(parent, "ribbon"):
                return parent.ribbon
            parent = parent.parent()
        return None
    def itemChange(self, change, value):
        # Apaga extremidades quando a polyline sai da cena
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene() is None:
            for ext in getattr(self, "_extremidades", []):
                if ext and ext.scene():
                    ext.scene().removeItem(ext)
            self._extremidades = []

        # Quando a posição do item muda, redesenha extremidades
        if change == QGraphicsItem.ItemPositionChange:
            # Atualiza as extremidades para a nova posição
            self.update_extremidades()

        return super().itemChange(change, value)
    
    def mouseDoubleClickEvent(self, event):
        self.setSelected(True)  # Força visibilidade dos handles
        super().mouseDoubleClickEvent(event)        

    def _adicionar_handle(self, point):
        handle = Handle(point.x(), point.y(), parent=None)
        handle.setParentItem(self)
        handle.setVisible(False)
        self.handles.append(handle)
        self.addToGroup(handle)

    def add_point(self, point):
        if not self.points:
            self.points.append(point)
            self._adicionar_handle(point)
            self.update_extremidades(tamanho_override=None)
            return

        last_point = self.points[-1]
        line = QGraphicsLineItem(last_point.x(), last_point.y(), point.x(), point.y())
        line.setPen(self.pen)
        line.setParentItem(self)
        self.addToGroup(line)
        self.lines.append(line)
        self.points.append(point)
        self._adicionar_handle(point)



    def setPen(self, pen):
        self.pen = pen
        for line in self.lines:
            line.setPen(pen)
        self.update_extremidades(tamanho_override=None)

    def update_extremidades(self, tamanho_override=None):
        # Remove extremidades anteriores
        if not getattr(self, "_carregando", False):
            for item in getattr(self, "_extremidades", []):
                if item and item.scene():
                    item.scene().removeItem(item)
            self._extremidades = []

        if len(self.points) < 2 or not self.scene():
            return

        p1 = self.points[0]
        p2 = self.points[-1]
        d1 = self.points[1] - self.points[0]
        d2 = self.points[-1] - self.points[-2]

        if d1.manhattanLength() == 0 or d2.manhattanLength() == 0:
            return

        dir_ini = d1 / d1.manhattanLength()
        dir_fim = d2 / d2.manhattanLength()

        estilo_ini = self.estilo_ini.replace(" Aberta", "")
        estilo_fim = self.estilo_fim.replace(" Aberta", "")
        tipo_ini = "aberta" if "Aberta" in self.estilo_ini else "fechada"
        tipo_fim = "aberta" if "Aberta" in self.estilo_fim else "fechada"

        # 🔹 Tamanho: prioridade -> argumento -> Ribbon -> padrão
        if tamanho_override is not None:
            tamanho = tamanho_override
        else:
            ribbon = self._get_ribbon()
            tamanho = getattr(ribbon, "tamanho_extremidade", 12) if ribbon else 12

        cor = self.pen.color()

        if estilo_ini != "Nenhuma":
            forma_ini = criar_extremidade(p1, -dir_ini, estilo_ini, tamanho=tamanho, cor=cor, tipo=tipo_ini)
            if forma_ini:
                forma_ini.setParentItem(self) 
                forma_ini.setZValue(self.zValue() + 1)
                self._extremidades.append(forma_ini)

        if estilo_fim != "Nenhuma":
            forma_fim = criar_extremidade(p2, dir_fim, estilo_fim, tamanho=tamanho, cor=cor, tipo=tipo_fim)
            if forma_fim:
                forma_fim.setParentItem(self) 
                forma_fim.setZValue(self.zValue() + 1)
                self._extremidades.append(forma_fim)


    def setSelected(self, selected):
        super().setSelected(selected)
        for handle in self.handles:
            handle.setVisible(selected)

    def serialize(self):
        return {
            "tipo": "polyline",
            "pontos": [(p.x(), p.y()) for p in self.points],
        }

    def finalizar(self):
        if self.show_handles:
            self.points = list(self.points)  # selar
            self.setFlag(self.ItemIsMovable, True)
            self.setFlag(self.ItemIsSelectable, True)

    def apply_pen(self, pen: QPen):
        if self.show_handles:
            self.pen = pen
            for line in self.lines:
                line.setPen(pen)



class EditableTextItem(QGraphicsTextItem):
    def __init__(self, text="Texto"):
        super().__init__(text)
        self.setFlags(
            QGraphicsTextItem.ItemIsSelectable |
            QGraphicsTextItem.ItemIsMovable
        )
        self.setTextInteractionFlags(Qt.TextEditorInteraction)  # já permite edição inicial
        self.setCursor(Qt.IBeamCursor)

    def mouseDoubleClickEvent(self, event):
            self.setTextInteractionFlags(Qt.TextEditorInteraction)
            super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        super().focusOutEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            scene = self.scene()
            parent = scene.parent() if scene else None
            if parent and getattr(parent, "snap_to_grid", False):
                spacing = parent.grid_spacing
                x = round(value.x() / spacing) * spacing
                y = round(value.y() / spacing) * spacing
                return QPointF(x, y)
        return super().itemChange(change, value)

class SvgObjectItem(QGraphicsItemGroup):
    def __init__(self, tag, parent=None):
        self.tag=tag
        super().__init__(parent)
        self.setFlag(self.ItemIsMovable)
        self.setFlag(self.ItemIsSelectable)
        # self.setHandlesChildEvents(False)  # ← importante para seleção funcionar
        self.setData(0, tag)
        self.path_items = []
        self.mode = "svg"  # <- para identificação no Ribbon
        self.pen = QPen(Qt.black, 2)
    def mouseDoubleClickEvent(self, event):
        self.setSelected(True)
        super().mouseDoubleClickEvent(event)

    def setSelected(self, selected):
        super().setSelected(selected)

        if selected:
            if not hasattr(self, '_selecionado_outline'):
                ret = self.boundingRect()
                self._selecionado_outline = QGraphicsRectItem(ret)
                self._selecionado_outline.setParentItem(self)
                self._selecionado_outline.setPen(QPen(Qt.blue, 1, Qt.DashLine))
                self._selecionado_outline.setBrush(QBrush(Qt.NoBrush))
                self._selecionado_outline.setZValue(1e6)  # garantir que fique por cima
        else:
            if hasattr(self, '_selecionado_outline'):
                self.scene().removeItem(self._selecionado_outline)
                del self._selecionado_outline


    def add_path(self, path_item):
        self.path_items.append(path_item)
        path_item.setParentItem(self)

    def apply_pen(self, pen):
        for item in self.path_items:
            item.setPen(pen)

    def apply_brush(self, brush):
        for item in self.path_items:
            item.setBrush(brush)
    
    def boundingRect(self):
        if not self.path_items:
            return QRectF()
        rect = self.path_items[0].mapToParent(self.path_items[0].boundingRect()).boundingRect()
        for item in self.path_items[1:]:
            mapped = item.mapToParent(item.boundingRect()).boundingRect()
            rect = rect.united(mapped)
        return rect

    def paint(self, painter, option, widget=None):
        # Não precisa desenhar diretamente, os filhos desenham por si
        pass

    def to_dict(self):
        children = []
        for child in self.childItems():
            if isinstance(child, QGraphicsPathItem):
                d = child.data(1) or self.path_to_svg_d(child.path())
                pen = child.pen()
                brush = child.brush()
                children.append({
                    "d": d,
                    "stroke": pen.color().name(),
                    "stroke-width": pen.widthF(),
                    "fill": brush.color().name() if brush.style() != Qt.NoBrush else "none"
                })

        return {
            "tipo": "svg",
            "tag": self.tag,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "paths": children,
            "z": self.zValue(),
            "scale_x": self.transform().m11(),
            "scale_y": self.transform().m22(),
            "rotation": self.rotation(),
            "id": id(self) 
            

        }

    @classmethod
    def from_dict(cls, data):
        grupo = cls(data.get("tag", ""))
        grupo.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
        grupo.setZValue(data.get("z", 0))  # ✅ aplique o valor da camada
        t = QTransform()
        t.scale(data.get("scale_x", 1.0), data.get("scale_y", 1.0))
        t.rotate(data.get("rotation", 0))
        grupo.setTransform(t)

        for item_data in data.get("paths", []):
            path_data = item_data.get("d")

            if not path_data:
                continue

            svg_path = parse_path(path_data)
            qt_path = QPainterPath()
            first = True

            for seg in svg_path:
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
            pen = QPen(QColor(item_data.get("stroke", "#000000")))
            pen.setWidthF(float(item_data.get("stroke-width", 1.0)))
            path_item.setPen(pen)

            fill = item_data.get("fill", "none")
            if fill != "none":
                path_item.setBrush(QBrush(QColor(fill)))
            else:
                path_item.setBrush(QBrush(Qt.transparent))

            grupo.add_path(path_item)

            
        return grupo

    def path_to_svg_d(self,qpath: QPainterPath) -> str:
        if qpath.data(1) is None:
            d = self.path_to_svg_d(path_item.path())
            path_item.setData(1, d)
        elements = []
        i = 0
        while i < qpath.elementCount():
            el = qpath.elementAt(i)
            if i == 0:
                elements.append(f"M {el.x} {el.y}")
            else:
                prev = qpath.elementAt(i - 1)
                elements.append(f"L {el.x} {el.y}")
            i += 1
        return " ".join(elements)

class EditableVariable(QGraphicsTextItem):
    def __init__(self, tag="", casas=2, digitos=4, parent=None):
        super().__init__(parent)
        self.tag = tag
        self.casas = casas
        self.digitos = digitos
        self.setFlags(
            QGraphicsTextItem.ItemIsSelectable |
            QGraphicsTextItem.ItemIsMovable
        )
        self.setFont(QFont("Microsoft Sans Serif", 12))
        self.setDefaultTextColor(Qt.black)
        self.atualizar_placeholder()

    def to_dict(self):
        return {
            "type": "variavel",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "tag": self.tag,
            "casas": self.casas,
            "digitos": self.digitos,
            "z": self.zValue(),
            "color": self.defaultTextColor().name(),
            "font": self.font().toString(),
            "id": id(self)
        }
    @classmethod
    def from_dict(cls, data):
        var = cls(
            tag=data.get("tag", ""),
            casas=data.get("casas", 2),
            digitos=data.get("digitos", 4)
        )
        var.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
        var.setZValue(data.get("z", 0))
        var.setDefaultTextColor(QColor(data.get("color", "#000000")))

        font_str = data.get("font", None)
        if font_str:
            f = QFont()
            f.fromString(font_str)
            var.setFont(f)

        var.atualizar_placeholder()
        return var
    
    def atualizar_placeholder(self):
        parte_int = "X" * self.digitos
        parte_dec = "X" * self.casas
        self.setPlainText(f"{parte_int}.{parte_dec}" if self.casas > 0 else parte_int)

    def atualizar_texto(self, valor):
        fmt = f"{{:>{self.digitos}.{self.casas}f}}"
        self.setPlainText(fmt.format(valor))

    def contextMenuEvent(self, event):
        menu = QMenu()
        prop_action = menu.addAction("Propriedades")
        action = menu.exec_(event.screenPos())
        if action == prop_action:
            from dialogs import VariableDialog
            dlg = VariableDialog(None, self.tag, self.casas, self.digitos)
            if dlg.exec_() == dlg.Accepted:
                data = dlg.get_data()
                self.tag = data["tag"]
                self.casas = data["casas"]
                self.digitos = data["digitos"]
                self.atualizar_placeholder()
    def mouseDoubleClickEvent(self, event):
        """Abre o diálogo de propriedades no duplo clique."""
        from dialogs import VariableDialog
        dlg = VariableDialog(None, self.tag, self.casas, self.digitos)
        if dlg.exec_() == dlg.Accepted:
            data = dlg.get_data()
            self.tag = data["tag"]
            self.casas = data["casas"]
            self.digitos = data["digitos"]
            self.atualizar_placeholder()
        super().mouseDoubleClickEvent(event)                


class SnapScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.snap_points = []

    def addItem(self, item):
        if sip.isdeleted(self):
            return
        try:
            super().addItem(item)
            if isinstance(item, EditableLine):
                self.snap_points.append(item.handle_start)
                self.snap_points.append(item.handle_end)
        except RuntimeError:
            pass  # evita quebra total se objeto foi deletado


    def removeItem(self, item):
        if sip.isdeleted(self):
            return
        try:
            super().removeItem(item)
            if isinstance(item, EditableLine):
                if item.handle_start in self.snap_points:
                    self.snap_points.remove(item.handle_start)
                if item.handle_end in self.snap_points:
                    self.snap_points.remove(item.handle_end)
        except RuntimeError:
            pass


    def clear(self):
        if sip.isdeleted(self):
            return
        self.snap_points.clear()
        try:
            super().clear()
        except RuntimeError:
            pass

    def get_snap_point(self, pos, threshold=10):
        for handle in self.snap_points[:]:  # faz cópia da lista para iterar com segurança
            try:
                if handle.scene() != self:
                    self.snap_points.remove(handle)
                    continue

                if (handle.pos() - pos).manhattanLength() < threshold:
                    return handle.pos()
            except RuntimeError:
                # Handle já foi deletado (wrapped C/C++ object), remove da lista
                self.snap_points.remove(handle)
        return pos



class SvgCanvas(QGraphicsView):
    mode_changed = pyqtSignal(str)
    texto_selecionado = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.scene = SnapScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setSceneRect(0, 0, 3000, 2000)
        self.setBackgroundBrush(QColor("#ffffa9"))
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.selection_rect = None
        self.selection_start = None
        self.selection_mode = "contain"  # ou "intersect", dependendo da direção
        self.grid_visible = False
        self.grid_spacing = 25  # você pode tornar isso configurável
        self.grid_group = None
        self.area_largura = 1920
        self.area_altura = 1080
        self.snap_to_grid = False

        self.mode = "selecionar"
        if not sip.isdeleted(self):
            self.mode_changed.emit(self.mode)
        self.scene.selectionChanged.connect(self.parent().atualizar_estilo_ativo)
        self.temp_line = None
        self.start_point = None
        self.historico = []
        self.futuro = []
        self._salvar_estado()  # Salva o estado inicial
        self.imagem_a_importar = None
        self.temp_shape = None
        self.start_point = None
        self.polyline_temp = None  # <- nova linha temporária para modo conector
        self.temp_line_conector = None
        self.tracking_line = None

        #NAVEGAÇÃO
        self.zoom_factor = 1.0
        self.zoom_min = 0.05
        self.zoom_max = 20.0
        self.zoom_mode = None
        self.zoom_start_point = None
        self.zoom_rect_item = None
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.mostrar_menu_contexto)
        shortcut_props = QShortcut(QKeySequence("Ctrl+P"), self)
        shortcut_props.activated.connect(lambda: self.abrir_propriedades(
            self.scene.selectedItems()[0] if self.scene.selectedItems() else None
        ))



    def snap_to_track(self, current):
        threshold = 5
        for item in self.scene.items():
            if isinstance(item, Handle):
                hx, hy = item.scenePos().x(), item.scenePos().y()
                if abs(current.x() - hx) < threshold:
                    return QPointF(hx, current.y()), 'v', hx  # Snap vertical
                if abs(current.y() - hy) < threshold:
                    return QPointF(current.x(), hy), 'h', hy  # Snap horizontal
        return current, None, None
    
    def _alinhar_objetos(self, direcao):
        itens = [i for i in self.scene.selectedItems()
            if isinstance(i, (QGraphicsItemGroup,EditableLine, EditableTextItem, QGraphicsPixmapItem,EditablePolyline,SvgObjectItem))]


        if len(itens) < 2:
            return

        if direcao in ["esquerda", "direita", "centro"]:
            if direcao == "esquerda":
                base = min(i.sceneBoundingRect().left() for i in itens)
                for i in itens:
                    dx = base - i.sceneBoundingRect().left()
                    i.moveBy(dx, 0)

            elif direcao == "direita":
                base = max(i.sceneBoundingRect().right() for i in itens)
                for i in itens:
                    dx = base - i.sceneBoundingRect().right()
                    i.moveBy(dx, 0)

            elif direcao == "centro":
                centros = [i.sceneBoundingRect().center().x() for i in itens]
                media = sum(centros) / len(centros)
                for i in itens:
                    dx = media - i.sceneBoundingRect().center().x()
                    i.moveBy(dx, 0)

        elif direcao in ["topo", "base", "meio"]:
            if direcao == "topo":
                base = min(i.sceneBoundingRect().top() for i in itens)
                for i in itens:
                    dy = base - i.sceneBoundingRect().top()
                    i.moveBy(0, dy)

            elif direcao == "base":
                base = max(i.sceneBoundingRect().bottom() for i in itens)
                for i in itens:
                    dy = base - i.sceneBoundingRect().bottom()
                    i.moveBy(0, dy)

            elif direcao == "meio":
                centros = [i.sceneBoundingRect().center().y() for i in itens]
                media = sum(centros) / len(centros)
                for i in itens:
                    dy = media - i.sceneBoundingRect().center().y()
                    i.moveBy(0, dy)

        self._salvar_estado()

    def _distribuir_objetos(self, direcao):
        itens = [i for i in self.scene.selectedItems()
                if isinstance(i, (EditableLine, EditableTextItem, QGraphicsPixmapItem,
                                EditablePolyline, SvgObjectItem))]

        if len(itens) < 3:
            return  # distribuição só faz sentido com 3 ou mais objetos

        # Ordenar por posição
        if direcao == "horizontal":
            itens.sort(key=lambda i: i.sceneBoundingRect().left())
            esquerda = itens[0].sceneBoundingRect().left()
            direita = itens[-1].sceneBoundingRect().right()
            largura_total = sum(i.sceneBoundingRect().width() for i in itens)
            espacamento = (direita - esquerda - largura_total) / (len(itens) - 1)

            x_atual = esquerda
            for item in itens:
                dx = x_atual - item.sceneBoundingRect().left()
                item.moveBy(dx, 0)
                x_atual += item.sceneBoundingRect().width() + espacamento

        elif direcao == "vertical":
            itens.sort(key=lambda i: i.sceneBoundingRect().top())
            topo = itens[0].sceneBoundingRect().top()
            base = itens[-1].sceneBoundingRect().bottom()
            altura_total = sum(i.sceneBoundingRect().height() for i in itens)
            espacamento = (base - topo - altura_total) / (len(itens) - 1)

            y_atual = topo
            for item in itens:
                dy = y_atual - item.sceneBoundingRect().top()
                item.moveBy(0, dy)
                y_atual += item.sceneBoundingRect().height() + espacamento

        self._salvar_estado()


    def _copiar_itens(self):
        self._clipboard = []
        for item in self.scene.selectedItems():
            if isinstance(item, EditableLine):
                self._clipboard.append({
                    "tipo": "linha",
                    "x1": item.handle_start.x(),
                    "y1": item.handle_start.y(),
                    "x2": item.handle_end.x(),
                    "y2": item.handle_end.y(),
                    "scale_x": self.transform().m11(),
                    "scale_y": self.transform().m22() 
                })
            elif isinstance(item, EditableTextItem):
                font = item.font()
                self._clipboard.append({
                    "tipo": "texto",
                    "texto": item.toPlainText(),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "fonte": font.family(),
                    "tamanho": font.pointSize(),
                    "negrito": font.bold(),
                    "italico": font.italic(),
                    "sublinhado": font.underline(),
                    "cor": item.defaultTextColor().name(),
                    "scale_x": self.transform().m11(),
                    "scale_y": self.transform().m22()                   
                })
            elif isinstance(item, SvgObjectItem):
                self._clipboard.append(item.to_dict())                

    def _colar_itens(self):
        if not hasattr(self, "_clipboard"):
            return

        for obj in self._clipboard:
            if obj["tipo"] == "linha":
                dx, dy = 10, 10
                linha = EditableLine(
                    QPointF(obj["x1"] + dx, obj["y1"] + dy),
                    QPointF(obj["x2"] + dx, obj["y2"] + dy),
                )
                linha.setZValue(z_topo_livre(self.scene))
                t = QTransform()
                t.scale(obj.get("scale_x", 1.0), obj.get("scale_y", 1.0))
                linha.setTransform(t)   
                self.scene.addItem(linha)
            elif obj["tipo"] == "texto":
                texto = EditableTextItem(obj["texto"])
                texto.setPos(QPointF(obj["x"] + 10, obj["y"] + 10))
                fonte = QFont(obj["fonte"], obj["tamanho"])
                fonte.setBold(obj["negrito"])
                fonte.setItalic(obj["italico"])
                fonte.setUnderline(obj["sublinhado"])
                texto.setFont(fonte)
                texto.setDefaultTextColor(QColor(obj["cor"]))
                texto.setZValue(z_topo_livre(self.scene))
                t = QTransform()
                t.scale(obj.get("scale_x", 1.0), obj.get("scale_y", 1.0))
                texto.setTransform(t)
                self.scene.addItem(texto)
            elif obj.get("tipo") == "svg":
                svg_item = SvgObjectItem(tag=obj.get("tag", ""), parent=None)
                svg_item.setZValue(z_topo_livre(self.scene))
                pos = obj.get("pos", [0, 0])
                svg_item.setPos(QPointF(*pos))
                for path_data in obj["paths"]:
                    d = path_data["d"]
                    svg_path = parse_path(d)
                    qt_path = QPainterPath()
                    first = True

                    for seg in svg_path:
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
                            qt_path.lineTo(end)  # ← substitua se quiser conversão real de arco

                    path_item = QGraphicsPathItem(qt_path)
                    path_item.setData(1, d)

                    pen = QPen(QColor(path_data.get("stroke", "#000000")))
                    pen.setWidthF(float(path_data.get("stroke-width", 1.0)))
                    path_item.setPen(pen)
                    t = QTransform()
                    t.scale(obj.get("scale_x", 1.0), obj.get("scale_y", 1.0))
                    svg_item.setTransform(t)
                    fill = path_data.get("fill", "none")
                    if fill != "none":
                        path_item.setBrush(QBrush(QColor(fill)))
                    else:
                        path_item.setBrush(QBrush(Qt.transparent))

                    svg_item.add_path(path_item)

                self.scene.addItem(svg_item)


        self._registrar_estado()
        self._salvar_estado()

    def _cortar_itens(self):
        self._copiar_itens()
        for item in self.scene.selectedItems():
            self.scene.removeItem(item)
        self._registrar_estado()
        self._salvar_estado()

    def desenhar_grid(self):
        # 🧽 Remove grupo antigo do grid (se existir)


        if self.grid_group and self.grid_group.scene() == self.scene:
            self.scene.removeItem(self.grid_group)
        self.grid_group = None

        if not self.grid_visible:
            return

        rect = QRectF(0, 0, self.area_largura, self.area_altura)
        spacing = self.grid_spacing
        cor_ponto = QColor("#cccccc")
        cor_ponto.setAlpha(80)

        self.grid_group = self.scene.createItemGroup([])

        for x in range(0, int(rect.width()), spacing):
            for y in range(0, int(rect.height()), spacing):
                ponto = QGraphicsEllipseItem(x - 0.5, y - 0.5, 1, 1)
                ponto.setBrush(cor_ponto)
                ponto.setZValue(-9999)
                #ponto.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
                self.grid_group.addToGroup(ponto)

        print("Desenhando grid...")
        print("Área:", self.area_largura, self.area_altura)
        print("Espaçamento:", self.grid_spacing)

    def keyPressEvent(self, event):
        if sip.isdeleted(self) or sip.isdeleted(self.scene):
            return
        
        item = self.scene.focusItem()
        if isinstance(item, QGraphicsTextItem):
                if event.key() == Qt.Key_Escape:
                    # Desativa modo de edição de texto, se houver foco
                    if isinstance(item, QGraphicsTextItem):
                        item.setTextInteractionFlags(Qt.NoTextInteraction)
                        self.scene.clearFocus()
                    
                    # 🔵 Desseleciona todos os itens
                    for obj in self.scene.selectedItems():
                        obj.setSelected(False)

                    # 🔵 Remove foco de qualquer item
                    self.scene.clearFocus()
                    self.clearFocus()
                    
                    return
                
                elif item.textInteractionFlags() == Qt.TextEditorInteraction:
                    super().keyPressEvent(event)
                    return
                

                                
        if event.matches(QKeySequence.Undo):
            print("CTRL+Z")
            self._desfazer()
        elif event.matches(QKeySequence.Redo):
            self._refazer()
            print("CTRL+Y")

        if event.key() == Qt.Key_S:
            self.set_mode("selecionar")
        elif event.key() == Qt.Key_L:
            self.set_mode("linha")
        elif event.key() == Qt.Key_Delete:
            for item in self.scene.selectedItems():
                self.scene.removeItem(item)
        elif event.key() == Qt.Key_T:
            self.set_mode("texto")
        elif event.key() == Qt.Key_C:
            self.set_mode("caminho")
        elif event.key() == Qt.Key_A:
            self.importar_svg()

        elif event.matches(QKeySequence.SelectAll):
                    self._selecionar_tudo()

        elif event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier) and event.key() == Qt.Key_A:
            self._inverter_selecao()

        # Ctrl+C → copiar
        elif event.matches(QKeySequence.Copy):
            print("CTRL+C")
            self._copiar_itens()

        # Ctrl+V → colar
        elif event.matches(QKeySequence.Paste):
            print("CTRL+V")
            self._colar_itens()

        elif event.key() in [Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter]:
            if self.polyline_temp:
                self.polyline_temp.finalizar()
                self.scene.addItem(self.polyline_temp)
                self.polyline_temp = None

                if self.temp_line_conector:
                    self.scene.removeItem(self.temp_line_conector)
                    self.temp_line_conector = None

                if self.tracking_line:
                    self.scene.removeItem(self.tracking_line)
                    self.tracking_line = None

                self.set_mode("selecionar")
                return



        else:
            if sip.isdeleted(self) or sip.isdeleted(self.scene):
                return
            super().keyPressEvent(event)
        


    def mousePressEvent(self, event):
        if sip.isdeleted(self) or sip.isdeleted(self.scene):
            return

        scene_pos = self.mapToScene(event.pos())
        item = self.scene.itemAt(scene_pos, self.transform())

        if self.mode == "selecionar" and event.button() == Qt.LeftButton:
            if isinstance(item, (Handle, QGraphicsTextItem)):
                super().mousePressEvent(event)
                return

            if item in self.scene.selectedItems():
                return

            self.selection_start = scene_pos
            self.selection_rect = QGraphicsRectItem()
            self.selection_rect.setRect(QRectF(scene_pos, scene_pos))
            self.selection_rect.setPen(QPen(Qt.blue, 1, Qt.DashLine))
            self.selection_rect.setBrush(Qt.transparent)
            self.selection_rect.setZValue(10000)
            self.scene.addItem(self.selection_rect)

        elif self.mode == "linha" and event.button() == Qt.LeftButton:
            point = self.mapToScene(event.pos())
            if self.snap_to_grid:
                spacing = self.grid_spacing
                point = QPointF(round(point.x() / spacing) * spacing,
                                round(point.y() / spacing) * spacing)
            self.start_point = point
            self.temp_line = QGraphicsLineItem()
            self.temp_line.setPen(QPen(Qt.gray, 1, Qt.DashLine))
            self.scene.addItem(self.temp_line)

        elif self.mode == "texto" and event.button() == Qt.LeftButton:
            pos = self.mapToScene(event.pos())
            if self.snap_to_grid:
                spacing = self.grid_spacing
                pos = QPointF(round(pos.x() / spacing) * spacing,
                            round(pos.y() / spacing) * spacing)

            texto = EditableTextItem("Texto")
            texto.setFont(QFont("Microsoft Sans Serif", 12))
            texto.setDefaultTextColor(QColor("black"))
            texto.setPos(pos)
            texto.setTextInteractionFlags(Qt.TextEditorInteraction)
            texto.setFlag(QGraphicsTextItem.ItemIsSelectable, True)
            texto.setFlag(QGraphicsTextItem.ItemIsMovable, True)
            texto.setCursor(Qt.SizeAllCursor)
            texto.setZValue(z_topo_livre(self.scene))
            self.scene.addItem(texto)
            texto.setSelected(True)

        elif self.mode == "inserir_imagem" and event.button() == Qt.LeftButton:
            self.selection_start = scene_pos
            self.selection_rect = QGraphicsRectItem(QRectF(self.selection_start, self.selection_start))
            self.selection_rect.setPen(QPen(Qt.red, 1, Qt.DashLine))
            self.selection_rect.setBrush(Qt.transparent)
            self.selection_rect.setZValue(10)
            self.scene.addItem(self.selection_rect)

        elif self.mode == "caminho" and event.button() == Qt.LeftButton:
            point = self.mapToScene(event.pos())
            if self.snap_to_grid:
                spacing = self.grid_spacing
                point = QPointF(round(point.x() / spacing) * spacing,
                                round(point.y() / spacing) * spacing)

            point = self.scene.get_snap_point(point)

            if self.polyline_temp:
                if event.modifiers() & Qt.ShiftModifier:
                    last = self.polyline_temp.points[-1]
                    delta = point - last
                    angle = math.atan2(delta.y(), delta.x())
                    snapped = round(angle / (math.pi / 4)) * (math.pi / 4)
                    length = math.hypot(delta.x(), delta.y())
                    dx = length * math.cos(snapped)
                    dy = length * math.sin(snapped)
                    point = last + QPointF(dx, dy)

                self.polyline_temp.add_point(point)
            else:
                self.polyline_temp = EditablePolyline(point)
                self.scene.addItem(self.polyline_temp)
                self.polyline_temp.update_extremidades()


        
        elif self.mode == "inserir_svg_path" and event.button() == Qt.LeftButton:
            pos = self.mapToScene(event.pos())
            if hasattr(self, "svg_temp_grupo") and self.svg_temp_grupo:
                self.svg_temp_grupo.setPos(pos)
                self.scene.addItem(self.svg_temp_grupo)
                del self.svg_temp_grupo
                self.set_mode("selecionar")

        elif self.mode == "variavel":
            from dialogs import VariableDialog
            dlg = VariableDialog(self)
            if dlg.exec_() == dlg.Accepted:
                data = dlg.get_data()
                var = EditableVariable(data["tag"], data["casas"], data["digitos"])
                scene_pos = self.mapToScene(event.pos())
                var.setPos(scene_pos)
                self.scene.addItem(var)
            self.modo_inserir = None
            return

        if self.zoom_mode == "retangulo" and event.button() == Qt.LeftButton:
                self.zoom_start_point = self.mapToScene(event.pos())
                self.zoom_rect_item = QGraphicsRectItem(QRectF(self.zoom_start_point, self.zoom_start_point))
                self.zoom_rect_item.setPen(QPen(Qt.blue, 1, Qt.DashLine))
                self.zoom_rect_item.setBrush(Qt.transparent)
                self.zoom_rect_item.setZValue(1000)
                self.scene.addItem(self.zoom_rect_item)
                return

        if hasattr(self.parent(), "atualizar_estilo_ativo"):
            self.parent().atualizar_estilo_ativo()



    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

        if self.mode == "linha" and self.temp_line and self.start_point:
            current = self.mapToScene(event.pos())

            if self.snap_to_grid:
                spacing = self.grid_spacing
                current = QPointF(round(current.x() / spacing) * spacing,
                                round(current.y() / spacing) * spacing)

            current = self.scene.get_snap_point(current)

            # SHIFT: trava ângulo
            if event.modifiers() & Qt.ShiftModifier:
                dx = current.x() - self.start_point.x()
                dy = current.y() - self.start_point.y()
                angle = math.atan2(dy, dx)
                snapped_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(dx, dy)
                current = self.start_point + QPointF(length * math.cos(snapped_angle),
                                                    length * math.sin(snapped_angle))

            # SNAP TRACK COM HANDLES
            if self.tracking_line:
                self.scene.removeItem(self.tracking_line)
                self.tracking_line = None

            tolerance = 6
            for handle in self.scene.snap_points:
                hpos = handle.scenePos()
                if abs(current.x() - hpos.x()) < tolerance:
                    current.setX(hpos.x())
                    self.tracking_line = QGraphicsLineItem(hpos.x(), hpos.y(), current.x(), current.y())
                    break
                if abs(current.y() - hpos.y()) < tolerance:
                    current.setY(hpos.y())
                    self.tracking_line = QGraphicsLineItem(hpos.x(), hpos.y(), current.x(), current.y())
                    break

            if self.tracking_line:
                pen = QPen(QColor("#000000"), 1, Qt.DotLine)
                self.tracking_line.setPen(pen)
                self.tracking_line.setZValue(-2)
                self.scene.addItem(self.tracking_line)

            self.temp_line.setLine(self.start_point.x(), self.start_point.y(), current.x(), current.y())
            self.end_point = current
        
        elif self.mode == "selecionar" and self.selection_rect:
            current_pos = self.mapToScene(event.pos())
            rect = QRectF(self.selection_start, current_pos).normalized()
            self.selection_rect.setRect(rect)

            # Atualiza o tipo da linha com base na direção
            if current_pos.x() >= self.selection_start.x():
                # Esquerda para direita → linha contínua
                pen = QPen(Qt.blue, 1, Qt.SolidLine)
            else:
                # Direita para esquerda → linha tracejada
                pen = QPen(Qt.blue, 1, Qt.DashLine)

            self.selection_rect.setPen(pen)
        elif self.mode == "inserir_imagem" and self.selection_rect:
            current = self.mapToScene(event.pos())
            rect = QRectF(self.selection_start, current).normalized()
            self.selection_rect.setRect(rect)
            
        elif self.mode == "caminho" and self.polyline_temp:
            current = self.mapToScene(event.pos())

            if self.snap_to_grid:
                spacing = self.grid_spacing
                current = QPointF(round(current.x() / spacing) * spacing,
                                round(current.y() / spacing) * spacing)

            current = self.scene.get_snap_point(current)
            last_point = self.polyline_temp.points[-1]

            # SHIFT: trava ângulo
            if event.modifiers() & Qt.ShiftModifier:
                delta = current - last_point
                angle = math.atan2(delta.y(), delta.x())
                snapped = round(angle / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(delta.x(), delta.y())
                dx = length * math.cos(snapped)
                dy = length * math.sin(snapped)
                current = last_point + QPointF(dx, dy)

            # Remove linha tracking anterior
            if self.tracking_line:
                self.scene.removeItem(self.tracking_line)
                self.tracking_line = None

            # Tracking colinear com Handles existentes
            tolerance = 6
            for handle in self.scene.snap_points:
                hpos = handle.scenePos()
                if abs(current.x() - hpos.x()) < tolerance:
                    current.setX(hpos.x())
                    self.tracking_line = QGraphicsLineItem(hpos.x(), hpos.y(), current.x(), current.y())
                    break
                if abs(current.y() - hpos.y()) < tolerance:
                    current.setY(hpos.y())
                    self.tracking_line = QGraphicsLineItem(hpos.x(), hpos.y(), current.x(), current.y())
                    break

            if self.tracking_line:
                pen = QPen(QColor("#000000"), 2, Qt.DotLine)
                self.tracking_line.setPen(pen)
                self.tracking_line.setZValue(-2)
                self.scene.addItem(self.tracking_line)
            # Linha temporária do segmento
            if self.temp_line_conector:
                self.scene.removeItem(self.temp_line_conector)
            self.temp_line_conector = QGraphicsLineItem(last_point.x(), last_point.y(), current.x(), current.y())
            self.temp_line_conector.setPen(QPen(Qt.gray, 1, Qt.DashLine))
            self.temp_line_conector.setZValue(0)
            self.scene.addItem(self.temp_line_conector)

        if self.zoom_mode == "retangulo" and self.zoom_rect_item:
                atual = self.mapToScene(event.pos())
                rect = QRectF(self.zoom_start_point, atual).normalized()
                self.zoom_rect_item.setRect(rect)
                return

       




    def mouseReleaseEvent(self, event):
        if sip.isdeleted(self) or sip.isdeleted(self.scene):
            return
        try:
            super().mouseReleaseEvent(event)
        except RuntimeError:
            return

        if self.mode == "linha" and self.temp_line and self.start_point and event.button() == Qt.LeftButton:
            if hasattr(self, "end_point") and self.end_point:
                rect = self.sceneRect()
                if not (rect.contains(self.start_point) and rect.contains(self.end_point)):
                    self.scene.removeItem(self.temp_line)
                else:
                    line = EditableLine(self.start_point, self.end_point)
                    line.setZValue(z_topo_livre(self.scene))
                    self.scene.addItem(line)
                    line.update_line(line.tamanho_extremidade)  # ✅ agora a cena já está atribuída corretamente

                self.scene.removeItem(self.temp_line)

            self.temp_line = None
            self.start_point = None
            self.end_point = None

            if self.tracking_line:
                self.scene.removeItem(self.tracking_line)
                self.tracking_line = None

        elif self.mode == "selecionar" and self.selection_rect:
            rect = self.selection_rect.rect()
            itens = []

            # Determina o modo de seleção com base na direção
            if self.selection_start.x() < rect.right():  # esquerda → direita
                # selecionar apenas itens totalmente contidos
                itens = [i for i in self.scene.items(rect) if rect.contains(i.sceneBoundingRect())]
            else:  # direita → esquerda
                # selecionar itens tocados
                itens = self.scene.items(rect)

            for item in self.scene.selectedItems():
                item.setSelected(False)

            for i in itens:
                i.setSelected(True)

            self.scene.removeItem(self.selection_rect)
            self.selection_rect = None
            self.selection_start = None

               # 🔔 Aqui notifica o MainWindow
            if hasattr(self.parent(), "atualizar_estilo_ativo"):
                self.parent().atualizar_estilo_ativo()

            for i in itens:
                i.setSelected(True)
                if isinstance(i, QGraphicsTextItem):
                    self.texto_selecionado.emit(i)

            if hasattr(self.parent(), "atualizar_estilo_ativo"):
                self.parent().atualizar_estilo_ativo()

        elif self.mode == "inserir_imagem" and self.selection_rect:

            rect = self.selection_rect.rect()
            imagem = QPixmap(self.imagem_a_importar)
                        
            scaled = imagem.scaled(int(rect.width()), int(rect.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = SnapPixmapItem(scaled)
            item.setPos(QPointF(rect.x(), rect.y()))
            item.setZValue(z_topo_livre(self.scene))
            self.scene.addItem(item)
            self.scene.removeItem(self.selection_rect)
            self.selection_rect = None
            self.imagem_a_importar = None
            self.set_mode("selecionar")

        if self.zoom_mode == "retangulo" and self.zoom_rect_item:
            rect = self.zoom_rect_item.rect()
            self.scene.removeItem(self.zoom_rect_item)
            self.zoom_rect_item = None
            self.zoom_mode = None
            self.setCursor(Qt.ArrowCursor)
            if rect.width() > 10 and rect.height() > 10:
                self.fitInView(rect, Qt.KeepAspectRatio)
            return






    def _restaurar_estado(self, estado):
        # Remove apenas itens de conteúdo (não o fundo)
        for item in self.scene.items():
            if isinstance(item, (EditableLine, EditableTextItem)):
                self.scene.removeItem(item)

        # Restaura os objetos do estado salvo
        for obj in estado:
            if obj["tipo"] == "linha":
                linha = EditableLine(
                    QPointF(obj["x1"], obj["y1"]),
                    QPointF(obj["x2"], obj["y2"]),
                )
                self.scene.addItem(linha)

            elif obj["tipo"] == "texto":
                texto = EditableTextItem(obj["texto"])
                texto.setPos(QPointF(obj["x"], obj["y"]))
                fonte = QFont(obj["fonte"], obj["tamanho"])
                fonte.setBold(obj["negrito"])
                fonte.setItalic(obj["italico"])
                fonte.setUnderline(obj["sublinhado"])
                texto.setFont(fonte)
                texto.setDefaultTextColor(QColor(obj["cor"]))
                self.scene.addItem(texto)
            elif obj["tipo"] == "imagem":
                import base64
                from PyQt5.QtCore import QBuffer
                imagem_bytes = base64.b64decode(obj["imagem_base64"])
                image = QPixmap()
                image.loadFromData(imagem_bytes, "PNG")
                item = SnapPixmapItem(image)
                item.setPos(QPointF(obj["x"], obj["y"]))
                self.scene.addItem(item)



        self.desenhar_grid()  # redesenha grade se visível

    def _desfazer(self):
        if len(self.historico) < 2:
            return
        estado_atual = self.historico.pop()
        self.futuro.append(estado_atual)
        estado_anterior = self.historico[-1]
        self._restaurar_estado(estado_anterior)

    def _refazer(self):
        if not self.futuro:
            return
        estado = self.futuro.pop()
        self.historico.append(estado)
        self._restaurar_estado(estado)


    def _reconstruir_a_partir_json(self, estado_json):
        from PyQt5.QtGui import QColor, QFont
        self.scene.clear()
        estado = json.loads(estado_json)
        for obj in estado:
            if obj["tipo"] == "linha":
                linha = EditableLine(QPointF(obj["x1"], obj["y1"]), QPointF(obj["x2"], obj["y2"]))
                self.scene.addItem(linha)
            elif obj["tipo"] == "texto":
                texto = EditableTextItem(obj["texto"])
                texto.setPos(QPointF(obj["x"], obj["y"]))
                fonte = QFont(obj["fonte"], obj["tamanho"])
                fonte.setBold(obj["negrito"])
                fonte.setItalic(obj["italico"])
                fonte.setUnderline(obj["sublinhado"])
                texto.setFont(fonte)
                texto.setDefaultTextColor(QColor(obj["cor"]))
                self.scene.addItem(texto)


    def _registrar_estado(self):
        estado = []
        for item in self.scene.items():
            if isinstance(item, EditableLine):
                estado.append({
                    "tipo": "linha",
                    "x1": item.handle_start.x(),
                    "y1": item.handle_start.y(),
                    "x2": item.handle_end.x(),
                    "y2": item.handle_end.y(),
                })
            elif isinstance(item, EditableTextItem):
                estado.append({
                    "tipo": "texto",
                    "texto": item.toPlainText(),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "fonte": item.font().family(),
                    "tamanho": item.font().pointSize(),
                    "negrito": item.font().bold(),
                    "italico": item.font().italic(),
                    "sublinhado": item.font().underline(),
                    "cor": item.defaultTextColor().name()
                })
            elif isinstance(item, QGraphicsPixmapItem):
                estado.append({
                    "tipo": "imagem",
                    "arquivo": "",  # opcional: manter caminho se quiser reabrir
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "largura": item.pixmap().width(),
                    "altura": item.pixmap().height(),
                    "imagem_base64": self._pixmap_to_base64(item.pixmap())
            })


        return estado  # ✅ agora retorna


    def _salvar_estado(self):
        estado_atual = self._registrar_estado()
        if self.historico and estado_atual == self.historico[-1]:
            return  # Evita salvar estado repetido

        self.historico.append(estado_atual)
        self.futuro.clear()

        if hasattr(self.parent(), "marcar_modificado"):
            self.parent().marcar_modificado(True)




    def set_area_util(self, largura, altura, cor_fundo=None):
        self.area_largura = largura   # ✅ armazena largura atual
        self.area_altura = altura     # ✅ armazena altura atual
        self.setSceneRect(0, 0, largura, altura)
        self.desenhar_grid()
        # Cor geral do fundo (fora da área útil)
        self.setBackgroundBrush(QColor("#FFFFA9"))
        
        # Remove bordas anteriores (se quiser múltiplos "Novos Projetos")
        for item in self.scene.items():
            if isinstance(item, QGraphicsRectItem) and item.zValue() == -10000:
                self.scene.removeItem(item)

        # Cria área útil delimitada (com z baixo para ir atrás dos objetos)
        area_util = QGraphicsRectItem(0, 0, largura, altura)
        area_util.setBrush(cor_fundo if cor_fundo else QColor("white"))
        area_util.setPen(QPen(Qt.gray, 0.5, Qt.DotLine))
        area_util.setZValue(-10000)
        self.scene.addItem(area_util)

    def set_grid_visible(self, visivel: bool):
        self.grid_visible = visivel
        self.desenhar_grid()
        
    def set_grid_spacing(self, spacing):
        spacing = max(5, min(200, spacing))  # garante intervalo permitido
        self.grid_spacing = spacing
        self.desenhar_grid()
        
    def set_mode(self, mode):
        self.mode = mode
        if sip.isdeleted(self) or sip.isdeleted(self.scene):
            return
        if not sip.isdeleted(self):
            self.mode_changed.emit(self.mode)
        if self.mode == "selecionar":
            self.setDragMode(QGraphicsView.NoDrag)

    def set_snap_to_grid(self, ativo: bool):
        self.snap_to_grid = ativo


    def _selecionar_tudo(self):
        for item in self.scene.items():
            if isinstance(item, (EditableLine, EditableTextItem, QGraphicsPixmapItem)):
                item.setSelected(True)

    def _inverter_selecao(self):
        for item in self.scene.items():
            if isinstance(item, (EditableLine, EditableTextItem, QGraphicsPixmapItem)):
                item.setSelected(not item.isSelected())

    def trazer_para_frente(self):
        for item in self.scene.selectedItems():
            item.setZValue(self._z_maximo() + 1)
        self._salvar_estado()

    def enviar_para_tras(self):
        for item in self.scene.selectedItems():
            item.setZValue(self._z_minimo() - 1)
        self._salvar_estado()

    def avancar_z(self):
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue() + 1)
        self._salvar_estado()

    def recuar_z(self):
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue() - 1)
        self._salvar_estado()

    def _z_maximo(self):
        return max((item.zValue() for item in self.scene.items()), default=0)

    def _z_minimo(self):
        return min((item.zValue() for item in self.scene.items() if item.zValue() > -9998), default=0)
    
    def rotacionar_selecionados(self, angulo):
        for item in self.scene.selectedItems():
            if item.flags() & QGraphicsItem.ItemIsMovable:
                item.setRotation(item.rotation() + angulo)
        self._registrar_estado()
        self._salvar_estado()

    def espelhar_horizontal(self):
        for item in self.scene.selectedItems():
            if item.flags() & QGraphicsItem.ItemIsMovable:
                origem = item.boundingRect().center()
                item.setTransformOriginPoint(origem)
                transform = item.transform()
                transform.scale(-1, 1)
                item.setTransform(transform)
        self._registrar_estado()
        self._salvar_estado()

    def espelhar_vertical(self):
        for item in self.scene.selectedItems():
            if item.flags() & QGraphicsItem.ItemIsMovable:
                origem = item.boundingRect().center()
                item.setTransformOriginPoint(origem)
                transform = item.transform()
                transform.scale(1, -1)
                item.setTransform(transform)
        self._registrar_estado()
        self._salvar_estado()

    def wheelEvent(self, event):
        if sip.isdeleted(self) or sip.isdeleted(self.scene):
            return

        if event.modifiers() & Qt.ControlModifier:
            # Pan vertical
            delta_y = int(event.angleDelta().y() / 8)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta_y)
            return

        # Fator de zoom
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15

        # Posição do mouse antes do zoom
        old_pos = self.mapToScene(event.pos())

        # Aplicar zoom
        self.scale(zoom_factor, zoom_factor)

        # Posição após o zoom
        new_pos = self.mapToScene(event.pos())

        # Ajustar para manter a posição original
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())



    def zoom_mais(self):
        if self.zoom_factor < self.zoom_max:
            self.zoom_factor *= 1.2
            self.scale(1.2, 1.2)

    def zoom_menos(self):
        if self.zoom_factor > self.zoom_min:
            self.zoom_factor /= 1.2
            self.scale(1 / 1.2, 1 / 1.2)

    def ajustar_a_tela(self):
        self.zoom_factor = 1.0
        self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def iniciar_zoom_por_janela(self):
        self.zoom_mode = "retangulo"
        self.setCursor(Qt.CrossCursor)

    def _pixmap_to_base64(self, pixmap):
        import base64
        from PyQt5.QtCore import QBuffer, QByteArray
        buffer = QBuffer()
        buffer.open(QBuffer.WriteOnly)
        pixmap.save(buffer, "PNG")
        return base64.b64encode(buffer.data()).decode("utf-8")
    
    def importar_svg(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar SVG", "", "SVG Files (*.svg)")
        if not caminho:
            return

        ns = {"svg": "http://www.w3.org/2000/svg"}
        tree = ET.parse(caminho)
        root = tree.getroot()

        paths = root.findall(".//svg:path", ns)
        print("Encontrados", len(paths), "paths")

        tag, ok = QInputDialog.getText(self, "Definir TAG", "Digite a TAG do objeto:")
        if not ok or not tag.strip():   
            return

        grupo = SvgObjectItem(tag.strip())

        
        for path_elem in paths:
            d = path_elem.attrib.get("d")
            if not d:
                continue

            svg_path_obj = parse_path(d)
            qt_path = QPainterPath()
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
                    # Fallback simples
                    qt_path.lineTo(end)

            # Detectar se o path parece fechado (primeiro ponto ≈ último ponto)
            if not qt_path.isEmpty():
                start_point = qt_path.elementAt(0)
                end_point = qt_path.elementAt(qt_path.elementCount() - 1)

                start = QPointF(start_point.x, start_point.y)
                end = QPointF(end_point.x, end_point.y)

                if (start - end).manhattanLength() > 0.001:  # tolerância
                    qt_path.closeSubpath()
                    
            stroke = path_elem.attrib.get("stroke", "#000000")
            stroke_width = float(path_elem.attrib.get("stroke-width", 1.0))
            pen = QPen(QColor(stroke))
            pen.setWidthF(stroke_width)
            item = QGraphicsPathItem(qt_path)
            item.setPen(pen)
            item.setData(1, d)

            # Verifica se há preenchimento no estilo SVG (ou permite aplicar depois via simulador)
            fill_color = path_elem.attrib.get("fill", "none")
            if fill_color != "none":
                item.setBrush(QBrush(QColor(fill_color)))
            else:
                item.setBrush(QBrush(Qt.transparent))

            item.setParentItem(grupo)
            grupo.add_path(item)

        self.svg_temp_grupo = grupo
        self.set_mode("inserir_svg_path")



    def mostrar_menu_contexto(self, pos):
        global_pos = self.mapToGlobal(pos)
        selecionados = self.scene.selectedItems()
        menu = QMenu()

        if len(selecionados) > 1:
            acao_agrupar = menu.addAction("🔗 Agrupar")
            acao_agrupar.triggered.connect(lambda: self.agrupar_itens(selecionados))
        elif len(selecionados) == 1 and isinstance(selecionados[0], QGraphicsItemGroup):
            grupo = selecionados[0]
            filhos = grupo.childItems()
            
            # Impede desagrupar grupo com exatamente 1 SVG
            if len(filhos) == 1 and isinstance(filhos[0], SvgObjectItem):
                print("❌ Grupo contém apenas 1 SVG. Não pode ser desagrupado.")
                return

            # Permite se for um grupo com múltiplos SVGs (ou outros tipos mistos)
            acao_desagrupar = menu.addAction("🔓 Desagrupar")
            acao_desagrupar.triggered.connect(lambda: self.desagrupar_itens(grupo))


        menu.addSeparator()
        acao_props = menu.addAction("ℹ️ Propriedades")
        acao_props.triggered.connect(lambda: self.abrir_propriedades(selecionados[0] if selecionados else None))

        menu.exec_(global_pos)

    def agrupar_itens(self, itens):
        grupo = self.scene.createItemGroup(itens)
        grupo.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable)
        bounding_center = grupo.boundingRect().center()
        scene_center = grupo.mapToScene(bounding_center)
        grupo.setTransformOriginPoint(grupo.boundingRect().center())
        grupo.setPos(scene_center - bounding_center)

        # Desseleciona tudo e seleciona apenas o grupo
        for item in itens:
            item.setSelected(False)

        grupo.setSelected(False)


    def desagrupar_itens(self, grupo):
        if isinstance(grupo, SvgObjectItem):
            QMessageBox.warning(self, "Desagrupar não permitido", "❌ Não é permitido desagrupar um objeto único.")
            return

        filhos = grupo.childItems()

        # Bloqueia caso o grupo tenha apenas 1 item que é um SvgObjectItem
        if len(filhos) == 1 and isinstance(filhos[0], SvgObjectItem):
            QMessageBox.warning(self, "Desagrupar não permitido", "❌ Não é permitido desagrupar um objeto único.")
            return
        
        if isinstance(grupo, EditablePolyline):
            data = grupo.to_dict()
            pontos = [QPointF(x, y) for x, y in data.get("pontos", [])]
            pen = grupo.pen

            for i in range(len(pontos) - 1):
                p1, p2 = pontos[i], pontos[i + 1]
                linha = EditableLine(p1, p2)
                linha.setPen(pen)
                linha.estilo_ini = "Nenhuma"
                linha.estilo_fim = "Nenhuma"
                linha.update_line()
                self.scene.addItem(linha)
                linha.setSelected(True)

            self.scene.removeItem(grupo)
            return

        self.scene.destroyItemGroup(grupo)

        for item in filhos:
            item.setSelected(False)  # remove a seleção visual


    def abrir_propriedades(self, obj=None):
        """
        Abre as propriedades para o objeto selecionado ou para a tela.
        """
        if obj is None:
            # Nenhum objeto → propriedades da tela
            self.abrir_propriedades_tela()
            return

        # Tratamento especial para cada tipo
        if isinstance(obj, EditableVariable):
            from dialogs import VariableDialog
            dlg = VariableDialog(self, obj.tag, obj.casas, obj.digitos)
            if dlg.exec_() == dlg.Accepted:
                data = dlg.get_data()
                obj.tag = data["tag"]
                obj.casas = data["casas"]
                obj.digitos = data["digitos"]
                obj.atualizar_placeholder()
            return

        if isinstance(obj, (SvgObjectItem, QGraphicsTextItem)):
            self.abrir_propriedades_objeto(obj)
            return

        # Padrão: abre o diálogo genérico
        dlg = PropriedadesDialog(objeto=obj, parent=self)
        dlg.exec_()

            
    def abrir_propriedades_tela(self):
        # Aqui você pode abrir um QDialog com:
        # - Cor de fundo
        # - Resolução (largura x altura)
        # - Tipo (Tela, Faceplate)
        ...

    def abrir_propriedades_objeto(self, obj):
        # Abre um QDialog com abas:
        # - Estilo: fonte, cor, espessura
        # - Modificadores: campos como
        #     • tipo: [fill, piscar, texto, cor do texto]
        #     • expressão lógica: (ex: pressao > 2)
        #     • valor A / valor B
        ...


    def ativar_modo_inserir_variavel(self):
        self.mode = "variavel"

    def abrir_propriedades(self, obj=None):
        dlg = PropriedadesDialog(objeto=obj, parent=self)
        dlg.exec_()

    def inserir_variavel(self):
        from dialogs import VariableDialog
        dlg = VariableDialog(self)
        if dlg.exec_() == dlg.Accepted:
            data = dlg.get_data()
            var = EditableVariable(
                tag=data["tag"],
                casas=data["casas"],
                digitos=data["digitos"]
            )
            var.setPos(100, 100)  # posição inicial padrão
            self.scene.addItem(var)


def z_topo_livre(scene):
    z_max = 0
    for item in scene.items():
        if item.zValue() > z_max:
            z_max = item.zValue()
    return z_max + 1

def criar_extremidade(pos, direcao, estilo, tamanho=12, cor=Qt.black, tipo="fechada"):
    ang = math.atan2(direcao.y(), direcao.x())

    if estilo == "Seta":
        if tipo == "fechada":
            # Seta sólida (triângulo)
            p1 = pos + QPointF(-math.cos(ang + 0.4) * tamanho, -math.sin(ang + 0.4) * tamanho)
            p2 = pos + QPointF(-math.cos(ang - 0.4) * tamanho, -math.sin(ang - 0.4) * tamanho)
            polygon = QPolygonF([pos, p1, p2])
            item = QGraphicsPolygonItem(polygon)
            item.setPen(QPen(cor))
            item.setBrush(QBrush(cor))
            return item
        else:
            # Seta aberta (">" com 2 linhas)
            p1 = pos + QPointF(-math.cos(ang + 0.4) * tamanho, -math.sin(ang + 0.4) * tamanho)
            p2 = pos + QPointF(-math.cos(ang - 0.4) * tamanho, -math.sin(ang - 0.4) * tamanho)
            linha1 = QGraphicsLineItem(QLineF(pos, p1))
            linha2 = QGraphicsLineItem(QLineF(pos, p2))
            linha1.setPen(QPen(cor, 1.5))
            linha2.setPen(QPen(cor, 1.5))

            # Envolve as duas linhas em um grupo (para tratar como 1)
            grupo = QGraphicsItemGroup()
            grupo.addToGroup(linha1)
            grupo.addToGroup(linha2)
            return grupo

    elif estilo == "Círculo":
        item = QGraphicsEllipseItem(pos.x() - tamanho/2, pos.y() - tamanho/2, tamanho, tamanho)
        item.setPen(QPen(cor))
        item.setBrush(QBrush(cor))
        return item

    elif estilo == "Quadrado":
        item = QGraphicsRectItem(pos.x() - tamanho/2, pos.y() - tamanho/2, tamanho, tamanho)
        item.setPen(QPen(cor))
        item.setBrush(QBrush(cor))
        return item

    return None



def criar_seta(pos, direcao, tamanho=8):
    ang = math.atan2(direcao.y(), direcao.x())
    p1 = pos + QPointF(-math.cos(ang + 0.5) * tamanho, -math.sin(ang + 0.5) * tamanho)
    p2 = pos + QPointF(-math.cos(ang - 0.5) * tamanho, -math.sin(ang - 0.5) * tamanho)
    polygon = QPolygonF([pos, p1, p2])
    item = QGraphicsPolygonItem(polygon)
    item.setBrush(QBrush(Qt.black))
    item.setPen(QPen(Qt.black))
    return item


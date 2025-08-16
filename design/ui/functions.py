# functions.py (SIMULAÇÃO) — versão com MERGE TBR->MBR e correções de SVG/Text
import json
import os
import sys
from copy import deepcopy

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QTransform
from PyQt5.QtWidgets import QFileDialog

# ---------------- MERGE CONFIG ----------------
VISUAL_FIELDS = {
    "content",
    "bold",
    "italic",
    "underline",
    "size",
    "stroke",
    "stroke_width",
    "stroke-width",
    "fill",
    "font",
    "font_family",
    "font_size",
    "text_align",
    "transform",
    "rotation",
    "scale",
    "x",
    "y",
    "w",
    "h",
    "shear_x",
    "shear_y",
    "items",
    "d",
}


def _identity_key(obj):
    if isinstance(obj, dict):
        for k in ("id", "tag", "nome", "name"):
            if k in obj:
                return (k, obj[k])
    return None


def deep_merge_preserve_visual(tbr, mbr):
    if isinstance(tbr, dict) and isinstance(mbr, dict):
        result = deepcopy(mbr)
        for k, v in tbr.items():
            if k not in result:
                result[k] = deepcopy(v)
            else:
                if k in VISUAL_FIELDS:
                    result[k] = deepcopy(v)
                else:
                    result[k] = deep_merge_preserve_visual(v, result[k])
        return result
    if isinstance(tbr, list) and isinstance(mbr, list):
        mbr_index = {}
        for item in mbr:
            ko = _identity_key(item)
            if ko is not None:
                mbr_index[ko] = item
        merged_list = []
        usados = set()
        for t_item in tbr:
            ko = _identity_key(t_item)
            if ko is not None and ko in mbr_index:
                merged_list.append(deep_merge_preserve_visual(t_item, mbr_index[ko]))
                usados.add(ko)
            else:
                merged_list.append(deepcopy(t_item))
        for m_item in mbr:
            ko = _identity_key(m_item)
            if ko is not None and ko in usados:
                continue
            merged_list.append(deepcopy(m_item))
        return merged_list
    return deepcopy(mbr)


# ---------------- Import Designer classes ----------------
designer_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "BRICSSIM_designer")
)
if designer_path not in sys.path:
    sys.path.append(designer_path)

from canvas import (
    EditableLine,
    EditablePolyline,
    EditableTextItem,
    EditableVariable,
    SvgObjectItem,
)


# ---------------- Utils ----------------
def qpath_to_svg_d(qpath):
    if qpath.isEmpty():
        return ""
    elementos = []
    for i in range(qpath.elementCount()):
        el = qpath.elementAt(i)
        if i == 0:
            elementos.append(f"M {el.x:.2f} {el.y:.2f}")
        else:
            elementos.append(f"L {el.x:.2f} {el.y:.2f}")
    return " ".join(elementos)


def _extrair_tela_tbr(canvas, nome_tela):
    tbr = getattr(canvas, "_tbr_full", None)
    if not isinstance(tbr, dict):
        return None

    if "telas" in tbr and isinstance(tbr["telas"], list):
        for t in tbr["telas"]:
            if t.get("nome") == nome_tela:
                return t
        if tbr["telas"]:
            return tbr["telas"][0]

    base = {
        "nome": nome_tela,
        "objetos": tbr.get("objetos") or tbr.get("items", []),
    }
    if "canvas_size" in tbr:
        base["canvas_size"] = tbr["canvas_size"]
    if "cor_fundo" in tbr:
        base["cor_fundo"] = tbr["cor_fundo"]
    return base


# ---------------- Save/Load ----------------
def salvar_simulacao(main_window):
    from canvas_simulator import TouchAreaItem

    caminho, _ = QFileDialog.getSaveFileName(
        None, "Salvar Simulação", "", "Simulação BRICSSIM (*.sbr)"
    )
    if not caminho:
        return

    projeto = {"telas": []}
    for i in range(main_window.tab_widget.count()):
        canvas = main_window.tab_widget.widget(i)
        nome_tela = main_window.tab_widget.tabText(i)
        dados_tela = {"nome": nome_tela, "objetos": []}
        for item in canvas.scene.items():
            if hasattr(item, "to_dict"):
                try:
                    dados_tela["objetos"].append(item.to_dict())
                except Exception as e:
                    print(f"Erro ao salvar item: {e}")
        projeto["telas"].append(dados_tela)

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(projeto, f, ensure_ascii=False, indent=4)


def carregar_design(canvas):
    from canvas_simulator import TouchAreaItem

    caminho, _ = QFileDialog.getOpenFileName(
        None, "Carregar Design", "", "Tela BRICSSIM (*.tbr)"
    )
    if not caminho:
        return
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    canvas._tbr_full = dados  # <<< guarda o TBR no canvas
    _montar_cena(canvas, dados, carregar_valores=False)


def salvar_modelo(main_window):
    from canvas_simulator import TouchAreaItem

    caminho, _ = QFileDialog.getSaveFileName(
        None, "Salvar Modelo", "", "Modelo BRICSSIM (*.mbr)"
    )
    if not caminho:
        return

    projeto = {"telas": []}

    for i in range(main_window.tab_widget.count()):
        canvas = main_window.tab_widget.widget(i)
        nome_tela = main_window.tab_widget.tabText(i)
        dados = {
            "nome": nome_tela,
            "objetos": [],
            "canvas_size": {
                "largura": getattr(canvas, "area_largura", 600),
                "altura": getattr(canvas, "area_altura", 400),
            },
            "cor_fundo": (
                canvas.cor_fundo.name() if hasattr(canvas, "cor_fundo") else "#ffffff"
            ),
        }
        print(
            "SALVAMENTO:Cor de fundo:",
            getattr(canvas, "cor_fundo", QColor("#ffffff")).name(),
        )

        for item in canvas.scene.items():
            if isinstance(item, SvgObjectItem):
                transform = item.transform()
                sx = transform.m11()
                sy = transform.m22()
                if abs(sx) < 0.01:
                    sx = 1.0
                if abs(sy) < 0.01:
                    sy = 1.0

                d = {
                    "type": "svg",
                    "tag": item.data(0),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "z": item.zValue(),
                    "scale_x": sx,
                    "scale_y": sy,
                    "rotation": item.rotation(),
                    "paths": [],
                }
                if hasattr(item, "_mods") and isinstance(item._mods, list):
                    d["mods"] = item._mods

                children = item.childItems()
                for idx, child in enumerate(children):
                    if hasattr(child, "path"):
                        stroke = (
                            child.pen().color().name()
                            if hasattr(child, "pen")
                            else "#000000"
                        )
                        stroke_width = (
                            child.pen().widthF() if hasattr(child, "pen") else 1
                        )
                        fill = (
                            child.brush().color().name()
                            if hasattr(child, "brush")
                            and child.brush().style() != Qt.NoBrush
                            else "none"
                        )

                        # >>> ORDEM DE PREFERÊNCIA PARA 'd' <<<
                        d_value = None

                        # 1) d original guardado no child (setData(1, d))
                        try:
                            if hasattr(child, "data"):
                                d_value = child.data(1) or None
                        except Exception:
                            d_value = None

                        # 2) (Opcional) d vindo de alguma estrutura original no item
                        if d_value is None:
                            try:
                                orig = getattr(item, "_original_paths", None)
                                if isinstance(orig, list) and idx < len(orig):
                                    d_value = orig[idx].get("d", None)
                            except Exception:
                                pass

                        # 3) Fallback (AVISO: perde curvas!)
                        if not d_value:
                            try:
                                d_value = qpath_to_svg_d(child.path())
                            except Exception:
                                d_value = ""
                            # Opcional: logar para você rastrear quando acontecer
                            print(
                                "⚠️ Fallback qpath_to_svg_d usado (curvas podem ser perdidas) — tag:",
                                item.data(0),
                            )

                        d["paths"].append(
                            {
                                "d": d_value,
                                "stroke": stroke,
                                "stroke-width": stroke_width,
                                "fill": fill,
                            }
                        )

                dados["objetos"].append(d)

            elif isinstance(item, EditableTextItem):
                f = item.font()
                d = {
                    "type": "text",
                    "content": item.toPlainText(),
                    "x": float(item.pos().x()),
                    "y": float(item.pos().y()),
                    "font": f.family(),
                    "size": int(f.pointSize() if f.pointSize() > 0 else 12),
                    "bold": bool(f.bold()),
                    "italic": bool(f.italic()),
                    "underline": bool(f.underline()),
                    "color": item.defaultTextColor().name(),
                    "scale_x": item.transform().m11(),
                    "scale_y": item.transform().m22(),
                }
                if hasattr(item, "_mods") and isinstance(item._mods, list):
                    d["mods"] = item._mods
                dados["objetos"].append(d)

            elif isinstance(item, EditableVariable):
                d = item.to_dict() if hasattr(item, "to_dict") else {}
                item.lei = getattr(item, "lei", "").strip()
                d["lei"] = item.lei if item.lei else ""
                item.controle = getattr(item, "controle", {})
                d["controle"] = {
                    "variavel_controlada": item.controle.get(
                        "variavel_controlada", False
                    ),
                    "Kp": item.controle.get("Kp", 1.0),
                    "Ki": item.controle.get("Ki", 0.0),
                    "Kd": item.controle.get("Kd", 0.0),
                    "modo": item.controle.get("modo", "MAN"),
                    "sp_tracking": item.controle.get("sp_tracking", False),
                    "pv_tag": item.controle.get("pv_tag", f"{item.tag}.pv"),
                    "sp_tag": item.controle.get("sp_tag", f"{item.tag}.sp"),
                    "mv_tag": item.controle.get("mv_tag", f"{item.tag}.mv"),
                    "acao": item.controle.get("acao", "direta"),
                    "mv_write_tag": item.controle.get("mv_write_tag", ""),
                    "pv_min": item.controle.get("pv_min", 0.0),
                    "pv_max": item.controle.get("pv_max", 100.0),
                }

                d["alarmes"] = getattr(
                    item, "alarmes", {"HH": None, "H": None, "L": None, "LL": None}
                )
                # --- DIGITAL: persistir tipo, mapa e bits PV0..PV5 ---
                from singleton import VariaveisGlobais

                vg = VariaveisGlobais()

                tipo = str(vg.get(f"{item.tag}.tipo", "ANA") or "ANA").upper()
                d["tipo"] = tipo  # facilita detectar no carregamento

                if tipo.startswith("D"):
                    bits = {
                        f"PV{i}": int(vg.get(f"{item.tag}.PV{i}", 0) or 0)
                        for i in range(6)
                    }
                    d["digital"] = {
                        "map": vg.get(f"{item.tag}.digi.map", {}) or {},
                        "bits": bits,
                        "hidden_offcanvas": bool(
                            getattr(item, "hidden_offcanvas", False)
                        ),
                        "pulse": int(
                            vg.get(f"{item.tag}.digi.pulse", 1) or 1
                        ),  # <<< novo
                    }
                    d["visible"] = False

                if hasattr(item, "_mods") and isinstance(item._mods, list):
                    d["mods"] = item._mods
                dados["logicas"] = vg.get("logicas", {}) or {}
                dados["iq"] = VariaveisGlobais().get("iq", []) or []
                dados["analog_eq"] = vg.get("analog.eq", []) or []
                dados["analog_tree"] = vg.get("analog.tree", {"root": []})
                dados["objetos"].append(d)

            elif hasattr(item, "to_dict"):
                try:
                    d = item.to_dict()
                    if hasattr(item, "_mods") and isinstance(item._mods, list):
                        d["mods"] = item._mods
                    dados["objetos"].append(d)
                except Exception as e:
                    print(f"⚠️ Não foi possível salvar item: {e}")

            elif item.__class__.__name__ == "TouchAreaItem":
                try:
                    dados["objetos"].append(item.to_dict())
                except Exception as e:
                    print(f"⚠️ Não foi possível salvar TouchAreaItem: {e}")

        # --- MERGE TBR->MBR por tela ---
        tbr_base = _extrair_tela_tbr(canvas, nome_tela)
        if isinstance(tbr_base, dict):
            dados = deep_merge_preserve_visual(tbr_base, dados)

        projeto["telas"].append(dados)

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(projeto, f, ensure_ascii=False, indent=4)


def carregar_modelo(main_window):
    from canvas_simulator import SimuladorCanvas, TouchAreaItem

    caminho, _ = QFileDialog.getOpenFileName(
        None, "Carregar Modelo", "", "Modelo BRICSSIM (*.mbr)"
    )
    if not caminho:
        return
    with open(caminho, "r", encoding="utf-8") as f:
        projeto = json.load(f)

    main_window.tab_widget.clear()
    main_window.sidebar.clear()

    telas = projeto.get("telas", None)
    if telas is None:
        nome_tela = os.path.splitext(os.path.basename(caminho))[0]
        novo_canvas = SimuladorCanvas(main_window, main_window=main_window)
        novo_canvas._garantir_variaveis_filhas()
        _montar_cena(novo_canvas, projeto, carregar_valores=False)
        main_window.tab_widget.addTab(novo_canvas, nome_tela)
        main_window.sidebar.addItem(nome_tela)
        return

    for tela in telas:
        nome_tela = tela.get("nome", "Sem Nome")
        dados_tela = tela
        novo_canvas = SimuladorCanvas(main_window, main_window=main_window)
        _montar_cena(novo_canvas, dados_tela, carregar_valores=False)
        main_window.tab_widget.addTab(novo_canvas, nome_tela)
        main_window.sidebar.addItem(nome_tela)

    if main_window.tab_widget.count() > 0:
        main_window.sidebar.setCurrentRow(0)


def carregar_simulacao(canvas):
    from canvas_simulator import TouchAreaItem

    caminho, _ = QFileDialog.getOpenFileName(
        None, "Carregar Simulação", "", "Simulação BRICSSIM (*.sbr)"
    )
    if not caminho:
        return
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    _montar_cena(canvas, dados, carregar_valores=True)


def _montar_cena(canvas, dados, carregar_valores=False):
    from canvas_simulator import TouchAreaItem, _capturar_baseline

    canvas.scene.clear()
    canvas.variaveis.clear()
    canvas_size = dados.get("canvas_size", [1920, 1080])
    if isinstance(canvas_size, dict):
        largura = float(canvas_size.get("largura", 1920))
        altura = float(canvas_size.get("altura", 1080))
    elif isinstance(canvas_size, list) and len(canvas_size) >= 2:
        largura = float(canvas_size[0])
        altura = float(canvas_size[1])
    else:
        largura, altura = 1920, 1080

    cor_fundo = QColor(dados.get("cor_fundo", "#a53838"))
    canvas.set_area_util(largura, altura, cor_fundo)

    objetos = dados.get("objetos") or dados.get("items", [])

    for obj in objetos:
        tipo = obj.get("type")
        item = None
        max_z = max((it.zValue() for it in canvas.scene.items()), default=0)
        if tipo == "linha":
            item = EditableLine.from_dict(obj)
            if hasattr(item, "setFlags"):
                item.setFlags(item.flags() | item.ItemIsSelectable)  # selecionável
                item.setFlag(item.ItemIsMovable, False)
            if hasattr(item, "handle_start"):
                item.handle_start.setVisible(False)
                item.handle_start.setFlag(item.handle_start.ItemIsMovable, False)
                item.handle_start.setFlag(item.handle_start.ItemIsSelectable, False)
            if hasattr(item, "handle_end"):
                item.handle_end.setVisible(False)
                item.handle_end.setFlag(item.handle_end.ItemIsMovable, False)
                item.handle_end.setFlag(item.handle_end.ItemIsSelectable, False)

        elif tipo == "caminho":
            item = EditablePolyline.from_dict(obj)
            if hasattr(item, "setFlags"):
                item.setFlags(item.flags() | item.ItemIsSelectable)
                item.setFlag(item.ItemIsMovable, False)
            if hasattr(item, "handles"):
                for h in item.handles:
                    h.setVisible(False)
                    h.setFlag(h.ItemIsMovable, False)
                    h.setFlag(h.ItemIsSelectable, False)

        elif tipo == "variavel":
            if obj.get("tag", "").endswith(".sp") or obj.get("tag", "").endswith(".mv"):
                if not obj.get("adicionar_visualmente", False):
                    continue
            item = EditableVariable.from_dict(obj)

            item.lei = obj.get("lei", "").strip() or ""
            item.alarmes = obj.get(
                "alarmes",
                {
                    "HH": float("inf"),
                    "H": float("inf"),
                    "L": float("-inf"),
                    "LL": float("-inf"),
                },
            )
            # --- DIGITAL: restaurar atributos e esconder off-canvas ---
            from singleton import VariaveisGlobais

            vg = VariaveisGlobais()
            vg.set("iq", dados.get("iq", []) or [])
            if "analog_tree" in dados:
                vg.set("analog.tree", dados.get("analog_tree", {"root": []}))
            elif vg.get("analog.tree") is None:
                vg.set("analog.tree", {"root": []})

            tipo_json = str(obj.get("tipo", "")).upper()
            if tipo_json.startswith("D"):
                vg.set(f"{item.tag}.tipo", "DIG")

                digital = obj.get("digital", {}) or {}

                # mapa de rótulos / visibilidade
                dig_map = digital.get("map")
                if dig_map:
                    vg.set(f"{item.tag}.digi.map", dig_map)

                # bits PV0..PV5
                bits = digital.get("bits", {}) or {}
                for i in range(6):
                    if f"PV{i}" in bits:
                        vg.set(f"{item.tag}.PV{i}", int(bits[f"PV{i}"]))

                pulse = digital.get("pulse", None)
                if pulse is not None:
                    vg.set(f"{item.tag}.digi.pulse", 1 if int(pulse or 0) else 0)
                # manter fora da área útil, invisível e inselecionável
                if digital.get("hidden_offcanvas", True):
                    item.setVisible(False)
                    item.setAcceptedMouseButtons(Qt.NoButton)
                    item.setFlag(item.ItemIsSelectable, False)
                    item.setFlag(item.ItemIsMovable, False)
                    item.setFlag(item.ItemIsFocusable, False)
                    item.setEnabled(False)
                    item.hidden_offcanvas = True
                    off_x = getattr(canvas, "area_largura", 1920) + 5000
                    off_y = getattr(canvas, "area_altura", 1080) + 5000
                    item.setPos(off_x, off_y)

            controle_raw = obj.get("controle", {})
            item.controle = {
                "variavel_controlada": controle_raw.get("variavel_controlada", False),
                "Kp": controle_raw.get("Kp", 1.0),
                "Ki": controle_raw.get("Ki", 0.0),
                "Kd": controle_raw.get("Kd", 0.0),
                "modo": controle_raw.get("modo", "MAN"),
                "sp_tracking": controle_raw.get("sp_tracking", False),
                "pv_tag": controle_raw.get("pv_tag", f"{item.tag}.pv"),
                "sp_tag": controle_raw.get("sp_tag", f"{item.tag}.sp"),
                "mv_tag": controle_raw.get("mv_tag", f"{item.tag}.mv"),
                "acao": controle_raw.get("acao", "direta"),
                "mv_write_tag": controle_raw.get("mv_write_tag", ""),
                "pv_min": controle_raw.get("pv_min", 0.0),
                "pv_max": controle_raw.get("pv_max", 100.0),
            }
            vg.set(f"{item.tag}.controle", item.controle)

            if item.controle.get("variavel_controlada", False):
                item.sp_tag = item.controle.get("sp_tag", f"{item.tag}.sp")
                item.mv_tag = item.controle.get("mv_tag", f"{item.tag}.mv")
                item.controle["pv_tag"] = item.controle.get("pv_tag", "")

            if getattr(canvas.main_window, "modo_modelo", False):
                item.setPlainText(getattr(item, "tag", ""))
            elif carregar_valores and "valor_atual" in obj:
                try:
                    item.setPlainText(str(obj["valor_atual"]))
                except Exception:
                    pass
            # >>> NOVO: hidratar alarmes do JSON e publicar no VG
            alarmes_json = obj.get("alarmes")
            if alarmes_json is not None:
                item.alarmes = alarmes_json
                VariaveisGlobais().set(f"{item.tag}.alarmes", dict(alarmes_json))
            else:
                # default consistente
                item.alarmes = {"HH": None, "H": None, "L": None, "LL": None}

            # (se você já inicializa controle/faixa, pode também publicar aqui)
            VariaveisGlobais().inicializar_tag(item.tag)
            log_file = dados.get("logicas", {}) or {}
            if "analog_eq" in dados:
                vg.set("analog.eq", dados.get("analog_eq", []) or [])
                # merge simples (arquivo vence)
            existentes = vg.get("logicas", {}) or {}
            existentes.update(log_file)
            vg.set("logicas", existentes)

            # (opcional) inicializa o passo atual para cada lógica
            import re

            for nome, spec in log_file.items():
                passos = spec.get("passos", []) or []
                if not passos:
                    continue
                m = re.match(r"\s*(P\d+)\s*:", str(passos[0]))
                if m:
                    vg.set(f"grafcet.{nome}.step", m.group(1))

            canvas.variaveis.append(item)

        elif tipo == "svg":
            try:
                item = SvgObjectItem.from_dict(obj)
                paths_src = obj.get("paths", [])
                children = item.childItems()
                for idx, child in enumerate(children):
                    try:
                        if idx < len(paths_src):
                            d_orig = paths_src[idx].get("d", "")
                            if hasattr(child, "setData"):
                                child.setData(1, d_orig)  # canal 1 = 'd' original
                    except Exception:
                        pass
                item.setPos(obj.get("x", 0), obj.get("y", 0))
                item.setZValue(obj.get("z", 0))
                sx = obj.get("scale_x", 1.0)
                sy = obj.get("scale_y", 1.0)
                if abs(sx) < 0.01:
                    sx = 1.0
                if abs(sy) < 0.01:
                    sy = 1.0
                transform = QTransform().scale(sx, sy)
                item.setTransform(transform)
                rotation = obj.get("rotation", 0.0)
                item.setRotation(rotation)
                canvas.scene.addItem(item)
                print(
                    f"[SVG] tag: {obj.get('tag')}, pos: ({obj.get('x')}, {obj.get('y')}), rot: {rotation}, scale: ({sx}, {sy})"
                )
            except Exception as e:
                print(f"[ERRO SVG] {e}")
                continue

        elif tipo == "text":
            item = EditableTextItem(obj.get("content", ""))
            item.setTextInteractionFlags(Qt.NoTextInteraction)  # nunca editável
            item.setFlag(item.ItemIsSelectable, True)  # selecionável
            item.setFlag(item.ItemIsMovable, False)  # não movível
            item.setPos(obj.get("x", 0), obj.get("y", 0))
            font = QFont(obj.get("font", "Arial"), obj.get("size", 12))
            font.setBold(obj.get("bold", False))
            font.setItalic(obj.get("italic", False))
            font.setUnderline(obj.get("underline", False))
            item.setZValue(max_z + 1)
            item.setFont(font)
            item.setDefaultTextColor(QColor(obj.get("color", "#000000")))
            t = QTransform()
            t.scale(obj.get("scale_x", 1.0), obj.get("scale_y", 1.0))
            item.setTransform(t)

        elif tipo == "touch_area":
            item = TouchAreaItem.from_dict(obj, canvas.main_window)
            item.setFlag(item.ItemIsSelectable, True)  # selecionável
            item.setFlag(item.ItemIsMovable, True)
            item.setPos(obj.get("x", 0), obj.get("y", 0))

        if item:
            _capturar_baseline(item)
            if hasattr(item, "setFlags"):
                flags = item.flags() & ~item.ItemIsMovable
                if not isinstance(
                    item, (EditableVariable, SvgObjectItem)
                ) and not hasattr(item, "toPlainText"):
                    flags &= ~item.ItemIsSelectable
                item.setFlags(flags)
            item._mods = obj.get("mods", [])
            canvas.scene.addItem(item)
            item._mods = obj.get("mods", [])

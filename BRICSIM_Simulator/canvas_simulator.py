import json
import random
import os
import sys
import math
import numpy as np
import control
import scipy.signal as signal
import re
from trends import open_trends
from faceplate import open_faceplate
from controle import aplicar_controle_PID


from PyQt5.QtWidgets import (QGraphicsView, QGraphicsScene,QDialog,QVBoxLayout,QLabel,QPushButton,
                             QDoubleSpinBox, QMessageBox,QLineEdit,QHBoxLayout,QComboBox,QCheckBox,
                             QPlainTextEdit,QTabWidget,QWidget,QGraphicsRectItem,QStyleOptionGraphicsItem,
                             QColorDialog,QMenu,QGroupBox,QListWidget,QGraphicsItem,QGridLayout,QInputDialog,
                             QSplitter,QListWidgetItem,QFormLayout
                             )
 
from PyQt5.QtCore import Qt, QTimer, QPointF,QRectF 
from PyQt5.QtGui import QColor, QFont,QPainter,QBrush,QPen,QCursor
from singleton import VariaveisGlobais
# 🔹 Garante que a pasta do Designer está no caminho de import
designer_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "BRICSSIM_designer"))
if designer_path not in sys.path:
    sys.path.append(designer_path)
# 🔹 Importa as classes direto do Designer
from canvas import EditableLine, EditablePolyline, EditableVariable, SvgObjectItem

from functions import salvar_simulacao, carregar_design, carregar_simulacao, carregar_modelo

def _capturar_baseline(item):
    if getattr(item, "_baseline_ok", False):
        return
    # item
    if hasattr(item, "toPlainText"):
        item._base_text = item.toPlainText()
        item._base_color = item.defaultTextColor()
    if hasattr(item, "pen"):
       # try: item._base_pen = item.pen()
        #except: item._base_pen = None
        pass
    if hasattr(item, "brush"):
        try: item._base_brush = item.brush()
        except: item._base_brush = None
    item._base_opacity = item.opacity()

    # filhos (SVG decomposto)
    try:
        for ch in getattr(item, "childItems", lambda: [])():
            if hasattr(ch, "pen"):
                try: ch._base_pen = ch.pen()
                except: ch._base_pen = None
            if hasattr(ch, "brush"):
                try: ch._base_brush = ch.brush()
                except: ch._base_brush = None
    except Exception:
        pass

    item._baseline_ok = True
# --- Apagar tudo que começa com prefixo no VariaveisGlobais (inclui históricos, se existirem) ---
def _vg_del_prefix(vg, prefix: str):
    removed = 0
    # stores principais
    for attr in ("_data", "_store", "store", "data"):
        d = getattr(vg, attr, None)
        if isinstance(d, dict):
            for k in list(d.keys()):
                if isinstance(k, str) and k.startswith(prefix):
                    del d[k]; removed += 1
    # históricos (se houver)
    for attr in ("_hist", "hist", "_history", "history"):
        h = getattr(vg, attr, None)
        if isinstance(h, dict):
            for k in list(h.keys()):
                if isinstance(k, str) and k.startswith(prefix):
                    del h[k]
    return removed

# === HELPER UNIVERSAL ===
def ensure_analog_tag(vg, base_tag: str, tipo_padrao="Temperatura"):
    """
    Cria TAG.pv / TAG.sp / TAG.mv (lowercase) e configura defaults.
    Idempotente: pode chamar várias vezes.
    """
    if not base_tag:
        return
    base = str(base_tag).strip().upper()

    # cria as séries (listas) no histórico
    if hasattr(vg, "inicializar_tag"):
        vg.inicializar_tag(base)  # cria TAG.pv/.sp/.mv no vg.dados

    # garanta 1º valor (senão a série fica vazia)
    for campo in ("pv", "sp", "mv"):
        if not vg.hist(f"{base}.{campo}"):
            vg.set(f"{base}.{campo}", 0.0)

    # marca tipo e controles mínimos
    vg.set(f"{base}.tipo", "ANA")
    conf = vg.get(f"{base}.controle", {}) or {}
    conf.setdefault("tipo", tipo_padrao)
    conf.setdefault("variavel_controlada", False)
    conf.setdefault("pv_min", 0.0)
    conf.setdefault("pv_max", 100.0)
    conf.setdefault("acao", "direta")
    vg.set(f"{base}.controle", conf)

def _purge_tag(vg, tag: str):
    """Remove TUDO da tag: variáveis, mapas, controle, alarmes, históricos, IQ, Grafcet."""
    if not tag: return
    # 1) chaves com prefixo TAG.
    _vg_del_prefix(vg, f"{tag}.")
    # 2) grafcet: remove lógicas da tag e steps
    log = vg.get("logicas", {}) or {}
    changed = False
    for nome in list(log.keys()):
        if nome == tag or nome.startswith(f"{tag}_"):
            log.pop(nome, None); changed = True
            _vg_del_prefix(vg, f"grafcet.{nome}.")
            try:  # alguns runtimes guardam step fora do dict
                _vg_del_prefix(vg, f"grafcet.{nome}.step")
            except Exception:
                pass
    if changed:
        vg.set("logicas", log)
    # 3) IQ: remove blocos com base==tag e equações cujo LHS é TAG.*
    iq = vg.get("iq", []) or []
    iq2 = []
    for b in iq:
        base = str(b.get("base", "") or "")
        if base == tag:
            continue  # descarta bloco inteiro
        eqs = []
        for ln in (b.get("equacoes", []) or []):
            lhs = ln.split("=", 1)[0].strip() if "=" in ln else ""
            if lhs.startswith(f"{tag}."):
                continue
            eqs.append(ln)
        b = dict(b); b["equacoes"] = eqs
        iq2.append(b)
    vg.set("iq", iq2)


def _iq_tokens(expr: str):
    return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_\.]*\b", expr))

def _iq_to_py(expr: str):
    s = expr
    s = s.replace("&&", " and ").replace("&", " and ")
    s = s.replace("||", " or ").replace("|", " or ")
    s = s.replace("!", " not ")
    s = s.replace("^", " != ")   # xor
    return s

def _as_bool(v):
    try: return bool(int(v))
    except Exception: return bool(v)

# === IQ: avaliação numérica/booleana com ADC/DAC ===
def _eval_iq_equation_numeric(lhs_key: str, rhs_expr: str, base: str, prev_cache: dict):
    vg = VariaveisGlobais()
    import re

    # 1) detecta se o LHS é digital (para histórico) E faz "self‑hold" para QUALQUER LHS
    is_pv_digital = bool(re.match(r".*\.PV\d+$", lhs_key))

    s = str(rhs_expr)
    s = s.replace("&&", " and ").replace("&", " and ")
    s = s.replace("||", " or ").replace("|", " or ")
    s = s.replace("!", " not ").replace("^", " != ")

    # embrulha tokens com ponto em G("...")
    def _wrap_dot_tokens(text):
        out, i, n, in_s, in_d = [], 0, len(text), False, False
        while i < n:
            c = text[i]
            if c == "'" and not in_d: in_s = not in_s; out.append(c); i += 1; continue
            if c == '"' and not in_s: in_d = not in_d; out.append(c); i += 1; continue
            if in_s or in_d:
                out.append(c); i += 1; continue
            m = re.match(r'([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)', text[i:])
            if m:
                tok = m.group(1)
                out.append(f'G("{tok}")')
                i += len(tok)
            else:
                out.append(c); i += 1
        return ''.join(out)

    rhs_py = _wrap_dot_tokens(s)

    # --------- 2) Pré-carrega nomes "locais" da base no ambiente (PV0..PV15, RUN, SP, MV, perm/mv_iq/mv_final) ---------
    base_names = [f"PV{i}" for i in range(16)] + ["RUN","SP","MV","perm_ok","mv_iq","mv_final","sp_eff"]
    env = {"True": 1, "False": 0, "dt": 1.0}

    def G(key, default=0):
        # 3) self‑hold: se a RHS referir o PRÓPRIO LHS, devolve valor anterior (selagem)
        if key == lhs_key:
            hist = prev_cache.get(lhs_key, [])
            if hist:
                return hist[-1]
            return vg.get(lhs_key, default)

        v = vg.get(key, default)
        if isinstance(v, str):
            try: return float(v.strip())
            except Exception: return default
        return v

    def BOOL(x):
        try: return 1.0 if bool(int(x or 0)) else 0.0
        except Exception: return 1.0 if bool(x) else 0.0
    def SEL(cond,a,b): return a if BOOL(cond) >= 0.5 else b
    def DAC(cond,on_val,off_val): return on_val if BOOL(cond) >= 0.5 else off_val
    def RAMP(prev,target,dt_local,tau):
        alpha = dt_local/(tau+dt_local) if (tau+dt_local)!=0 else 1.0
        try: pf=float(prev)
        except: pf=0.0
        try: tf=float(target)
        except: tf=pf
        return pf + alpha*(tf-pf)

    env.update({"G":G,"BOOL":BOOL,"SEL":SEL,"DAC":DAC,"RAMP":RAMP})

    # torna acessíveis PV0, PV1, RUN etc. SEM ponto, qualificados pela base, se houver
    if base:
        for name in base_names:
            env[name] = G(f"{base}.{name}", 0)

    # avalia
    try:
        val = eval(rhs_py, {"__builtins__": {}}, env)
    except Exception:
        val = 0.0

    # normaliza
    if isinstance(val, bool):
        return 1 if val else 0
    try:
        return float(val)
    except Exception:
        return 1 if bool(val) else 0



def _tick_iq(canvas, prev_cache: dict):
    """
    Espera vg['iq'] = [
      {"nome":"BOMBA01_LATCH_IQ","base":"BOMBA01",
       "equacoes":[ "BOMBA01.PV5 = PV0 | (PV5 & !PV1)",
                    "TRIP1 = TI001.pv > 90",
                    "FC003.mv_final = 0 if !BOMBA001.PV5 else FC003.mv_final" ]}
    ]
    Retorna as chaves escritas neste ciclo.
    """
    vg = VariaveisGlobais()
    wrote = set()
    blocos = vg.get("iq", []) or []
    import re

    for bloco in blocos:
        base = str(bloco.get("base","") or "")
        for ln in (bloco.get("equacoes", []) or []):
            line = str(ln).strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            lhs, rhs = [p.strip() for p in line.split("=", 1)]

            # resolve LHS sem base → prefixa
            if "." not in lhs:
                if not base:
                    continue
                lhs = f"{base}.{lhs}"

            # avalia RHS (numérico/booleano)
            val = _eval_iq_equation_numeric(lhs, rhs, base, prev_cache)

            # decide tipo de escrita: digital (PVx ou .perm_ok) vs analógica
            is_digital = bool(re.match(r".*\.PV\d+$", lhs))
            is_perm    = lhs.endswith(".perm_ok")

            if is_digital or is_perm:
                out = 1 if (1 if int(bool(val)) else 0) else 0
                _ensure_iq_tag_exists(canvas, lhs) if is_digital else None
            else:
                # analógico/DAC: grava float
                try:
                    out = float(val)
                except Exception:
                    out = 0.0

            vg.set(lhs, out)
            wrote.add(lhs)


    hist = prev_cache.get(lhs, [])
    if re.match(r".*\.PV\d+$", lhs):
        cur = 1 if int(vg.get(lhs, 0) or 0) else 0
        prev_cache[lhs] = (hist + [cur])[-3:]
    else:
        # salva o valor numérico para self-hold de variáveis como RUN
        try: cur = float(vg.get(lhs, 0) or 0)
        except: cur = 0.0
        prev_cache[lhs] = (hist + [cur])[-3:]


    return wrote


def _ensure_iq_tag_exists(canvas, lhs_key: str):
    """
    Se a equação usa 'BASE.PVx', garanta que a BASE exista como variável DIG.
    """
    base = lhs_key.split(".", 1)[0] if "." in lhs_key else lhs_key
    if not base:
        return
    vg = VariaveisGlobais()
    tipo = (vg.get(f"{base}.tipo", "") or "").upper()
    if tipo != "DIG":
        try:
            canvas.inserir_variavel_digital_modelo(base)
        except Exception:
            # fallback: só inicializa no singleton
            vg.set(f"{base}.tipo", "DIG")
            for i in range(6):
                vg.set(f"{base}.PV{i}", int(vg.get(f"{base}.PV{i}", 0) or 0))

import re

def _iq_eval_and_set(vg, lhs: str, rhs_expr: str, dt: float = 1.0):
    """
    Executa uma sentença IQ: <lhs> = <rhs_expr>
      - Converte tokens com ponto (ex.: TI001.pv) em G("TI001.pv")
      - Aceita '!' como NOT (vira ' not ')
      - ADC: bool -> 0/1; DAC: numérico -> float
      - Se lhs tem ponto, grava direto na tag (vg.set("TAG.xxx", valor))
      - Integra com árbitro via .mv_final / .mv_iq / .perm_ok
    """
    # ---------- helpers usados dentro do eval ----------
    def G(key, default=0):
        try:
            v = vg.get(key, default)
            if isinstance(v, str):
                s = v.strip()
                if s == "": return default
                try: return float(s)
                except: return default
            return v
        except:
            return default

    def BOOL(x):
        try:    return 1.0 if bool(int(x or 0)) else 0.0
        except: return 1.0 if bool(x) else 0.0

    def SEL(cond, a, b):  # ternário numérico
        return a if BOOL(cond) >= 0.5 else b

    def DAC(cond, on_val, off_val):  # alias semântico
        return on_val if BOOL(cond) >= 0.5 else off_val

    def RAMP(prev, target, dt_local, tau):
        alpha = dt_local / (tau + dt_local) if (tau + dt_local) != 0 else 1.0
        try: prev_f = float(prev)
        except: prev_f = 0.0
        try: tgt_f = float(target)
        except: tgt_f = prev_f
        return prev_f + alpha * (tgt_f - prev_f)

    env = {
        "G": G, "BOOL": BOOL, "SEL": SEL, "DAC": DAC, "RAMP": RAMP,
        "dt": dt, "True": 1, "False": 0,
    }

    # ---------- pré-processamento do RHS ----------
    rhs = str(rhs_expr)

    # troca '!' por ' not ' (sem quebrar '!=')
    rhs = re.sub(r'!\s*(?!=)', ' not ', rhs)

    # envolve tokens com ponto em G("...") — ex.: TI001.pv  -> G("TI001.pv")
    # evita capturar números com ponto e já ignora tokens dentro de aspas
    def _wrap_tokens(text):
        out, i, n = [], 0, len(text)
        in_s, in_d = False, False
        while i < n:
            c = text[i]
            if c == "'" and not in_d: in_s = not in_s; out.append(c); i += 1; continue
            if c == '"' and not in_s: in_d = not in_d; out.append(c); i += 1; continue
            if in_s or in_d:
                out.append(c); i += 1; continue
            # tenta capturar token com ponto do tipo NAME.NAME[.NAME]*
            m = re.match(r'([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)', text[i:])
            if m:
                token = m.group(1)
                # não embrulhar chamadas (ex.: G("x").alguma_coisa) já com aspas
                out.append(f'G("{token}")')
                i += len(token)
            else:
                out.append(c); i += 1
        return ''.join(out)

    rhs_py = _wrap_tokens(rhs)

    # ---------- avalia RHS com ambiente restrito ----------
    try:
        val = eval(rhs_py, {"__builtins__": {}}, env)
    except Exception as e:
        # print(f"[IQ] erro avaliando '{rhs_expr}' => '{rhs_py}': {e}")
        return

    # ---------- normaliza tipo de saída ----------
    if isinstance(val, bool):
        out = 1.0 if val else 0.0
    else:
        try: out = float(val)
        except: out = 1.0 if bool(val) else 0.0

    # ---------- grava no VariaveisGlobais ----------
    lhs = lhs.strip()
    vg.set(lhs, out)  # com ou sem ponto o vg aceita chave "lhs" como string

def _tick_eqs_analogicas(canvas, dt=0.2):
    from singleton import VariaveisGlobais
    import math, random, numpy as np, builtins, uuid
    vg = VariaveisGlobais()

    tree = vg.get("analog.tree", None)
    flat = vg.get("analog.eq", None)

    # --- MIGRAÇÃO: se não há tree, mas há lista antiga, crie pasta "Importado"
    if tree is None:
        children = []
        if isinstance(flat, list) and flat:
            def _to_entry(s):
                if isinstance(s, dict) and "lhs" in s:
                    return {"id": str(uuid.uuid4()), "type":"equation",
                            "name": s.get("nome", s.get("lhs","(eq)")),
                            "lhs": s.get("lhs",""), "rhs": s.get("rhs",""),
                            "enabled": bool(s.get("habilitado", True))}
                if isinstance(s, str) and "=" in s:
                    L,R = [p.strip() for p in s.split("=",1)]
                    if "." not in L: L = f"{L}.pv"
                    return {"id": str(uuid.uuid4()), "type":"equation",
                            "name": L, "lhs": L, "rhs": R, "enabled": True}
                return None
            for s in flat:
                e = _to_entry(s)
                if e: children.append(e)
        tree = {"root":[{"id": str(uuid.uuid4()), "type":"folder",
                         "name":"Importado", "children": children}]}
        vg.set("analog.tree", tree)

    # --- achatar a árvore na ordem visual (DFS)
    def _flatten(nodes, out):
        for n in (nodes or []):
            if n.get("type") == "equation":
                if n.get("enabled", True) and n.get("lhs") and n.get("rhs"):
                    out.append((n.get("name") or n.get("lhs"), n["lhs"], n["rhs"]))
            elif n.get("type") == "folder":
                _flatten(n.get("children",[]), out)

    eqs = []
    _flatten((tree or {}).get("root", []), eqs)
    if not eqs:
        return set()

    # --- bucketização por dinâmica (usa tipo do .controle da TAG base)
    ordem = getattr(canvas, "TIPO_ORDEM", ["Temperatura","Nível","Pressão","Vazão","logica"])
    def _tipo(tag_base: str):
        conf = vg.get(f"{tag_base}.controle", {}) or {}
        return conf.get("tipo", "Temperatura")
    buckets = {t: [] for t in ordem}
    outros = []

    pairs = []
    for (nome, lhs, rhs) in eqs:
        L = (lhs or "").strip()
        R = (rhs or "").strip()
        if not L or not R: continue
        if "." not in L: L = f"{L}.pv"
        base = L.split(".",1)[0]
        t = _tipo(base)
        rec = (L, R, nome)
        pairs.append(rec)
        (buckets[t] if t in buckets else outros).append(rec)

    # --- ambiente seguro
    def _env_for(lhs_key: str):
        def G(key, default=0.0):
            if key == lhs_key:  # auto-dependência pega valor anterior
                h = vg.hist(lhs_key)
                if h:
                    try: return float(h[-1])
                    except: return h[-1]
            v = vg.get(key, default)
            try: return float(v)
            except: return v

        def passado(key, k=1, default=0.0):
            try: return float(vg.passado(key, int(k), default))
            except: return default

        def CLAMP(x,a,b):
            try:
                x=float(x); a=float(a); b=float(b)
                if a>b: a,b=b,a
                return a if x<a else (b if x>b else x)
            except: return x
        import random as _rnd    
        def NOISE(amp=1.0, mode="uniform"):
            """
            Ruído de média ~0.
            - mode="uniform": U[-amp, +amp]
            - mode="gauss":   N(0, amp)  (amp = desvio padrão)
            """
            a = float(amp)
            if mode == "gauss":
                return _rnd.gauss(0.0, a)
            return (_rnd.random()*2.0 - 1.0) * a

        def NOISE_LP(key: str, amp=1.0, tau=3.0):
            """
            Ruído 'suave' (passa-baixa) com memória por chave.
            Ex.: NOISE_LP("AMB", 0.2, 5.0)
            """
            st_key = f"_noise.{key}"
            prev = vg.get(st_key, 0.0)
            inov = NOISE(amp, "gauss")
            alpha = float(dt) / (float(tau) + float(dt))
            val = prev + alpha * (inov - prev)
            vg.set(st_key, val)
            return val
        
        def RAMP(prev,target,dt_local,tau):
            try:
                prev=float(prev); target=float(target)
                dt_local=float(dt_local); tau=float(tau)
                alpha = dt_local/(tau+dt_local) if (tau+dt_local)!=0 else 1.0
                return prev + alpha*(target-prev)
            except: return target

        return {
            "__builtins__": None,
            "math": math, "np": np, "random": random,
            "min": builtins.min, "max": builtins.max, "abs": builtins.abs,
            "round": builtins.round, "float": builtins.float, "int": builtins.int, "len": builtins.len,
            "G": G, "hist": vg.hist, "passado": passado, "atual": vg.atual,
            "RAMP": RAMP, "CLAMP": CLAMP, "dt": float(dt),
            "NOISE": NOISE, "NOISE_LP": NOISE_LP 
        }

    wrote = set()
    prev_flag = vg.usar_buffer

    for tipo in ordem + (["outros"] if outros else []):
        lst = buckets.get(tipo, []) if tipo != "outros" else outros
        if not lst: continue

        vg.usar_buffer = True
        vg.buffer.clear()

        for (L, R, _nome) in lst:
            env = _env_for(L)
            try:
                val = eval(R, env, {})
            except Exception:
                val = vg.get(L, vg.get(L, 0.0))

            base, campo = L.split(".",1)
            if campo in ("pv","sp"):
                conf = vg.get(f"{base}.controle", {}) or {}
                pv_min = conf.get("pv_min"); pv_max = conf.get("pv_max")
                try:
                    val = float(val)
                    if pv_min is not None and pv_max is not None:
                        a,b = (pv_min,pv_max) if pv_min<=pv_max else (pv_max,pv_min)
                        val = max(a, min(b, val))
                except: pass

            try: val = float(val)
            except:
                try: val = 0.0 if not val else float(val)
                except: val = vg.get(L, 0.0)

            vg.set(L, val)
            wrote.add(L)

        vg.commit_buffer()

    vg.usar_buffer = prev_flag
    return wrote

def _dsl_G(key):
    vg = VariaveisGlobais()
    v = vg.get(key, 0)
    try:
        return 1 if int(v) else 0
    except Exception:
        return 1 if bool(v) else 0

def _dsl_W(key, val):
    vg = VariaveisGlobais()
    vg.set(key, 1 if val else 0)

def _dsl_passado(cache: dict, key: str, n: int = 1, default: int = 0):
    # usa cache preenchido a cada ciclo do motor
    hist = cache.get(key, [])
    if len(hist) >= n:
        return hist[-n]
    return default

def _dsl_STEP(nome_logica: str):
    vg = VariaveisGlobais()
    return vg.get(f"grafcet.{nome_logica}.step", "P0")
def _parse_passos(passos_list):
    # "P0: NOME" -> ["P0", ...]; primeiro da lista é o inicial
    ids = []
    for ln in passos_list or []:
        m = re.match(r"\s*(P\d+)\s*:", str(ln))
        if m:
            ids.append(m.group(1))
    return ids

def _eval_expr(expr: str, base_tag: str):
    """
    Converte 'A && !B || TAG.PV0' em Python e avalia.
    Tokens sem ponto ganham prefixo base_tag+'.'
    """
    if not expr:
        return False
    vg = VariaveisGlobais()
    s = expr.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    # mapeia tokens
    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_\.]*\b", s))
    env = {}
    for t in tokens:
        if t in ("and", "or", "not", "True", "False"):
            continue
        key = t if "." in t else f"{base_tag}.{t}"
        env[t] = bool(vg.get(key, 0))
    try:
        return bool(eval(s, {"__builtins__": None}, env))
    except Exception:
        return False

def _tick_grafcets():
    vg = VariaveisGlobais()
    d = vg.get("logicas", {}) or {}
    for nome, spec in d.items():
        # passo atual (inicial = primeiro da lista de passos)
        passos_ids = _parse_passos(spec.get("passos", []))
        if not passos_ids:
            continue
        cur = vg.get(f"grafcet.{nome}.step", None)
        if cur is None or cur not in passos_ids:
            vg.set(f"grafcet.{nome}.step", passos_ids[0])
            cur = passos_ids[0]

        # base_tag para resolver CMD_LIGA -> BOMBA01.CMD_LIGA
        base = nome.split("_", 1)[0] if "_" in nome else nome

        # avalia transições na ordem (primeira verdadeira vence)
        trans = spec.get("transicoes", []) or []
        for ln in trans:
            ln = str(ln).strip()
            m = re.match(r"\s*(\*|P\d+)\s*->\s*(P\d+)\s*:\s*(.+)$", ln)
            if not m:
                continue
            de, para, expr = m.group(1), m.group(2), m.group(3)
            if de != "*" and de != cur:
                continue
            if _eval_expr(expr, base):
                vg.set(f"grafcet.{nome}.step", para)
                break  # 1 transição por ciclo
def _listar_tags_do_vg(vg, canvas=None):
    tags = set()
    for attr in ("_data", "_store", "store", "data"):
        d = getattr(vg, attr, None)
        if isinstance(d, dict):
            for k in d:
                if isinstance(k, str) and "." in k:
                    tags.add(k.split(".", 1)[0])
    # fallback canvas
    if canvas is not None and hasattr(canvas, "variaveis"):
        for v in canvas.variaveis:
            t = getattr(v, "tag", None)
            if t: tags.add(t)
    # filtra removidas
    out = []
    for t in sorted(tags):
        tipo = (vg.get(f"{t}.tipo", "ANA") or "ANA").upper()
        if tipo != "REM":
            out.append(t)
    return out

def _tick_leis_digitais(canvas, prev_cache, skip_keys=None):
    """
    Executa leis digitais.
    - canvas: referência ao canvas (p/ utilidades e acesso à scene, se necessário)
    - prev_cache: cache de passado()
    - skip_keys: set/list das chaves (ex.: {"BOMBA01.PV0", "P001.HH"}) que NÃO devem ser escritas aqui
                 (ex.: porque o IQ já escreveu no ciclo)
    """
    from singleton import VariaveisGlobais
    vg = VariaveisGlobais()

    # normaliza skip_keys para set imutável de strings
    skip_keys = set(skip_keys or [])

    # liste as tags/chaves que serão tocadas por leis digitais neste passo
    touched = set()

    # helpers do seu DSL/leitor de leis (ajuste os nomes se forem diferentes)
    def _dsl_R(key, default=0):
        v = vg.get(key, default)
        if isinstance(v, str) and v.isdigit():
            v = int(v)
        return v

    def _dsl_W(key, value):
        vg.set(key, value)

    # wrapper de escrita que respeita o skip_keys
    def W(key, value):
        if key in skip_keys:
            return
        touched.add(key)
        _dsl_W(key, value)

    # --------------------------
    # AQUI entra o seu processamento das leis digitais,
    # usando _dsl_R(...) para ler e W(...) para escrever.
    # Exemplo ilustrativo (troque pelo seu executor real):
    #
    # for lei in leis_digitais:
    #     val = eval_lei(lei, R=_dsl_R)   # sua função de avaliação
    #     W(lei.lhs, val)
    # --------------------------

    # Se você usa buffer no singleton, não mude; o commit acontece fora.
    return touched
    
def _listar_tags_do_vg(vg, canvas=None):
    """
    Retorna lista de TAGs conhecidas no VariaveisGlobais (inclui off-canvas).
    Ignora tags marcadas como REM.
    """
    tags = set()

    # 1) varrer possíveis dicts internos do singleton
    for attr in ("_data", "_store", "store", "data"):
        d = getattr(vg, attr, None)
        if isinstance(d, dict):
            for k in d.keys():
                if isinstance(k, str) and "." in k:
                    tags.add(k.split(".", 1)[0])

    # 2) se tiver dump() disponível, usa também
    if hasattr(vg, "dump"):
        try:
            d = vg.dump()
            if isinstance(d, dict):
                for k in d.keys():
                    if isinstance(k, str) and "." in k:
                        tags.add(k.split(".", 1)[0])
        except Exception:
            pass

    # 3) incluir o que existir no canvas (fallback)
    if canvas is not None and hasattr(canvas, "variaveis"):
        for v in canvas.variaveis:
            t = getattr(v, "tag", None)
            if t:
                tags.add(t)

    # 4) filtrar tags removidas
    out = []
    for t in sorted(tags):
        tipo = (vg.get(f"{t}.tipo", "ANA") or "ANA").upper()
        if tipo != "REM":
            out.append(t)
    return out

def renomear_tag_no_vg(vg, old_tag: str, new_tag: str):
    if old_tag == new_tag:
        return

    # snapshot do tipo antigo
    old_tipo = str(vg.get(f"{old_tag}.tipo", "ANA") or "ANA").upper()

    # 1) descobrir os stores internos
    stores = []
    for attr in ("_data", "_store", "store", "data"):
        if hasattr(vg, attr) and isinstance(getattr(vg, attr), dict):
            stores.append(getattr(vg, attr))

    # 2) coletar chaves old_tag.*
    keys = set()
    for store in stores:
        for k in list(store.keys()):
            if isinstance(k, str) and k.startswith(old_tag + "."):
                keys.add(k)

    # 3) copiar para new_tag.*
    for k in keys:
        suffix = k[len(old_tag):]  # inclui o ponto
        vg.set(new_tag + suffix, vg.get(k))

    # 4) ajustar leis no digi.map e reforçar tipo
    dig_map = vg.get(f"{new_tag}.digi.map", {}) or {}
    changed = False
    for pv, cfg in dig_map.items():
        law = cfg.get("law", "")
        if isinstance(law, str) and (old_tag + ".") in law:
            cfg["law"] = law.replace(old_tag + ".", new_tag + ".")
            changed = True
    if changed:
        vg.set(f"{new_tag}.digi.map", dig_map)

    # >>> manter o tipo correto no novo nome <<<
    if old_tipo == "DIG" or dig_map:
        vg.set(f"{new_tag}.tipo", "DIG")
    else:
        vg.set(f"{new_tag}.tipo", old_tipo)

    # 5) remover chaves antigas
    for store in stores:
        for k in list(keys):
            try:
                del store[k]
            except Exception:
                pass



def atualizar_referencias_no_canvas(canvas, old_tag: str, new_tag: str):
    """Atualiza TAG em itens de variável e referências simples (TouchArea target tag)."""
    if not canvas:
        return
    # 1) atualizar item de variável (mesmo off-canvas)
    for it in getattr(canvas, "variaveis", []):
        if getattr(it, "tag", "") == old_tag:
            it.tag = new_tag
            # se for QGraphicsTextItem e estiver visível um dia, já fica com texto certo
            if hasattr(it, "setPlainText"):
                try:
                    it.setPlainText(new_tag)
                except Exception:
                    pass

    # 2) atualizar TouchAreas que apontam para a tag (sem import circular)
    for it in list(canvas.scene.items()):
        # identifica TouchArea por "assinatura": tem os atributos target_type/target_value
        if getattr(it, "target_type", None) == "tag" and getattr(it, "target_value", None) == old_tag:
            it.target_value = new_tag
            if hasattr(it, "update"):
                try:
                    it.update()
                except Exception:
                    pass

    # 3) fechar/reabrir faceplate aberto dessa TAG (se você usa o dicionário faceplates_abertos)
    if hasattr(canvas, "faceplates_abertos"):
        w = canvas.faceplates_abertos.pop(old_tag, None)
        if w is not None:
            try:
                w.close()
            except Exception:
                pass
        try:
            from faceplate import open_faceplate
            nw = open_faceplate(new_tag)
            nw.show()
            canvas.faceplates_abertos[new_tag] = nw
        except Exception:
            pass


def _ensure_digital_defaults(vg, tag):
    """Garante tipo=DIG e mapa default se ainda não existirem."""
    tipo = str(vg.get(f"{tag}.tipo", "") or "").upper()
    if tipo != "DIG":
        vg.set(f"{tag}.tipo", "DIG")
    if vg.get(f"{tag}.digi.map", None) is None:
        vg.set(f"{tag}.digi.map", {
            "PV0": {"text0": "LIGA", "text1": "LIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
            "PV1": {"text0": "DESLIGA", "text1": "DESLIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
            "PV2": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV3": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV4": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV5": {"text0": "PARADO", "text1": "OPERANDO", "visible": True, "law": "", "pulse": False, "confirm": True}
        })

class TouchAreaItem(QGraphicsRectItem):
    def __init__(self, main_window, rect=QRectF(0, 0, 80, 80), target_type="tag", target_value="", border_color=QColor("red")):
        super().__init__(rect)
        self.main_window = main_window
        self.target_type = target_type
        self.target_value = target_value
        self.border_color = border_color
        self.setFlags(self.ItemIsSelectable | self.ItemIsMovable)
        self.setAcceptHoverEvents(True)
        self.setZValue(10000)

        # Movível e redimensionável
        self.setFlags(
            self.ItemIsSelectable |
            self.ItemIsMovable |
            self.ItemSendsGeometryChanges
        )

        self.setAcceptHoverEvents(True)
        self.setZValue(999999)



    def to_dict(self):
        return {
            "type": "touch_area",
            "x": self.pos().x(),
            "y": self.pos().y(),    
            "w": self.rect().width(),
            "h": self.rect().height(),
            "target_type": self.target_type,
            "target_value": self.target_value,
            "border_color": self.border_color.name()
        }

    @staticmethod
    def from_dict(data, main_window):
        item = TouchAreaItem(
            main_window,
            QRectF(0, 0, data.get("w", 80), data.get("h", 80)),
            target_type=data.get("target_type", "tag"),
            target_value=data.get("target_value", ""),
            border_color=QColor(data.get("border_color", "#ff0000"))
        )
        item.setPos(data.get("x", 0), data.get("y", 0))
        return item

    def hoverEnterEvent(self, event):
        if not self.main_window.modo_modelo:
            self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.main_window.modo_modelo:
            self.update()
        super().hoverLeaveEvent(event)
    def mousePressEvent(self, event):
        if self.target_type == "tag" and not self.main_window.modo_modelo:
            for var in self.main_window.tab_widget.currentWidget().variaveis:
                if var.tag == self.target_value:
                    fp = open_faceplate(var.tag)
                    fp.show()
                    break
        return super().mousePressEvent(event)

    def _apply_config(self, type_combo, value_combo, width_input, height_input):
        self.target_type = type_combo.currentText()
        self.target_value = value_combo.currentText()
        self.setRect(0, 0, width_input.value(), height_input.value())

    def _choose_color(self, btn):
        color = QColorDialog.getColor(self.border_color)
        if color.isValid():
            self.border_color = color

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
            modo_modelo = getattr(self.main_window, "modo_modelo", False)

            painter.setBrush(Qt.NoBrush)  # sempre transparente

            if modo_modelo:
                painter.setPen(QPen(self.border_color, 2, Qt.SolidLine))
                painter.drawRect(self.rect())
                painter.drawText(self.rect(), Qt.AlignCenter, "🖱")
            else:
                if self.isUnderMouse():
                    painter.setPen(QPen(self.border_color, 2, Qt.SolidLine))
                    painter.drawRect(self.rect())
                    
    def update_flags(self):
        if getattr(self.main_window, "modo_modelo", False):
            self.setFlags(self.ItemIsSelectable | self.ItemIsMovable)
        else:
            self.setFlags(self.ItemIsSelectable)  # não movível no modo simulação

class AlarmesDialog(QDialog):
    def __init__(self, tag="", alarmes=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração da Variável")

        self.tag = tag
        self.alarmes = alarmes or {"HH": None, "H": None, "L": None, "LL": None}

        layout = QVBoxLayout(self)

        # Campo TAG
        layout.addWidget(QLabel("TAG:"))
        self.tag_input = QLineEdit()
        self.tag_input.setText(self.tag)
        layout.addWidget(self.tag_input)

        # Campos de alarmes
        self.inputs = {}
        for nome in ["HH", "H", "L", "LL"]:
            lbl = QLabel(f"{nome}:")
            spin = QDoubleSpinBox()
            spin.setRange(-999999, 999999)
            if self.alarmes.get(nome) is not None:
                spin.setValue(self.alarmes[nome])
            layout.addWidget(lbl)
            layout.addWidget(spin)
            self.inputs[nome] = spin

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

    def get_config(self):
        return self.tag_input.text(), {nome: spin.value() for nome, spin in self.inputs.items()}


class ConfigVariavelDialog(QDialog):
    def __init__(self, tag="", alarmes=None, lei="", controle=None, variaveis_existentes=None, mods=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração da Variável")
        self.resize(400, 400)

        self.tag = tag
        self.alarmes = alarmes or {"HH": None, "H": None, "L": None, "LL": None}
        self.lei = lei or ""
        self.controle = controle or {}
        self.variaveis_existentes = variaveis_existentes or []
        

        # carregar mods já existentes (quando reabrir o editor)
        existentes = {}
        try:
            existentes = self.parent().parent().currentWidget()  # segurança
        except Exception:
            pass
        # melhor: receba 'mods' via parâmetro; usaremos no abrir_editor_variavel

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # === Aba Geral ===
        geral_tab = QWidget()
        geral_layout = QVBoxLayout(geral_tab)
        geral_layout.addWidget(QLabel("TAG:"))
        self.tag_input = QLineEdit(self.tag)
        geral_layout.addWidget(self.tag_input)
        # === Tipo da variável ===
        geral_layout.addWidget(QLabel("Tipo da variável:"))
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItems(["Temperatura", "Nível", "Vazão", "Pressão", "logica"])
        self.tipo_combo.setCurrentText(self.controle.get("tipo", "estado_lento"))
        geral_layout.addWidget(self.tipo_combo)
        self.alarm_inputs = {}
        for nome in ["HH", "H", "L", "LL"]:
            geral_layout.addWidget(QLabel(f"{nome}:"))
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setSpecialValueText("—") 
            spin.setMinimum(-1e9)
            if self.alarmes.get(nome) is None:
                spin.setValue(spin.minimum()    )
            else:
                spin.setValue(float(self.alarmes[nome]))
                
            geral_layout.addWidget(spin)
            self.alarm_inputs[nome] = spin
        # === Faixa de engenharia (PV) ===
        geral_layout.addWidget(QLabel("Faixa PV (min / max):"))
        row_range = QHBoxLayout()
        self.pv_min_input = QDoubleSpinBox(); self.pv_min_input.setRange(-1e9, 1e9)
        self.pv_max_input = QDoubleSpinBox(); self.pv_max_input.setRange(-1e9, 1e9)
        # valores atuais (se já existirem no controle)
        self.pv_min_input.setValue(self.controle.get("pv_min", 0.0))
        self.pv_max_input.setValue(self.controle.get("pv_max", 100.0))
        row_range.addWidget(self.pv_min_input); row_range.addWidget(self.pv_max_input)
        geral_layout.addLayout(row_range)

        tabs.addTab(geral_tab, "Geral")

        # === Aba Lei ===
        lei_tab = QWidget()
        lei_layout = QVBoxLayout(lei_tab)
        self.lei_edit = QPlainTextEdit(self.lei)
        self.lei_edit.setTabChangesFocus(False)  # <<< agora Tab insere \t em vez de mudar de campo
        lei_layout.addWidget(self.lei_edit)

        self.mods = list(mods or [])

        grp = QGroupBox("Modificadores")
        grp_layout = QVBoxLayout(grp)

        # Linha: condição / consequências
        row_mod = QHBoxLayout()
        self.in_if = QLineEdit()
        self.in_if.setPlaceholderText("Condição (ex.: G('FC001.ALRM') in ('H','HH'))")
        self.in_then = QLineEdit()
        self.in_then.setPlaceholderText("Consequências (ex.: Pisca('#f00','#000');Borda('#f00',2))")
        btn_add = QPushButton("Adicionar")
        row_mod.addWidget(self.in_if)
        row_mod.addWidget(self.in_then)
        row_mod.addWidget(btn_add)
        grp_layout.addLayout(row_mod)

        # Lista de regras
        self.lst_mods = QListWidget()
        self.lst_mods.setContextMenuPolicy(Qt.CustomContextMenu)
        grp_layout.addWidget(self.lst_mods)

        lei_layout.addWidget(grp)

        # Conexões
        btn_add.clicked.connect(self.add_mod)
        self.lst_mods.customContextMenuRequested.connect(self._remove_selected)

        # Preenche a lista
        self._refresh_mod_list()

        tabs.addTab(lei_tab, "Lei")

        # === Aba Controle ===
        ctrl_tab = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_tab)

        self.chk_controlada = QCheckBox("Variável Controlada")
        self.chk_controlada.setChecked(self.controle.get("variavel_controlada", False))
        ctrl_layout.addWidget(self.chk_controlada)

        # PID params
        self.kp_input = QDoubleSpinBox(); self.kp_input.setValue(self.controle.get("Kp", 1.0))
        self.ki_input = QDoubleSpinBox(); self.ki_input.setValue(self.controle.get("Ki", 0.0))
        self.kd_input = QDoubleSpinBox(); self.kd_input.setValue(self.controle.get("Kd", 0.0))
        for lbl, spin in [("Kp:", self.kp_input), ("Ki:", self.ki_input), ("Kd:", self.kd_input)]:
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl))
            row.addWidget(spin)
            ctrl_layout.addLayout(row)

        # Modo de operação
        ctrl_layout.addWidget(QLabel("Modo:"))
        self.modo_combo = QComboBox()
        self.modo_combo.addItems(["MAN", "AUT", "CAS", "PRD"])
        if "modo" in self.controle:
            idx = self.modo_combo.findText(self.controle["modo"])
            if idx >= 0:
                self.modo_combo.setCurrentIndex(idx)
        ctrl_layout.addWidget(self.modo_combo)

        # SP Tracking
        self.chk_sp_tracking = QCheckBox("SP Tracking (em modo manual)")
        self.chk_sp_tracking.setChecked(self.controle.get("sp_tracking", False))
        ctrl_layout.addWidget(self.chk_sp_tracking)

        # PV Tag (automático)
        ctrl_layout.addWidget(QLabel("PV (Process Variable):"))
        self.pv_combo = QComboBox()
        self.pv_combo.addItems([
            f"{v}.pv" for v in self.variaveis_existentes if "." not in v
        ])

        if "pv_tag" in self.controle:
            idx = self.pv_combo.findText(self.controle["pv_tag"])
            if idx >= 0:
                self.pv_combo.setCurrentIndex(idx)
        ctrl_layout.addWidget(self.pv_combo)

        tabs.addTab(ctrl_tab, "Controle")
        # Ação da malha
        ctrl_layout.addWidget(QLabel("Ação:"))
        self.acao_combo = QComboBox()
        self.acao_combo.addItems(["Direta", "Reversa"])
        acao_atual = (self.controle.get("acao", "direta")).lower()
        self.acao_combo.setCurrentText("Reversa" if acao_atual == "reversa" else "Direta")
        ctrl_layout.addWidget(self.acao_combo)
        ctrl_layout.addWidget(QLabel("Destino SP remoto (master → slave):"))
        self.mv_write_input = QLineEdit(self.controle.get("mv_write_tag", ""))  # ex.: "FC002.sp"
        ctrl_layout.addWidget(self.mv_write_input)
        

        # Conversão OP% → SP (engenharia) para cascata
        ctrl_layout.addWidget(QLabel("Conversão OP% → SP (Linear)"))
        row0 = QHBoxLayout(); row1 = QHBoxLayout()
        self.op_min = QDoubleSpinBox(); self.op_min.setRange(-1e6,1e6); self.op_min.setValue(self.controle.get("op_min", 0))
        self.op_max = QDoubleSpinBox(); self.op_max.setRange(-1e6,1e6); self.op_max.setValue(self.controle.get("op_max", 100))
        self.sp_min = QDoubleSpinBox(); self.sp_min.setRange(-1e9,1e9); self.sp_min.setValue(self.controle.get("sp_min", 0))
        self.sp_max = QDoubleSpinBox(); self.sp_max.setRange(-1e9,1e9); self.sp_max.setValue(self.controle.get("sp_max", 1000))
        row0.addWidget(QLabel("OP% min:")); row0.addWidget(self.op_min)
        row0.addWidget(QLabel("OP% max:")); row0.addWidget(self.op_max)
        row1.addWidget(QLabel("SP min:")); row1.addWidget(self.sp_min)
        row1.addWidget(QLabel("SP max:")); row1.addWidget(self.sp_max)
        ctrl_layout.addLayout(row0); ctrl_layout.addLayout(row1)
        # Botão OK
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

    def add_mod(self):
        cond = self.in_if.text().strip()
        then_raw = self.in_then.text().strip()
        if not cond or not then_raw:
            return
        thens = [t.strip() for t in then_raw.split(";") if t.strip()]
        self.mods.append({"if": cond, "then": thens})
        self._refresh_mod_list()
        self.in_if.clear()
        self.in_then.clear()

    def _refresh_mod_list(self):
        self.lst_mods.clear()
        for rule in self.mods:
            txt = f"if: {rule.get('if','')}  |  then: {', '.join(rule.get('then',[]))}"
            self.lst_mods.addItem(txt)

    def _remove_selected(self, pos):
        item = self.lst_mods.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        act_del = menu.addAction("Remover")
        if menu.exec_(self.lst_mods.mapToGlobal(pos)) == act_del:
            row = self.lst_mods.row(item)
            if 0 <= row < len(self.mods):
                self.mods.pop(row)
                self._refresh_mod_list()


    def get_config(self):
        def _val(vspin):
            v = vspin.value()
            return None if (v == vspin.minimum()) else float(v)

        alarmes = {nome: _val(spin) for nome, spin in self.alarm_inputs.items()}  # <<< usar _val
        acao_str = "reversa" if self.acao_combo.currentText() == "Reversa" else "direta"
        controle = {
            "variavel_controlada": self.chk_controlada.isChecked(),
            "Kp": self.kp_input.value(),
            "Ki": self.ki_input.value(),
            "Kd": self.kd_input.value(),
            "modo": self.modo_combo.currentText(),
            "sp_tracking": self.chk_sp_tracking.isChecked(),
            "pv_tag": self.pv_combo.currentText(),
            "acao": acao_str,
            "mv_write_tag": self.mv_write_input.text().strip(),
            "op_min": self.op_min.value(),
            "op_max": self.op_max.value(),
            "sp_min": self.sp_min.value(),
            "sp_max": self.sp_max.value(),
            "pv_min": self.pv_min_input.value(),
            "pv_max": self.pv_max_input.value(),
            "tipo": self.tipo_combo.currentText()
        }
        return self.tag_input.text(), alarmes, self.lei_edit.toPlainText(), controle, self.mods


                    


class SimuladorCanvas(QGraphicsView):
    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing)
        self.simulacao_rodando = False
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.faceplates_abertos = {} 
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._abrir_menu_contexto)

        # Lista de variáveis para atualizar
        self.variaveis = []

        # Timer de atualização de valores
        self.timer_controle = QTimer()
        try:
            self.timer_controle.timeout.disconnect()
        except Exception:
            pass
        self.timer_controle.timeout.connect(self._tick_motor)
        self.timer_controle.start(200)  # 200 ms

        self.timer_interface = QTimer()
        self.timer_interface.timeout.connect(self.atualizar_interface)
        self.timer_interface.start(1000)  # Ex: interface a cada 1000 ms
        self._prev_cache = {}  # para passado()


    def _tick_motor(self):
        if not getattr(self, "simulacao_rodando", False):
            return

        # 1) Equações Analógicas
        lhs_eq = _tick_eqs_analogicas(self, dt=0.2)  # (set de TAG.campo escritos)

        # 2) IQ + Leis Digitais (se tiver)
        wrote_iq = _tick_iq(self, self._prev_cache)
        _tick_leis_digitais(self, self._prev_cache, skip_keys=wrote_iq)

        # 2.1) (opcional) Leis locais de compatibilidade — só se você QUISER manter por transição:
        # self._rodar_leis_locais_compat(skip_lhs=lhs_eq)

        # 3) PID
        from controle import aplicar_controle_PID
        aplicar_controle_PID(self, dt=0.2)

    def _rodar_leis_locais_compat(self, skip_lhs: set):
        from singleton import VariaveisGlobais
        vg = VariaveisGlobais()
        skip_lhs = skip_lhs or set()
        for var in self.variaveis:
            lei = (getattr(var, "lei", "") or "").strip()
            if not lei:
                continue  # lei vazia não interfere
            lhs = f"{var.tag}.pv" if not any(var.tag.endswith(s) for s in (".pv",".sp",".mv")) else var.tag
            if lhs in skip_lhs:
                continue  # já veio da Central
            # executa com seu executor atual
            try:
                val = self._executa_lei(var)
                if val is not None:
                    # aplica com travas de faixa
                    self._aplica_resultado(var, val)
            except Exception:
                pass
            
    def abrir_faceplate_variavel(self, item):
        tag = getattr(item, "tag", None)
        if not tag:
            return
        if tag in self.faceplates_abertos:
            self.faceplates_abertos[tag].raise_()  # traz para frente
            self.faceplates_abertos[tag].activateWindow()
            return
        fp = Faceplate(tag_name=tag)
        self.faceplates_abertos[tag] = fp
        fp.finished.connect(lambda: self.faceplates_abertos.pop(tag, None))
        fp.show()

    def set_area_util(self, largura, altura, cor_fundo):
        self.area_largura = largura
        self.area_altura = altura
        self.cor_fundo = cor_fundo 
        print("Cor de fundo:", cor_fundo.name())
        self.setSceneRect(0, 0, largura, altura)

        # Limpa fundos anteriores
        for item in self.scene.items():
            if isinstance(item, QGraphicsRectItem) and item.zValue() == -10000:
                self.scene.removeItem(item)

        fundo = QGraphicsRectItem(0, 0, largura, altura)
        fundo.setBrush(self.cor_fundo)
        fundo.setPen(QPen(Qt.gray, 0.5, Qt.DotLine))
        fundo.setZValue(-10000)
        fundo.setData(0, "BG")
        self.scene.addItem(fundo)



    def carregar_projeto(self, caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)

        for obj in data.get("objetos", []):
            tipo = obj.get("type")
            if tipo == "linha":
                item = EditableLine.from_dict(obj)
                self.scene.addItem(item)

            elif tipo == "caminho":
                item = EditablePolyline.from_dict(obj)
                self.scene.addItem(item)


            elif tipo == "variavel":
                item = EditableVariable.from_dict(obj)
                self.scene.addItem(item)
                self.variaveis.append(item)
                # 🔹 Inicializa no singleton
                vg = VariaveisGlobais()
                vg.inicializar_tag(item.tag)
                

            elif tipo == "svg":
                item = SvgObjectItem.from_dict(obj)
                self.scene.addItem(item)

            # Remove flags de edição
            if hasattr(item, "setFlags"):
                item.setFlags(item.flags() & ~item.ItemIsMovable & ~item.ItemIsSelectable)
                
    def atualizar_controle(self):
        # legado desativado: tudo roda em _tick_motor
        return


    def atualizar_interface(self):
        if getattr(self.main_window, "modo_modelo", False) or not getattr(self, "simulacao_rodando", False):
            return
        self._atualizar_variaveis_simuladas()
        self._aplicar_modificadores_tick()

    # Ordem global (do mais lento pro mais rápido)
    TIPO_ORDEM = ["Temperatura", "Nível", "Vazão", "Pressão", "logica"]

    def _executa_lei(self, var):
        from singleton import VariaveisGlobais
        vg = VariaveisGlobais()
        lei_codigo = getattr(var, "lei", "").strip() or "valor = G(f'{var.tag}.pv', 0)"
        contexto = {v.tag: vg.get(f"{v.tag}.pv", 0) for v in self.variaveis if hasattr(v, "tag")}
        try:
            safe_globals = {
                "__builtins__": None,
                "math": math, "np": np, "control": control, "signal": signal, "random": random,
                "min": min, "max": max, "abs": abs, "round": round,
                "float": float, "int": int, "len": len,
                "G": vg.get, "hist": vg.hist, "S": vg.set, "passado": vg.passado, "atual": vg.atual
            }
            safe_locals = dict(contexto)
            exec(lei_codigo, safe_globals, safe_locals)
            valor = safe_locals.get("valor")
            if valor is None:
                raise ValueError(f"[{var.tag}] 'valor' não definido")
        except Exception as e:
            print(f"[LEI ERRO] {var.tag}: {e}")
            valor = vg.get(f"{var.tag}.pv", 0)
        return valor
    def _executar_lei_local_se_preciso(tag_base, lei_texto, vg, dt=0.2):
        # 1) lei vazia → NÃO altera nada
        if not lei_texto or not str(lei_texto).strip():
            return None  # sinal: manter o que já está em vg

        # 2) prepara ambiente seguro
        import math, random
        env = {
            "__builtins__": None,
            "math": math, "random": random,
            "G": vg.get, "hist": vg.hist, "passado": vg.passado, "atual": vg.atual,
            "dt": float(dt),
        }
        loc = {}
        try:
            exec(lei_texto, env, loc)
        except Exception:
            # erro na lei → não altera nada
            return None

        # 3) só aplica se 'valor' estiver definido e não for None
        if "valor" not in loc or loc["valor"] is None:
            return None

        try:
            return float(loc["valor"])
        except Exception:
            return None
        
    def _aplica_resultado(self, var, valor):
        from singleton import VariaveisGlobais
        vg = VariaveisGlobais()

        ctrl = getattr(var, "controle", {}) or {}
        pv_min = ctrl.get("pv_min", 0.0)
        pv_max = ctrl.get("pv_max", 100.0)
        if pv_min > pv_max:
            pv_min, pv_max = pv_max, pv_min

        # trava PV
        valor = max(pv_min, min(pv_max, valor))

        if var.tag.endswith((".pv", ".sp", ".mv")):
            vg.set(var.tag, valor)
        else:
            vg.set(f"{var.tag}.pv", valor)
        var.atualizar_texto(valor)


    def _atualizar_variaveis_simuladas(self):
        # Só reflete na HMI o que o motor já calculou no VariaveisGlobais
        if getattr(self.main_window, "modo_modelo", False) or not getattr(self, "simulacao_rodando", False):
            return
        from singleton import VariaveisGlobais
        vg = VariaveisGlobais()

        for var in self.variaveis:
            tag = getattr(var, "tag", "")
            if not tag:
                continue
            # chave de leitura
            lhs = tag if any(tag.endswith(s) for s in (".pv",".sp",".mv")) else f"{tag}.pv"
            val = vg.get(lhs, 0.0)

            # clamp opcional para PV/SP (se quiser manter consistência visual)
            ctrl = getattr(var, "controle", {}) or {}
            if lhs.endswith(".pv") or lhs.endswith(".sp"):
                pv_min = ctrl.get("pv_min", None); pv_max = ctrl.get("pv_max", None)
                try:
                    fv = float(val)
                    if pv_min is not None and pv_max is not None:
                        a,b = (pv_min,pv_max) if pv_min <= pv_max else (pv_max,pv_min)
                        fv = max(a, min(b, fv))
                    val = fv
                except Exception:
                    pass

            # apenas atualiza o texto no canvas
            try:
                var.atualizar_texto(val)
            except Exception:
                pass





    def adicionar_area_toque(self, largura=80, altura=80):


        # calcula o maior Z da cena
        max_z = max((item.zValue() for item in self.scene.items()), default=0)

        rect = QRectF(0, 0, largura, altura)
        item = TouchAreaItem(self.main_window, rect)

        # define Z para estar acima de todos
        item.setZValue(max_z + 1)

        self.scene.addItem(item)
    def keyPressEvent(self, event):
        if self.main_window.modo_modelo and event.key() == Qt.Key_Delete:
            for item in self.scene.selectedItems():
                if isinstance(item, TouchAreaItem):
                    self.scene.removeItem(item)
                    return
        super().keyPressEvent(event)
        
    def _normalizar_item_alvo(self, it):
            # Sobe para um tipo "conhecido" (var/SVG/linha/polyl/texto); TouchArea é QGraphicsRectItem -> retorna como está
        while it and not isinstance(it, (EditableVariable, SvgObjectItem, EditableLine, EditablePolyline, TouchAreaItem)) \
            and getattr(it, "toPlainText", None) is None:
            it = it.parentItem()
        return it
    def mouseDoubleClickEvent(self, event):
        it = self.itemAt(event.pos())
        if not it:
            return super().mouseDoubleClickEvent(event)

        item = self._normalizar_item_alvo(it)

        # --- MODO MODELO: abre editores ---
        if self.main_window and getattr(self.main_window, "modo_modelo", False):
            if isinstance(item, TouchAreaItem):
                self._configurar_touch_area(item)
                # limpar seleção pra sumir a borda azul
                item.setSelected(False); self.scene.clearSelection()
                return
            if isinstance(item, EditableVariable):
                self.abrir_editor_variavel(item); return
            if isinstance(item, (SvgObjectItem, EditableLine, EditablePolyline)):
                self.abrir_editor_modificadores(item); return
            if hasattr(item, "toPlainText") and not hasattr(item, "tag"):  # texto livre
                self.abrir_editor_modificadores(item); return

        # --- MODO SIMULAÇÃO: comportamento da TouchArea (abrir faceplate / navegar) ---
        if isinstance(item, TouchAreaItem) and event.button() == Qt.LeftButton:
            if item.target_type == "tag":
                for var in self.main_window.tab_widget.currentWidget().variaveis:
                    if var.tag == item.target_value:
                        Faceplate(tag_name=var.tag).show()
                        break
            elif item.target_type == "tela":
                for i in range(self.main_window.tab_widget.count()):
                    if self.main_window.tab_widget.tabText(i) == item.target_value:
                        self.main_window.sidebar.setCurrentRow(i)
                        break
            return  # já tratou

        return super().mouseDoubleClickEvent(event)


# 2) REESCREVA o mousePressEvent
    def mousePressEvent(self, event):
        # --------- MODO SIMULAÇÃO: NADA DE SELEÇÃO ----------
        if event.button() == Qt.LeftButton and not getattr(self.main_window, "modo_modelo", False):
            hit = self.itemAt(event.pos())

            # fundo: limpa seleção e consome
            if (not hit) or (isinstance(hit, QGraphicsRectItem) and hit.data(0) == "BG"):
                self.scene.clearSelection()
                return

            item = self._normalizar_item_alvo(hit)

        if not getattr(self.main_window, "modo_modelo", False) and event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if hasattr(item, "tag"):
                tag = getattr(item, "tag", None)
                if tag:
                    fp = open_faceplate(tag)
                    fp.show()
                    return



        # --------- MODO MODELO: comportamento padrão (seleciona/edita) ----------
        super().mousePressEvent(event)

    def aplicar_flags_por_modo(self):
        em_modelo = getattr(self.main_window, "modo_modelo", False)
        for it in self.scene.items():
            if hasattr(it, "setFlag"):
                it.setFlag(it.ItemIsSelectable & it.ItemIsMovable, em_modelo)
                

    def _abrir_menu_contexto(self, pos):
        item = self._normalizar_item_alvo(self.itemAt(pos))
        if not item: return

        if isinstance(item, EditableVariable):
            tag = getattr(item, "tag", "")
            menu = QMenu(self)
            act_props  = menu.addAction("Propriedades")
            act_face   = menu.addAction("Abrir Faceplate")
            act_tuning = menu.addAction("Tuning")
            act_trends = menu.addAction("Tendências")
            acao = menu.exec_(self.mapToGlobal(pos))

            if acao == act_props:
                self.abrir_editor_variavel(item)
            elif acao == act_face:
                from faceplate import BaseFaceplate
                BaseFaceplate(tag_name=tag).show()
            elif acao == act_tuning:
                from tuning import TuningDialog
                TuningDialog(tag, self).exec_()
            elif acao == act_trends:
                presets = [
                    f"{tag}|#00AEEF|",     # PV
                    f"{tag}.sp|#FFD400|",  # SP
                    f"{tag}.mv|#FF5A5A|%"  # MV no eixo de %
                ]
                open_trends(parent=self, titulo=f"Tendências - {tag}", presets=presets)

            # (opcional) menu para outros itens em modo modelo
            # dentro de _abrir_menu_contexto(...)
            elif isinstance(item, (EditableLine, EditablePolyline, SvgObjectItem)) and getattr(self.main_window, "modo_modelo", False):
                menu = QMenu(self)
                act_props = menu.addAction("Modificadores")   # renomeei pra ficar claro
                acao = menu.exec_(self.mapToGlobal(pos))
                if acao == act_props:
                    self.abrir_editor_modificadores(item)     # <<< aqui era abrir_editor_objeto(item)

        if isinstance(item, (EditableLine, EditablePolyline, SvgObjectItem)) and getattr(self.main_window, "modo_modelo", False):
                menu = QMenu(self)
                act_props = menu.addAction("Modificadores")
                if menu.exec_(self.mapToGlobal(pos)) == act_props:
                    self.abrir_editor_modificadores(item)
                return

    def abrir_editor_variavel(self, item):
        vg = VariaveisGlobais()  # <-- CRIE o vg AQUI no topo

        variaveis_existentes = [v.tag for v in self.variaveis if hasattr(v, "tag")]
        # 3) carregue alarmes e controle priorizando o que está no Singleton (tuning)
        conf_vg = vg.get(f"{item.tag}.controle", None)
        ctrl_base = dict(conf_vg) if isinstance(conf_vg, dict) else dict(getattr(item, "controle", {}) or {})
        alarmes_exist = (
            getattr(item, "alarmes", None)
            or vg.get(f"{item.tag}.alarmes", None)
            or {"HH": None, "H": None, "L": None, "LL": None}
        )

        # 4) abre o diálogo já com os valores atuais do PID vindos do vg (se houver)
        dlg = ConfigVariavelDialog(
            getattr(item, "tag", ""),
            alarmes_exist,
            getattr(item, "lei", ""),
            ctrl_base,                        # <<<<< aqui vai o controle “atual”
            variaveis_existentes,
            getattr(item, "_mods", []),
            self
        )

        if dlg.exec_() == QDialog.Accepted:
            nova_tag, novos_alarmes, nova_lei, novo_controle, novos_mods = dlg.get_config()

            # 5) persiste no item (para salvar/reabrir o modelo do arquivo)
            item.tag = nova_tag
            item.alarmes = novos_alarmes
            item.lei = nova_lei
            item.controle = dict(novo_controle)     # <<<<< garante que Kp/Ki/Kd vão pro arquivo
            item._mods = list(novos_mods or [])

            # 6) persiste no Singleton (para refletir imediatamente na simulação)
            vg.set(f"{nova_tag}.controle", dict(novo_controle))
            vg.set(f"{nova_tag}.alarmes", dict(novos_alarmes))
            
    def _garantir_variaveis_filhas(self):
        sufixos = [".pv", ".sp", ".mv"]
        existentes = {v.tag for v in self.variaveis}
        novas = []

        for v in self.variaveis:
            if "." in v.tag:
                continue  # pula variáveis que já são .pv, .sp, .mv

            for sufixo in sufixos:
                tag_filha = f"{v.tag}{sufixo}"
                if tag_filha not in existentes:
                    nova = EditableVariable()
                    nova.tag = tag_filha
                    nova.setPlainText(tag_filha)
                    nova.setVisible(False)  # não aparece no canvas
                    nova.setFlag(QGraphicsItem.ItemIsSelectable, False)
                    nova.setFlag(QGraphicsItem.ItemIsMovable, False)
                    novas.append(nova)

        self.variaveis.extend(novas)


    def abrir_editor_objeto(self, item):
        self._abrir_dialogo("Editor de Objeto", "Configuração de modificadores de cor")

    def abrir_editor_texto(self, item):
        self._abrir_dialogo("Editor de Texto", f"Configuração de '{item.toPlainText()}'")

    def _abrir_dialogo(self, titulo, texto):
        dlg = QDialog(self)
        dlg.setWindowTitle(titulo)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(texto))
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        layout.addWidget(ok_btn)
        dlg.exec_()
        
    def _aplicar_modificadores_tick(self):
        from singleton import VariaveisGlobais
        vg = VariaveisGlobais()

        # tempo para piscar (1 Hz -> alterna a cada chamada, ou use contador/tempo real)
        if not hasattr(self, "_blink_on"):
            self._blink_on = False
        self._blink_on = not self._blink_on

        safe_globals = {
            "__builtins__": None,
            "math": math,
            "np": np,
            "random": random,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            # acesso a variáveis
            "G": vg.get,
        }

        for item in self.scene.items():
            mods = getattr(item, "_mods", None)
            if not mods:
                continue

            _capturar_baseline(item)

            # reset visual a cada tick; regras re-aplicam se verdadeiras
            self._reset_visual(item)

            for rule in mods:
                cond = rule.get("if", "").strip()
                if not cond:
                    continue
                try:
                    ok = bool(eval(cond, safe_globals, {}))
                except Exception as e:
                    # log opcional
                    # print("[Mods] erro condição:", e, cond)
                    ok = False

                if not ok:
                    continue

                # aplica ações
                for action in rule.get("then", []):
                    self._aplicar_acao(item, action, blink_on=self._blink_on)
    def _reset_visual(self, item):
        # Reverte para baseline visual
        if hasattr(item, "_base_pen") and item._base_pen is not None and hasattr(item, "setPen"):
            item.setPen(item._base_pen)
        if hasattr(item, "_base_brush") and item._base_brush is not None and hasattr(item, "setBrush"):
            item.setBrush(item._base_brush)
        if hasattr(item, "_base_opacity"):
            item.setOpacity(item._base_opacity)
        # Evita sobrescrever texto de variáveis dinâmicas
        if not hasattr(item, "tag") and hasattr(item, "_base_text") and hasattr(item, "setPlainText"):
            item.setPlainText(item._base_text)
        if hasattr(item, "_base_color") and hasattr(item, "setDefaultTextColor"):
            item.setDefaultTextColor(item._base_color)
        try:
            for ch in getattr(item, "childItems", lambda: [])():
                if hasattr(ch, "_base_pen") and hasattr(ch, "setPen") and ch._base_pen is not None:
                    ch.setPen(ch._base_pen)
                if hasattr(ch, "_base_brush") and hasattr(ch, "setBrush") and ch._base_brush is not None:
                    ch.setBrush(ch._base_brush)
        except Exception:
            pass


    def _aplicar_acao(self, item, action_str, blink_on=False):
        """
        action_str: "Borda('#f00',2)" | "Preenchimento('#0f0')" | "Pisca('#f00','#000')" | "MudarTexto('Alarme')"
        """
        try:
            nome, args = action_str.split("(", 1)
            args = args.rstrip(")")
        except ValueError:
            return

        args = [a.strip() for a in args.split(",")] if args else []

        def _parse_cor(arg):
            arg = arg.strip().strip("'").strip('"')
            return QColor(arg) if arg else QColor("transparent")

        if nome == "Borda":
            # Borda(cor, largura=1)
            cor = _parse_cor(args[0]) if args else QColor("black")
            largura = float(args[1]) if len(args) > 1 else 1.0
            if hasattr(item, "setPen"):
                pen = QPen(cor, largura)
                item.setPen(pen)

        elif nome == "Preenchimento":
            # Preenchimento(cor)
            cor = _parse_cor(args[0]) if args else QColor("transparent")
            brush = QBrush(cor)
            applied = False

            # 1) Itens "normais" (retângulos, elipses, polígonos, QGraphicsPathItem etc.)
            if hasattr(item, "setBrush"):
                try:
                    item.setBrush(brush)
                    applied = True
                except Exception:
                    pass

            # 2) SVG decomposto em filhos (paths): tenta aplicar nos filhos
            if not applied:
                try:
                    for ch in getattr(item, "childItems", lambda: [])():
                        if hasattr(ch, "setBrush"):
                            ch.setBrush(brush)
                            applied = True
                except Exception:
                    pass

            # 3) Ganchos comuns em wrappers de SVG
            #    (se seu SvgObjectItem tiver um desses métodos, eles serão chamados)
            if not applied:
                for m in ("setFill", "set_fill", "setFillColor", "set_fill_color", "apply_fill"):
                    if hasattr(item, m):
                        try:
                            getattr(item, m)(cor)
                            applied = True
                            break
                        except Exception:
                            pass

            # (opcional) você pode fazer um print se nada aplicou:
            # if not applied:
            #     print("[Mods] Preenchimento: item não aceita brush nem filhos com brush")


        elif nome == "Pisca":
            # Pisca(c1, c2) -> alterna cor da borda entre c1 e c2
            c1 = _parse_cor(args[0]) if len(args) > 0 else QColor("red")
            c2 = _parse_cor(args[1]) if len(args) > 1 else QColor("black")
            if hasattr(item, "setPen"):
                pen = QPen(c1 if blink_on else c2, getattr(item, "pen", lambda: QPen()).__call__().widthF() or 1.0)
                item.setPen(pen)
            # para textos, piscar cor do texto
            if hasattr(item, "setDefaultTextColor"):
                item.setDefaultTextColor(c1 if blink_on else c2)

        elif nome == "MudarTexto":
            # MudarTexto('string')
            novo = args[0].strip().strip("'").strip('"') if args else ""
            if hasattr(item, "setPlainText"):
                item.setPlainText(novo)
        elif nome == "CorTexto":
            # CorTexto(cor)
            cor = _parse_cor(args[0]) if args else QColor("black")
            if hasattr(item, "setDefaultTextColor"):
                item.setDefaultTextColor(cor)

        elif nome == "TipoBorda":
            # TipoBorda('DashLine')
            estilo_str = args[0].strip().strip("'").strip('"') if args else "SolidLine"
            estilos = {
                "SolidLine": Qt.SolidLine,
                "DashLine": Qt.DashLine,
                "DotLine": Qt.DotLine,
                "DashDotLine": Qt.DashDotLine,
                "DashDotDotLine": Qt.DashDotDotLine
            }
            estilo = estilos.get(estilo_str, Qt.SolidLine)
            if hasattr(item, "setPen"):
                pen_atual = item.pen() if hasattr(item, "pen") else QPen()
                pen = QPen(pen_atual.color(), pen_atual.widthF(), estilo)
                item.setPen(pen)
                
    def abrir_editor_modificadores(self, item):
        mods_existentes = getattr(item, "_mods", [])
        dlg = ConfigVariavelDialog(
            tag="",
            alarmes={},
            lei="",
            controle={},
            variaveis_existentes=[],
            mods=mods_existentes,
            parent=self
        )
        # Remove abas "Geral" e "Controle"
        dlg.findChild(QTabWidget).removeTab(2)  # Controle
        dlg.findChild(QTabWidget).removeTab(0)  # Geral
        if dlg.exec_() == QDialog.Accepted:
            _, _, _, _, novos_mods = dlg.get_config()
            item._mods = list(novos_mods or [])
        item.setSelected(False)
        if self.scene:
            self.scene.clearSelection()

    def _configurar_touch_area(self, touch_item: TouchAreaItem):
        dlg = QDialog(self)
        dlg.setWindowTitle("Configurar Área de Toque")
        layout = QVBoxLayout(dlg)

        # Tipo de destino
        layout.addWidget(QLabel("Tipo de destino:"))
        type_combo = QComboBox()
        type_combo.addItems(["tag", "tela"])
        type_combo.setCurrentText(touch_item.target_type)
        layout.addWidget(type_combo)

        # Valor
        layout.addWidget(QLabel("Valor:"))
        value_combo = QComboBox()
        if touch_item.target_type == "tag":
            # lista de tags visíveis no tab atual
            try:
                vars_tab = self.main_window.tab_widget.currentWidget().variaveis
                value_combo.addItems([v.tag for v in vars_tab])
            except Exception:
                pass
        else:
            try:
                value_combo.addItems([self.main_window.tab_widget.tabText(i)
                                    for i in range(self.main_window.tab_widget.count())])
            except Exception:
                pass
        value_combo.setEditable(True)
        value_combo.setCurrentText(touch_item.target_value)
        layout.addWidget(value_combo)

        # Cor da borda
        btn_color = QPushButton("Escolher cor da borda")
        def choose_color():
            c = QColorDialog.getColor(touch_item.border_color, self)
            if c.isValid(): touch_item.border_color = c
        btn_color.clicked.connect(choose_color)
        layout.addWidget(btn_color)

        # Largura e altura
        layout.addWidget(QLabel("Largura:"))
        width_input = QDoubleSpinBox(); width_input.setRange(10, 1000); width_input.setValue(touch_item.rect().width())
        layout.addWidget(width_input)
        layout.addWidget(QLabel("Altura:"))
        height_input = QDoubleSpinBox(); height_input.setRange(10, 1000); height_input.setValue(touch_item.rect().height())
        layout.addWidget(height_input)

        # OK
        btn_ok = QPushButton("OK")
        
        def apply_and_close():
            touch_item.target_type = type_combo.currentText()
            touch_item.target_value = value_combo.currentText()
            touch_item.setRect(0, 0, width_input.value(), height_input.value())
            dlg.accept()
        btn_ok.clicked.connect(apply_and_close)
        layout.addWidget(btn_ok)

        dlg.exec_()

    def inserir_variavel_digital_modelo(self, tag: str = None):
        """
        Cria (ou garante) uma variável digital.
        - Se 'tag' vier None, gera DI###.
        - Retorna a TAG criada/garantida.
        """
        from PyQt5.QtWidgets import QGraphicsTextItem
        vg = VariaveisGlobais()

        # define nome
        if not tag:
            used = {getattr(v, "tag", "") for v in self.variaveis}
            seq = 1
            while f"DI{seq:03d}" in used:
                seq += 1
            tag = f"DI{seq:03d}"
        else:
            # se já existe no canvas, só garante no singleton e retorna
            for v in self.variaveis:
                if getattr(v, "tag", "") == tag:
                    vg.set(f"{tag}.tipo", "DIG")
                    for i in range(6): vg.set(f"{tag}.PV{i}", int(vg.get(f"{tag}.PV{i}", 0) or 0))
                    if vg.get(f"{tag}.digi.map", None) is None:
                        vg.set(f"{tag}.digi.map", {
                            "PV0": {"text0": "LIGA", "text1": "LIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
                            "PV1": {"text0": "DESLIGA", "text1": "DESLIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
                            "PV2": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
                            "PV3": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
                            "PV4": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
                            "PV5": {"text0": "PARADO",  "text1": "OPERANDO", "visible": True, "law": "", "pulse": False, "confirm": True}
                        })
                    return tag

        # cria item invisível/off-canvas
        item = EditableVariable()
        item.tag = tag
        item.setPlainText(tag)
        off_x = (getattr(self, "area_largura", 1920)) + 5000
        off_y = (getattr(self, "area_altura", 1080)) + 5000
        item.setPos(off_x, off_y)
        item.setVisible(False)
        item.setAcceptedMouseButtons(Qt.NoButton)
        item.setFlag(QGraphicsItem.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.ItemIsMovable, False)
        item.setFlag(QGraphicsItem.ItemIsFocusable, False)
        item.setEnabled(False)
        item.hidden_offcanvas = True

        self.scene.addItem(item)
        self.variaveis.append(item)

        # singleton
        vg.inicializar_tag(tag)
        vg.set(f"{tag}.tipo", "DIG")
        for i in range(6):
            vg.set(f"{tag}.PV{i}", 0)
        vg.set(f"{tag}.digi.map", {
            "PV0": {"text0": "LIGA", "text1": "LIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
            "PV1": {"text0": "DESLIGA", "text1": "DESLIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
            "PV2": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV3": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV4": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV5": {"text0": "PARADO",  "text1": "OPERANDO", "visible": True, "law": "", "pulse": False, "confirm": True}
        })

        print(f"[+] Variável digital criada (off-canvas, oculta): {tag}")
        return tag



# ... seus imports no topo ...
from PyQt5.QtWidgets import (
    # ...
    QListWidget, QListWidgetItem, QFormLayout, QSpinBox
)
# ...

from singleton import VariaveisGlobais

# =========================================================
#  DIALOGO: Editor de Variável Digital (PV0..PV5 + Modificadores)
# =========================================================
class DigitalVarEditor(QDialog):
    """
    Editor de variável DIGITAL (PV0..PV5):
      - Texto(0), Texto(1), Visível e Lei por PV.
    Persiste em:
      vg[f"{tag}.digi.map"] = {
         "PV0": {"text0": "...", "text1": "...", "visible": True, "law": "..."},
         ...
      }
      vg[f"{tag}.tipo"] = "DIG"
    """
    def __init__(self, tag, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Variável Digital • {tag}")
        self.resize(640, 360)
        self.tag = tag
        self.vg = VariaveisGlobais()

        self._ensure_default_map()

        main = QVBoxLayout(self)

        # Tabela PV0..PV5
        grid = QGridLayout()
        grid.setHorizontalSpacing(8); grid.setVerticalSpacing(6)

        # --- cabeçalhos ---
        hdr = ["PV", "Texto (0)", "Texto (1)", "Visível", "Pulso", "Confirmação", "Lei (opcional)"]
        for c, t in enumerate(hdr):
            lbl = QLabel(t); lbl.setStyleSheet("font-weight:600;")
            grid.addWidget(lbl, 0, c)

        self.rows = []  # lista de dicts por PV
        m = self.vg.get(f"{self.tag}.digi.map", {}) or {}
        for i in range(6):
            key = f"PV{i}"
            cfg = m.get(key, {"text0": key, "text1": key, "visible": False, "law": ""})

            lbl_pv = QLabel(key)
            ed_t0 = QLineEdit(cfg.get("text0", key))
            ed_t1 = QLineEdit(cfg.get("text1", key))
            ck_vis = QCheckBox(); ck_vis.setChecked(bool(cfg.get("visible", False)))
            ck_pulse = QCheckBox(); ck_pulse.setChecked(bool(cfg.get("pulse", True if i in (0,1) else False)))
            ck_confirm = QCheckBox(); ck_confirm.setChecked(bool(cfg.get("confirm", False)))
            ed_law = QLineEdit(cfg.get("law", ""))

            r = {"key": key, "t0": ed_t0, "t1": ed_t1, "vis": ck_vis, "pulse": ck_pulse, "confirm": ck_confirm, "law": ed_law}
            self.rows.append(r)

            row = i + 1
            grid.addWidget(lbl_pv,    row, 0)
            grid.addWidget(ed_t0,     row, 1)
            grid.addWidget(ed_t1,     row, 2)
            grid.addWidget(ck_vis,    row, 3)
            grid.addWidget(ck_pulse,  row, 4)
            grid.addWidget(ck_confirm,row, 5)
            grid.addWidget(ed_law,    row, 6)


        main.addLayout(grid)

        # Botões
        btns = QHBoxLayout()
        bt_ok = QPushButton("Salvar"); bt_ok.clicked.connect(self._salvar)
        bt_cancel = QPushButton("Cancelar"); bt_cancel.clicked.connect(self.reject)
        btns.addStretch(1); btns.addWidget(bt_ok); btns.addWidget(bt_cancel)
        main.addLayout(btns)

    def _ensure_default_map(self):
        """Se não houver mapa, cria um padrão amigável para 'status de bomba'."""
        if self.vg.get(f"{self.tag}.digi.map", None) is not None:
            return
        default_map = {
            "PV0": {"text0": "LIGA", "text1": "LIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
            "PV1": {"text0": "DESLIGA", "text1": "DESLIGA", "visible": True, "law": "", "pulse": True, "confirm": True},
            "PV2": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV3": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV4": {"text0": "...", "text1": "...", "visible": False, "law": "", "pulse": False, "confirm": True},
            "PV5": {"text0": "PARADO",  "text1": "OPERANDO", "visible": True, "law": "", "pulse": False, "confirm": True}


        }
        self.vg.set(f"{self.tag}.digi.map", default_map)

    def _salvar(self):
        m = {}
        for r in self.rows:
            m[r["key"]] = {
                "text0": r["t0"].text().strip(),
                "text1": r["t1"].text().strip(),
                "visible": bool(r["vis"].isChecked()),
                "pulse": bool(r["pulse"].isChecked()),
                "confirm": bool(r["confirm"].isChecked()),
                "law": r["law"].text().strip(),
            }
        self.vg.set(f"{self.tag}.digi.map", m)
        self.vg.set(f"{self.tag}.tipo", "DIG")
        self.accept()

# =========================================================
#  DIALOGO: Central de Variáveis (abas Analógicas / Digitais)
# =========================================================
class VariaveisCentralDialog(QDialog):
    """
    Abas:
      - Analógicas: lista tudo que NÃO é DIG → 2 cliques abre ConfigVariavelDialog
      - Digitais  : lista DIG → Add / Edit / Remover (abre DigitalVarEditor)
    """
    def __init__(self, canvas: 'SimuladorCanvas', parent=None):
        super().__init__(parent)
        self.setWindowTitle("Central de Variáveis")
        self.resize(520, 420)
        self.canvas = canvas
        self.vg = VariaveisGlobais()
        self.show()  # abre já com a lista; se preferir modal, mantenha exec_() lá no main

        main = QVBoxLayout(self)
        self.tabs = QTabWidget(); main.addWidget(self.tabs)

        # --- Analógicas
        w_ana = QWidget(); lay_ana = QVBoxLayout(w_ana)
        self.lst_ana = QListWidget(); lay_ana.addWidget(self.lst_ana)
        bt_edit_ana = QPushButton("Editar"); bt_edit_ana.clicked.connect(self._editar_analogica)
        lay_ana.addWidget(bt_edit_ana)
        self.tabs.addTab(w_ana, "Analógicas")
        # Dentro de VariaveisCentralDialog.__init__ (na aba Analógicas)
        row_ana = QHBoxLayout()
        bt_add_ana = QPushButton("Remover Analógica"); bt_add_ana.clicked.connect(self._remover_analogica)
        row_ana.addWidget(bt_add_ana)
        lay_ana.addLayout(row_ana)


        # --- Digitais
        w_dig = QWidget(); lay_dig = QVBoxLayout(w_dig)
        self.lst_dig = QListWidget(); lay_dig.addWidget(self.lst_dig)
        row_dig = QHBoxLayout()
        bt_add_dig = QPushButton("Adicionar Digital"); bt_add_dig.clicked.connect(self._adicionar_digital)
        bt_edit_dig = QPushButton("Editar"); bt_edit_dig.clicked.connect(self._editar_digital)
        bt_ren_dig  = QPushButton("Renomear"); bt_ren_dig.clicked.connect(self._renomear_digital)
        bt_del_dig = QPushButton("Remover"); bt_del_dig.clicked.connect(self._remover_digital)
        row_dig.addWidget(bt_add_dig)
        row_dig.addWidget(bt_edit_dig)
        row_dig.addWidget(bt_ren_dig)  
        row_dig.addWidget(bt_del_dig)
        lay_dig.addLayout(row_dig)
        self.tabs.addTab(w_dig, "Digitais")

        self.lst_ana.itemDoubleClicked.connect(lambda *_: self._editar_analogica())
        self.lst_dig.itemDoubleClicked.connect(lambda *_: self._editar_digital())
        self._popular_listas()

    def _remover_analogica(self):
        from PyQt5.QtWidgets import QMessageBox
        item = self.lst_ana.currentItem()
        if not item:
            QMessageBox.information(self, "Remover", "Selecione uma variável analógica na lista.")
            return

        base = item.text().strip().upper()
        if QMessageBox.question(
            self, "Confirmar remoção",
            f"Remover a TAG '{base}'?\nIsso também remove equações analógicas com LHS dessa TAG.",
        ) != QMessageBox.Yes:
            return

        vg = self.vg  # VariaveisGlobais()

        # ---- remover chaves do store (pv/sp/mv/controle/tipo/auxiliares com prefixo) ----
        def _del_prefix(prefix: str):
            # remove no store principal
            for attr in ("_data", "_store", "store", "data"):
                d = getattr(vg, attr, None)
                if isinstance(d, dict):
                    for k in list(d.keys()):
                        if isinstance(k, str) and (k == f"{base}.tipo" or k == f"{base}.controle" or k.startswith(prefix)):
                            try: del d[k]
                            except Exception: pass
            # histórico
            hist = getattr(vg, "historico", None)
            if isinstance(hist, dict):
                for k in list(hist.keys()):
                    if isinstance(k, str) and k.startswith(prefix):
                        try: del hist[k]
                        except Exception: pass
            # buffer
            buf = getattr(vg, "buffer", None)
            if isinstance(buf, dict):
                for k in list(buf.keys()):
                    if isinstance(k, str) and k.startswith(prefix):
                        try: del buf[k]
                        except Exception: pass

        _del_prefix(f"{base}.")

        # ---- remover equações analógicas com LHS dessa TAG ----
        eq = vg.get("analog.eq", []) or []
        def _lhs_base(lhs: str) -> str:
            lhs = (lhs or "").strip()
            if not lhs: return ""
            if "=" in lhs: lhs = lhs.split("=", 1)[0].strip()
            if "." in lhs: lhs = lhs.split(".", 1)[0].strip()
            return lhs.upper()

        if isinstance(eq, list):
            new_eq = []
            for it in eq:
                lhs = ""
                if isinstance(it, dict):
                    lhs = it.get("lhs", "")
                elif isinstance(it, str):
                    lhs = it
                if _lhs_base(lhs) != base:
                    new_eq.append(it)
            vg.set("analog.eq", new_eq)

        # repopula a lista e limpa seleção
        self._popular_listas()
        self.lst_ana.clearSelection()

            
    def _popular_listas(self):
        self.lst_ana.clear()
        self.lst_dig.clear()

        # 1) Tentar obter o dicionário interno do VariaveisGlobais
        vg_dict = None
        for attr in ("_data", "_store", "store", "data"):
            if hasattr(self.vg, attr) and isinstance(getattr(self.vg, attr), dict):
                vg_dict = getattr(self.vg, attr)
                break

        tags = set()

        if isinstance(vg_dict, dict):
            # 2) Extrai TAGs a partir das chaves "TAG.campo"
            for k in vg_dict.keys():
                if isinstance(k, str) and "." in k:
                    tags.add(k.split(".", 1)[0])

        # 3) Fallback: inclui também o que houver no canvas (garante nada ficar de fora)
        if getattr(self, "canvas", None):
            for v in getattr(self.canvas, "variaveis", []):
                t = getattr(v, "tag", None)
                if t:
                    tags.add(t)
        # 3.1) Também coleta TAGs definidas nas Equações Analógicas (analog.eq)
        eq = self.vg.get("analog.eq", []) or []
        def _lhs_to_base(lhs: str) -> str:
            lhs = (lhs or "").strip()
            if not lhs:
                return ""
            base = lhs.split("=", 1)[0].strip() if "=" in lhs else lhs
            if "." in base:
                base = base.split(".", 1)[0].strip()
            return base

        if isinstance(eq, list):
            for it in eq:
                if isinstance(it, dict):
                    base = _lhs_to_base(it.get("lhs", ""))
                elif isinstance(it, str):
                    base = _lhs_to_base(it)
                else:
                    continue
                if base:
                    tags.add(base)
        # 4) Preenche listas por tipo (DIG x não-DIG)
        for tag in sorted(tags):
            tipo = (self.vg.get(f"{tag}.tipo", "ANA") or "ANA").upper()
            if tipo == "DIG":
                self.lst_dig.addItem(tag)
            elif tipo != "REM":   # ignora removidas
                self.lst_ana.addItem(tag)
        eq = self.vg.get("analog.eq", []) or []
        def _lhs_to_base(lhs: str) -> str:
            lhs = (lhs or "").strip()
            if not lhs: return ""
            if "=" in lhs: lhs = lhs.split("=", 1)[0].strip()
            if "." in lhs: lhs = lhs.split(".", 1)[0].strip()
            return lhs.upper()

        if isinstance(eq, list):
            for it in eq:
                if isinstance(it, dict):
                    base = _lhs_to_base(it.get("lhs", ""))
                elif isinstance(it, str):
                    base = _lhs_to_base(it)
                else:
                    continue
                if base:
                    tags.add(base)       


    def _sel(self, lst): 
        it = lst.currentItem()
        return it.text().strip() if it else ""

    def _editar_analogica(self):
        tag = self._sel(self.lst_ana)
        if not tag:
            return
        item = None
        if getattr(self, "canvas", None):
            item = next((v for v in self.canvas.variaveis if getattr(v, "tag", "") == tag), None)
        if item is None:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Variável não está na tela",
                                    f"A variável '{tag}' não está no canvas desta tela.\n"
                                    f"Adicione-a à tela para editar os parâmetros analógicos.")
            return
        self.canvas.abrir_editor_variavel(item)
        self._popular_listas()


    def _adicionar_digital(self):
        if not self.canvas:
            return
        new_tag = self.canvas.inserir_variavel_digital_modelo()
        self._popular_listas()
        if not new_tag:
            return
        # seleciona a nova tag e abre editor
        for i in range(self.lst_dig.count()):
            if self.lst_dig.item(i).text().strip() == new_tag:
                self.lst_dig.setCurrentRow(i)
                break
        _ensure_digital_defaults(self.vg, new_tag)
        dlg = DigitalVarEditor(new_tag, self)
        dlg.exec_()
        self._popular_listas()


    def _editar_digital(self):
        tag = self._sel(self.lst_dig)
        if not tag:
            # se nada selecionado, pega o primeiro da lista
            if self.lst_dig.count() == 0:
                QMessageBox.information(self, "Sem digitais",
                                        "Não há variáveis digitais cadastradas.")
                return
            tag = self.lst_dig.item(0).text().strip()
            self.lst_dig.setCurrentRow(0)

        _ensure_digital_defaults(self.vg, tag)

        dlg = DigitalVarEditor(tag, self)
        dlg.exec_()
        self._popular_listas()

    def _renomear_digital(self):
        tag = self._sel(self.lst_dig)
        if not tag:
            if self.lst_dig.count() == 0:
                QMessageBox.information(self, "Digitais", "Não há variáveis digitais na lista.")
                return
            self.lst_dig.setCurrentRow(0)
            tag = self._sel(self.lst_dig)

        # pergunta o novo nome
        novo, ok = QInputDialog.getText(self, "Renomear variável digital",
                                        f"Novo nome para '{tag}':", QLineEdit.Normal, tag)
        if not ok or not novo:
            return
        novo = novo.strip()
        if "." in novo:
            QMessageBox.warning(self, "Nome inválido", "A TAG não pode conter ponto (.).")
            return
        if novo == tag:
            return
        # LIMPA QUALQUER RESÍDUO DO NOVO NOME (se já existiu antes)
        _purge_tag(self.vg, novo)

        # agora sim, move old_tag.* -> new_tag.*
        renomear_tag_no_vg(self.vg, tag, novo)

        # reforça defaults digitais (continua igual)
        _ensure_digital_defaults(self.vg, novo)
        # valida duplicidade
        tags_existentes = set(_listar_tags_do_vg(self.vg, self.canvas))
        if novo in tags_existentes:
            QMessageBox.warning(self, "TAG existente", f"Já existe uma variável chamada '{novo}'.")
            return

        # renomeia no VariaveisGlobais
        renomear_tag_no_vg(self.vg, tag, novo)

        # atualiza referências no canvas
        atualizar_referencias_no_canvas(self.canvas, tag, novo)

        # refresh da lista e selecionar o novo
        self._popular_listas()
        for i in range(self.lst_dig.count()):
            if self.lst_dig.item(i).text().strip() == novo:
                self.lst_dig.setCurrentRow(i)
                break

        QMessageBox.information(self, "OK", f"Variável '{tag}' foi renomeada para '{novo}'.")


    def _remover_digital(self):
        tag = self._sel(self.lst_dig)
        if not tag:
            return
        # remove do canvas (se existir) e marca tipo como REM no singleton
        for it in list(self.canvas.scene.items()):
            if hasattr(it, "tag") and getattr(it, "tag", "") == tag:
                self.canvas.scene.removeItem(it)
        self.vg.set(f"{tag}.tipo", "REM")
        self._popular_listas()



# =========================================================
#  CENTRAL DE LÓGICA + EDITOR GRAFCET (placeholder)
# =========================================================
class GrafcetEditorDialog(QDialog):
    """
    Editor simples de Grafcet:
      - Nome da lógica
      - Lista de 'Passos' e 'Transições' (texto simples)
    Guarda tudo em vg.set(f"logicas.{nome}", {"passos": [...], "transicoes": [...]})
    """
    def __init__(self, nome="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editor de Grafcet • {nome or '(novo)'}")
        self.resize(560, 460)
        self.vg = VariaveisGlobais()
        self.nome = nome

        data = self.vg.get(f"logicas.{nome}", {}) if nome else {}

        main = QVBoxLayout(self)
        self.ed_nome = QLineEdit(nome)
        main.addWidget(QLabel("Nome da lógica:"))
        main.addWidget(self.ed_nome)

        cols = QHBoxLayout()
        # passos
        bx_p = QVBoxLayout(); bx_p.addWidget(QLabel("Passos (1 por linha)"))
        self.txt_passos = QPlainTextEdit("\n".join(data.get("passos", [])))
        bx_p.addWidget(self.txt_passos)
        cols.addLayout(bx_p)
        # transições
        bx_t = QVBoxLayout(); bx_t.addWidget(QLabel("Transições (1 por linha)"))
        self.txt_trans = QPlainTextEdit("\n".join(data.get("transicoes", [])))
        bx_t.addWidget(self.txt_trans)
        cols.addLayout(bx_t)
        main.addLayout(cols)

        row = QHBoxLayout()
        bt_ok = QPushButton("Salvar"); bt_ok.clicked.connect(self._salvar)
        bt_cancel = QPushButton("Cancelar"); bt_cancel.clicked.connect(self.reject)
        row.addWidget(bt_ok); row.addWidget(bt_cancel)
        main.addLayout(row)

    def _salvar(self):
        nome = self.ed_nome.text().strip()
        if not nome:
            return
        passos = [l.strip() for l in self.txt_passos.toPlainText().splitlines() if l.strip()]
        trans = [l.strip() for l in self.txt_trans.toPlainText().splitlines() if l.strip()]
        self.vg.set(f"logicas.{nome}", {"passos": passos, "transicoes": trans})
        self.accept()


class GrafcetEditorDialog(QDialog):
    """
    Editor simples de Grafcet (passos/transições como texto).
    Persiste em: vg["logicas"][nome] = {"passos":[...], "transicoes":[...]}
    """
    def __init__(self, nome="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editor de Grafcet • {nome or '(novo)'}")
        self.resize(560, 460)
        self.vg = VariaveisGlobais()
        self.nome = nome
        data = (self.vg.get("logicas", {}) or {}).get(nome, {})

        main = QVBoxLayout(self)
        self.ed_nome = QLineEdit(nome)
        main.addWidget(QLabel("Nome da lógica:")); main.addWidget(self.ed_nome)

        cols = QHBoxLayout()
        bx_p = QVBoxLayout(); bx_p.addWidget(QLabel("Passos (1 por linha)"))
        self.txt_passos = QPlainTextEdit("\n".join(data.get("passos", [])))
        bx_p.addWidget(self.txt_passos); cols.addLayout(bx_p)

        bx_t = QVBoxLayout(); bx_t.addWidget(QLabel("Transições (1 por linha)"))
        self.txt_trans = QPlainTextEdit("\n".join(data.get("transicoes", [])))
        bx_t.addWidget(self.txt_trans); cols.addLayout(bx_t)

        main.addLayout(cols)
        row = QHBoxLayout()
        bt_ok = QPushButton("Salvar"); bt_ok.clicked.connect(self._salvar)
        bt_cancel = QPushButton("Cancelar"); bt_cancel.clicked.connect(self.reject)
        row.addWidget(bt_ok); row.addWidget(bt_cancel); main.addLayout(row)

    def _salvar(self):
        nome = self.ed_nome.text().strip()
        if not nome:
            return
        d = self.vg.get("logicas", {}) or {}
        d[nome] = {
            "passos": [l.strip() for l in self.txt_passos.toPlainText().splitlines() if l.strip()],
            "transicoes": [l.strip() for l in self.txt_trans.toPlainText().splitlines() if l.strip()],
        }
        self.vg.set("logicas", d)
        self.accept()


from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QHBoxLayout, QListWidget,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QFormLayout,
    QLineEdit, QPlainTextEdit, QCheckBox, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt
import uuid

# se já existir VariaveisGlobais no seu módulo
from singleton import VariaveisGlobais

class LogicaCentralDialog(QDialog):
    """Central com 3 abas: Grafcet, IQ/Ladder e Equações Analógicas (em árvore)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Central de Lógica")
        self.resize(900, 560)
        self.vg = VariaveisGlobais()

        main = QVBoxLayout(self)
        self.tabs = QTabWidget(); main.addWidget(self.tabs)

        # --- Aba GRAFCET ---
        w_g = QWidget(); vg_layout = QVBoxLayout(w_g)
        self.lst_g = QListWidget(); vg_layout.addWidget(self.lst_g)
        row_g = QHBoxLayout()
        bt_add_g = QPushButton("Adicionar"); bt_add_g.clicked.connect(self._add_g)
        bt_edit_g = QPushButton("Editar");   bt_edit_g.clicked.connect(self._edit_g)
        bt_del_g = QPushButton("Remover");   bt_del_g.clicked.connect(self._del_g)
        row_g.addWidget(bt_add_g); row_g.addWidget(bt_edit_g); row_g.addWidget(bt_del_g)
        vg_layout.addLayout(row_g)
        self.tabs.addTab(w_g, "Grafcet")

        # --- Aba IQ/Ladder ---
        w_iq = QWidget(); vi_layout = QVBoxLayout(w_iq)
        self.lst_iq = QListWidget(); vi_layout.addWidget(self.lst_iq)
        row_iq = QHBoxLayout()
        bt_add_iq = QPushButton("Adicionar"); bt_add_iq.clicked.connect(self._add_iq)
        bt_edit_iq = QPushButton("Editar");   bt_edit_iq.clicked.connect(self._edit_iq)
        bt_del_iq = QPushButton("Remover");   bt_del_iq.clicked.connect(self._del_iq)
        row_iq.addWidget(bt_add_iq); row_iq.addWidget(bt_edit_iq); row_iq.addWidget(bt_del_iq)
        vi_layout.addLayout(row_iq)
        self.tabs.addTab(w_iq, "IQ/Ladder")

        # --- Equações Analógicas (Árvore) ---
        w_eq = QWidget(); lay_eq = QVBoxLayout(w_eq)
        split = QSplitter(Qt.Horizontal); split.setChildrenCollapsible(False)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 3)
        lay_eq.addWidget(split)

        # Árvore à esquerda
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Pastas / Equações")
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setDragDropMode(self.tree.InternalMove)  # drag interno (opcional)
        split.addWidget(self.tree)

        # Formulário à direita
        right = QWidget(); rlay = QVBoxLayout(right)
        form = QFormLayout()
        self.ed_nome = QLineEdit()
        self.cmb_tipo_item = QComboBox(); self.cmb_tipo_item.addItems(["equation","folder"])
        self.ed_lhs = QLineEdit(); self.ed_lhs.setPlaceholderText("ex.: TI001.pv (assume .pv se omitir)")
        self.txt_rhs = QPlainTextEdit(); self.txt_rhs.setPlaceholderText("expr: G(), passado(), CLAMP(), math, dt…")
        self.chk_on = QCheckBox("Habilitado"); self.chk_on.setChecked(True)
        form.addRow("Nome", self.ed_nome)
        form.addRow("Tipo", self.cmb_tipo_item)
        form.addRow("LHS",  self.ed_lhs)
        form.addRow("RHS",  self.txt_rhs)
        form.addRow("",     self.chk_on)
        rlay.addLayout(form)

        row = QHBoxLayout()
        self.bt_new_folder = QPushButton("Nova Pasta")
        self.bt_new_eq     = QPushButton("Nova Equação")
        self.bt_dup        = QPushButton("Duplicar")
        self.bt_del        = QPushButton("Excluir")
        self.bt_up         = QPushButton("↑")
        self.bt_dn         = QPushButton("↓")
        self.bt_save       = QPushButton("Salvar item")
        self.bt_save_all   = QPushButton("Salvar tudo")
        for b in (self.bt_new_folder, self.bt_new_eq, self.bt_dup, self.bt_del, self.bt_up, self.bt_dn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.bt_save); row.addWidget(self.bt_save_all)
        rlay.addLayout(row)
        split.addWidget(right)

        self.tabs.addTab(w_eq, "Equações Analógicas")

        # Liga sinais
        self.tree.currentItemChanged.connect(self._on_tree_current_changed)
        self.bt_new_folder.clicked.connect(self._on_new_folder)
        self.bt_new_eq.clicked.connect(self._on_new_equation)
        self.bt_dup.clicked.connect(self._on_dup_node)
        self.bt_del.clicked.connect(self._on_del_node)
        self.bt_up.clicked.connect(lambda: self._move_node(-1))
        self.bt_dn.clicked.connect(lambda: self._move_node(+1))
        self.bt_save.clicked.connect(self._save_item)
        self.bt_save_all.clicked.connect(self._save_all)

        # Inicializa dados/árvore
        self._tree_load()
        self._reload()

    # ================== MÉTODOS: ÁRVORE ==================

    def _get_tree(self):
        """Obtém árvore; se não existir, cria vazia.
           (Opcional) migra analog.eq plano para uma pasta 'Importado'."""
        tree = self.vg.get("analog.tree", None)
        if tree is None:
            # migração simples do formato antigo (se existir)
            flat = self.vg.get("analog.eq", []) or []
            children = []
            for e in flat:
                if isinstance(e, dict) and e.get("lhs") and e.get("rhs"):
                    children.append({
                        "id": str(uuid.uuid4()), "type": "equation",
                        "name": e.get("nome", e.get("lhs")),
                        "lhs": e.get("lhs"), "rhs": e.get("rhs"),
                        "enabled": bool(e.get("habilitado", True)),
                    })
                elif isinstance(e, str) and "=" in e:
                    L, R = [p.strip() for p in e.split("=", 1)]
                    if "." not in L: L = f"{L}.pv"
                    children.append({
                        "id": str(uuid.uuid4()), "type": "equation",
                        "name": L, "lhs": L, "rhs": R, "enabled": True,
                    })
            tree = {"root": ([{"id": str(uuid.uuid4()), "type": "folder", "name": "Importado", "children": children}] if children else [])}
            self.vg.set("analog.tree", tree)
        return tree

    def _tree_load(self):
        self.tree.clear()
        tree = self._get_tree()
        def _mk(node, parent=None):
            it = QTreeWidgetItem(parent or self.tree, [node.get("name","(sem nome)")])
            it.setData(0, Qt.UserRole, node)
            if node.get("type") == "folder":
                it.setExpanded(True)
                for ch in node.get("children", []) or []:
                    _mk(ch, it)
        for n in (tree or {}).get("root", []):
            _mk(n)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _tree_dump(self):
        def _node_from_item(it: QTreeWidgetItem):
            node = it.data(0, Qt.UserRole) or {}
            node.setdefault("id", node.get("id", str(uuid.uuid4())))
            node["name"] = it.text(0)
            t = node.get("type", "equation")
            node["type"] = t
            if t == "folder":
                node["children"] = []
                for i in range(it.childCount()):
                    node["children"].append(_node_from_item(it.child(i)))
            else:
                node.setdefault("enabled", True)
                node.setdefault("lhs", ""); node.setdefault("rhs", "")
            return node
        root = []
        for i in range(self.tree.topLevelItemCount()):
            root.append(_node_from_item(self.tree.topLevelItem(i)))
        self.vg.set("analog.tree", {"root": root})

    def _on_tree_current_changed(self, cur: QTreeWidgetItem, prev: QTreeWidgetItem):
        if not cur:
            self.ed_nome.clear(); self.ed_lhs.clear(); self.txt_rhs.clear(); self.chk_on.setChecked(True)
            return
        node = cur.data(0, Qt.UserRole) or {}
        self.ed_nome.setText(node.get("name",""))
        self.cmb_tipo_item.setCurrentText(node.get("type","equation"))
        is_folder = (node.get("type") == "folder")
        self.ed_lhs.setEnabled(not is_folder); self.txt_rhs.setEnabled(not is_folder); self.chk_on.setEnabled(not is_folder)
        self.ed_lhs.setText("" if is_folder else node.get("lhs",""))
        self.txt_rhs.setPlainText("" if is_folder else node.get("rhs",""))
        self.chk_on.setChecked(True if is_folder else bool(node.get("enabled", True)))

    def _apply_form_to_item(self, it: QTreeWidgetItem):
        if not it: return
        node = it.data(0, Qt.UserRole) or {}
        node["name"] = self.ed_nome.text().strip() or node.get("name","(sem nome)")
        node["type"] = self.cmb_tipo_item.currentText()
        if node["type"] == "equation":
            lhs = self.ed_lhs.text().strip()
            if lhs and "." not in lhs: lhs = f"{lhs}.pv"
            node["lhs"] = lhs
            node["rhs"] = self.txt_rhs.toPlainText().strip()
            node["enabled"] = self.chk_on.isChecked()
        it.setText(0, node["name"])
        it.setData(0, Qt.UserRole, node)

    def _on_new_folder(self):
        parent = self.tree.currentItem()
        # só permite criar dentro de pasta; se item atual não é pasta, cria no topo
        if not parent or (parent.data(0, Qt.UserRole) or {}).get("type") != "folder":
            parent = None
        node = {"id": str(uuid.uuid4()), "type": "folder", "name": "Nova Pasta", "children": []}
        it = QTreeWidgetItem(parent or self.tree, [node["name"]]); it.setData(0, Qt.UserRole, node)
        self.tree.setCurrentItem(it)

    def _on_new_equation(self):
        parent = self.tree.currentItem()
        if not parent or (parent.data(0, Qt.UserRole) or {}).get("type") != "folder":
            parent = None
        node = {"id": str(uuid.uuid4()), "type": "equation", "name": "Nova Equação", "lhs": "", "rhs": "", "enabled": True}
        it = QTreeWidgetItem(parent or self.tree, [node["name"]]); it.setData(0, Qt.UserRole, node)
        self.tree.setCurrentItem(it)

    def _on_dup_node(self):
        it = self.tree.currentItem()
        if not it: return
        node = dict(it.data(0, Qt.UserRole) or {})
        node["id"] = str(uuid.uuid4())
        node["name"] = f'{node.get("name","(sem nome)")} (cópia)'
        parent = it.parent() or self.tree.invisibleRootItem()
        newit = QTreeWidgetItem([node["name"]]); newit.setData(0, Qt.UserRole, node)
        parent.addChild(newit); self.tree.setCurrentItem(newit)

    def _on_del_node(self):
        it = self.tree.currentItem()
        if not it: return
        if QMessageBox.question(self, "Excluir", f"Excluir '{it.text(0)}'?") != QMessageBox.Yes:
            return
        parent = it.parent() or self.tree.invisibleRootItem()
        parent.removeChild(it)

    def _move_node(self, delta: int):
        it = self.tree.currentItem()
        if not it: return
        parent = it.parent() or self.tree.invisibleRootItem()
        idx = parent.indexOfChild(it)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= parent.childCount(): return
        parent.removeChild(it); parent.insertChild(new_idx, it)
        self.tree.setCurrentItem(it)

    def _ensure_analog_tag(self, base: str):
        """Fallback local caso você não tenha ensure_analog_tag() global."""
        try:
            from functions import ensure_analog_tag as _ext_ensure
            _ext_ensure(self.vg, base)
            return
        except Exception:
            pass
        if not base: return
        base = str(base).upper()
        for campo, default in (("pv",0.0),("sp",0.0),("mv",0.0)):
            if self.vg.get(f"{base}.{campo}") is None:
                self.vg.set(f"{base}.{campo}", default)
        if (self.vg.get(f"{base}.tipo") or "ANA").upper() in (None, "REM"):
            self.vg.set(f"{base}.tipo","ANA")
        conf = self.vg.get(f"{base}.controle", {}) or {}
        conf.setdefault("tipo","Temperatura")
        conf.setdefault("pv_min",0.0); conf.setdefault("pv_max",100.0)
        self.vg.set(f"{base}.controle", conf)

    def _save_item(self):
        it = self.tree.currentItem()
        if not it: return
        self._apply_form_to_item(it)
        node = it.data(0, Qt.UserRole) or {}
        if node.get("type") == "equation":
            base = (node.get("lhs","").split(".",1)[0] or "").upper()
            if base: self._ensure_analog_tag(base)
        self._tree_dump()
        QMessageBox.information(self, "Salvo", "Item salvo.")

    def _save_all(self):
        it = self.tree.currentItem()
        if it: self._apply_form_to_item(it)
        self._tree_dump()
        QMessageBox.information(self, "Salvo", "Árvore salva.")

    # ================== MÉTODOS: GRAFCET / IQ ==================

    def _sel(self, lst):
        it = lst.currentItem()
        return it.text().strip() if it else ""

    def _reload(self):
        # grafcet
        self.lst_g.clear()
        d = self.vg.get("logicas", {}) or {}
        for k in sorted(d.keys()):
            self.lst_g.addItem(k)
        # iq
        self.lst_iq.clear()
        for b in sorted(self.vg.get("iq", []) or [], key=lambda x: x.get("nome","")):
            nm = b.get("nome","")
            if nm: self.lst_iq.addItem(nm)
        # árvore já está carregada em _tree_load()

    def _add_g(self):
        dlg = GrafcetEditorDialog("", self)
        if dlg.exec_() == QDialog.Accepted:
            self._reload()

    def _edit_g(self):
        nome = self._sel(self.lst_g)
        dlg = GrafcetEditorDialog(nome, self)
        if dlg.exec_() == QDialog.Accepted:
            self._reload()

    def _del_g(self):
        nome = self._sel(self.lst_g)
        if not nome: return
        d = self.vg.get("logicas", {}) or {}
        if nome in d:
            d.pop(nome, None)
            self.vg.set("logicas", d)
        self._reload()

    # --------- IQ/LADDER ----------
    def _add_iq(self):
        dlg = IQEditorDialog("", self)
        if dlg.exec_() == QDialog.Accepted:
            self._reload()

    def _edit_iq(self):
        nome = self._sel(self.lst_iq)
        dlg = IQEditorDialog(nome, self)
        if dlg.exec_() == QDialog.Accepted:
            self._reload()

    def _del_iq(self):
        nome = self._sel(self.lst_iq)
        if not nome: return
        blocos = self.vg.get("iq", []) or []
        blocos = [b for b in blocos if b.get("nome") != nome]
        self.vg.set("iq", blocos)
        self._reload()

class IQEditorDialog(QDialog):
    """
    Editor de bloco IQ/Ladder (equações booleanas).
    Persiste em vg["iq"] = [ { "nome":str, "base":str, "equacoes":[str, ...] }, ... ]
    """
    def __init__(self, nome="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editor IQ • {nome or '(novo)'}")
        self.resize(640, 480)
        self.vg = VariaveisGlobais()
        self.nome = nome

        # carrega bloco, se existir
        blocos = self.vg.get("iq", []) or []
        cur = next((b for b in blocos if b.get("nome") == nome), {"nome": nome, "base": "", "equacoes": []})

        main = QVBoxLayout(self)

        self.ed_nome = QLineEdit(cur.get("nome", nome))
        self.ed_base = QLineEdit(cur.get("base", ""))

        main.addWidget(QLabel("Nome do bloco:"))
        main.addWidget(self.ed_nome)
        main.addWidget(QLabel("Base (prefixo para tokens sem ponto, ex.: BOMBA01):"))
        main.addWidget(self.ed_base)

        main.addWidget(QLabel("Equações (uma por linha) • Ex.:\nBOMBA01.PV0 = (CMD_LIGA & PERMISS_OK & !TRIP) | (BOMBA01.PV0 & !CMD_DESLIGA & !TRIP)"))
        self.txt_eq = QPlainTextEdit("\n".join(cur.get("equacoes", [])))
        main.addWidget(self.txt_eq)

        row = QHBoxLayout()
        bt_ok = QPushButton("Salvar"); bt_ok.clicked.connect(self._salvar)
        bt_cancel = QPushButton("Cancelar"); bt_cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(bt_ok); row.addWidget(bt_cancel)
        main.addLayout(row)

    def _salvar(self):
        nome = self.ed_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "IQ", "Informe um nome para o bloco.")
            return
        base = self.ed_base.text().strip()
        eqs = [l.strip() for l in self.txt_eq.toPlainText().splitlines() if l.strip()]

        blocos = self.vg.get("iq", []) or []

        # substitui se já existir, senão adiciona
        idx = next((i for i,b in enumerate(blocos) if b.get("nome")==nome), -1)
        payload = {"nome": nome, "base": base, "equacoes": eqs}
        if idx >= 0:
            blocos[idx] = payload
        else:
            blocos.append(payload)
        self.vg.set("iq", blocos)
        self.accept()


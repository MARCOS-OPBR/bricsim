class VariaveisGlobais:
    """
    Singleton para armazenar e compartilhar valores da simulação.
    Cada chave (ex: "TAG.pv") mantém um histórico de valores.
    Suporta buffer temporário para cálculos em duas passadas.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.dados = {}      # chave -> lista de valores
            cls._instance.buffer = {}     # valores temporários da passada 1
            cls._instance.usar_buffer = False
        return cls._instance

    def set(self, nome, valor):
        """
        Adiciona o valor ao histórico (ou ao buffer se usar_buffer=True).
        Retorna o valor para encadeamento.
        """
        if self.usar_buffer:
            self.buffer[nome] = valor
        else:
            if nome not in self.dados or not isinstance(self.dados[nome], list):
                self.dados[nome] = []
            self.dados[nome].append(valor)
        return valor

    def get(self, nome, default=0):
        """
        Retorna o valor atual.
        Se estiver em modo buffer, dá preferência ao buffer.
        """
        if self.usar_buffer and nome in self.buffer:
            return self.buffer[nome]
        if nome not in self.dados or not isinstance(self.dados[nome], list) or not self.dados[nome]:
            return default
        return self.dados[nome][-1]

    def hist(self, nome):
        """
        Retorna a lista de valores dessa chave (histórico).
        """
        val = self.dados.get(nome, [])
        if not isinstance(val, list):
            return []
        return val
    def passado(self, nome, atraso=1, default=0):
        """
        Retorna o valor de 'atraso' iterações atrás.
        atraso=1 -> último valor anterior
        atraso=2 -> penúltimo valor, etc.
        """
        val = self.hist(nome)
        if len(val) >= atraso:
            return val[-atraso]
        return default

    def atual(self, nome, default=0):
        """
        Retorna o valor atual (último registrado).
        """
        return self.get(nome, default)

    def commit_buffer(self):
        """
        Passa todos os valores do buffer para o histórico oficial.
        """
        for nome, valor in self.buffer.items():
            if nome not in self.dados or not isinstance(self.dados[nome], list):
                self.dados[nome] = []
            self.dados[nome].append(valor)
        self.buffer.clear()

    def all(self):
        return {k: list(v) for k, v in self.dados.items()}

    def inicializar_tag(self, tag):
        for sufixo in (".pv", ".sp", ".mv"):
            self.dados[f"{tag}{sufixo}"] = []

    def diagnostico(self):
        print("📋 DIAGNÓSTICO DO SINGLETON:")
        for nome, hist in self.dados.items():
            if not isinstance(hist, list): continue
            atual = hist[-1] if hist else None
            print(f" - {nome:20} → len={len(hist):3} | atual = {atual}")

    # ===== Helpers de limites e modo =====
    def _ctrl_conf(self, tag):
        return self.get(f"{tag}.controle", {}) or {}

    def _pv_limits(self, tag):
        conf = self._ctrl_conf(tag)
        pv_min = conf.get("pv_min", 0.0)
        pv_max = conf.get("pv_max", 100.0)
        if pv_min > pv_max:
            pv_min, pv_max = pv_max, pv_min
        return pv_min, pv_max

    def modo(self, tag, default="MAN"):
        return self.get(f"{tag}.modo", default)

    # ===== Setters "seguros" =====
    def set_pv(self, tag, value):
        """PV pode ser escrito pelo processo/simulações; sempre clampa em pv_min/pv_max."""
        pv_min, pv_max = self._pv_limits(tag)
        v = max(pv_min, min(pv_max, float(value)))
        return self.set(f"{tag}.pv", v)

    def set_sp(self, tag, value, *, source="user", force=False):
        """
        Edita SP respeitando o modo:
        - AUT/PRD: permite.
        - CAS: bloqueia edição manual (a não ser force=True ou source='master').
        - MAN: permite (útil pra pré‑ajuste), mas será rastreado pelo SP tracking se ligando.
        Sempre clampa em pv_min/pv_max.
        """
        m = self.modo(tag)
        if (m == "CAS") and not (force or source == "master"):
            return self.get(f"{tag}.sp", 0.0)  # ignora manualmente
        pv_min, pv_max = self._pv_limits(tag)
        v = max(pv_min, min(pv_max, float(value)))
        return self.set(f"{tag}.sp", v)

    def set_mv(self, tag, value, *, force=False):
        """
        Edita MV respeitando o modo:
        - MAN: permite.
        - AUT/CAS/PRD: bloqueia (a não ser force=True).
        Clampa em 0..100 (%).
        """
        m = self.modo(tag)
        if (m not in ("MAN",)) and not force:
            return self.get(f"{tag}.mv", 0.0)  # ignora manualmente
        try:
            v = max(0.0, min(100.0, float(value)))
        except Exception:
            v = 0.0
        return self.set(f"{tag}.mv", v)

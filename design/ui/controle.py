def aplicar_controle_PID(canvas, dt=0.1):
    from singleton import VariaveisGlobais

    vg = VariaveisGlobais()

    # ------------------- Árbitro de MV (IQ tem a palavra final) -------------------
    def _exists(vg_obj, key: str) -> bool:
        # usa um sentinela para diferenciar "existe e está 0" de "não existe"
        _S = object()
        return vg_obj.get(key, _S) is not _S

    def _arb_mv(tag: str, mv_calc: float, vg_obj=None) -> float:
        vg2 = vg_obj or vg
        key_final = f"{tag}.mv_final"
        key_iq = f"{tag}.mv_iq"
        key_perm = f"{tag}.perm_ok"

        # 1) mv_final tem prioridade total (mesmo que seja 0.0)
        _S = object()
        mv_final_val = vg2.get(key_final, _S)
        if mv_final_val is not _S:
            try:
                mv_val = float(mv_final_val)
            except Exception:
                mv_val = 0.0
            return 0.0 if mv_val < 0.0 else (100.0 if mv_val > 100.0 else mv_val)

        # 2) mv_iq tem precedência sobre PID (mesmo se 0.0)
        mv_iq_val = vg2.get(key_iq, _S)
        if mv_iq_val is not _S:
            try:
                mv_val = float(mv_iq_val)
            except Exception:
                mv_val = mv_calc
            if mv_val < 0.0:
                mv_val = 0.0
            if mv_val > 100.0:
                mv_val = 100.0
            return mv_val

        # 3) permissivo cai → força 0 (pode trocar para hold se quiser)
        perm_val = vg2.get(key_perm, 1)
        try:
            ok = bool(int(perm_val or 0))
        except Exception:
            ok = bool(perm_val)
        if not ok:
            return 0.0

        # 4) default: PID
        return 0.0 if mv_calc < 0.0 else (100.0 if mv_calc > 100.0 else mv_calc)

    # ------------------------------------------------------------------------------

    # Lista de controladores válidos
    items = [
        it
        for it in getattr(canvas, "variaveis", [])
        if hasattr(it, "controle") and it.controle.get("variavel_controlada", False)
    ]

    def _conf(item):
        conf = vg.get(f"{item.tag}.controle", {}) or {}
        pv_tag = item.controle.get("pv_tag", f"{item.tag}.pv")
        sp_tag = item.controle.get("sp_tag", f"{item.tag}.sp")
        mv_tag = item.controle.get("mv_tag", f"{item.tag}.mv")
        pv_min = conf.get("pv_min", item.controle.get("pv_min", 0.0))
        pv_max = conf.get("pv_max", item.controle.get("pv_max", 100.0))
        if pv_min > pv_max:
            pv_min, pv_max = pv_max, pv_min
        Kp = conf.get("Kp", item.controle.get("Kp", 1.0))
        Ki = conf.get("Ki", item.controle.get("Ki", 0.0))
        Kd = conf.get("Kd", item.controle.get("Kd", 0.0))
        acao = (item.controle.get("acao", "direta")).lower()
        sign = 1 if acao == "direta" else -1
        sp_tracking = conf.get("sp_tracking", item.controle.get("sp_tracking", False))
        mv_write_tag = conf.get("mv_write_tag") or item.controle.get("mv_write_tag")
        return (
            conf,
            pv_tag,
            sp_tag,
            mv_tag,
            pv_min,
            pv_max,
            Kp,
            Ki,
            Kd,
            sign,
            sp_tracking,
            mv_write_tag,
        )

    def _read_pv(pv_tag, pv_min, pv_max):
        pv = vg.get(pv_tag, 0.0)
        return max(pv_min, min(pv_max, pv))

    # Buffer para duas passadas
    prev_flag = vg.usar_buffer
    vg.usar_buffer = True
    vg.buffer.clear()

    # ---------------- PASSO 0: tracking (MAN) ----------------
    for item in items:
        modo = vg.get(f"{item.tag}.modo", "MAN")
        _, pv_tag, sp_tag, _, pv_min, pv_max, *_rest = _conf(item)
        pv = _read_pv(pv_tag, pv_min, pv_max)
        sp_tracking = _rest[4]
        if modo == "MAN" and sp_tracking:
            vg.set(sp_tag, pv)

    # ---------------- PASSO 1: MASTERS (publicam SP do slave) ----------------
    for item in items:
        modo = vg.get(f"{item.tag}.modo", "MAN")
        (
            conf,
            pv_tag,
            sp_tag,
            mv_tag,
            pv_min,
            pv_max,
            Kp,
            Ki,
            Kd,
            sign,
            _spt,
            mv_write_tag,
        ) = _conf(item)

        if modo not in ("AUT", "CAS"):
            continue

        pv = _read_pv(pv_tag, pv_min, pv_max)

        if modo == "AUT":
            sp = vg.get(sp_tag, pv)
        else:
            fonte = conf.get("fonte_cascata", "") or item.controle.get(
                "fonte_cascata", sp_tag
            )
            sp = vg.get(fonte, pv)
        sp = max(pv_min, min(pv_max, sp))

        modo_prev = vg.get(f"{item.tag}.modo_prev", modo)
        if modo != modo_prev:
            mv_atual = vg.get(mv_tag, 0.0)
            integral_ant = (mv_atual - Kp * (sp - pv)) / Ki if Ki != 0 else 0.0
            vg.set(f"{item.tag}.integral", integral_ant)
        vg.set(f"{item.tag}.modo_prev", modo)

        erro = sp - pv
        erro_ant = vg.passado(f"{item.tag}.erro", 1, 0.0)
        integral_ant = vg.passado(f"{item.tag}.integral", 1, 0.0)
        derivada = (erro - erro_ant) / dt if dt > 0 else 0.0
        mv_raw = sign * (Kp * erro + Ki * (integral_ant + erro * dt) + Kd * derivada)
        mv_pid = max(0.0, min(100.0, mv_raw))
        if (mv_pid != mv_raw) and (
            (mv_pid == 100 and erro > 0) or (mv_pid == 0 and erro < 0)
        ):
            integral = integral_ant
        else:
            integral = integral_ant + erro * dt

        # publica SP no slave, se aplicável
        if mv_write_tag:
            slave_tag = mv_write_tag.split(".")[0]
            if vg.get(f"{slave_tag}.modo", "MAN") == "CAS":
                op_min = conf.get("op_min", item.controle.get("op_min", 0.0))
                op_max = conf.get("op_max", item.controle.get("op_max", 100.0))
                sp_min = conf.get("sp_min", item.controle.get("sp_min", 0.0))
                sp_max = conf.get("sp_max", item.controle.get("sp_max", 100.0))
                den = (op_max - op_min) or 1.0
                sp_slave = sp_min + ((mv_pid - op_min) * (sp_max - sp_min) / den)

                slave_conf = vg.get(f"{slave_tag}.controle", {}) or {}
                s_pvmin = slave_conf.get("pv_min", 0.0)
                s_pvmax = slave_conf.get("pv_max", 100.0)
                if s_pvmin > s_pvmax:
                    s_pvmin, s_pvmax = s_pvmax, s_pvmin
                sp_slave = max(s_pvmin, min(s_pvmax, sp_slave))
                vg.set(mv_write_tag, sp_slave)

        # >>> Árbitro decide o que vai para a MV do master (para histórico/faceplate)
        mv_final = _arb_mv(item.tag, mv_pid, vg)
        vg.set(mv_tag, mv_final)
        vg.set(f"{item.tag}.erro", erro)
        vg.set(f"{item.tag}.integral", integral)

    # ---------------- PASSO 2: SLAVES / controladores sem mv_write_tag --------
    for item in items:
        modo = vg.get(f"{item.tag}.modo", "MAN")
        (
            conf,
            pv_tag,
            sp_tag,
            mv_tag,
            pv_min,
            pv_max,
            Kp,
            Ki,
            Kd,
            sign,
            sp_tracking,
            mv_write_tag,
        ) = _conf(item)

        if mv_write_tag:
            continue  # masters já tratados no Passo 1

        pv = _read_pv(pv_tag, pv_min, pv_max)

        if modo == "MAN":
            continue
        if modo not in ("AUT", "CAS"):
            continue

        sp = vg.get(sp_tag, pv)
        sp = max(pv_min, min(pv_max, sp))

        modo_prev = vg.get(f"{item.tag}.modo_prev", modo)
        if modo != modo_prev:
            mv_atual = vg.get(mv_tag, 0.0)
            integral_ant = (mv_atual - Kp * (sp - pv)) / Ki if Ki != 0 else 0.0
            vg.set(f"{item.tag}.integral", integral_ant)
        vg.set(f"{item.tag}.modo_prev", modo)

        erro = sp - pv
        erro_ant = vg.passado(f"{item.tag}.erro", 1, 0.0)
        integral_ant = vg.passado(f"{item.tag}.integral", 1, 0.0)
        derivada = (erro - erro_ant) / dt if dt > 0 else 0.0
        mv_raw = sign * (Kp * erro + Ki * (integral_ant + erro * dt) + Kd * derivada)
        mv_pid = max(0.0, min(100.0, mv_raw))
        if (mv_pid != mv_raw) and (
            (mv_pid == 100 and erro > 0) or (mv_pid == 0 and erro < 0)
        ):
            integral = integral_ant
        else:
            integral = integral_ant + erro * dt

        # >>> Árbitro decide a saída que realmente vai para o atuador
        mv_final = _arb_mv(item.tag, mv_pid, vg)
        vg.set(mv_tag, mv_final)
        vg.set(f"{item.tag}.erro", erro)
        vg.set(f"{item.tag}.integral", integral)

    # Commit e restaura flag do buffer
    vg.commit_buffer()
    vg.usar_buffer = prev_flag

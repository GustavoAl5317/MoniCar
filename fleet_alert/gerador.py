import json
import os
import time
import logging
from datetime import datetime, timedelta
from fleet_alert import config, zabbix
from fleet_alert.timeutil import TZ_BR, agora_data_hora, agora_iso
from fleet_alert.whatsapp import enviar_texto, enviar_audio
from fleet_alert.audio import gerar_audio_base64

log = logging.getLogger(__name__)

_TANQUE_LITROS  = 80
_POLL_INTERVAL  = 30      # segundos
_RPM_MIN        = 100     # RPM mínimo para considerar ligado
_VOLT_PRESENTE  = 100     # V — acima = tensão presente
_VOLT_GEN_MIN   = 200     # V — subtensão gerador
_VOLT_GEN_MAX   = 240     # V — sobretensão gerador
_DESEQ_MAX_PCT  = 3.0     # % — desequilíbrio máximo entre fases
_BAT_MIN_V      = 11.5    # V — bateria baixa
_RPM_NORM_MIN   = 1700
_RPM_NORM_MAX   = 1900

_ESTADO_FILE = "data/gerador_estado.json"
_estado: dict = {}
_ultimo_valores: dict = {}  # exposto para o painel web


# ── Persistência ──────────────────────────────────────────────────

def _carregar():
    global _estado
    if os.path.exists(_ESTADO_FILE):
        try:
            with open(_ESTADO_FILE, encoding="utf-8") as f:
                _estado = json.load(f)
        except Exception:
            _estado = {}


def _salvar():
    os.makedirs("data", exist_ok=True)
    try:
        with open(_ESTADO_FILE, "w", encoding="utf-8") as f:
            json.dump(_estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Erro ao salvar estado gerador: %s", e)


# ── Helpers matemáticos ───────────────────────────────────────────

def _agora() -> str:
    return agora_data_hora()


def _agora_iso() -> str:
    return agora_iso()


def _litros(pct: float) -> float:
    return round(pct / 100 * _TANQUE_LITROS, 1)


def _horas_desde(iso: str) -> float:
    try:
        return (datetime.now(TZ_BR) - datetime.fromisoformat(iso)).total_seconds() / 3600
    except Exception:
        return 0.0


def _fmt_tempo(horas: float) -> str:
    h = int(horas)
    m = int((horas - h) * 60)
    return f"{h}h {m:02d}min" if h else f"{m} minutos"


def _autonomia(litros: float, taxa_lph: float) -> str:
    if taxa_lph <= 0:
        return "N/D"
    return _fmt_tempo(litros / taxa_lph)


def _previsao_zeramento(litros: float, taxa_lph: float) -> str:
    if taxa_lph <= 0:
        return "N/D"
    hora_zero = datetime.now(TZ_BR) + timedelta(hours=litros / taxa_lph)
    return hora_zero.strftime("%d/%m às %H:%M")


def _desequilibrio(l1: float, l2: float, l3: float) -> float:
    vals = [v for v in [l1, l2, l3] if v and v > 0]
    if len(vals) < 2:
        return 0.0
    media = sum(vals) / len(vals)
    return round((max(vals) - min(vals)) / media * 100, 1) if media else 0.0


def _calcular_consumo(vals: dict) -> tuple[float, float, str, str]:
    """Retorna (taxa_lph, consumo_litros_sessao, autonomia, previsao)."""
    fuel_pct = vals.get("fuel_pct", 0)
    litros = _litros(fuel_pct)
    fuel_inicio = _estado.get("fuel_ao_ligar", fuel_pct)
    hora_iso = _estado.get("hora_ligou_iso")
    taxa_lph = 0.0
    consumo_litros = 0.0
    if hora_iso:
        horas = _horas_desde(hora_iso)
        consumo_litros = _litros(max(0.0, fuel_inicio - fuel_pct))
        if horas > 0.05:
            taxa_lph = round(consumo_litros / horas, 2)
    return taxa_lph, consumo_litros, _autonomia(litros, taxa_lph), _previsao_zeramento(litros, taxa_lph)


# ── Envio WhatsApp ────────────────────────────────────────────────

def _enviar(grupo: str, texto: str):
    enviar_texto(grupo, texto)
    audio_txt = texto.replace("*", "").replace("_", "").replace("#", "")
    audio = gerar_audio_base64(audio_txt)
    if audio:
        enviar_audio(grupo, audio)


# ── Alertas de partida / desligamento ────────────────────────────

def _alerta_ligou(vals: dict):
    fuel_pct = vals.get("fuel_pct", 0.0)
    litros   = _litros(fuel_pct)
    hora_iso = _estado.get("hora_ligou_iso", _agora_iso())

    texto = (
        f"🚨 *GERADOR LIGADO*\n\n"
        f"🕒 Data/Hora: {_agora()}\n\n"
        f"⚡ *FASES GERADOR*\n"
        f"Fase 1: {vals.get('gen_l1', 0):.1f} V\n"
        f"Fase 2: {vals.get('gen_l2', 0):.1f} V\n"
        f"Fase 3: {vals.get('gen_l3', 0):.1f} V\n"
        f"Tensão média: {(vals.get('gen_l1',0)+vals.get('gen_l2',0)+vals.get('gen_l3',0))/3:.1f} V\n\n"
        f"🏢 *FASES ENEL*\n"
        f"Fase 1: {vals.get('rede_l1', 0):.1f} V\n"
        f"Fase 2: {vals.get('rede_l2', 0):.1f} V\n"
        f"Fase 3: {vals.get('rede_l3', 0):.1f} V\n\n"
        f"⚙️ RPM: {vals.get('rpm', 0):.0f}\n\n"
        f"⛽ *Combustível:* {fuel_pct:.1f}%\n"
        f"Volume estimado: {litros} L\n\n"
        f"📊 Consumo acumulado: 0% (início da sessão)"
    )
    _enviar(config.GRUPO_GERADOR_LIGA_DESLIGA, texto)
    log.info("📤 Alerta GERADOR LIGOU enviado")


def _alerta_desligou(vals: dict):
    fuel_pct       = vals.get("fuel_pct", 0.0)
    litros         = _litros(fuel_pct)
    fuel_inicio    = _estado.get("fuel_ao_ligar", fuel_pct)
    hora_iso       = _estado.get("hora_ligou_iso")
    consumo_pct    = round(max(0.0, fuel_inicio - fuel_pct), 1)
    consumo_litros = _litros(consumo_pct)
    tempo          = _fmt_tempo(_horas_desde(hora_iso)) if hora_iso else "N/D"

    texto = (
        f"✅ *GERADOR DESLIGADO*\n\n"
        f"🕒 Data/Hora: {_agora()}\n"
        f"⏱️ Tempo ligado: {tempo}\n\n"
        f"⚡ *FASES GERADOR*\n"
        f"Fase 1: {vals.get('gen_l1', 0):.1f} V\n"
        f"Fase 2: {vals.get('gen_l2', 0):.1f} V\n"
        f"Fase 3: {vals.get('gen_l3', 0):.1f} V\n\n"
        f"🏢 *FASES ENEL*\n"
        f"Fase 1: {vals.get('rede_l1', 0):.1f} V\n"
        f"Fase 2: {vals.get('rede_l2', 0):.1f} V\n"
        f"Fase 3: {vals.get('rede_l3', 0):.1f} V\n\n"
        f"⛽ *Combustível restante:* {fuel_pct:.1f}% ({litros} L)\n"
        f"📊 *Consumo nesta sessão:* {consumo_pct:.1f}% ({consumo_litros} L)"
    )
    _enviar(config.GRUPO_GERADOR_LIGA_DESLIGA, texto)
    log.info("📤 Alerta GERADOR DESLIGOU enviado")


# ── Alertas de combustível ────────────────────────────────────────

def _verificar_combustivel(vals: dict):
    fuel_pct               = vals.get("fuel_pct", 0.0)
    litros                 = _litros(fuel_pct)
    taxa_lph, consumo_l, autonomia, previsao = _calcular_consumo(vals)
    alertas_enviados       = _estado.get("alertas_fuel", [])
    hora_iso               = _estado.get("hora_ligou_iso")
    tempo_ligado           = _fmt_tempo(_horas_desde(hora_iso)) if hora_iso else "N/D"

    for threshold in [50, 30, 20, 10]:
        if fuel_pct <= threshold and threshold not in alertas_enviados:
            emoji = "🔴" if threshold <= 20 else "🟡"
            texto = (
                f"{emoji} *ALERTA DE COMBUSTÍVEL — {threshold}%*\n\n"
                f"🕒 Data/Hora: {_agora()}\n"
                f"⏱️ Gerador ligado há: {tempo_ligado}\n\n"
                f"⛽ *Nível atual: {fuel_pct:.1f}%*\n"
                f"Volume restante: {litros} L\n\n"
                f"📉 *Taxa de consumo:* {taxa_lph} L/h\n"
                f"⏱️ *Autonomia estimada:* {autonomia}\n"
                f"🕰️ *Previsão de zeramento:* {previsao}\n\n"
                f"⚙️ Consumo nesta sessão: {consumo_l:.1f} L"
            )
            _enviar(config.GRUPO_GERADOR_COMBUSTIVEL, texto)
            alertas_enviados.append(threshold)
            _estado["alertas_fuel"] = alertas_enviados
            _salvar()
            log.info("📤 Alerta combustível %d%% enviado", threshold)
            break


# ── Alertas de tensão ─────────────────────────────────────────────

def _verificar_tensao(vals: dict):
    rede   = {1: vals.get("rede_l1", 0.0), 2: vals.get("rede_l2", 0.0), 3: vals.get("rede_l3", 0.0)}
    gen    = {1: vals.get("gen_l1",  0.0), 2: vals.get("gen_l2",  0.0), 3: vals.get("gen_l3",  0.0)}
    t_ant  = _estado.get("tensao", {})

    def _linha_rede(f):
        v = rede[f]
        ok = v > _VOLT_PRESENTE
        return f"Fase {f}: {v:.1f} V {'✅' if ok else '❌'}"

    # ENEL — queda e retorno por fase
    for f in [1, 2, 3]:
        ok_ant  = t_ant.get(f"rede_ok_{f}", True)
        ok_agora = rede[f] > _VOLT_PRESENTE
        if ok_ant and not ok_agora:
            texto = (
                f"⚡ *ENEL FASE {f} CAIU*\n\n"
                f"🕒 Data/Hora: {_agora()}\n"
                f"Tensão medida: {rede[f]:.1f} V\n\n"
                f"📊 *Estado das fases ENEL:*\n"
                + "\n".join(_linha_rede(x) for x in [1, 2, 3])
            )
            _enviar(config.GRUPO_GERADOR_TENSAO, texto)
            log.info("📤 ENEL Fase %d caiu", f)
        elif not ok_ant and ok_agora:
            texto = (
                f"✅ *ENEL FASE {f} VOLTOU*\n\n"
                f"🕒 Data/Hora: {_agora()}\n"
                f"Tensão restaurada: {rede[f]:.1f} V\n\n"
                f"📊 *Estado das fases ENEL:*\n"
                + "\n".join(_linha_rede(x) for x in [1, 2, 3])
            )
            _enviar(config.GRUPO_GERADOR_TENSAO, texto)
            log.info("📤 ENEL Fase %d voltou", f)
        t_ant[f"rede_ok_{f}"] = ok_agora

    # Verificações do gerador só quando ligado
    if _estado.get("ligado") and all(gen[f] > _VOLT_PRESENTE for f in [1, 2, 3]):
        media_gen = sum(gen.values()) / 3
        deseq     = _desequilibrio(gen[1], gen[2], gen[3])

        # Desequilíbrio de fases
        deseq_ant = t_ant.get("deseq_alertado", False)
        if deseq > _DESEQ_MAX_PCT and not deseq_ant:
            texto = (
                f"⚠️ *DESEQUILÍBRIO DE FASES — GERADOR*\n\n"
                f"🕒 Data/Hora: {_agora()}\n\n"
                f"⚡ *Tensões:*\n"
                f"Fase 1: {gen[1]:.1f} V\n"
                f"Fase 2: {gen[2]:.1f} V\n"
                f"Fase 3: {gen[3]:.1f} V\n\n"
                f"📊 Tensão média: {media_gen:.1f} V\n"
                f"📉 Desequilíbrio: *{deseq:.1f}%* (limite: {_DESEQ_MAX_PCT}%)\n"
                f"Diferença máx: {max(gen.values()) - min(gen.values()):.1f} V"
            )
            _enviar(config.GRUPO_GERADOR_TENSAO, texto)
            t_ant["deseq_alertado"] = True
            log.info("📤 Alerta desequilíbrio %.1f%%", deseq)
        elif deseq <= _DESEQ_MAX_PCT:
            t_ant["deseq_alertado"] = False

        # Sub/sobretensão por fase
        for f in [1, 2, 3]:
            v = gen[f]
            k_baixa = f"gen_baixa_{f}"
            k_alta  = f"gen_alta_{f}"
            if v < _VOLT_GEN_MIN and not t_ant.get(k_baixa):
                _enviar(config.GRUPO_GERADOR_TENSAO,
                    f"📉 *SUBTENSÃO GERADOR — FASE {f}*\n\n"
                    f"🕒 {_agora()}\n"
                    f"Tensão: *{v:.1f} V* (mínimo: {_VOLT_GEN_MIN} V)\n"
                    f"Tensão média: {media_gen:.1f} V")
                t_ant[k_baixa] = True
                log.info("📤 Subtensão gerador fase %d: %.1f V", f, v)
            elif v >= _VOLT_GEN_MIN:
                t_ant[k_baixa] = False

            if v > _VOLT_GEN_MAX and not t_ant.get(k_alta):
                _enviar(config.GRUPO_GERADOR_TENSAO,
                    f"📈 *SOBRETENSÃO GERADOR — FASE {f}*\n\n"
                    f"🕒 {_agora()}\n"
                    f"Tensão: *{v:.1f} V* (máximo: {_VOLT_GEN_MAX} V)\n"
                    f"Tensão média: {media_gen:.1f} V")
                t_ant[k_alta] = True
                log.info("📤 Sobretensão gerador fase %d: %.1f V", f, v)
            elif v <= _VOLT_GEN_MAX:
                t_ant[k_alta] = False

    _estado["tensao"] = t_ant
    _salvar()


# ── Alertas de motor ──────────────────────────────────────────────

def _verificar_motor(vals: dict):
    rpm     = vals.get("rpm", 0.0)
    bateria = vals.get("bateria", 0.0)
    emerg   = str(vals.get("di_emerg", "OFF")).upper()
    oleo    = str(vals.get("di_oleo", "OFF")).upper()
    temp    = str(vals.get("di_temp",  "OFF")).upper()
    alarmes = vals.get("alarmes", 0)
    m_ant   = _estado.get("motor", {})

    # Emergency stop
    if emerg == "ON" and not m_ant.get("emerg"):
        _enviar(config.GRUPO_GERADOR_MOTOR,
            f"🛑 *EMERGENCY STOP ATIVO*\n\n"
            f"🕒 {_agora()}\n"
            f"RPM atual: {rpm:.0f}\n"
            f"O gerador foi parado por emergência!")
        m_ant["emerg"] = True
        log.info("📤 Emergency stop")
    elif emerg != "ON":
        m_ant["emerg"] = False

    # Pressão de óleo
    if oleo == "OFF" and _estado.get("ligado") and not m_ant.get("oleo"):
        _enviar(config.GRUPO_GERADOR_MOTOR,
            f"🛢️ *FALHA DE PRESSÃO DE ÓLEO*\n\n"
            f"🕒 {_agora()}\n"
            f"RPM atual: {rpm:.0f}\n"
            f"Verifique o nível de óleo imediatamente!")
        m_ant["oleo"] = True
        log.info("📤 Falha pressão óleo")
    elif oleo != "OFF":
        m_ant["oleo"] = False

    # Temperatura
    if temp == "ON" and not m_ant.get("temp"):
        _enviar(config.GRUPO_GERADOR_MOTOR,
            f"🌡️ *TEMPERATURA DE ARREFECIMENTO ALTA*\n\n"
            f"🕒 {_agora()}\n"
            f"RPM atual: {rpm:.0f}\n"
            f"Verifique o sistema de arrefecimento!")
        m_ant["temp"] = True
        log.info("📤 Temp arrefecimento alta")
    elif temp != "ON":
        m_ant["temp"] = False

    # RPM fora do padrão (só quando ligado)
    if _estado.get("ligado") and rpm > _RPM_MIN:
        if rpm < _RPM_NORM_MIN and not m_ant.get("rpm_baixo"):
            _enviar(config.GRUPO_GERADOR_MOTOR,
                f"⚠️ *RPM ABAIXO DO NORMAL*\n\n"
                f"🕒 {_agora()}\n"
                f"RPM atual: *{rpm:.0f}* (mínimo: {_RPM_NORM_MIN})\n"
                f"Verifique o regulador de velocidade.")
            m_ant["rpm_baixo"] = True
            log.info("📤 RPM baixo: %.0f", rpm)
        elif rpm >= _RPM_NORM_MIN:
            m_ant["rpm_baixo"] = False

        if rpm > _RPM_NORM_MAX and not m_ant.get("rpm_alto"):
            _enviar(config.GRUPO_GERADOR_MOTOR,
                f"⚠️ *RPM ACIMA DO NORMAL*\n\n"
                f"🕒 {_agora()}\n"
                f"RPM atual: *{rpm:.0f}* (máximo: {_RPM_NORM_MAX})\n"
                f"Verifique o regulador de velocidade.")
            m_ant["rpm_alto"] = True
            log.info("📤 RPM alto: %.0f", rpm)
        elif rpm <= _RPM_NORM_MAX:
            m_ant["rpm_alto"] = False

    # Bateria
    if isinstance(bateria, float) and bateria > 0:
        if bateria < _BAT_MIN_V and not m_ant.get("bateria"):
            _enviar(config.GRUPO_GERADOR_MOTOR,
                f"🔋 *BATERIA DO GERADOR BAIXA*\n\n"
                f"🕒 {_agora()}\n"
                f"Tensão: *{bateria:.1f} V* (mínimo: {_BAT_MIN_V} V)\n"
                f"Verifique o carregador de bateria.")
            m_ant["bateria"] = True
            log.info("📤 Bateria baixa: %.1fV", bateria)
        elif bateria >= 12.0:
            m_ant["bateria"] = False

    # Alarme ativo
    try:
        n_alarmes = int(alarmes)
    except (ValueError, TypeError):
        n_alarmes = 0
    if n_alarmes > 0 and not m_ant.get("alarme"):
        _enviar(config.GRUPO_GERADOR_MOTOR,
            f"🚨 *ALARME ATIVO NO CONTROLADOR DSE*\n\n"
            f"🕒 {_agora()}\n"
            f"Total de alarmes: *{n_alarmes}*\n"
            f"Verifique o painel do controlador DSE.")
        m_ant["alarme"] = True
        log.info("📤 Alarme ativo: %d", n_alarmes)
    elif n_alarmes == 0:
        m_ant["alarme"] = False

    _estado["motor"] = m_ant
    _salvar()


# ── Loop principal ────────────────────────────────────────────────

def _processar(vals: dict):
    global _ultimo_valores
    _ultimo_valores = vals

    rpm    = vals.get("rpm", 0.0)
    gen_l1 = vals.get("gen_l1", 0.0)
    gen_l2 = vals.get("gen_l2", 0.0)
    gen_l3 = vals.get("gen_l3", 0.0)

    ligado_agora  = rpm > _RPM_MIN or (gen_l1 > _VOLT_PRESENTE and gen_l2 > _VOLT_PRESENTE and gen_l3 > _VOLT_PRESENTE)
    estava_ligado = _estado.get("ligado", False)

    if ligado_agora and not estava_ligado:
        log.info("🔌 GERADOR LIGOU (RPM=%.0f L1=%.1fV)", rpm, gen_l1)
        _estado.update({
            "ligado":       True,
            "hora_ligou_iso": _agora_iso(),
            "fuel_ao_ligar": vals.get("fuel_pct", 0),
            "alertas_fuel": [],
            "tensao":       {},
            "motor":        {},
        })
        _salvar()
        _alerta_ligou(vals)

    elif not ligado_agora and estava_ligado:
        log.info("🔌 GERADOR DESLIGOU (RPM=%.0f L1=%.1fV)", rpm, gen_l1)
        _alerta_desligou(vals)
        _estado["ligado"] = False
        _salvar()

    _verificar_tensao(vals)

    if ligado_agora:
        _verificar_combustivel(vals)
        _verificar_motor(vals)


def get_estado_painel() -> dict:
    """Retorna dados formatados para o painel web."""
    v = _ultimo_valores
    if not v:
        return {"disponivel": False}

    rpm    = v.get("rpm", 0.0)
    gen_l1 = v.get("gen_l1", 0.0)
    gen_l2 = v.get("gen_l2", 0.0)
    gen_l3 = v.get("gen_l3", 0.0)
    ligado = _estado.get("ligado", False)
    fuel_pct = v.get("fuel_pct", 0.0)
    litros   = _litros(fuel_pct)

    taxa_lph, consumo_l, autonomia, previsao = _calcular_consumo(v) if ligado else (0, 0, "N/D", "N/D")
    hora_iso = _estado.get("hora_ligou_iso")
    tempo_ligado = _fmt_tempo(_horas_desde(hora_iso)) if hora_iso and ligado else "—"

    return {
        "disponivel":    True,
        "ligado":        ligado,
        "rpm":           rpm,
        "freq_gen":      v.get("freq_gen", 0),
        "freq_rede":     v.get("freq_rede", 0),
        "bateria":       v.get("bateria", 0),
        "alarmes":       v.get("alarmes", 0),
        "horas":         v.get("horas", "N/A"),
        "partidas":      v.get("partidas", 0),
        "supervisor":    v.get("supervisor", "—"),
        "gen_l1": gen_l1, "gen_l2": gen_l2, "gen_l3": gen_l3,
        "gen_media":     round((gen_l1 + gen_l2 + gen_l3) / 3, 1) if ligado else 0,
        "gen_deseq":     _desequilibrio(gen_l1, gen_l2, gen_l3),
        "rede_l1": v.get("rede_l1", 0), "rede_l2": v.get("rede_l2", 0), "rede_l3": v.get("rede_l3", 0),
        "fuel_pct":      fuel_pct,
        "fuel_litros":   litros,
        "taxa_lph":      taxa_lph,
        "consumo_sessao_litros": consumo_l,
        "autonomia":     autonomia,
        "previsao_zero": previsao,
        "tempo_ligado":  tempo_ligado,
    }


def iniciar_monitor():
    _carregar()
    log.info("⚡ Monitor DSE iniciado (polling %ds)", _POLL_INTERVAL)
    falhas = 0
    while True:
        try:
            vals = zabbix.buscar_valores()
            if vals:
                falhas = 0
                _processar(vals)
            else:
                falhas += 1
                if falhas == 3:
                    log.warning("⚠️ Zabbix sem resposta há %d tentativas", falhas)
        except Exception as e:
            log.error("Monitor DSE erro: %s", e)
        time.sleep(_POLL_INTERVAL)

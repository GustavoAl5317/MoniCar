import logging
from datetime import datetime
from fleet_alert import state, config
from fleet_alert.timeutil import agora_iso, agora_data_hora, fmt_iso_br, parse_iso_br, TZ_BR

log = logging.getLogger(__name__)

LIGADO_PARADO = "LIGADO_PARADO"
EM_MOVIMENTO  = "EM_MOVIMENTO"
DESLIGADO     = "DESLIGADO"

# Cooldown mínimo entre alertas consecutivos do mesmo veículo (segundos)
_COOLDOWN_MOVIMENTO = 180   # 3 min entre parado↔movimento (oscilação GPS)
_COOLDOWN_GERAL     = 60    # 1 min entre qualquer outro alerta


def _segundos_desde_ultimo_alerta(est: dict) -> float:
    ts = est.get("ultimo_alerta_ts")
    if not ts:
        return float("inf")
    try:
        dt = parse_iso_br(ts)
        if not dt:
            return float("inf")
        return (datetime.now(TZ_BR) - dt).total_seconds()
    except Exception:
        return float("inf")


def _ligou_as(est: dict, fallback: str) -> str:
    """Hora em que o veiculo ligou — sempre derivada do ISO salvo."""
    return fmt_iso_br(est.get("hora_ligou_iso")) if est.get("hora_ligou_iso") else fallback


def _tempo_ligado(hora_iso: str | None, ate_iso: str | None = None) -> str:
    if not hora_iso:
        return "N/D"
    try:
        inicio = parse_iso_br(hora_iso)
        fim    = parse_iso_br(ate_iso) if ate_iso else datetime.now(TZ_BR)
        if not inicio or not fim:
            return "N/D"
        minutos = int((fim - inicio).total_seconds() // 60)
        if minutos < 0:
            return "N/D"
        if minutos >= 60:
            return f"{minutos // 60}h {minutos % 60}min"
        return f"{minutos} minutos"
    except Exception:
        return "N/D"


def _fmt_km(odometro) -> str:
    if odometro is None:
        return "N/D"
    inteiro, dec = f"{float(odometro):.2f}".split(".")
    inteiro_br = f"{int(inteiro):,}".replace(",", ".")
    return f"{inteiro_br},{dec} km"


def _fmt_bat(bateria) -> str:
    return f"{bateria}%" if bateria not in (None, "N/D") else "N/D"


CARROS_FROTA = ("GOL", "CELTA", "AGILE")


def status_operacional(ignition, speed: float, motion: int) -> str:
    if ignition is True and (motion == 1 or speed > config.SPEED_MOVING_KMPH):
        return "Em movimento"
    if ignition is True:
        return "Ligado e parado"
    if ignition is False:
        return "Desligado"
    return "Desconhecido"


def montar_alerta_inicio(nome: str, pos: dict, device: dict) -> dict:
    """Monta alerta de status ao reiniciar o servidor."""
    hora        = agora_data_hora()
    status_site = device.get("status", "desconhecido")

    if not pos:
        texto = (
            f"🚀 *Sistema reiniciado* — status do *{nome}*\n\n"
            f"Horário: {hora}.\n"
            f"Rastreador: {status_site}.\n"
            f"Posição: indisponível no momento."
        )
        audio = (
            f"Alerta da frota. Sistema reiniciado. Veículo {nome}. "
            f"Posição indisponível no momento. Rastreador {status_site}."
        )
        return {"tipo": "INICIO", "texto": texto, "audio": audio}

    attrs    = pos.get("attributes", {})
    speed    = round(pos.get("speed", 0), 1)
    ignition = attrs.get("ignition")
    motion   = 1 if attrs.get("motion") else 0
    endereco = pos.get("address") or (
        f"lat={pos.get('latitude', '?')}, lon={pos.get('longitude', '?')}"
    )
    bat         = _fmt_bat(attrs.get("batteryLevel") or attrs.get("battery"))
    km          = _fmt_km(
        round(attrs.get("odometer", 0) / 1000, 2) if attrs.get("odometer") else None
    )
    status_op   = status_operacional(ignition, speed, motion)
    status_site = device.get("status", "desconhecido")

    texto = (
        f"🚀 *Sistema reiniciado* — status do *{nome}*\n\n"
        f"Horário: {hora}.\n"
        f"Estado: {status_op}.\n"
        f"Rastreador: {status_site}.\n"
        f"Velocidade: {speed} km/h.\n"
        f"Localização: {endereco}.\n"
        f"KM: {km}.\n"
        f"Bateria: {bat}."
    )
    audio = (
        f"Alerta da frota. Sistema reiniciado. Veículo {nome}. "
        f"Estado: {status_op}. Velocidade: {speed} quilômetros por hora. "
        f"Localização: {endereco}. Bateria: {bat}."
    )
    return {"tipo": "INICIO", "texto": texto, "audio": audio}


def processar(nome: str, dados: dict) -> dict | None:
    """
    Aplica as regras de estado ao veículo.
    Retorna { tipo, texto, audio } quando há alerta a disparar, ou None.
    """
    est = state.get(nome)

    ig_ant    = est.get("ignition")        # ignição anterior
    alerta_ant = est.get("ultimo_alerta")

    ig_atual   = dados.get("ignition", 0)
    motion     = dados.get("motion",   0)
    speed      = dados.get("speed",    0)
    endereco   = dados.get("address")  or "Endereço não disponível"
    bateria    = dados.get("batteryLevel") or dados.get("battery")
    odometro   = dados.get("odometer")
    hora_agora = agora_data_hora()

    km_str  = _fmt_km(odometro)
    bat_str = _fmt_bat(bateria)

    resultado = None

    # ── Veículo desligou ─────────────────────────────────────────
    if ig_ant == 1 and ig_atual == 0:
        iso_desligou  = agora_iso()
        hora_desligou = hora_agora
        tempo_str     = _tempo_ligado(est.get("hora_ligou_iso"), iso_desligou)
        ligou_as      = _ligou_as(est, "N/D")

        state.atualizar(nome, {
            "ignition":      0,
            "motion":        0,
            "speed":         0,
            "hora_desligou": hora_desligou,
            "ultimo_alerta": DESLIGADO,
        })

        resultado = {
            "tipo":  DESLIGADO,
            "texto": (
                f"🔴 Veículo *{nome}* foi desligado.\n\n"
                f"Horário: {hora_desligou}.\n"
                f"Desligado às: {hora_desligou}.\n"
                f"Ligado às: {ligou_as}.\n"
                f"Tempo ligado: {tempo_str}.\n"
                f"Localização: {endereco}.\n"
                f"KM final: {km_str}.\n"
                f"Bateria: {bat_str}."
            ),
            "audio": (
                f"Alerta da frota. O veículo {nome} foi desligado. "
                f"Horário: {hora_desligou}. "
                f"Tempo ligado: {tempo_str}. "
                f"Localização: {endereco}. "
                f"Bateria em {bat_str}."
            ),
        }

    # ── Veículo ligou (estava desligado ou sem dados) ─────────────
    elif ig_ant != 1 and ig_atual == 1:
        iso_ligou  = agora_iso()
        hora_ligou = hora_agora
        state.atualizar(nome, {
            "ignition":       1,
            "hora_ligou":     hora_ligou,
            "hora_ligou_iso": iso_ligou,
            "ultimo_alerta":  None,
        })

        if motion == 1 or speed > config.SPEED_MOVING_KMPH:
            resultado = _alerta_movimento(nome, hora_ligou, speed, endereco, km_str, bat_str, hora_agora)
        else:
            resultado = _alerta_ligado_parado(nome, hora_ligou, endereco, km_str, bat_str, hora_agora)

    # ── Estava parado, começou a andar ───────────────────────────
    elif (ig_atual == 1
          and alerta_ant != EM_MOVIMENTO
          and (motion == 1 or speed > config.SPEED_MOVING_KMPH)):
        seg = _segundos_desde_ultimo_alerta(est)
        if seg >= _COOLDOWN_MOVIMENTO:
            hora_ligou = _ligou_as(est, hora_agora)
            resultado  = _alerta_movimento(nome, hora_ligou, speed, endereco, km_str, bat_str, hora_agora)
        else:
            log.debug("[%s] EM_MOVIMENTO suprimido — cooldown (%ds restantes)", nome, int(_COOLDOWN_MOVIMENTO - seg))

    # ── Estava andando, parou ────────────────────────────────────
    elif (ig_atual == 1
          and alerta_ant == EM_MOVIMENTO
          and motion == 0
          and speed <= config.SPEED_STOPPED_KMPH):
        seg = _segundos_desde_ultimo_alerta(est)
        if seg >= _COOLDOWN_MOVIMENTO:
            hora_ligou = _ligou_as(est, hora_agora)
            resultado  = _alerta_ligado_parado(nome, hora_ligou, endereco, km_str, bat_str, hora_agora)
        else:
            log.debug("[%s] LIGADO_PARADO suprimido — cooldown (%ds restantes)", nome, int(_COOLDOWN_MOVIMENTO - seg))

    # Sempre atualiza estado com dados mais recentes
    state.atualizar(nome, {
        "ignition":     ig_atual,
        "motion":       motion,
        "speed":        speed,
        "address":      endereco,
        "odometer":     odometro,
        "batteryLevel": bateria,
    })

    if resultado:
        state.atualizar(nome, {
            "ultimo_alerta":    resultado["tipo"],
            "ultimo_alerta_ts": agora_iso(),
        })
        log.info("🚨 [%s] %s → %s", resultado["tipo"], nome, alerta_ant)

    return resultado


def _alerta_ligado_parado(nome, hora_ligou, endereco, km_str, bat_str, hora_notif) -> dict:
    return {
        "tipo":  LIGADO_PARADO,
        "texto": (
            f"🟡 Veículo *{nome}* está ligado e parado.\n\n"
            f"Horário: {hora_notif}.\n"
            f"Ligado às: {hora_ligou}.\n"
            f"Endereço atual: {endereco}.\n"
            f"KM atual: {km_str}.\n"
            f"Bateria: {bat_str}."
        ),
        "audio": (
            f"Alerta da frota. O veículo {nome} está ligado, porém parado. "
            f"Horário: {hora_notif}. "
            f"Ligado às {hora_ligou}. "
            f"Localização: {endereco}. "
            f"Bateria em {bat_str}."
        ),
    }


def processar_celular(nome: str, dados: dict) -> dict | None:
    """Regras para celular: sem ignição, usa só velocidade/movimento."""
    est        = state.get(nome)
    alerta_ant = est.get("ultimo_alerta")

    motion   = dados.get("motion", 0)
    speed    = dados.get("speed",  0)
    endereco = dados.get("address") or "Endereço não disponível"
    bateria  = dados.get("batteryLevel") or dados.get("battery")
    bat_str  = _fmt_bat(bateria)

    resultado = None
    em_movimento = motion == 1 or speed > config.SPEED_MOVING_KMPH
    parado       = motion == 0 and speed <= config.SPEED_STOPPED_KMPH

    if em_movimento and alerta_ant != EM_MOVIMENTO:
        seg = _segundos_desde_ultimo_alerta(est)
        if seg >= _COOLDOWN_MOVIMENTO:
            hora = agora_data_hora()
            resultado = {
                "tipo":  EM_MOVIMENTO,
                "texto": (
                    f"🟢 *{nome}* em movimento.\n\n"
                    f"Horário: {hora}.\n"
                    f"Localização: {endereco}.\n"
                    f"Velocidade: {speed:.0f} km/h.\n"
                    f"Bateria: {bat_str}."
                ),
                "audio": (
                    f"Alerta da frota. O celular {nome} está em movimento. "
                    f"Localização: {endereco}. Velocidade: {speed:.0f} quilômetros por hora."
                ),
            }

    elif parado and alerta_ant == EM_MOVIMENTO:
        seg = _segundos_desde_ultimo_alerta(est)
        if seg >= _COOLDOWN_MOVIMENTO:
            hora = agora_data_hora()
            resultado = {
                "tipo":  LIGADO_PARADO,
                "texto": (
                    f"🟡 *{nome}* parou.\n\n"
                    f"Horário: {hora}.\n"
                    f"Localização: {endereco}.\n"
                    f"Bateria: {bat_str}."
                ),
                "audio": (
                    f"Alerta da frota. O celular {nome} parou. "
                    f"Localização: {endereco}. Bateria em {bat_str}."
                ),
            }

    state.atualizar(nome, {
        "motion":       motion,
        "speed":        speed,
        "address":      endereco,
        "batteryLevel": bateria,
    })

    if resultado:
        state.atualizar(nome, {
            "ultimo_alerta":    resultado["tipo"],
            "ultimo_alerta_ts": agora_iso(),
        })
        log.info("📱 [%s] %s → %s", resultado["tipo"], nome, alerta_ant)

    return resultado


def _alerta_movimento(nome, hora_ligou, speed, endereco, km_str, bat_str, hora_notif) -> dict:
    speed_str = f"{speed:.0f} km/h" if speed else "N/D"
    return {
        "tipo":  EM_MOVIMENTO,
        "texto": (
            f"🟢 Veículo *{nome}* iniciou deslocamento.\n\n"
            f"Horário: {hora_notif}.\n"
            f"Ligado às: {hora_ligou}.\n"
            f"Endereço: {endereco}.\n"
            f"Bateria: {bat_str}.\n"
            f"Velocidade: {speed_str}."
        ),
        "audio": (
            f"Alerta da frota. O veículo {nome} iniciou deslocamento. "
            f"Horário: {hora_notif}. "
            f"Localização: {endereco}. "
            f"Bateria em {bat_str}. "
            f"Velocidade: {speed_str}."
        ),
    }

import logging
from datetime import datetime
from fleet_alert import state, config

log = logging.getLogger(__name__)

LIGADO_PARADO = "LIGADO_PARADO"
EM_MOVIMENTO  = "EM_MOVIMENTO"
DESLIGADO     = "DESLIGADO"


def _agora() -> str:
    return datetime.now().strftime("%H:%M")


def _agora_iso() -> str:
    return datetime.now().isoformat()


def _tempo_ligado(hora_iso: str | None) -> str:
    if not hora_iso:
        return "N/D"
    try:
        delta   = datetime.now() - datetime.fromisoformat(hora_iso)
        minutos = int(delta.total_seconds() // 60)
        if minutos >= 60:
            return f"{minutos // 60}h {minutos % 60}min"
        return f"{minutos} minutos"
    except Exception:
        return "N/D"


def _fmt_km(odometro) -> str:
    if odometro is None:
        return "N/D"
    return f"{odometro:,.2f} km".replace(",", ".")


def _fmt_bat(bateria) -> str:
    return f"{bateria}%" if bateria not in (None, "N/D") else "N/D"


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

    km_str  = _fmt_km(odometro)
    bat_str = _fmt_bat(bateria)

    resultado = None

    # ── Veículo desligou ─────────────────────────────────────────
    if ig_ant == 1 and ig_atual == 0:
        hora_desligou = _agora()
        tempo_str     = _tempo_ligado(est.get("hora_ligou_iso"))

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
                f"Desligado às: {hora_desligou}.\n"
                f"Tempo ligado: {tempo_str}.\n"
                f"Localização: {endereco}.\n"
                f"KM final: {km_str}.\n"
                f"Bateria: {bat_str}."
            ),
            "audio": (
                f"Alerta da frota. O veículo {nome} foi desligado às {hora_desligou}. "
                f"Tempo ligado: {tempo_str}. "
                f"Localização: {endereco}. "
                f"Bateria em {bat_str}."
            ),
        }

    # ── Veículo ligou (estava desligado ou sem dados) ─────────────
    elif ig_ant != 1 and ig_atual == 1:
        hora_ligou = _agora()
        state.atualizar(nome, {
            "ignition":       1,
            "hora_ligou":     hora_ligou,
            "hora_ligou_iso": _agora_iso(),
            "ultimo_alerta":  None,
        })

        if motion == 1 or speed > config.SPEED_MOVING_KMPH:
            resultado = _alerta_movimento(nome, hora_ligou, speed, endereco, km_str, bat_str)
        else:
            resultado = _alerta_ligado_parado(nome, hora_ligou, endereco, km_str, bat_str)

    # ── Estava parado, começou a andar ───────────────────────────
    elif (ig_atual == 1
          and alerta_ant != EM_MOVIMENTO
          and (motion == 1 or speed > config.SPEED_MOVING_KMPH)):
        hora_ligou = est.get("hora_ligou", _agora())
        resultado  = _alerta_movimento(nome, hora_ligou, speed, endereco, km_str, bat_str)

    # ── Estava andando, parou ────────────────────────────────────
    elif (ig_atual == 1
          and alerta_ant == EM_MOVIMENTO
          and motion == 0
          and speed <= config.SPEED_STOPPED_KMPH):
        hora_ligou = est.get("hora_ligou", _agora())
        resultado  = _alerta_ligado_parado(nome, hora_ligou, endereco, km_str, bat_str)

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
        state.atualizar(nome, {"ultimo_alerta": resultado["tipo"]})
        log.info("🚨 [%s] %s → %s", resultado["tipo"], nome, alerta_ant)

    return resultado


def _alerta_ligado_parado(nome, hora_ligou, endereco, km_str, bat_str) -> dict:
    return {
        "tipo":  LIGADO_PARADO,
        "texto": (
            f"🟡 Veículo *{nome}* está ligado e parado.\n\n"
            f"Ligado às: {hora_ligou}.\n"
            f"Endereço atual: {endereco}.\n"
            f"KM atual: {km_str}.\n"
            f"Bateria: {bat_str}."
        ),
        "audio": (
            f"Alerta da frota. O veículo {nome} está ligado, porém parado. "
            f"Ligado às {hora_ligou}. "
            f"Localização: {endereco}. "
            f"Bateria em {bat_str}."
        ),
    }


def _alerta_movimento(nome, hora_ligou, speed, endereco, km_str, bat_str) -> dict:
    speed_str = f"{speed:.0f} km/h" if speed else "N/D"
    return {
        "tipo":  EM_MOVIMENTO,
        "texto": (
            f"🟢 Veículo *{nome}* iniciou deslocamento.\n\n"
            f"Ligado às: {hora_ligou}.\n"
            f"Endereço: {endereco}.\n"
            f"Bateria: {bat_str}.\n"
            f"Velocidade: {speed_str}."
        ),
        "audio": (
            f"Alerta da frota. O veículo {nome} iniciou deslocamento às {hora_ligou}. "
            f"Localização: {endereco}. "
            f"Bateria em {bat_str}. "
            f"Velocidade: {speed_str}."
        ),
    }

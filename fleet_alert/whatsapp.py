import time
import requests
import logging
from fleet_alert import config

log = logging.getLogger(__name__)

_MAX_TENTATIVAS = 3
_DELAY_BASE     = 5   # segundos entre retentativas (5s, 10s)


def _headers() -> dict:
    return {
        "apikey":       config.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }


def _post(endpoint: str, payload: dict) -> bool:
    url = f"{config.EVOLUTION_URL}/{endpoint}/{config.EVOLUTION_INSTANCE}"
    for tentativa in range(1, _MAX_TENTATIVAS + 1):
        try:
            r = requests.post(url, json=payload, headers=_headers(), timeout=20)
            if r.status_code in (200, 201):
                return True
            log.warning(
                "Tentativa %d/%d — Evolution API %s → %d: %s",
                tentativa, _MAX_TENTATIVAS, endpoint, r.status_code, r.text[:200],
            )
        except Exception as e:
            log.warning(
                "Tentativa %d/%d — Erro Evolution API (%s): %s",
                tentativa, _MAX_TENTATIVAS, endpoint, e,
            )
        if tentativa < _MAX_TENTATIVAS:
            espera = _DELAY_BASE * tentativa
            log.info("Aguardando %ds antes de retentar...", espera)
            time.sleep(espera)

    log.error("❌ Falha após %d tentativas em %s", _MAX_TENTATIVAS, endpoint)
    return False


def enviar_texto(grupo_id: str, mensagem: str) -> bool:
    ok = _post("message/sendText", {"number": grupo_id, "text": mensagem})
    if ok:
        log.info("✅ Texto enviado → %s", grupo_id)
    return ok


def enviar_audio(grupo_id: str, audio_base64: str) -> bool:
    payload = {
        "number":   grupo_id,
        "audio":    audio_base64,
        "encoding": True,
    }
    ok = _post("message/sendWhatsAppAudio", payload)
    if ok:
        log.info("🎤 Voz enviada → %s", grupo_id)
    return ok


def verificar_conexao() -> bool:
    """Verifica se a instância WhatsApp está conectada na Evolution API."""
    try:
        r = requests.get(
            f"{config.EVOLUTION_URL}/instance/fetchInstances",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code != 200:
            log.error("Evolution API inacessível (HTTP %d)", r.status_code)
            return False
        dados = r.json()
        instancias = dados if isinstance(dados, list) else [dados]
        for inst in instancias:
            nome = (
                inst.get("instance", {}).get("instanceName")
                or inst.get("instanceName")
                or inst.get("name")
            )
            if nome != config.EVOLUTION_INSTANCE:
                continue
            status = (
                inst.get("instance", {}).get("connectionStatus")
                or inst.get("connectionStatus")
                or inst.get("state")
                or ""
            )
            if str(status).lower() in ("open", "connected"):
                log.info("WhatsApp conectado (instância %s)", config.EVOLUTION_INSTANCE)
                return True
            log.critical(
                "WhatsApp DESCONECTADO (instância %s, status=%s) — alertas não serão enviados",
                config.EVOLUTION_INSTANCE, status,
            )
            return False
        log.error("Instância '%s' não encontrada na Evolution API", config.EVOLUTION_INSTANCE)
        return False
    except Exception as e:
        log.error("Falha ao verificar conexão WhatsApp: %s", e)
        return False


def enviar_alerta(nome: str, texto: str, audio_base64: str | None = None) -> bool:
    cfg = config.VEICULOS.get(nome.upper())
    if not cfg:
        log.warning("Veículo '%s' não mapeado em config.VEICULOS", nome)
        return False
    if cfg.get("tipo") == "celular":
        log.debug("Celular '%s' — alerta WhatsApp desabilitado", nome)
        return True
    if not cfg.get("ativo", True):
        log.info("Veículo '%s' desativado — alerta ignorado", nome)
        return False

    grupo = cfg.get("grupo_id")
    if not grupo:
        log.info("Veículo '%s' sem grupo WhatsApp — alerta só no painel", nome)
        return True   # não é falha, só não envia

    ok = enviar_texto(grupo, texto)

    if audio_base64:
        ok_audio = enviar_audio(grupo, audio_base64)
        ok = ok and ok_audio

    return ok

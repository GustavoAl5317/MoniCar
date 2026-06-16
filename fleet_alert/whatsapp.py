import requests
import logging
from fleet_alert import config

log = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "apikey":       config.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }


def _post(endpoint: str, payload: dict) -> bool:
    url = f"{config.EVOLUTION_URL}/{endpoint}/{config.EVOLUTION_INSTANCE}"
    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=20)
        if r.status_code in (200, 201):
            return True
        log.warning("Evolution API %s → %d: %s", endpoint, r.status_code, r.text[:300])
        return False
    except Exception as e:
        log.error("Erro Evolution API (%s): %s", endpoint, e)
        return False


def enviar_texto(grupo_id: str, mensagem: str) -> bool:
    ok = _post("message/sendText", {"number": grupo_id, "text": mensagem})
    if ok:
        log.info("✅ Texto enviado → %s", grupo_id)
    return ok


def enviar_audio(grupo_id: str, audio_base64: str) -> bool:
    payload = {
        "number":    grupo_id,
        "mediatype": "audio",
        "mimetype":  "audio/ogg; codecs=opus",
        "media":     audio_base64,
        "fileName":  "alerta.ogg",
    }
    ok = _post("message/sendMedia", payload)
    if ok:
        log.info("🔊 Áudio enviado → %s", grupo_id)
    return ok


def enviar_alerta(nome: str, texto: str, audio_base64: str | None = None) -> bool:
    cfg = config.VEICULOS.get(nome.upper())
    if not cfg:
        log.warning("Veículo '%s' não mapeado em config.VEICULOS", nome)
        return False
    if not cfg.get("ativo", True):
        log.info("Veículo '%s' desativado — alerta ignorado", nome)
        return False

    grupo = cfg["grupo_id"]
    ok    = enviar_texto(grupo, texto)

    if audio_base64:
        ok_audio = enviar_audio(grupo, audio_base64)
        ok = ok and ok_audio

    return ok

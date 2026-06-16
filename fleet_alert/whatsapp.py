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

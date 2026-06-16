import json
import time
import logging
import requests
import websocket
from fleet_alert import config, rules
from fleet_alert.whatsapp import enviar_alerta
from fleet_alert.audio import gerar_audio_base64
from fleet_alert.db import registrar, registrar_posicao

log = logging.getLogger(__name__)

_session  = requests.Session()
_nomes: dict = {}   # { deviceId: nome_traccar }

# Mapeamento nome_traccar → nome_exibição (chave de config.VEICULOS)
def _build_traccar_map() -> dict:
    return {
        cfg.get("traccar_nome", nome): nome
        for nome, cfg in config.VEICULOS.items()
    }

_traccar_para_display: dict = {}


# ── Auth ─────────────────────────────────────────────────────────

def _login() -> bool:
    for tentativa in range(1, 11):
        try:
            r = _session.post(
                f"{config.TRACCAR_URL}/api/session",
                data={"email": config.TRACCAR_EMAIL, "password": config.TRACCAR_PASSWORD},
                timeout=15,
            )
            if r.status_code == 200:
                log.info("✅ Login Traccar OK: %s", r.json().get("name"))
                return True
            log.warning("Login tentativa %d/10 → %d", tentativa, r.status_code)
        except Exception as e:
            log.warning("Login tentativa %d/10 → %s", tentativa, e)
        time.sleep(15)
    return False


def _carregar_dispositivos():
    global _nomes, _traccar_para_display
    try:
        r = _session.get(f"{config.TRACCAR_URL}/api/devices", timeout=15)
        _nomes = {d["id"]: d.get("name", f"device_{d['id']}") for d in r.json()}
        _traccar_para_display = _build_traccar_map()
        log.info("📡 %d dispositivo(s) | %d mapeado(s)", len(_nomes), len(_traccar_para_display))
    except Exception as e:
        log.error("Erro ao carregar dispositivos: %s", e)


# ── Processamento ─────────────────────────────────────────────────

def _processar_posicao(pos: dict):
    did         = pos.get("deviceId")
    nome_traccar = _nomes.get(did)
    if not nome_traccar:
        return

    # Resolve nome de exibição via mapeamento traccar_nome → display
    nome = _traccar_para_display.get(nome_traccar)
    if not nome:
        return

    attrs = pos.get("attributes", {})
    dados = {
        "latitude":     pos.get("latitude"),
        "longitude":    pos.get("longitude"),
        "speed":        round(pos.get("speed", 0), 2),
        "address":      pos.get("address", ""),
        "ignition":     1 if attrs.get("ignition") else 0,
        "motion":       1 if attrs.get("motion")   else 0,
        "batteryLevel": attrs.get("batteryLevel"),
        "battery":      attrs.get("battery"),
        "odometer":     round(attrs.get("odometer", 0) / 1000, 2) if attrs.get("odometer") else None,
    }

    # Registra todos os dados recebidos
    registrar_posicao(
        nome,
        dados["ignition"], dados["motion"], dados["speed"],
        dados["address"], dados.get("batteryLevel"), dados.get("odometer"),
    )

    resultado = rules.processar(nome.upper(), dados)
    if not resultado:
        return

    tipo  = resultado["tipo"]
    texto = resultado["texto"]
    audio_txt = resultado["audio"]

    registrar(nome, tipo, texto[:200])

    audio_b64 = gerar_audio_base64(audio_txt)
    ok = enviar_alerta(nome.upper(), texto, audio_b64)

    registrar(nome, "ENVIO", "ok" if ok else "falha")
    if not ok:
        log.warning("⚠️  Falha ao enviar alerta para '%s'", nome)


# ── WebSocket callbacks ───────────────────────────────────────────

def _on_message(ws, message):
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return
    for pos in data.get("positions", []):
        _processar_posicao(pos)
    # Atualiza nomes se algum device mudou
    for dev in data.get("devices", []):
        if dev.get("id") and dev.get("name"):
            _nomes[dev["id"]] = dev["name"]


def _on_error(ws, error):
    log.error("WebSocket erro: %s", error)


def _on_close(ws, code, msg):
    log.warning("WebSocket fechado (%s) — reconectando em 10s...", code)


def _on_open(ws):
    log.info("🔌 WebSocket conectado")


# ── Loop principal ────────────────────────────────────────────────

def iniciar_coletor():
    global _traccar_para_display
    _traccar_para_display = _build_traccar_map()

    if not _login():
        log.critical("Login falhou. Coletor encerrado.")
        return

    _carregar_dispositivos()

    cookies = "; ".join(f"{k}={v}" for k, v in _session.cookies.items())
    ws_url  = (
        config.TRACCAR_URL
        .replace("https://", "wss://")
        .replace("http://",  "ws://")
        + "/api/socket"
    )
    log.info("🌐 Conectando: %s", ws_url)

    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                header={"Cookie": cookies},
                on_open=_on_open,
                on_message=_on_message,
                on_error=_on_error,
                on_close=_on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except KeyboardInterrupt:
            log.info("Coletor encerrado.")
            break
        except Exception as e:
            log.error("Erro inesperado: %s — reconectando em 15s...", e)

        time.sleep(15)
        _login()
        _carregar_dispositivos()
        cookies = "; ".join(f"{k}={v}" for k, v in _session.cookies.items())

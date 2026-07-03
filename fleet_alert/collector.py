import json
import time
import logging
import requests
import websocket
from fleet_alert.timeutil import hora_alerta
from fleet_alert import config, state
from fleet_alert import rules, geofence
from fleet_alert.whatsapp import enviar_alerta, verificar_conexao
from fleet_alert.audio import gerar_audio_base64
from fleet_alert.db import registrar, registrar_posicao

log = logging.getLogger(__name__)

_session  = requests.Session()
_nomes: dict = {}          # { deviceId: nome_traccar }
_desconhecidos: dict = {}  # { traccar_nome: True } — vistos mas não mapeados


def get_desconhecidos() -> list:
    return [{"traccar_nome": n} for n in sorted(_desconhecidos.keys())]

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
        return r.json()
    except Exception as e:
        log.error("Erro ao carregar dispositivos: %s", e)
        return []


def _inicializar_estado_veiculo(nome: str, pos: dict):
    """Sincroniza estado sem disparar alertas de transição."""
    attrs = pos.get("attributes", {})
    lat   = pos.get("latitude")
    lon   = pos.get("longitude")
    dados = {
        "ignition":     1 if attrs.get("ignition") else 0,
        "motion":       1 if attrs.get("motion")   else 0,
        "speed":        round(pos.get("speed", 0), 2),
        "address":      pos.get("address", ""),
        "odometer":     round(attrs.get("odometer", 0) / 1000, 2) if attrs.get("odometer") else None,
        "batteryLevel": attrs.get("batteryLevel"),
    }
    if lat and lon:
        dados["latitude"]  = lat
        dados["longitude"] = lon
        dados.update(geofence.estado_lojas(lat, lon))
    state.atualizar(nome.upper(), dados)


def _enviar_alertas_inicio():
    """Envia status atual dos 3 carros nos grupos WhatsApp ao iniciar o servidor."""
    try:
        devices   = _session.get(f"{config.TRACCAR_URL}/api/devices", timeout=15).json()
        positions = _session.get(f"{config.TRACCAR_URL}/api/positions", timeout=15).json()
    except Exception as e:
        log.error("Falha ao buscar dados para alerta inicial: %s", e)
        return

    dev_por_id = {d["id"]: d for d in devices}
    pos_por_id = {p["deviceId"]: p for p in positions}
    traccar_para_id = {nome: did for did, nome in _nomes.items()}

    log.info("📤 Enviando alerta inicial da frota (GOL, CELTA, AGILE)...")

    for nome in rules.CARROS_FROTA:
        cfg = config.VEICULOS.get(nome, {})
        if cfg.get("tipo") != "veiculo" or not cfg.get("ativo") or not cfg.get("grupo_id"):
            continue

        tn  = cfg.get("traccar_nome")
        did = traccar_para_id.get(tn)
        if not did:
            log.warning("[%s] Dispositivo '%s' não encontrado no Traccar", nome, tn)
            continue

        pos    = pos_por_id.get(did, {})
        device = dev_por_id.get(did, {})

        if pos:
            _inicializar_estado_veiculo(nome, pos)

        alerta = rules.montar_alerta_inicio(nome, pos, device)
        registrar(nome, alerta["tipo"], alerta["texto"][:200])

        audio_b64 = gerar_audio_base64(alerta["audio"])
        ok = enviar_alerta(nome, alerta["texto"], audio_b64)
        registrar(nome, "ENVIO", "ok" if ok else "falha")

        if ok:
            log.info("✅ Alerta inicial enviado para %s", nome)
        else:
            log.warning("⚠️  Falha no alerta inicial de %s", nome)

        time.sleep(2)  # evita flood na Evolution API


# ── Processamento ─────────────────────────────────────────────────

def _processar_posicao(pos: dict):
    did         = pos.get("deviceId")
    nome_traccar = _nomes.get(did)
    if not nome_traccar:
        return

    # Resolve nome de exibição via mapeamento traccar_nome → display
    nome = _traccar_para_display.get(nome_traccar)
    if not nome:
        _desconhecidos[nome_traccar] = True
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
        "event_time":   pos.get("deviceTime") or pos.get("fixTime"),
    }

    # Registra todos os dados recebidos
    registrar_posicao(
        nome,
        dados["ignition"], dados["motion"], dados["speed"],
        dados["address"], dados.get("batteryLevel"), dados.get("odometer"),
    )

    cfg_veiculo = config.VEICULOS.get(nome.upper(), {})
    if cfg_veiculo.get("tipo") == "celular":
        resultado = rules.processar_celular(nome.upper(), dados)
    else:
        resultado = rules.processar(nome.upper(), dados)

    # ── Geofence (lojas) ──────────────────────────────────────────
    lat = dados.get("latitude")
    lon = dados.get("longitude")
    if lat and lon:
        est_atual = state.get(nome.upper())
        chegou    = geofence.verificar(nome.upper(), lat, lon, est_atual)
        if chegou:
            hora      = hora_alerta()
            loja_nome = chegou["loja_nome"]
            endereco  = dados.get("address") or "N/D"
            texto_loja = (
                f"📍 *{nome}* chegou na loja *{loja_nome}*.\n\n"
                f"Horário: {hora}.\n"
                f"Localização: {endereco}."
            )
            registrar(nome, geofence.CHEGOU_LOJA, texto_loja[:200])
            # Geofence WhatsApp: somente carros
            if cfg_veiculo.get("tipo") == "veiculo":
                audio_loja = (
                    f"Alerta da frota. {nome} chegou na loja {loja_nome}. "
                    f"Horário: {hora}. Localização: {endereco}."
                )
                audio_b64_loja = gerar_audio_base64(audio_loja)
                ok_loja = enviar_alerta(nome.upper(), texto_loja, audio_b64_loja)
                registrar(nome, "ENVIO", "ok" if ok_loja else "falha")
        # Sempre atualiza estado de presença nas lojas e salva coordenadas
        state.atualizar(nome.upper(), {
            "latitude":  lat,
            "longitude": lon,
            **geofence.estado_lojas(lat, lon),
        })
    # ─────────────────────────────────────────────────────────────

    if not resultado:
        return

    tipo  = resultado["tipo"]
    texto = resultado["texto"]
    audio_txt = resultado["audio"]

    registrar(nome, tipo, texto[:200])

    # Celulares: registra no painel, sem WhatsApp
    if cfg_veiculo.get("tipo") == "celular":
        log.debug("Celular '%s' — %s registrado apenas no painel", nome, tipo)
        return

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

    if not verificar_conexao():
        log.warning("WhatsApp desconectado — alerta inicial pode falhar")

    _enviar_alertas_inicio()

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

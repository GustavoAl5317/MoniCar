import os

# ── Traccar ──────────────────────────────────────────────────────
TRACCAR_URL      = os.getenv("TRACCAR_URL",      "https://rastreamentopopular.com")
TRACCAR_EMAIL    = os.getenv("TRACCAR_EMAIL",    "aquitelecom")
TRACCAR_PASSWORD = os.getenv("TRACCAR_PASSWORD", "267426")

# ── Evolution API (WhatsApp) ─────────────────────────────────────
EVOLUTION_URL      = os.getenv("EVOLUTION_URL",      "http://10.169.0.20:8080")
EVOLUTION_API_KEY  = os.getenv("EVOLUTION_API_KEY",  "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "interatell01")

# ── Mapeamento nome_exibição → configuração ───────────────────────
# traccar_nome: nome EXATO como aparece no Traccar
# grupo_id: None = só monitora, sem enviar WhatsApp
VEICULOS: dict = {
    "GOL": {
        "traccar_nome": "GOL",
        "grupo_id":     "120363429714140442@g.us",
        "ativo":        True,
    },
    "CELTA": {
        "traccar_nome": "Celta NUN-8248 - Celta Telefone",
        "grupo_id":     "120363428415301635@g.us",
        "ativo":        True,
    },
    "AGILE": {
        "traccar_nome": "AGILE - agile telefone",
        "grupo_id":     "120363410128424553@g.us",
        "ativo":        True,
    },
    # ── Equipamentos — monitorados no painel, sem alertas WhatsApp ──
    "O-TECH HOEA3500": {
        "traccar_nome": " O-TECH HOEA3500",
        "grupo_id":     None,
        "ativo":        True,
    },
    "OTDR HOEA5500": {
        "traccar_nome": "OTDR O-TECH HOEA5500",
        "grupo_id":     None,
        "ativo":        True,
    },
    "T-40 FUSAO": {
        "traccar_nome": "Maquina de fusao ORIENTEK T-40",
        "grupo_id":     None,
        "ativo":        True,
    },
    "OTDR AQ1210E": {
        "traccar_nome": "OTDR YOKOGAWA AQ1210E",
        "grupo_id":     None,
        "ativo":        True,
    },
    "T-40 VERDE": {
        "traccar_nome": "T-40 VERDE",
        "grupo_id":     None,
        "ativo":        True,
    },
    "TELEFONE 55": {
        "traccar_nome": "telefone 55",
        "grupo_id":     None,
        "ativo":        True,
    },
    "OTDR T303": {
        "traccar_nome": "OTDR-ORIENTEK T303",
        "grupo_id":     None,
        "ativo":        True,
    },
    "TELEFONE CELTA": {
        "traccar_nome": "Telefone Celta ",
        "grupo_id":     None,
        "ativo":        True,
    },
    "T-40 AZUL": {
        "traccar_nome": "T-40 AZUL",
        "grupo_id":     None,
        "ativo":        True,
    },
}

# ── Thresholds de velocidade ─────────────────────────────────────
SPEED_MOVING_KMPH  = 3   # acima → "em movimento"
SPEED_STOPPED_KMPH = 2   # abaixo → "parado"

# ── Persistência ─────────────────────────────────────────────────
STATE_FILE = os.getenv("STATE_FILE", "data/estado.json")
DB_PATH    = os.getenv("DB_PATH",    "data/logs.db")

# ── Painel web ───────────────────────────────────────────────────
WEB_PORT       = int(os.getenv("WEB_PORT", "5000"))
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "fleet-alert-secret-2026")
WEB_USER       = os.getenv("WEB_USER",       "admin")
WEB_PASSWORD   = os.getenv("WEB_PASSWORD",   "fleet2026")

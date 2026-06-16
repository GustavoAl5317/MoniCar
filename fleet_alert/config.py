import os

# ── Traccar ──────────────────────────────────────────────────────
TRACCAR_URL      = os.getenv("TRACCAR_URL",      "https://rastreamentopopular.com")
TRACCAR_EMAIL    = os.getenv("TRACCAR_EMAIL",    "aquitelecom")
TRACCAR_PASSWORD = os.getenv("TRACCAR_PASSWORD", "267426")

# ── Evolution API (WhatsApp) ─────────────────────────────────────
EVOLUTION_URL      = os.getenv("EVOLUTION_URL",      "http://10.169.0.20:8080")
EVOLUTION_API_KEY  = os.getenv("EVOLUTION_API_KEY",  "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "interatell01")

# ── Mapeamento veículo → grupo WhatsApp ──────────────────────────
# O nome do dispositivo no Traccar deve bater com a chave aqui (case-insensitive)
VEICULOS: dict = {
    "CELTA": {
        "grupo_id": "120363428415301635@g.us",
        "ativo":    True,
    },
    "GOL": {
        "grupo_id": "120363429714140442@g.us",
        "ativo":    True,
    },
    "AGILE": {
        "grupo_id": "120363410128424553@g.us",
        "ativo":    True,
    },
}

# ── Thresholds de velocidade ─────────────────────────────────────
SPEED_MOVING_KMPH  = 3   # acima → "em movimento"
SPEED_STOPPED_KMPH = 2   # abaixo → "parado"

# ── Persistência ─────────────────────────────────────────────────
STATE_FILE = os.getenv("STATE_FILE", "data/estado.json")
DB_PATH    = os.getenv("DB_PATH",    "data/logs.db")

# ── Painel web ───────────────────────────────────────────────────
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))

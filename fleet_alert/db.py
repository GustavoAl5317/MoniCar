import sqlite3
import logging
import os
from datetime import datetime
from fleet_alert import config

log = logging.getLogger(__name__)


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(config.DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       TEXT    NOT NULL,
                veiculo  TEXT    NOT NULL,
                tipo     TEXT    NOT NULL,
                detalhe  TEXT
            )
        """)
    log.info("Banco de logs pronto: %s", config.DB_PATH)


def registrar(veiculo: str, tipo: str, detalhe: str = ""):
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO logs (ts, veiculo, tipo, detalhe) VALUES (?,?,?,?)",
                (datetime.now().isoformat(), veiculo.upper(), tipo, detalhe),
            )
    except Exception as e:
        log.warning("Falha ao gravar log: %s", e)


def ultimos(limit: int = 100) -> list[dict]:
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("Falha ao ler logs: %s", e)
        return []

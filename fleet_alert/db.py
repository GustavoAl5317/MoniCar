import sqlite3
import logging
import os
from datetime import datetime
from fleet_alert import config

log = logging.getLogger(__name__)

_MAX_POSICOES = 500   # mantém só as últimas N posições no banco


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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posicoes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT    NOT NULL,
                veiculo    TEXT    NOT NULL,
                ignition   INTEGER,
                motion     INTEGER,
                speed      REAL,
                address    TEXT,
                battery    INTEGER,
                odometer   REAL
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


def registrar_posicao(veiculo: str, ignition: int, motion: int, speed: float,
                      address: str, battery, odometer):
    try:
        with _conn() as conn:
            conn.execute(
                """INSERT INTO posicoes (ts, veiculo, ignition, motion, speed, address, battery, odometer)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (datetime.now().isoformat(), veiculo.upper(),
                 ignition, motion, speed, address, battery, odometer),
            )
            # Mantém só os últimos _MAX_POSICOES registros por veículo
            conn.execute(
                """DELETE FROM posicoes WHERE veiculo = ? AND id NOT IN (
                    SELECT id FROM posicoes WHERE veiculo = ?
                    ORDER BY id DESC LIMIT ?
                )""",
                (veiculo.upper(), veiculo.upper(), _MAX_POSICOES),
            )
    except Exception as e:
        log.warning("Falha ao gravar posição: %s", e)


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


def ultimas_posicoes(veiculo: str = None, limit: int = 50) -> list[dict]:
    try:
        with _conn() as conn:
            if veiculo:
                rows = conn.execute(
                    "SELECT * FROM posicoes WHERE veiculo = ? ORDER BY id DESC LIMIT ?",
                    (veiculo.upper(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM posicoes ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("Falha ao ler posições: %s", e)
        return []

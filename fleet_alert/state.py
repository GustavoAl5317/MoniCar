import json
import os
import logging
from threading import Lock
from fleet_alert import config

log = logging.getLogger(__name__)

_lock: Lock = Lock()
_estado: dict = {}


def _carregar():
    global _estado
    path = config.STATE_FILE
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                _estado = json.load(f)
            log.info("Estado restaurado: %d veículo(s)", len(_estado))
        except Exception as e:
            log.warning("Falha ao restaurar estado: %s", e)
            _estado = {}


def _salvar():
    path = config.STATE_FILE
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("Falha ao salvar estado: %s", e)


def get(nome: str) -> dict:
    with _lock:
        return dict(_estado.get(nome.upper(), {}))


def atualizar(nome: str, dados: dict):
    nome = nome.upper()
    with _lock:
        if nome not in _estado:
            _estado[nome] = {}
        _estado[nome].update(dados)
        _salvar()


def todos() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _estado.items()}


_carregar()

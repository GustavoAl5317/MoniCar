import json
import os
import logging
from threading import Lock
from fleet_alert import config

log = logging.getLogger(__name__)
_lock = Lock()


def _path() -> str:
    base = os.path.dirname(os.path.abspath(config.STATE_FILE))
    return os.path.join(base, "veiculos_config.json")


def carregar():
    """Aplica overrides persistidos sobre config.VEICULOS na inicialização."""
    p = _path()
    if not os.path.exists(p):
        return
    try:
        with open(p, encoding="utf-8") as f:
            overrides = json.load(f)
        for nome, dados in overrides.items():
            if nome in config.VEICULOS:
                config.VEICULOS[nome].update(dados)
            else:
                config.VEICULOS[nome] = dados
        log.info("Config de veículos restaurada: %s", list(overrides.keys()))
    except Exception as e:
        log.warning("Falha ao carregar config de veículos: %s", e)


def salvar(nome: str, grupo_id: str, ativo: bool):
    """Persiste e aplica nova config de um veículo."""
    p = _path()
    with _lock:
        overrides = {}
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    overrides = json.load(f)
            except Exception:
                pass
        overrides[nome] = {"grupo_id": grupo_id, "ativo": ativo}
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)

    if nome not in config.VEICULOS:
        config.VEICULOS[nome] = {}
    config.VEICULOS[nome]["grupo_id"] = grupo_id
    config.VEICULOS[nome]["ativo"]    = ativo
    log.info("Config salva: %s → grupo=%s ativo=%s", nome, grupo_id, ativo)

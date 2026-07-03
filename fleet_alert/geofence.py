import json
import os
import math
import logging
import requests
from fleet_alert import config

log = logging.getLogger(__name__)

CHEGOU_LOJA = "CHEGOU_LOJA"
_RAIO_PADRAO = 150  # metros


def _data_path() -> str:
    base = os.path.dirname(os.path.abspath(config.STATE_FILE))
    return os.path.join(base, "lojas.json")


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def geocodificar(endereco: str) -> tuple[float, float] | None:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": endereco, "format": "json", "limit": 1},
            headers={"User-Agent": "FleetAlert/1.0"},
            timeout=10,
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        log.warning("Geocoding falhou para '%s': %s", endereco, e)
    return None


def carregar() -> list:
    p = _data_path()
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def salvar(lojas: list):
    p = _data_path()
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(lojas, f, ensure_ascii=False, indent=2)


def adicionar(nome: str, endereco: str, raio: int = _RAIO_PADRAO) -> dict | None:
    coords = geocodificar(endereco)
    if not coords:
        log.error("Não foi possível geocodificar: %s", endereco)
        return None
    lat, lon = coords
    lojas = carregar()
    loja_id = str(len(lojas) + 1)
    loja = {"id": loja_id, "nome": nome, "endereco": endereco, "lat": lat, "lon": lon, "raio": raio}
    lojas.append(loja)
    salvar(lojas)
    log.info("Loja adicionada: %s (%.6f, %.6f) raio=%dm", nome, lat, lon, raio)
    return loja


def remover(loja_id: str):
    lojas = [l for l in carregar() if l["id"] != loja_id]
    salvar(lojas)


def verificar(nome: str, lat: float, lon: float, est: dict) -> dict | None:
    """Retorna alerta se o dispositivo acabou de entrar em alguma loja."""
    if not lat or not lon:
        return None
    # Sem histórico = primeiro contato após restart — só registra, não alerta
    tem_historico = any(k.startswith("loja_") for k in est)
    for loja in carregar():
        dist = _haversine(lat, lon, loja["lat"], loja["lon"])
        dentro = dist <= loja.get("raio", _RAIO_PADRAO)
        chave  = f"loja_{loja['id']}"
        estava = est.get(chave, False)
        if dentro and not estava:
            if not tem_historico:
                log.debug(
                    "[%s] Já estava na loja '%s' na inicialização — alerta suprimido",
                    nome, loja["nome"],
                )
                return None
            log.info("📍 [%s] Chegou na loja '%s' (%.0fm)", nome, loja["nome"], dist)
            return {
                "tipo":      CHEGOU_LOJA,
                "loja_nome": loja["nome"],
                "loja_id":   loja["id"],
                "dist":      round(dist),
            }
    return None


def estado_lojas(lat: float, lon: float) -> dict:
    """Retorna {loja_X: True/False} para atualizar o estado do dispositivo."""
    resultado = {}
    if not lat or not lon:
        return resultado
    for loja in carregar():
        dist  = _haversine(lat, lon, loja["lat"], loja["lon"])
        resultado[f"loja_{loja['id']}"] = dist <= loja.get("raio", _RAIO_PADRAO)
    return resultado

import logging
import requests
from fleet_alert import config

log = logging.getLogger(__name__)

ITEMS = {
    "rpm":        "1774759",
    "fuel_pct":   "1774758",
    "gen_l1":     "1774849",
    "gen_l2":     "1776163",
    "gen_l3":     "1776168",
    "rede_l1":    "1774765",
    "rede_l2":    "1774841",
    "rede_l3":    "1774842",
    "bateria":    "1774757",
    "freq_gen":   "1776177",
    "freq_rede":  "1774764",
    "alarmes":    "1774763",
    "horas":      "1774760",
    "partidas":   "1774761",
    "supervisor": "1774851",
    "di_emerg":   "1777327",
    "di_oleo":    "1777329",
    "di_temp":    "1777328",
}

_token = None
_session = requests.Session()
_API = lambda: config.ZABBIX_URL + "/api_jsonrpc.php"


def _auth() -> bool:
    global _token
    try:
        r = _session.post(_API(), json={
            "jsonrpc": "2.0",
            "method": "user.login",
            "params": {"user": config.ZABBIX_USER, "password": config.ZABBIX_PASSWORD},
            "id": 1,
        }, timeout=15)
        d = r.json()
        if "result" in d:
            _token = d["result"]
            log.info("Zabbix autenticado OK")
            return True
        log.error("Zabbix auth falhou: %s", d.get("error"))
    except Exception as e:
        log.error("Zabbix auth erro: %s", e)
    return False


def buscar_valores() -> dict | None:
    """Retorna {chave: valor} para todos os itens DSE, ou None se falhar."""
    global _token
    if not _token:
        if not _auth():
            return None

    try:
        r = _session.post(_API(), json={
            "jsonrpc": "2.0",
            "method": "item.get",
            "params": {
                "output": ["itemid", "lastvalue"],
                "itemids": list(ITEMS.values()),
            },
            "auth": _token,
            "id": 2,
        }, timeout=15)
        d = r.json()
        if "error" in d:
            _token = None
            if not _auth():
                return None
            return buscar_valores()

        id_to_key = {v: k for k, v in ITEMS.items()}
        resultado = {}
        for item in d.get("result", []):
            chave = id_to_key.get(item["itemid"])
            if not chave:
                continue
            val = item["lastvalue"]
            try:
                resultado[chave] = float(val)
            except (ValueError, TypeError):
                resultado[chave] = val
        return resultado

    except Exception as e:
        log.error("Zabbix buscar_valores erro: %s", e)
        _token = None
        return None

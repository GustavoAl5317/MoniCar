import logging
import threading
import os
import time

# Garante fuso de Brasilia no processo (Linux/Docker)
os.environ.setdefault("TZ", "America/Sao_Paulo")
if hasattr(time, "tzset"):
    time.tzset()

# Carrega .env se existir (desenvolvimento local)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fleet_alert.db import inicializar
from fleet_alert.collector import iniciar_coletor
from fleet_alert.gerador import iniciar_monitor
from fleet_alert.web.app import criar_app
from fleet_alert import config, config_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    inicializar()
    config_manager.carregar()

    coletor = threading.Thread(target=iniciar_coletor, daemon=True, name="coletor")
    coletor.start()

    monitor_dse = threading.Thread(target=iniciar_monitor, daemon=True, name="monitor_dse")
    monitor_dse.start()

    app = criar_app()
    app.run(host="0.0.0.0", port=config.WEB_PORT, debug=False)

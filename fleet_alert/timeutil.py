from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ_BR = ZoneInfo("America/Sao_Paulo")
FMT_DATA_HORA = "%d/%m/%Y %H:%M"
FMT_HORA = "%H:%M"


def agora() -> str:
    """Hora atual em Brasilia (HH:MM)."""
    return datetime.now(TZ_BR).strftime(FMT_HORA)


def agora_data_hora() -> str:
    """Data e hora atual em Brasilia."""
    return datetime.now(TZ_BR).strftime(FMT_DATA_HORA)


def agora_iso() -> str:
    """ISO com fuso de Brasilia."""
    return datetime.now(TZ_BR).isoformat()


def parse_traccar(ts: str | None) -> datetime | None:
    """Converte timestamp do Traccar (UTC) para datetime em Brasilia."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_BR)
    except Exception:
        return None


def hora_alerta() -> str:
    """Horario exibido nos alertas WhatsApp — sempre Brasilia, momento do envio."""
    return agora_data_hora()

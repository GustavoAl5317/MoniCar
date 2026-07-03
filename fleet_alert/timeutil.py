from datetime import datetime
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
    """Converte timestamp UTC do Traccar para datetime em Brasilia."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ_BR)
    except Exception:
        return None


def hora_evento(ts: str | None) -> str:
    """Horario do evento GPS em Brasilia (dd/mm/YYYY HH:MM)."""
    dt = parse_traccar(ts)
    return dt.strftime(FMT_DATA_HORA) if dt else agora_data_hora()

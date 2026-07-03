#!/usr/bin/env python3
"""Compara horarios do Traccar vs horario local nos alertas."""
import sys
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from fleet_alert import config
except ImportError:
    import os
    class config:
        TRACCAR_URL = os.getenv("TRACCAR_URL", "https://rastreamentopopular.com")
        TRACCAR_EMAIL = os.getenv("TRACCAR_EMAIL", "aquitelecom")
        TRACCAR_PASSWORD = os.getenv("TRACCAR_PASSWORD", "267426")
        VEICULOS = {
            "GOL": {"traccar_nome": "GOL"},
            "CELTA": {"traccar_nome": "Celta NUN-8248 - Celta Telefone"},
            "AGILE": {"traccar_nome": "AGILE - agile telefone"},
        }

TZ_BR = ZoneInfo("America/Sao_Paulo")
CARROS = ("GOL", "CELTA", "AGILE")

def parse_traccar(ts: str) -> datetime | None:
    if not ts:
        return None
    # Traccar retorna ISO com +00:00 (UTC)
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def fmt_local(dt: datetime | None) -> str:
    if not dt:
        return "(vazio)"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_BR).strftime("%d/%m/%Y %H:%M:%S")

def fmt_utc(dt: datetime | None) -> str:
    if not dt:
        return "(vazio)"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")

session = requests.Session()
r = session.post(
    f"{config.TRACCAR_URL}/api/session",
    data={"email": config.TRACCAR_EMAIL, "password": config.TRACCAR_PASSWORD},
    timeout=15,
)
print("=" * 70)
print("COMPARACAO DE HORARIOS — SITE vs SISTEMA DE ALERTAS")
print("=" * 70)

agora_local = datetime.now(TZ_BR)
agora_naive = datetime.now()
agora_utc   = datetime.now(timezone.utc)

print("\n--- Relogio desta maquina (como o sistema gera alertas hoje) ---")
print(f"  datetime.now()              : {agora_naive.strftime('%d/%m/%Y %H:%M:%S')}  <- usado nos alertas")
print(f"  datetime.now(Brasil)        : {agora_local.strftime('%d/%m/%Y %H:%M:%S')}  <- horario correto BR")
print(f"  datetime.now(UTC)           : {agora_utc.strftime('%d/%m/%Y %H:%M:%S UTC')}")
diff_h = (agora_naive.hour - agora_local.hour) % 24
if agora_naive.tzinfo is None and diff_h in (3, -21):
    print("  [PROBLEMA] datetime.now() parece estar em UTC (+3h vs Brasil)")
elif agora_naive.strftime("%H:%M") == agora_local.strftime("%H:%M"):
    print("  [OK] Relogio local coincide com horario de Brasilia")
else:
    print(f"  [AVISO] Diferenca de {diff_h}h entre now() e horario BR")

if r.status_code != 200:
    print(f"\nLogin falhou: {r.status_code}")
    sys.exit(1)

devices = session.get(f"{config.TRACCAR_URL}/api/devices", timeout=15).json()
positions = session.get(f"{config.TRACCAR_URL}/api/positions", timeout=15).json()
pos_map = {p["deviceId"]: p for p in positions}
traccar_map = {cfg.get("traccar_nome", n): n for n, cfg in config.VEICULOS.items()}

print("\n--- Horarios retornados pelo site (por carro) ---")
for nome in CARROS:
    tn = config.VEICULOS[nome]["traccar_nome"]
    d = next((x for x in devices if x["name"] == tn), None)
    if not d:
        print(f"\n{nome}: dispositivo nao encontrado")
        continue
    p = pos_map.get(d["id"], {})
    fix   = parse_traccar(p.get("fixTime", ""))
    dev   = parse_traccar(p.get("deviceTime", ""))
    srv   = parse_traccar(p.get("serverTime", ""))
    last  = parse_traccar(d.get("lastUpdate", ""))

    print(f"\n>> {nome}")
    print(f"   lastUpdate (device) : {fmt_utc(last)}  ->  {fmt_local(last)}")
    print(f"   fixTime  (GPS)      : {fmt_utc(fix)}  ->  {fmt_local(fix)}")
    print(f"   deviceTime          : {fmt_utc(dev)}  ->  {fmt_local(dev)}")
    print(f"   serverTime          : {fmt_utc(srv)}  ->  {fmt_local(srv)}")

    if fix and agora_local:
        atraso_min = (agora_local - fix.astimezone(TZ_BR)).total_seconds() / 60
        print(f"   atraso fixTime vs agora BR: {atraso_min:.0f} min")

print("\n" + "=" * 70)
print("CONCLUSAO")
print("=" * 70)
print("""
O site Traccar retorna horarios em UTC (+00:00).
Convertidos para Brasilia (UTC-3), os horarios do GPS estao corretos.

Os ALERTAS usam datetime.now() do SERVIDOR no momento do envio,
NAO o fixTime/deviceTime do Traccar. Se o servidor/docker estiver
em UTC, os alertas saem com +3 horas de diferenca.
""")

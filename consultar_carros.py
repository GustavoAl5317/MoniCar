#!/usr/bin/env python3
"""
Consulta o Traccar e valida se os carros estao retornando
os dados necessarios para o sistema de alertas.
"""
import sys
import requests
from fleet_alert import config, rules, state

# Evita erro de encoding no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CARROS = ("GOL", "CELTA", "AGILE")

session = requests.Session()

# ── Login ─────────────────────────────────────────────────────────
print("=" * 65)
print("CONSULTA TRACCAR — VALIDACAO DOS CARROS PARA ALERTAS")
print("=" * 65)
print(f"URL: {config.TRACCAR_URL}")

r = session.post(
    f"{config.TRACCAR_URL}/api/session",
    data={"email": config.TRACCAR_EMAIL, "password": config.TRACCAR_PASSWORD},
    timeout=15,
)
if r.status_code != 200:
    print(f"\n[ERRO] Login falhou: HTTP {r.status_code}")
    sys.exit(1)
print(f"Login: OK ({r.json().get('name')})")

# ── Dispositivos e posicoes ───────────────────────────────────────
devices   = session.get(f"{config.TRACCAR_URL}/api/devices", timeout=15).json()
positions = session.get(f"{config.TRACCAR_URL}/api/positions", timeout=15).json()
pos_map   = {p["deviceId"]: p for p in positions}

traccar_map = {
    cfg.get("traccar_nome", nome): nome
    for nome, cfg in config.VEICULOS.items()
}

print(f"\nDispositivos no site: {len(devices)}")
print(f"Posicoes retornadas:  {len(positions)}")
print(f"Mapeamentos config:   {len(traccar_map)}")

# ── Validacao por carro ───────────────────────────────────────────
print("\n" + "-" * 65)
print("CARROS CONFIGURADOS PARA ALERTA")
print("-" * 65)

problemas = []
ok_count  = 0

for nome in CARROS:
    cfg = config.VEICULOS.get(nome, {})
    tn  = cfg.get("traccar_nome", "")
    print(f"\n>> {nome}")
    print(f"   traccar_nome esperado : '{tn}'")
    print(f"   grupo WhatsApp        : {cfg.get('grupo_id') or '(nenhum)'}")
    print(f"   ativo                 : {cfg.get('ativo')}")
    print(f"   tipo                  : {cfg.get('tipo', 'veiculo')}")

    # 1) Dispositivo existe?
    found = [d for d in devices if d["name"] == tn]
    if not found:
        print("   [FALHA] Dispositivo NAO encontrado no site")
        problemas.append(f"{nome}: nome '{tn}' nao existe no Traccar")
        continue

    d = found[0]
    print(f"   dispositivo id        : {d['id']}")
    print(f"   status site           : {d.get('status')}")
    print(f"   ultima atualizacao    : {d.get('lastUpdate')}")

    # 2) Mapeamento reverso funciona?
    display = traccar_map.get(d["name"])
    if display != nome:
        print(f"   [FALHA] Mapeamento incorreto: retornou '{display}'")
        problemas.append(f"{nome}: mapeamento traccar_nome incorreto")
        continue
    print("   mapeamento            : OK")

    # 3) Posicao existe?
    p = pos_map.get(d["id"])
    if not p:
        print("   [FALHA] Sem posicao na API /api/positions")
        problemas.append(f"{nome}: sem posicao retornada pelo site")
        continue

    attrs = p.get("attributes", {})
    lat   = p.get("latitude")
    lon   = p.get("longitude")
    speed = round(p.get("speed", 0), 2)
    ig    = attrs.get("ignition")
    mot   = attrs.get("motion")
    addr  = p.get("address") or ""

    print(f"   coordenadas           : {lat}, {lon}")
    print(f"   endereco              : {addr[:70] or '(vazio)'}")
    print(f"   velocidade            : {speed} km/h")
    print(f"   ignition (bruto)      : {ig}")
    print(f"   motion (bruto)        : {mot}")
    print(f"   bateria               : {attrs.get('batteryLevel') or attrs.get('battery') or 'N/D'}")
    print(f"   hodometro             : {attrs.get('odometer') or 'N/D'}")

    # 4) Campos criticos para alerta
    checks = []
    if lat is None or lon is None:
        checks.append("sem coordenadas")
    if ig is None:
        checks.append("ignition ausente (alertas de ligar/desligar nao funcionam)")
    if not addr:
        checks.append("endereco vazio (alerta funciona, mas sem local)")

    # Status derivado (mesma logica do script.py / collector)
    if ig is True and speed > 2:
        situacao = "ANDANDO"
    elif ig is True:
        situacao = "LIGADO PARADO"
    elif ig is False:
        situacao = "DESLIGADO"
    else:
        situacao = "IGNICAO DESCONHECIDA"
    print(f"   situacao atual        : {situacao}")

    # 5) Simula se geraria alerta agora (sem alterar estado real)
    est = state.get(nome)
    dados = {
        "latitude": lat, "longitude": lon, "speed": speed,
        "address": addr,
        "ignition": 1 if ig else 0,
        "motion": 1 if mot else 0,
        "batteryLevel": attrs.get("batteryLevel"),
        "battery": attrs.get("battery"),
        "odometer": round(attrs.get("odometer", 0) / 1000, 2) if attrs.get("odometer") else None,
    }
    ig_ant     = est.get("ignition")
    alerta_ant = est.get("ultimo_alerta")
    em_mov     = mot == 1 or speed > config.SPEED_MOVING_KMPH
    parado     = mot == 0 and speed <= config.SPEED_STOPPED_KMPH

    alerta_possivel = None
    if ig_ant == 1 and dados["ignition"] == 0:
        alerta_possivel = "DESLIGADO"
    elif ig_ant != 1 and dados["ignition"] == 1:
        alerta_possivel = "EM_MOVIMENTO" if em_mov else "LIGADO_PARADO"
    elif dados["ignition"] == 1 and alerta_ant != rules.EM_MOVIMENTO and em_mov:
        alerta_possivel = "EM_MOVIMENTO (se cooldown ok)"
    elif dados["ignition"] == 1 and alerta_ant == rules.EM_MOVIMENTO and parado:
        alerta_possivel = "LIGADO_PARADO (se cooldown ok)"

    print(f"   estado salvo          : ignition={ig_ant} ultimo_alerta={alerta_ant}")
    if alerta_possivel:
        print(f"   proximo alerta        : {alerta_possivel}")
    else:
        print("   proximo alerta        : nenhum (sem mudanca de estado)")

    if checks:
        for c in checks:
            print(f"   [AVISO] {c}")
            problemas.append(f"{nome}: {c}")
    else:
        print("   validacao dados       : OK")
        ok_count += 1

# ── Resumo ────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("RESUMO")
print("=" * 65)
print(f"Carros validados OK: {ok_count}/{len(CARROS)}")

if problemas:
    print("\nProblemas encontrados:")
    for p in problemas:
        print(f"  - {p}")
else:
    print("\nO site esta retornando os 3 carros corretamente para alerta.")
    print("Os alertas dependem de MUDANCA de estado (ligar, desligar, andar, parar).")

# Dispositivos no site sem mapeamento
nao_mapeados = [d for d in devices if d["name"] not in traccar_map]
if nao_mapeados:
    print(f"\nDispositivos no site sem mapeamento ({len(nao_mapeados)}):")
    for d in nao_mapeados:
        print(f"  - '{d['name']}' (id={d['id']})")

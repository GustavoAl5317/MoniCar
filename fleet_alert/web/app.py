import os
from flask import Flask, jsonify, request, render_template
from fleet_alert import state, config
from fleet_alert.db import ultimos, ultimas_posicoes
from fleet_alert import config_manager

_TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


def criar_app() -> Flask:
    app = Flask(__name__, template_folder=_TEMPLATES)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/veiculos")
    def api_veiculos():
        dados = state.todos()
        result = []
        for nome, cfg in config.VEICULOS.items():
            est = dados.get(nome, {})
            result.append({
                "nome":          nome,
                "ativo":         cfg.get("ativo", True),
                "grupo_id":      cfg.get("grupo_id", ""),
                "ignition":      est.get("ignition"),
                "motion":        est.get("motion"),
                "speed":         est.get("speed"),
                "address":       est.get("address", "—"),
                "odometer":      est.get("odometer"),
                "batteryLevel":  est.get("batteryLevel"),
                "ultimo_alerta": est.get("ultimo_alerta"),
                "hora_ligou":    est.get("hora_ligou"),
                "hora_desligou": est.get("hora_desligou"),
            })
        return jsonify(result)

    @app.route("/api/logs")
    def api_logs():
        limit = request.args.get("limit", 100, type=int)
        return jsonify(ultimos(limit))

    @app.route("/api/posicoes")
    def api_posicoes():
        veiculo = request.args.get("veiculo")
        limit   = request.args.get("limit", 50, type=int)
        return jsonify(ultimas_posicoes(veiculo, limit))

    @app.route("/api/toggle/<nome>", methods=["POST"])
    def api_toggle(nome: str):
        nome = nome.upper()
        if nome not in config.VEICULOS:
            return jsonify({"error": "not found"}), 404
        novo_ativo = not config.VEICULOS[nome].get("ativo", True)
        grupo_id   = config.VEICULOS[nome].get("grupo_id", "")
        config_manager.salvar(nome, grupo_id, novo_ativo)
        return jsonify({"nome": nome, "ativo": novo_ativo})

    @app.route("/api/config/veiculo/<nome>", methods=["POST"])
    def api_config_veiculo(nome: str):
        nome = nome.upper()
        body = request.get_json(silent=True) or {}
        grupo_id = body.get("grupo_id", "").strip()
        if not grupo_id:
            return jsonify({"error": "grupo_id obrigatório"}), 400
        ativo = config.VEICULOS.get(nome, {}).get("ativo", True)
        config_manager.salvar(nome, grupo_id, ativo)
        return jsonify({"nome": nome, "grupo_id": grupo_id, "ativo": ativo})

    return app

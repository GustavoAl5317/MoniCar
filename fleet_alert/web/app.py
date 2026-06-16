import os
from functools import wraps
from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from fleet_alert import state, config
from fleet_alert.db import ultimos, ultimas_posicoes
from fleet_alert import config_manager

_TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("autenticado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def criar_app() -> Flask:
    app = Flask(__name__, template_folder=_TEMPLATES)
    app.secret_key = config.WEB_SECRET_KEY

    @app.route("/login", methods=["GET", "POST"])
    def login():
        erro = None
        if request.method == "POST":
            usuario = request.form.get("usuario", "")
            senha   = request.form.get("senha", "")
            if usuario == config.WEB_USER and senha == config.WEB_PASSWORD:
                session["autenticado"] = True
                return redirect(url_for("index"))
            erro = "Usuário ou senha incorretos."
        return render_template("login.html", erro=erro)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @_login_required
    def index():
        return render_template("index.html")

    @app.route("/api/veiculos")
    @_login_required
    def api_veiculos():
        dados = state.todos()
        result = []
        for nome, cfg in config.VEICULOS.items():
            est = dados.get(nome, {})
            result.append({
                "nome":          nome,
                "ativo":         cfg.get("ativo", True),
                "grupo_id":      cfg.get("grupo_id") or "",
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
    @_login_required
    def api_logs():
        limit = request.args.get("limit", 100, type=int)
        return jsonify(ultimos(limit))

    @app.route("/api/posicoes")
    @_login_required
    def api_posicoes():
        veiculo = request.args.get("veiculo")
        limit   = request.args.get("limit", 50, type=int)
        return jsonify(ultimas_posicoes(veiculo, limit))

    @app.route("/api/toggle/<nome>", methods=["POST"])
    @_login_required
    def api_toggle(nome: str):
        nome = nome.upper()
        if nome not in config.VEICULOS:
            return jsonify({"error": "not found"}), 404
        novo_ativo = not config.VEICULOS[nome].get("ativo", True)
        grupo_id   = config.VEICULOS[nome].get("grupo_id") or ""
        config_manager.salvar(nome, grupo_id, novo_ativo)
        return jsonify({"nome": nome, "ativo": novo_ativo})

    @app.route("/api/config/veiculo/<nome>", methods=["POST"])
    @_login_required
    def api_config_veiculo(nome: str):
        nome = nome.upper()
        body     = request.get_json(silent=True) or {}
        grupo_id = body.get("grupo_id", "").strip()
        if not grupo_id:
            return jsonify({"error": "grupo_id obrigatório"}), 400
        ativo = config.VEICULOS.get(nome, {}).get("ativo", True)
        config_manager.salvar(nome, grupo_id, ativo)
        return jsonify({"nome": nome, "grupo_id": grupo_id, "ativo": ativo})

    return app

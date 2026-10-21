"""painel.py — dashboard web: login, gráfico ao vivo, alertas, comandos e CSV.

Perfis: OPERADOR (vê e reconhece alertas) e ADMINISTRADOR (também envia comandos,
altera limites e cadastra dispositivos).
"""
import csv
import io
import json
import logging
from functools import wraps

from flask import (Blueprint, Response, abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

from api import ID_VALIDO
from banco import agora, cadastrar_dispositivo, db
from relatorio import gerar_html, hora, ler_periodo

painel = Blueprint("painel", __name__)
log = logging.getLogger("vaxguard")

ADMIN = "ADMINISTRADOR"
PLACAS = ["UNO_R4_WIFI", "ESP32", "SIMULADOR"]


@painel.app_template_filter("data")
def filtro_data(ts):
    return hora(ts)


def login_obrigatorio(perfil=None):
    """Decorador: exige sessão e, se informado, um perfil específico."""
    def decorador(funcao):
        @wraps(funcao)
        def protegida(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("painel.login"))
            if perfil and session["perfil"] != perfil:
                abort(403)
            return funcao(*args, **kwargs)
        return protegida
    return decorador


def esta_online(disp):
    """OFFLINE = sem dados há mais de 3 intervalos do dispositivo."""
    return disp["ultimo_contato"] is not None and agora() - disp["ultimo_contato"] <= 3 * disp["intervalo_s"]


def enfileirar(con, dispositivo_id, tipo, **parametros):
    if not con.execute("SELECT 1 FROM dispositivos WHERE id = ?", (dispositivo_id,)).fetchone():
        abort(404)
    con.execute("INSERT INTO comandos (dispositivo_id, tipo, parametros, criado_por, criado_em) VALUES (?, ?, ?, ?, ?)",
                (dispositivo_id, tipo, json.dumps(parametros), session["usuario"], agora()))
    log.info("Comando %s %s para %s por %s", tipo, parametros, dispositivo_id, session["usuario"])


def numero_do_form(campo):
    try:
        return float(request.form[campo].replace(",", "."))
    except (KeyError, ValueError):
        return None


# ---------------- Login ----------------

@painel.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("SELECT * FROM usuarios WHERE nome = ?", (request.form.get("usuario", ""),)).fetchone()
        if u and check_password_hash(u["senha_hash"], request.form.get("senha", "")):
            session.clear()
            session["usuario"], session["perfil"] = u["nome"], u["perfil"]
            return redirect(url_for("painel.inicio"))
        log.warning("Login falhou para '%s' de %s", request.form.get("usuario", ""), request.remote_addr)
        flash("Usuário ou senha incorretos.")
    return render_template("login.html")


@painel.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("painel.login"))


# ---------------- Painel ----------------

@painel.get("/")
@login_obrigatorio()
def inicio():
    con = db()
    dispositivos = con.execute("SELECT * FROM dispositivos ORDER BY id").fetchall()
    escolhido = request.args.get("d") or (dispositivos[0]["id"] if dispositivos else None)
    disp = con.execute("SELECT * FROM dispositivos WHERE id = ?", (escolhido,)).fetchone()
    comandos = con.execute("SELECT * FROM comandos WHERE dispositivo_id = ? ORDER BY id DESC LIMIT 10",
                           (escolhido,)).fetchall()
    return render_template("painel.html", dispositivos=dispositivos, disp=disp, comandos=comandos, placas=PLACAS)


@painel.get("/painel/estado")
@login_obrigatorio()
def estado():
    """Cartões dos dispositivos (atualizados pelo JavaScript a cada 5 s)."""
    con = db()
    resultado = []
    for d in con.execute("SELECT * FROM dispositivos ORDER BY id").fetchall():
        ultima = con.execute("SELECT * FROM leituras WHERE dispositivo_id = ? ORDER BY ts DESC LIMIT 1",
                             (d["id"],)).fetchone()
        alertas = con.execute("SELECT COUNT(*) FROM alertas WHERE dispositivo_id = ? AND reconhecido_em IS NULL",
                              (d["id"],)).fetchone()[0]
        resultado.append({
            "id": d["id"], "nome": d["nome"], "placa": d["placa"], "online": esta_online(d),
            "temp_min": d["temp_min"], "temp_max": d["temp_max"], "alertas_abertos": alertas,
            "ultima": dict(ultima) if ultima else None,
        })
    return jsonify(resultado)


@painel.get("/painel/leituras")
@login_obrigatorio()
def leituras():
    """Série para o gráfico: últimos N minutos de um dispositivo."""
    minutos = request.args.get("minutos", 30, type=int)
    linhas = db().execute(
        "SELECT ts, temp, umid FROM leituras WHERE dispositivo_id = ? AND ts >= ? ORDER BY ts",
        (request.args.get("d"), agora() - minutos * 60)).fetchall()
    return jsonify([dict(l) for l in linhas])


# ---------------- Ações do ADMINISTRADOR ----------------

@painel.post("/dispositivos")
@login_obrigatorio(ADMIN)
def cadastrar():
    device_id = request.form.get("device_id", "").strip()
    placa = request.form.get("placa", "")
    if not ID_VALIDO.fullmatch(device_id) or placa not in PLACAS:
        flash("ID inválido (letras, números, _ ou -) ou placa desconhecida.")
    elif cadastrar_dispositivo(db(), device_id, placa, request.form.get("nome", "").strip() or None):
        db().commit()
        flash(f"Dispositivo {device_id} cadastrado.")
    else:
        flash(f"{device_id} já existe.")
    return redirect(url_for("painel.inicio", d=device_id))


@painel.post("/dispositivos/<device_id>/limites")
@login_obrigatorio(ADMIN)
def alterar_limites(device_id):
    minimo, maximo = numero_do_form("min"), numero_do_form("max")
    if minimo is None or maximo is None or not -40 <= minimo < maximo <= 80:  # mesma regra do firmware
        flash("Limites inválidos: precisa -40 ≤ mín < máx ≤ 80.")
    else:
        con = db()
        con.execute("UPDATE dispositivos SET temp_min = ?, temp_max = ? WHERE id = ?", (minimo, maximo, device_id))
        enfileirar(con, device_id, "SET_LIMITES", min=minimo, max=maximo)
        con.commit()
        flash(f"Limites salvos e SET_LIMITES enviado para {device_id}.")
    return redirect(url_for("painel.inicio", d=device_id))


@painel.post("/dispositivos/<device_id>/comando")
@login_obrigatorio(ADMIN)
def comando(device_id):
    tipo = request.form.get("tipo")
    con = db()
    if tipo in ("VENTILACAO_ON", "VENTILACAO_OFF", "REINICIAR"):
        enfileirar(con, device_id, tipo)
    elif tipo == "SET_INTERVALO" and request.form.get("segundos", "").isdigit() \
            and 1 <= int(request.form["segundos"]) <= 3600:
        enfileirar(con, device_id, tipo, segundos=int(request.form["segundos"]))
    else:
        flash("Comando inválido (intervalo deve ser 1 a 3600 s).")
        return redirect(url_for("painel.inicio", d=device_id))
    con.commit()
    flash(f"{tipo} enfileirado para {device_id}.")
    return redirect(url_for("painel.inicio", d=device_id))


# ---------------- Alertas, eventos e CSV ----------------

def filtros():
    """Lê ?inicio=&fim=&d= e devolve (inicio, fim, dispositivo, where, parâmetros)."""
    inicio, fim = ler_periodo(request.args.get("inicio"), request.args.get("fim"))
    dispositivo = request.args.get("d") or None
    where = "ts BETWEEN ? AND ?" + (" AND dispositivo_id = ?" if dispositivo else "")
    params = [inicio, fim] + ([dispositivo] if dispositivo else [])
    return inicio, fim, dispositivo, where, params


@painel.get("/alertas")
@login_obrigatorio()
def alertas():
    _, _, _, where, params = filtros()
    con = db()
    return render_template(
        "alertas.html",
        alertas=con.execute(f"SELECT * FROM alertas WHERE {where} ORDER BY ts DESC LIMIT 500", params).fetchall(),
        eventos=con.execute(f"SELECT * FROM eventos WHERE {where} ORDER BY ts DESC LIMIT 500", params).fetchall(),
        dispositivos=con.execute("SELECT id FROM dispositivos ORDER BY id").fetchall())


@painel.post("/alertas/<int:alerta_id>/reconhecer")
@login_obrigatorio()
def reconhecer(alerta_id):
    db().execute("UPDATE alertas SET reconhecido_por = ?, reconhecido_em = ? WHERE id = ? AND reconhecido_em IS NULL",
                 (session["usuario"], agora(), alerta_id))
    db().commit()
    return redirect(request.referrer or url_for("painel.alertas"))


@painel.get("/exportar.csv")
@login_obrigatorio()
def exportar_csv():
    tabela = "alertas" if request.args.get("tipo") == "alertas" else "eventos"  # nunca vem direto do usuário
    _, _, _, where, params = filtros()
    linhas = db().execute(f"SELECT * FROM {tabela} WHERE {where} ORDER BY ts", params).fetchall()
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")  # ";" abre certo no Excel em português
    if linhas:
        escritor.writerow(["data_hora", *linhas[0].keys()])
        escritor.writerows([[hora(l["ts"]), *l] for l in linhas])
    return Response("﻿" + saida.getvalue(), mimetype="text/csv",  # BOM: Excel lê os acentos
                    headers={"Content-Disposition": f"attachment; filename={tabela}.csv"})


@painel.get("/relatorio")
@login_obrigatorio()
def relatorio():
    inicio, fim, dispositivo, _, _ = filtros()
    return gerar_html(db(), inicio, fim, dispositivo)

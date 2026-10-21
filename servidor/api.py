"""api.py — rotas usadas pelo ESP32/UNO R4 e pelo simulador (contrato em firmware/vaxguard/rede.h).

Dispositivo desconhecido que manda telemetria ou evento é CADASTRADO
automaticamente (faixa padrão 2–8 °C). O ADMIN pode renomear/ajustar pelo painel.
"""
import json
import logging
import re

from flask import Blueprint, jsonify, request

import ia
from banco import agora, cadastrar_dispositivo, db

api = Blueprint("api", __name__)
log = logging.getLogger("vaxguard")

ESTADOS = ["NORMAL", "ATENCAO", "CRITICO", "RECONHECIDO", "FALHA_SENSOR"]
MOTIVOS = ["TEMP_FORA_FAIXA", "PORTA_ABERTA", "PERTO_LIMITE", "DIVERGENCIA_TEMP", "SENSOR_FALHA", "BOTAO", "OK"]
ID_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,32}")  # também evita HTML/JS no painel
MAX_COMANDOS_POR_VEZ = 3  # a resposta precisa caber no buffer de 1 KB do firmware

# campo: (tipo, aceita null, faixa ou lista de opções)
REGRAS_TELEMETRIA = {
    "device_id":  (str, False, ID_VALIDO),
    "placa":      (str, False, ID_VALIDO),
    "seq":        (int, False, (0, 2**32)),
    "ts":         (int, False, (0, 2**32)),
    "temp":       (float, True, (-40, 80)),
    "umid":       (float, True, (0, 100)),
    "porta":      (bool, False, None),
    "estado":     (str, False, ESTADOS),
    "luz_pct":    (float, False, (0, 100)),
    "temp_ntc":   (float, True, (-40, 80)),
    "ventilacao": (bool, False, None),
}
REGRAS_EVENTO = {
    "device_id": (str, False, ID_VALIDO),
    "placa":     (str, False, ID_VALIDO),
    "ts":        (int, False, (0, 2**32)),
    "de":        (str, False, ESTADOS),
    "para":      (str, False, ESTADOS),
    "motivo":    (str, False, MOTIVOS),
}
REGRAS_ACK = {
    "device_id": (str, False, ID_VALIDO),
    "ok":        (bool, False, None),
}


def tipo_certo(valor, tipo):
    if isinstance(valor, bool):  # em Python, True também é int: tratamos à parte
        return tipo is bool
    if tipo is float:
        return isinstance(valor, (int, float))
    return isinstance(valor, tipo)


def validar(dados, regras):
    """Devolve a mensagem de erro, ou None se estiver tudo certo."""
    if not isinstance(dados, dict):
        return "corpo precisa ser um objeto JSON"
    for campo, (tipo, aceita_null, regra) in regras.items():
        if campo not in dados:
            return f"campo obrigatório ausente: {campo}"
        valor = dados[campo]
        if valor is None:
            if aceita_null:
                continue
            return f"{campo} não pode ser null"
        if not tipo_certo(valor, tipo):
            return f"{campo} deveria ser {tipo.__name__}"
        if isinstance(regra, tuple) and not regra[0] <= valor <= regra[1]:  # NaN também cai aqui
            return f"{campo}={valor} fora da faixa {regra[0]} a {regra[1]}"
        if isinstance(regra, list) and valor not in regra:
            return f"{campo}={valor} não é um valor aceito"
        if isinstance(regra, re.Pattern) and not regra.fullmatch(valor):
            return f"{campo} inválido (use letras, números, _ ou -, até 32)"
    return None


def rejeitar(erro):
    """Loga no arquivo e responde 400."""
    corpo = request.get_data(as_text=True)[:300]
    log.warning("REJEITADO %s de %s: %s | corpo=%s", request.path, request.remote_addr, erro, corpo)
    return jsonify(ok=False, erro=erro), 400


def receber(regras):
    """Lê o JSON do corpo e valida. Devolve (dados, resposta_de_erro)."""
    dados = request.get_json(force=True, silent=True)  # force: aceita mesmo sem Content-Type
    erro = "JSON inválido" if dados is None else validar(dados, regras)
    return (None, rejeitar(erro)) if erro else (dados, None)


def garantir_dispositivo(con, dados, momento):
    if cadastrar_dispositivo(con, dados["device_id"], dados["placa"]):
        log.info("Dispositivo novo cadastrado automaticamente: %s (%s)", dados["device_id"], dados["placa"])
    con.execute("UPDATE dispositivos SET placa = ?, ultimo_contato = ? WHERE id = ?",
                (dados["placa"], momento, dados["device_id"]))


@api.post("/telemetria")
def telemetria():
    d, erro = receber(REGRAS_TELEMETRIA)
    if erro:
        return erro
    con = db()
    recebido = agora()
    garantir_dispositivo(con, d, recebido)

    # Reenvio do buffer offline que já tinha chegado: aceita sem duplicar.
    if d["ts"] and con.execute("SELECT 1 FROM leituras WHERE dispositivo_id = ? AND seq = ? AND ts_dispositivo = ?",
                               (d["device_id"], d["seq"], d["ts"])).fetchone():
        con.commit()
        return jsonify(ok=True, duplicada=True)

    ts = d["ts"] or recebido  # ts = 0: dispositivo ainda sem hora, usa a hora de chegada
    cur = con.execute(
        "INSERT INTO leituras (dispositivo_id, seq, ts, ts_dispositivo, recebido_em, temp, umid, temp_ntc, "
        "luz_pct, porta, ventilacao, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (d["device_id"], d["seq"], ts, d["ts"], recebido, d["temp"], d["umid"], d["temp_ntc"],
         d["luz_pct"], d["porta"], d["ventilacao"], d["estado"]))
    if d["temp"] is not None:
        disp = con.execute("SELECT * FROM dispositivos WHERE id = ?", (d["device_id"],)).fetchone()
        ia.analisar_leitura(con, disp, cur.lastrowid, ts, d["temp"])
    con.commit()
    return jsonify(ok=True), 201


@api.post("/eventos")
def eventos():
    d, erro = receber(REGRAS_EVENTO)
    if erro:
        return erro
    con = db()
    recebido = agora()
    garantir_dispositivo(con, d, recebido)
    con.execute("INSERT INTO eventos (dispositivo_id, ts, recebido_em, de, para, motivo) VALUES (?, ?, ?, ?, ?, ?)",
                (d["device_id"], d["ts"] or recebido, recebido, d["de"], d["para"], d["motivo"]))
    con.commit()
    log.info("Evento %s: %s -> %s (%s)", d["device_id"], d["de"], d["para"], d["motivo"])
    return jsonify(ok=True), 201


@api.get("/comandos")
def comandos_pendentes():
    device_id = request.args.get("device_id", "")
    if not ID_VALIDO.fullmatch(device_id):
        return rejeitar("device_id ausente ou inválido")
    linhas = db().execute(
        "SELECT id, tipo, parametros FROM comandos WHERE dispositivo_id = ? AND status = 'PENDENTE' ORDER BY id LIMIT ?",
        (device_id, MAX_COMANDOS_POR_VEZ)).fetchall()
    # Fica PENDENTE até o ack: se o ack se perder, o comando é entregue de novo.
    return jsonify([{"id": l["id"], "tipo": l["tipo"], **json.loads(l["parametros"])} for l in linhas])


@api.post("/comandos/<int:comando_id>/ack")
def confirmar_comando(comando_id):
    d, erro = receber(REGRAS_ACK)
    if erro:
        return erro
    con = db()
    cmd = con.execute("SELECT * FROM comandos WHERE id = ? AND dispositivo_id = ?",
                      (comando_id, d["device_id"])).fetchone()
    if cmd is None:
        log.warning("ACK de comando inexistente %s de %s", comando_id, d["device_id"])
        return jsonify(ok=False, erro="comando não encontrado para este dispositivo"), 404
    if cmd["status"] == "PENDENTE":
        status = "EXECUTADO" if d["ok"] else "REJEITADO"
        con.execute("UPDATE comandos SET status = ?, confirmado_em = ? WHERE id = ?", (status, agora(), comando_id))
        if d["ok"] and cmd["tipo"] == "SET_INTERVALO":  # muda o critério de ONLINE/OFFLINE
            segundos = json.loads(cmd["parametros"])["segundos"]
            con.execute("UPDATE dispositivos SET intervalo_s = ? WHERE id = ?", (segundos, d["device_id"]))
        con.commit()
        log.info("Comando %s (%s) de %s: %s", comando_id, cmd["tipo"], d["device_id"], status)
    return jsonify(ok=True)

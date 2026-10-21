"""ponte_mqtt.py — liga o ESP32 (via broker MQTT público) ao servidor Flask local.

Por quê: o firewall do PC bloqueia conexões de ENTRADA. O ESP32 publica no broker e
esta ponte, rodando no PC, só faz conexões de SAÍDA (para o broker e para o Flask local).

Rodar (com o servidor já ligado em outro terminal):  python ponte_mqtt.py

Tópicos (BASE = MQTT_BASE):
  BASE/<device_id>/telemetria  -> POST /api/telemetria
  BASE/<device_id>/eventos     -> POST /api/eventos
  BASE/<device_id>/ack         -> POST /api/comandos/<id>/ack
  BASE/<device_id>/cmd         <- comandos pendentes (um objeto por mensagem)

ATENÇÃO: broker público = qualquer pessoa pode ler e publicar. Só para demonstração.
"""
import json
import os
import random
import re
import time
import urllib.error
import urllib.request

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "broker.hivemq.com")
MQTT_PORTA = int(os.environ.get("MQTT_PORTA", "1883"))
MQTT_BASE = os.environ.get("MQTT_BASE", "vaxguard_senai_x7k2")
SERVIDOR_URL = os.environ.get("SERVIDOR_URL", "http://127.0.0.1:5000").rstrip("/")

INTERVALO_CMD_S = 2     # de quanto em quanto tempo consulta comandos pendentes
REENVIO_CMD_S = 15      # sem ack nesse tempo, publica o comando de novo
ID_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,32}")  # mesma regra do api.py
TIPOS = ("telemetria", "eventos", "ack")

dispositivos = set()    # device_ids que o servidor aceitou (só eles têm comandos consultados)
enviados = {}           # device_id -> {id_comando: momento da última publicação}


def log(area, texto):
    print(f"{time.strftime('%H:%M:%S')} [{area}] {texto}", flush=True)


# ---------- validação (o broker é público: não confie em nada que chega) ----------

def validar_mensagem(topico, payload, base=MQTT_BASE):
    """Devolve (device_id, tipo, dados) ou levanta ValueError com o motivo."""
    partes = topico.split("/")
    if len(partes) != 3 or partes[0] != base or partes[2] not in TIPOS:
        raise ValueError("tópico inesperado")
    device_id, tipo = partes[1], partes[2]
    if not ID_VALIDO.fullmatch(device_id):
        raise ValueError("device_id inválido no tópico")
    try:
        dados = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("payload não é JSON") from None
    if not isinstance(dados, dict):
        raise ValueError("payload não é um objeto JSON")
    if dados.get("device_id") != device_id:
        raise ValueError("device_id do JSON diferente do tópico")
    if tipo == "ack" and (type(dados.get("id")) is not int or type(dados.get("ok")) is not bool):
        raise ValueError("ack precisa de id (inteiro) e ok (true/false)")
    return device_id, tipo, dados


def deve_publicar(device_id, id_comando, agora):
    """True se o comando nunca foi publicado ou se já passou REENVIO_CMD_S sem ack."""
    ultimo = enviados.get(device_id, {}).get(id_comando)
    return ultimo is None or agora - ultimo >= REENVIO_CMD_S


# ---------- HTTP para o servidor local (urllib da biblioteca padrão) ----------

def http(metodo, caminho, dados=None):
    """Devolve (status, corpo_json). status 0 = servidor fora do ar."""
    corpo = json.dumps(dados).encode() if dados is not None else None
    req = urllib.request.Request(SERVIDOR_URL + caminho, data=corpo, method=metodo,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:  # 400/404: o servidor recusou, segue a vida
        return e.code, e.read()[:200].decode(errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, str(e)


# ---------- MQTT ----------

def ao_conectar(cliente, _userdata, _flags, codigo, _props):
    if codigo.is_failure:
        log("MQTT", f"falha ao conectar: {codigo}")
        return
    log("MQTT", f"conectado em {MQTT_HOST}:{MQTT_PORTA}, base '{MQTT_BASE}'")
    # assina de novo a cada (re)conexão
    cliente.subscribe([(f"{MQTT_BASE}/+/{tipo}", 0) for tipo in TIPOS])


def ao_desconectar(_cliente, _userdata, _flags, codigo, _props):
    log("MQTT", f"desconectado ({codigo}); tentando reconectar...")


def ao_receber(_cliente, _userdata, msg):
    try:
        device_id, tipo, dados = validar_mensagem(msg.topic, msg.payload)
    except ValueError as e:
        log("MQTT", f"descartado {msg.topic}: {e} | {msg.payload[:100]!r}")
        return

    if tipo == "ack":
        status, resp = http("POST", f"/api/comandos/{dados['id']}/ack",
                            {"device_id": device_id, "ok": dados["ok"]})
        enviados.get(device_id, {}).pop(dados["id"], None)
        log("CMD", f"ack {device_id} comando {dados['id']} ok={dados['ok']} -> HTTP {status} {resp}")
        return

    status, resp = http("POST", f"/api/{tipo}", dados)
    if 200 <= status < 300:
        if device_id not in dispositivos:
            log("SERVIDOR", f"dispositivo {device_id} visto; vou consultar comandos dele")
        dispositivos.add(device_id)
        log("SERVIDOR", f"{tipo} de {device_id} -> HTTP {status}")
    else:
        log("SERVIDOR", f"{tipo} de {device_id} recusado -> HTTP {status} {resp}")


def publicar_comandos(cliente):
    """Busca os pendentes de cada dispositivo e publica os que ainda não foram (ou venceram 15 s)."""
    for device_id in list(dispositivos):  # list(): o conjunto muda na thread do MQTT
        status, pendentes = http("GET", f"/api/comandos?device_id={device_id}")
        if status != 200 or not isinstance(pendentes, list):
            log("SERVIDOR", f"GET comandos {device_id} -> HTTP {status} {pendentes}")
            continue
        agora = time.monotonic()
        ja = enviados.setdefault(device_id, {})
        ids_pendentes = {c["id"] for c in pendentes}
        for id_antigo in list(ja):  # esquece os que deixaram de estar pendentes
            if id_antigo not in ids_pendentes:
                ja.pop(id_antigo)
        for cmd in pendentes:
            if deve_publicar(device_id, cmd["id"], agora):
                cliente.publish(f"{MQTT_BASE}/{device_id}/cmd", json.dumps(cmd), qos=0, retain=False)
                ja[cmd["id"]] = agora
                log("CMD", f"publicado para {device_id}: {cmd}")


def main():
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                          client_id=f"vaxguard-ponte-{random.randint(0, 0xFFFFFF):06x}")
    cliente.on_connect = ao_conectar
    cliente.on_disconnect = ao_desconectar
    cliente.on_message = ao_receber
    cliente.reconnect_delay_set(min_delay=1, max_delay=30)
    log("MQTT", f"conectando em {MQTT_HOST}:{MQTT_PORTA} (servidor: {SERVIDOR_URL})")
    cliente.connect_async(MQTT_HOST, MQTT_PORTA, keepalive=30)
    cliente.loop_start()  # thread do MQTT: recebe e reconecta sozinha
    try:
        while True:
            if cliente.is_connected():
                publicar_comandos(cliente)
            time.sleep(INTERVALO_CMD_S)
    except KeyboardInterrupt:
        log("MQTT", "encerrando")
    finally:
        cliente.loop_stop()
        cliente.disconnect()


if __name__ == "__main__":
    main()

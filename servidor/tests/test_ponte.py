"""Testes da ponte MQTT sem rede. Rodar:  python -m pytest tests"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ponte_mqtt as p  # noqa: E402

B = "base_teste"


def test_mensagem_valida():
    dados = {"device_id": "VG-CAM01", "temp": 5}
    assert p.validar_mensagem(f"{B}/VG-CAM01/telemetria", json.dumps(dados).encode(), B) == \
        ("VG-CAM01", "telemetria", dados)
    ack = {"device_id": "VG-CAM01", "id": 7, "ok": True}
    assert p.validar_mensagem(f"{B}/VG-CAM01/ack", json.dumps(ack).encode(), B)[2] == ack


@pytest.mark.parametrize("topico,payload", [
    ("outra_base/VG-CAM01/telemetria", '{"device_id":"VG-CAM01"}'),
    (f"{B}/VG-CAM01/cmd", '{"device_id":"VG-CAM01"}'),            # tópico que a ponte não trata
    (f"{B}/VG-CAM01/telemetria/x", '{"device_id":"VG-CAM01"}'),
    (f"{B}/<script>/telemetria", '{"device_id":"<script>"}'),
    (f"{B}/VG-CAM01/telemetria", "não é json"),
    (f"{B}/VG-CAM01/telemetria", b"\xff\xfe"),
    (f"{B}/VG-CAM01/telemetria", "[1, 2]"),
    (f"{B}/VG-CAM01/telemetria", '{"device_id":"VG-CAM99"}'),     # JSON diferente do tópico
    (f"{B}/VG-CAM01/ack", '{"device_id":"VG-CAM01","id":"1","ok":true}'),
    (f"{B}/VG-CAM01/ack", '{"device_id":"VG-CAM01","id":1,"ok":1}'),
])
def test_mensagem_invalida(topico, payload):
    with pytest.raises(ValueError):
        p.validar_mensagem(topico, payload.encode() if isinstance(payload, str) else payload, B)


def test_nao_republica_antes_de_15s():
    p.enviados.clear()
    assert p.deve_publicar("VG-CAM01", 1, 100.0)
    p.enviados["VG-CAM01"] = {1: 100.0}
    assert not p.deve_publicar("VG-CAM01", 1, 102.0)
    assert not p.deve_publicar("VG-CAM01", 1, 114.9)
    assert p.deve_publicar("VG-CAM01", 1, 115.0)
    assert p.deve_publicar("VG-CAM01", 2, 102.0)      # outro comando: publica
    assert p.deve_publicar("VG-CAM02", 1, 102.0)      # outro dispositivo: publica
    p.enviados.clear()

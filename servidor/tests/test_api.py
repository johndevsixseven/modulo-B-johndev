"""Testes do servidor. Rodar:  python -m pytest tests   (ou  python tests/test_api.py)"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["VAXGUARD_SENHA_ADMIN"] = "admin-teste"
os.environ["VAXGUARD_SENHA_OPERADOR"] = "operador-teste"

import ia  # noqa: E402
from app import PASTA, criar_app  # noqa: E402


def novo_cliente():
    pasta = tempfile.mkdtemp()
    app = criar_app(os.path.join(pasta, "teste.db"))
    return app, app.test_client()


def leitura(**mudancas):
    base = {"device_id": "VG-CAM01", "placa": "UNO_R4_WIFI", "seq": 1, "ts": int(time.time()), "temp": 5.0,
            "umid": 60, "porta": False, "estado": "NORMAL", "luz_pct": 3, "temp_ntc": 5.1, "ventilacao": False}
    base.update(mudancas)
    return base


def login(cliente, usuario):
    return cliente.post("/login", data={"usuario": usuario, "senha": f"{usuario}-teste"})


def test_validacao():
    _, c = novo_cliente()
    assert c.post("/api/telemetria", json=leitura()).status_code == 201
    assert c.post("/api/telemetria", json=leitura(seq=2, temp=None, umid=None, temp_ntc=None)).status_code == 201
    invalidos = [leitura(umid=150), leitura(temp=-41), leitura(temp="5"), leitura(porta=1), leitura(seq=True),
                 leitura(estado="QUALQUER"), leitura(device_id="<script>"), {"device_id": "VG-CAM01"}]
    for corpo in invalidos:
        r = c.post("/api/telemetria", json=corpo)
        assert r.status_code == 400, corpo
    assert c.post("/api/telemetria", data="isto não é json").status_code == 400
    with open(os.path.join(PASTA, "logs", "servidor.log"), encoding="utf-8") as f:
        assert "REJEITADO /api/telemetria" in f.read()
    evento = {"device_id": "VG-CAM01", "placa": "UNO_R4_WIFI", "ts": 0, "de": "NORMAL", "para": "ATENCAO",
              "motivo": "PORTA_ABERTA"}
    assert c.post("/api/eventos", json=evento).status_code == 201
    assert c.post("/api/eventos", json={**evento, "motivo": "X"}).status_code == 400


def test_ts_zero_e_duplicada():
    app, c = novo_cliente()
    c.post("/api/telemetria", json=leitura(ts=0))
    ts = int(time.time())
    c.post("/api/telemetria", json=leitura(seq=2, ts=ts))
    assert c.post("/api/telemetria", json=leitura(seq=2, ts=ts)).get_json()["duplicada"]
    with app.app_context():
        from banco import db
        linhas = db().execute("SELECT ts, ts_dispositivo, recebido_em FROM leituras ORDER BY id").fetchall()
    assert len(linhas) == 2
    assert linhas[0]["ts_dispositivo"] == 0 and linhas[0]["ts"] == linhas[0]["recebido_em"]


def test_fluxo_de_comandos():
    _, c = novo_cliente()
    c.post("/api/telemetria", json=leitura())  # cadastra VG-CAM01 automaticamente
    login(c, "admin")
    assert c.post("/dispositivos/VG-CAM01/limites", data={"min": "3", "max": "7,5"}).status_code == 302
    cmds = c.get("/api/comandos?device_id=VG-CAM01").get_json()
    assert cmds == [{"id": 1, "tipo": "SET_LIMITES", "min": 3.0, "max": 7.5}]
    assert c.post("/api/comandos/1/ack", json={"device_id": "VG-CAM01", "ok": True}).status_code == 200
    assert c.get("/api/comandos?device_id=VG-CAM01").get_json() == []
    assert c.post("/api/comandos/1/ack", json={"device_id": "OUTRO", "ok": True}).status_code == 404

    c.post("/dispositivos/VG-CAM01/comando", data={"tipo": "SET_INTERVALO", "segundos": "10"})
    for tipo in ("VENTILACAO_ON", "VENTILACAO_OFF", "REINICIAR"):
        c.post("/dispositivos/VG-CAM01/comando", data={"tipo": tipo})
    cmds = c.get("/api/comandos?device_id=VG-CAM01").get_json()
    assert [x["tipo"] for x in cmds] == ["SET_INTERVALO", "VENTILACAO_ON", "VENTILACAO_OFF"]  # no máximo 3
    assert cmds[0]["segundos"] == 10
    c.post(f"/api/comandos/{cmds[0]['id']}/ack", json={"device_id": "VG-CAM01", "ok": True})
    c.post(f"/api/comandos/{cmds[1]['id']}/ack", json={"device_id": "VG-CAM01", "ok": False})
    pagina = c.get("/?d=VG-CAM01").get_data(as_text=True)
    assert "EXECUTADO" in pagina and "REJEITADO" in pagina
    assert 'value="10"' in pagina  # intervalo atualizado depois do ack


def test_risco_de_excursao_sem_duplicar():
    app, c = novo_cliente()
    agora = int(time.time())
    # Sobe 0,6 °C/min a partir de 4 °C: chega a 8 °C em menos de 5 min.
    for i in range(12):
        c.post("/api/telemetria", json=leitura(seq=i, ts=agora - 110 + i * 10, temp=round(4 + 0.01 * i * 10, 2)))
    with app.app_context():
        from banco import db
        alertas = db().execute("SELECT tipo, mensagem FROM alertas").fetchall()
    assert [a["tipo"] for a in alertas] == [ia.RISCO], [dict(a) for a in alertas]


def test_estavel_nao_gera_risco_e_anomalia_dispara():
    app, c = novo_cliente()
    agora = int(time.time())
    for i in range(15):
        c.post("/api/telemetria", json=leitura(seq=i, ts=agora - 100 + i * 5, temp=5.0))
    c.post("/api/telemetria", json=leitura(seq=99, ts=agora, temp=7.5))
    with app.app_context():
        from banco import db
        tipos = [a["tipo"] for a in db().execute("SELECT tipo FROM alertas")]
    assert ia.ANOMALIA in tipos


def test_segundos_ate_limite():
    assert ia.segundos_ate_limite(5.0, 0.01, 2, 8) == 300  # 3 °C a 0,01 °C/s
    assert ia.segundos_ate_limite(5.0, -0.01, 2, 8) == 300
    assert ia.segundos_ate_limite(9.0, 0.01, 2, 8) is None  # já está fora


def test_login_e_perfis():
    _, c = novo_cliente()
    assert c.get("/").status_code == 302  # sem login vai para /login
    assert login(c, "operador").status_code == 302
    assert c.get("/").status_code == 200
    assert c.get("/alertas").status_code == 200
    assert c.post("/dispositivos/VG-CAM01/limites", data={"min": "2", "max": "8"}).status_code == 403
    assert c.post("/dispositivos", data={"device_id": "VG-CAM09", "placa": "ESP32"}).status_code == 403
    c.get("/logout")
    assert c.post("/login", data={"usuario": "admin", "senha": "errada"}).status_code == 200  # volta ao form
    login(c, "admin")
    assert c.post("/dispositivos", data={"device_id": "VG-CAM09", "placa": "ESP32"}).status_code == 302
    assert any(d["id"] == "VG-CAM09" for d in c.get("/painel/estado").get_json())


def test_relatorio_e_csv():
    _, c = novo_cliente()
    agora = int(time.time())
    for i, t in enumerate([5, 5, 9, 9.5, 5]):
        c.post("/api/telemetria", json=leitura(seq=i, ts=agora - 50 + i * 5, temp=t, porta=i == 1))
    login(c, "operador")
    html = c.get("/relatorio").get_data(as_text=True)
    assert "NÃO CONFORME" in html and "data:image/png;base64" in html and "9.5 °C" in html
    assert c.get("/exportar.csv?tipo=eventos").status_code == 200


if __name__ == "__main__":
    for nome, funcao in list(globals().items()):
        if nome.startswith("test_"):
            funcao()
            print("ok", nome)

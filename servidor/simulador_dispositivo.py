"""simulador_dispositivo.py — finge ser uma segunda câmara fria (VG-CAM02, placa SIMULADOR).

Usa exatamente o mesmo contrato do firmware: telemetria, eventos, busca e ack de comandos.

Exemplos:
    python simulador_dispositivo.py                      # câmara estável em ~5 °C
    python simulador_dispositivo.py --aquecer 0.5        # esquenta 0,5 °C por minuto
    python simulador_dispositivo.py --url http://192.168.0.10:5000 --ciclos 20
"""
import argparse
import json
import random
import time
import urllib.error
import urllib.request

PLACA = "SIMULADOR"


def http(metodo, url, corpo=None):
    """Faz a requisição e devolve (código, resposta em JSON ou None)."""
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except OSError as e:  # servidor fora do ar
        print("  [REDE] falha:", e)
        return -1, None


def calcular_estado(temp, porta_aberta, tmin, tmax):
    """Versão simplificada da máquina de estados do firmware."""
    if not tmin <= temp <= tmax:
        return "CRITICO", "TEMP_FORA_FAIXA"
    if porta_aberta:
        return "ATENCAO", "PORTA_ABERTA"
    if temp < tmin + 1 or temp > tmax - 1:
        return "ATENCAO", "PERTO_LIMITE"
    return "NORMAL", "OK"


def main():
    p = argparse.ArgumentParser(description="Simulador de câmara fria VaxGuard")
    p.add_argument("--url", default="http://127.0.0.1:5000")
    p.add_argument("--device", default="VG-CAM02")
    p.add_argument("--intervalo", type=float, default=5, help="segundos entre leituras")
    p.add_argument("--aquecer", type=float, default=0.0, help="aquecimento gradual em °C por minuto (ex.: 0.5)")
    p.add_argument("--ciclos", type=int, default=0, help="quantas leituras enviar (0 = sem fim)")
    p.add_argument("--temp-inicial", type=float, default=5.0)
    a = p.parse_args()

    temp, tmin, tmax = a.temp_inicial, 2.0, 8.0
    intervalo, ventilacao, estado, seq = a.intervalo, False, "NORMAL", 0
    ciclo = 0
    while a.ciclos == 0 or ciclo < a.ciclos:
        ciclo += 1
        seq += 1
        # Física de brinquedo: aquece no ritmo pedido; a ventilação esfria 1 °C/min.
        temp += (a.aquecer - (1.0 if ventilacao else 0.0)) * intervalo / 60 + random.uniform(-0.05, 0.05)
        porta = random.random() < 0.05

        novo, motivo = calcular_estado(temp, porta, tmin, tmax)
        if novo != estado:
            http("POST", f"{a.url}/api/eventos", {"device_id": a.device, "placa": PLACA, "ts": int(time.time()),
                                                   "de": estado, "para": novo, "motivo": motivo})
            estado = novo

        leitura = {"device_id": a.device, "placa": PLACA, "seq": seq, "ts": int(time.time()),
                   "temp": round(temp, 1), "umid": round(random.uniform(55, 65), 1), "porta": porta,
                   "estado": estado, "luz_pct": 80 if porta else 3, "temp_ntc": round(temp + random.uniform(-0.3, 0.3), 1),
                   "ventilacao": ventilacao}
        codigo, _ = http("POST", f"{a.url}/api/telemetria", leitura)
        print(f"[{seq}] {temp:5.1f} °C  {estado:8}  porta={'ABERTA' if porta else 'fechada'}  -> HTTP {codigo}")

        # Comandos: busca, executa e confirma (igual ao firmware).
        codigo, comandos = http("GET", f"{a.url}/api/comandos?device_id={a.device}")
        for c in (comandos or []) if codigo == 200 else []:
            ok = True
            if c["tipo"] == "SET_LIMITES" and -40 <= c.get("min", 99) < c.get("max", -99) <= 80:
                tmin, tmax = c["min"], c["max"]
            elif c["tipo"] == "SET_INTERVALO" and 1 <= c.get("segundos", 0) <= 3600:
                intervalo = c["segundos"]
            elif c["tipo"] in ("VENTILACAO_ON", "VENTILACAO_OFF"):
                ventilacao = c["tipo"] == "VENTILACAO_ON"
            elif c["tipo"] == "REINICIAR":
                seq = 0  # "reinício": contador volta do zero
            else:
                ok = False
            print(f"  [CMD] {c} -> {'ok' if ok else 'rejeitado'}")
            http("POST", f"{a.url}/api/comandos/{c['id']}/ack", {"device_id": a.device, "ok": ok})

        if a.ciclos == 0 or ciclo < a.ciclos:
            time.sleep(intervalo)


if __name__ == "__main__":
    main()

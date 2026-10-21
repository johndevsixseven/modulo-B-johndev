"""ia.py — "inteligência" do servidor: anomalias, previsão de excursão e KPIs.

Tudo com a biblioteca padrão (statistics), sem scikit-learn.
"""
import statistics

from banco import agora

# Anomalia: z-score da leitura nova contra as últimas leituras do dispositivo.
JANELA_ZSCORE = 30      # quantas leituras anteriores entram na média
MINIMO_ZSCORE = 10      # com menos que isso não dá para julgar
LIMIAR_Z = 3.0          # |z| acima disso = anomalia
DESVIO_MINIMO = 0.5     # °C; o DHT11 mede de 1 em 1 °C, então o desvio real costuma ser ~0
PAUSA_ANOMALIA_S = 300  # não repete alerta de anomalia antes disso

# Previsão: regressão linear das leituras dos últimos 2 min.
JANELA_REGRESSAO_S = 120
MINIMO_REGRESSAO = 5
HORIZONTE_RISCO_S = 300  # cruza o limite em menos de 5 min = RISCO DE EXCURSÃO

RISCO = "RISCO DE EXCURSÃO"
ANOMALIA = "ANOMALIA"


def criar_alerta(con, dispositivo_id, ts, tipo, mensagem):
    con.execute("INSERT INTO alertas (dispositivo_id, ts, tipo, mensagem) VALUES (?, ?, ?, ?)",
                (dispositivo_id, ts, tipo, mensagem))


def analisar_leitura(con, disp, leitura_id, ts, temp):
    """Chamada a cada telemetria nova com temperatura. disp = linha de dispositivos."""
    if ts < agora() - JANELA_REGRESSAO_S:
        return  # leitura antiga vinda do buffer offline: não gera alerta "ao vivo"
    verificar_anomalia(con, disp, leitura_id, ts, temp)
    verificar_risco(con, disp, ts)


def zscore(valor, historico):
    """z = (valor - média) / desvio, com desvio mínimo para não exagerar."""
    desvio = max(statistics.pstdev(historico), DESVIO_MINIMO)
    return (valor - statistics.mean(historico)) / desvio


def verificar_anomalia(con, disp, leitura_id, ts, temp):
    linhas = con.execute(
        "SELECT temp FROM leituras WHERE dispositivo_id = ? AND temp IS NOT NULL AND id != ? "
        "ORDER BY ts DESC LIMIT ?", (disp["id"], leitura_id, JANELA_ZSCORE)).fetchall()
    if len(linhas) < MINIMO_ZSCORE:
        return
    z = zscore(temp, [l["temp"] for l in linhas])
    if abs(z) < LIMIAR_Z:
        return
    recente = con.execute("SELECT 1 FROM alertas WHERE dispositivo_id = ? AND tipo = ? AND ts > ?",
                          (disp["id"], ANOMALIA, ts - PAUSA_ANOMALIA_S)).fetchone()
    if not recente:
        criar_alerta(con, disp["id"], ts, ANOMALIA, f"Leitura {temp:.1f} °C fora do padrão (z = {z:+.1f})")


def segundos_ate_limite(atual, inclinacao, temp_min, temp_max):
    """Quanto tempo (s) a reta leva para cruzar um limite. None = não cruza / já está fora."""
    if not temp_min <= atual <= temp_max:
        return None
    if inclinacao > 0:
        return (temp_max - atual) / inclinacao
    if inclinacao < 0:
        return (temp_min - atual) / inclinacao
    return None


def verificar_risco(con, disp, ts):
    linhas = con.execute(
        "SELECT ts, temp FROM leituras WHERE dispositivo_id = ? AND temp IS NOT NULL AND ts BETWEEN ? AND ? ORDER BY ts",
        (disp["id"], ts - JANELA_REGRESSAO_S, ts)).fetchall()
    xs = [l["ts"] - ts for l in linhas]  # segundos relativos a agora (evita números enormes)
    if len(linhas) < MINIMO_REGRESSAO or len(set(xs)) < 2:
        return
    inclinacao, atual = statistics.linear_regression(xs, [l["temp"] for l in linhas])  # atual = valor da reta em x=0
    faltam = segundos_ate_limite(atual, inclinacao, disp["temp_min"], disp["temp_max"])
    em_risco = faltam is not None and faltam < HORIZONTE_RISCO_S

    if em_risco and not disp["risco_ativo"]:
        limite = disp["temp_max"] if inclinacao > 0 else disp["temp_min"]
        criar_alerta(con, disp["id"], ts, RISCO,
                     f"Tendência {inclinacao * 60:+.2f} °C/min: cruza {limite:.1f} °C em ~{faltam / 60:.1f} min")
        con.execute("UPDATE dispositivos SET risco_ativo = 1 WHERE id = ?", (disp["id"],))
    elif not em_risco and disp["temp_min"] <= atual <= disp["temp_max"]:
        # voltou ao normal dentro da faixa: um próximo risco pode gerar alerta novo
        con.execute("UPDATE dispositivos SET risco_ativo = 0 WHERE id = ?", (disp["id"],))


# ---------------- KPIs e excursões (usados no painel e no relatório) ----------------

def leituras_periodo(con, dispositivo_id, inicio, fim):
    return con.execute(
        "SELECT ts, temp, umid, porta FROM leituras WHERE dispositivo_id = ? AND ts BETWEEN ? AND ? ORDER BY ts",
        (dispositivo_id, inicio, fim)).fetchall()


def fora_da_faixa(temp, disp):
    return temp is not None and not disp["temp_min"] <= temp <= disp["temp_max"]


def calcular_kpis(disp, linhas, inicio, fim):
    """KPIs de um dispositivo. Usa os limites ATUAIS do dispositivo."""
    lacuna_max = 3 * disp["intervalo_s"]  # buraco maior que isso = dispositivo offline
    online = fora = porta_aberta = 0
    aberturas = 1 if linhas and linhas[0]["porta"] else 0
    for a, b in zip(linhas, linhas[1:]):
        dt = min(b["ts"] - a["ts"], lacuna_max)
        online += dt
        if fora_da_faixa(a["temp"], disp):
            fora += dt
        if a["porta"]:
            porta_aberta += dt
        if b["porta"] and not a["porta"]:
            aberturas += 1

    temps = [l["temp"] for l in linhas if l["temp"] is not None]
    periodo = max(fim - max(inicio, disp["criado_em"]), 1)
    return {
        "leituras": len(linhas),
        "tempo_fora_min": fora / 60,
        "aberturas_porta": aberturas,
        "porta_media_s": porta_aberta / aberturas if aberturas else 0,
        "disponibilidade_pct": min(100.0, 100 * online / periodo),
        "temp_min": min(temps) if temps else None,
        "temp_media": statistics.mean(temps) if temps else None,
        "temp_max": max(temps) if temps else None,
    }


def calcular_excursoes(disp, linhas):
    """Trechos seguidos fora da faixa: [{inicio, fim, pico}]."""
    def distancia(t):  # quanto passou do limite
        return max(t - disp["temp_max"], disp["temp_min"] - t)

    lista, atual = [], None
    for l in linhas:
        if l["temp"] is None:
            continue
        if fora_da_faixa(l["temp"], disp):
            if atual is None:
                atual = {"inicio": l["ts"], "fim": l["ts"], "pico": l["temp"]}
            atual["fim"] = l["ts"]
            atual["pico"] = max(atual["pico"], l["temp"], key=distancia)
        elif atual:
            atual["fim"] = l["ts"]  # termina quando volta para a faixa
            lista.append(atual)
            atual = None
    if atual:
        lista.append(atual)
    return lista

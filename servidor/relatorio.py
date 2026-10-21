"""relatorio.py — relatório de conformidade em HTML (um arquivo só, gráficos PNG embutidos).

Uso pela linha de comando:
    python relatorio.py --inicio 2026-10-20 --fim 2026-10-21 [--dispositivo VG-CAM01]
Também abre pelo painel em /relatorio.
"""
import argparse
import base64
import io
import os
from datetime import datetime, timedelta
from html import escape

import matplotlib
matplotlib.use("Agg")  # gera imagens sem abrir janela
from matplotlib.figure import Figure

import ia
from banco import agora


def ler_periodo(inicio_txt, fim_txt):
    """Datas 'AAAA-MM-DD' (hora local) -> (epoch início, epoch fim). Fim inclui o dia todo. Padrão: últimas 24 h."""
    try:
        inicio = int(datetime.strptime(inicio_txt, "%Y-%m-%d").timestamp())
        fim = int((datetime.strptime(fim_txt, "%Y-%m-%d") + timedelta(days=1)).timestamp()) - 1
        return inicio, fim
    except (TypeError, ValueError):
        return agora() - 86400, agora()


def hora(ts):
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")


def numero(valor, casas=1):
    return "—" if valor is None else f"{valor:.{casas}f}"


def grafico_png(disp, linhas):
    """Gráfico de temperatura (com a faixa ideal) e umidade, em base64."""
    fig = Figure(figsize=(9, 4.5))
    ax_t, ax_u = fig.subplots(2, 1, sharex=True)
    datas = [datetime.fromtimestamp(l["ts"]) for l in linhas]
    ax_t.axhspan(disp["temp_min"], disp["temp_max"], color="green", alpha=0.15, label="faixa ideal")
    ax_t.plot(datas, [l["temp"] for l in linhas], color="tab:red", label="temperatura")
    ax_t.set_ylabel("°C")
    ax_t.legend(loc="upper left")
    ax_u.plot(datas, [l["umid"] for l in linhas], color="tab:blue")
    ax_u.set_ylabel("umidade %")
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=80, bbox_inches="tight")
    return base64.b64encode(buf.getvalue()).decode()


def gerar_html(con, inicio, fim, dispositivo_id=None):
    if dispositivo_id:
        dispositivos = con.execute("SELECT * FROM dispositivos WHERE id = ?", (dispositivo_id,)).fetchall()
    else:
        dispositivos = con.execute("SELECT * FROM dispositivos ORDER BY id").fetchall()

    partes = [f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>Relatório de conformidade</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:auto;padding:16px}}
table{{border-collapse:collapse;margin:8px 0}}td,th{{border:1px solid #ccc;padding:4px 8px}}
img{{max-width:100%}}</style></head><body>
<h1>VaxGuard Connect — Relatório de conformidade</h1>
<p>Período: <b>{hora(inicio)}</b> a <b>{hora(fim)}</b> · gerado em {hora(agora())}</p>"""]

    for disp in dispositivos:
        linhas = ia.leituras_periodo(con, disp["id"], inicio, fim)
        k = ia.calcular_kpis(disp, linhas, inicio, fim)
        excursoes = ia.calcular_excursoes(disp, linhas)
        alertas = con.execute("SELECT COUNT(*) FROM alertas WHERE dispositivo_id = ? AND ts BETWEEN ? AND ?",
                              (disp["id"], inicio, fim)).fetchone()[0]
        conforme = "CONFORME" if not excursoes else "NÃO CONFORME"
        partes.append(f"""<h2>{escape(disp['nome'])} ({escape(disp['id'])}, {escape(disp['placa'])}) — {conforme}</h2>
<p>Faixa ideal: {disp['temp_min']:.1f} a {disp['temp_max']:.1f} °C · alertas da IA no período: {alertas}</p>
<table>
<tr><th>Leituras</th><td>{k['leituras']}</td></tr>
<tr><th>Tempo fora da faixa</th><td>{k['tempo_fora_min']:.1f} min</td></tr>
<tr><th>Aberturas de porta</th><td>{k['aberturas_porta']}</td></tr>
<tr><th>Tempo médio de porta aberta</th><td>{k['porta_media_s']:.0f} s</td></tr>
<tr><th>Disponibilidade (online)</th><td>{k['disponibilidade_pct']:.1f} %</td></tr>
<tr><th>Temperatura mín / média / máx</th>
<td>{numero(k['temp_min'])} / {numero(k['temp_media'])} / {numero(k['temp_max'])} °C</td></tr>
</table>""")
        if linhas:
            partes.append(f'<img alt="gráfico de {escape(disp["id"])}" src="data:image/png;base64,{grafico_png(disp, linhas)}">')
        partes.append("<h3>Excursões de temperatura</h3>")
        if excursoes:
            partes.append("<table><tr><th>Início</th><th>Fim</th><th>Duração</th><th>Pico</th></tr>")
            for e in excursoes:
                partes.append(f"<tr><td>{hora(e['inicio'])}</td><td>{hora(e['fim'])}</td>"
                              f"<td>{(e['fim'] - e['inicio']) / 60:.1f} min</td><td>{e['pico']:.1f} °C</td></tr>")
            partes.append("</table>")
        else:
            partes.append("<p>Nenhuma excursão no período.</p>")

    if not dispositivos:
        partes.append("<p>Nenhum dispositivo cadastrado.</p>")
    partes.append("</body></html>")
    return "\n".join(partes)


if __name__ == "__main__":
    from app import caminho_banco
    from banco import conectar

    p = argparse.ArgumentParser(description="Gera o relatório de conformidade em HTML.")
    p.add_argument("--inicio", help="AAAA-MM-DD (padrão: últimas 24 h)")
    p.add_argument("--fim", help="AAAA-MM-DD (inclui o dia todo)")
    p.add_argument("--dispositivo", help="só este device_id")
    args = p.parse_args()

    inicio, fim = ler_periodo(args.inicio, args.fim)
    con = conectar(caminho_banco())
    html = gerar_html(con, inicio, fim, args.dispositivo)
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relatorios")
    os.makedirs(pasta, exist_ok=True)
    arquivo = os.path.join(pasta, f"conformidade_{datetime.now():%Y%m%d_%H%M%S}.html")
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write(html)
    print("Relatório salvo em", arquivo)

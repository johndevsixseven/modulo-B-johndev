# VaxGuard Connect — Servidor

Servidor Flask + SQLite que recebe a telemetria do ESP32/UNO R4 (e do simulador), detecta
riscos com IA simples e mostra tudo num painel web.

| Arquivo | O que faz |
|---|---|
| `app.py` | inicia o servidor (0.0.0.0:5000), log, usuários iniciais |
| `banco.py` | tabelas SQLite (dispositivos, leituras, eventos, comandos, usuarios, alertas) |
| `api.py` | rotas do dispositivo `/api/...` + validação |
| `ia.py` | z-score (anomalia), regressão (risco de excursão), KPIs |
| `painel.py` + `templates/` | painel web com login e perfis |
| `relatorio.py` | relatório de conformidade em HTML com gráficos |
| `simulador_dispositivo.py` | segunda câmara de mentira (VG-CAM02) |
| `criar_usuario.py` | cria usuário ou troca senha |

## 1. Instalar (uma vez)

```powershell
cd servidor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Rodar

```powershell
.venv\Scripts\activate
python app.py
```

Abra http://localhost:5000 no navegador.

### Usuários iniciais

Na **primeira** execução são criados `admin` (ADMINISTRADOR) e `operador` (OPERADOR).
- Se as variáveis `VAXGUARD_SENHA_ADMIN` / `VAXGUARD_SENHA_OPERADOR` existirem, elas viram as senhas.
- Se não, uma senha aleatória é **impressa no console uma única vez**. Anote!

Esqueceu? `python criar_usuario.py admin ADMINISTRADOR` (pede a nova senha).

Opcional: `set VAXGUARD_SECRET_KEY=algum-texto-longo` antes de rodar, para o login
continuar valendo depois de reiniciar o servidor (sem ela, uma chave nova é gerada a cada início).

## 3. Ligar o ESP32 / UNO R4

1. Descubra o IP do PC: `ipconfig` → "Endereço IPv4" do adaptador Wi-Fi (ex.: `192.168.0.10`).
2. Coloque esse IP em `SERVIDOR_HOST` no `firmware/vaxguard/secrets.h` (porta 5000). PC e placa na mesma rede.
3. Libere a porta 5000 no Firewall do Windows (PowerShell **como administrador**):
   ```powershell
   New-NetFirewallRule -DisplayName "VaxGuard 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
   ```

Dispositivo desconhecido que manda dados é **cadastrado automaticamente** (faixa 2–8 °C).
O ADMIN também pode cadastrar pelo painel.

## 3b. Rodando com o ESP32 via broker MQTT

Use quando o firewall do PC bloqueia conexões de entrada. O ESP32 publica no broker público
`broker.hivemq.com:1883` e a `ponte_mqtt.py`, rodando no PC, só faz conexões de **saída**:
repassa telemetria/eventos/acks ao Flask e publica os comandos pendentes para a placa.

```powershell
# terminal 1
.venv\Scripts\activate
python app.py

# terminal 2
.venv\Scripts\activate
python ponte_mqtt.py
```

Variáveis opcionais: `MQTT_HOST`, `MQTT_PORTA`, `MQTT_BASE` (padrão `vaxguard_senai_x7k2`, tem que
ser igual ao do firmware) e `SERVIDOR_URL` (padrão `http://127.0.0.1:5000`).

> **Aviso:** broker público é **inseguro** — qualquer pessoa que souber o tópico pode ler os dados
> e publicar leituras ou acks falsos. A ponte descarta o que não for JSON válido do dispositivo
> certo, mas isso **não** é autenticação. Só para demonstração.

## 4. Simulador (segundo ponto, VG-CAM02)

Com o servidor rodando, em outro terminal:

```powershell
python simulador_dispositivo.py                 # estável em ~5 °C
python simulador_dispositivo.py --aquecer 0.5   # esquenta 0,5 °C/min -> gera "RISCO DE EXCURSÃO"
python simulador_dispositivo.py --url http://192.168.0.10:5000 --ciclos 50
```

Ele também busca e confirma comandos (ventilação, limites, intervalo, reiniciar).

## 5. Relatório de conformidade

- Pelo painel: menu **Relatório** ou em *Alertas e eventos* → link do período filtrado.
- Pela linha de comando (salva em `relatorios/`):
  ```powershell
  python relatorio.py --inicio 2026-10-20 --fim 2026-10-21
  ```

## 6. Testes

```powershell
pip install pytest
python -m pytest tests
```

## Regras importantes

- Validação: campos obrigatórios e tipos; temperatura −40 a 80 °C, umidade 0 a 100 %.
  O que for rejeitado volta **400** e fica em `logs/servidor.log`.
- `ts = 0` (placa sem hora) → usa a hora de chegada. Guarda também `recebido_em`.
- OFFLINE = sem dados há mais de 3 intervalos do dispositivo.
- Comandos ficam PENDENTES até o ack; no máximo 3 por consulta (resposta < 1 KB).
- A API do dispositivo não tem senha (o firmware não envia token): use só em rede local.

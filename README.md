# VaxGuard Connect

Monitoramento IoT de câmaras frias de vacinas (2–8 °C) — SENAI Dev Experience, Módulo B.
**Equipe:** johndev

## Placa

**ESP32 DevKit.** O firmware também compila para **Arduino UNO R4 WiFi**: tudo que depende da placa
(pinos, Wi-Fi, watchdog, memória) fica em `firmware/vaxguard/board.h`.

## Sensores e atuadores do kit

| Componente | Função |
|---|---|
| DHT11 | temperatura e umidade da câmara |
| NTC KY-013 | temperatura redundante (confere o DHT11) |
| Reed switch | porta aberta/fechada |
| LDR | luz dentro da câmara → confirma porta aberta |
| Botão | silencia o alarme |
| Buzzer ativo | alarme crítico |
| Relé | liga a ventilação |
| LEDs verde / amarelo / vermelho | estado: normal / atenção / crítico |

## Pinos (ESP32)

| Componente | GPIO | Observação |
|---|---|---|
| DHT11 | 4 | 3V3 |
| Reed (porta) | 27 | INPUT_PULLUP |
| Botão (silenciar) | 13 | INPUT_PULLUP |
| Buzzer ativo | 25 | |
| Relé (ventilação) | 23 | alimentado em **VIN 5 V** |
| LED verde | 19 | resistor 220 Ω |
| LED amarelo | 21 | resistor 220 Ω |
| LED vermelho | 18 | resistor 220 Ω |
| LDR | 34 | ADC1, divisor em 3V3 |
| NTC KY-013 | 35 | ADC1, 3V3 |

Sensores em 3V3, GND comum a tudo. Montagem passo a passo: [docs/LIGACOES.md](docs/LIGACOES.md).

## Arquitetura

```
ESP32 ──MQTT──▶ broker.hivemq.com:1883 ──▶ servidor/ponte_mqtt.py ──HTTP──▶ Flask + SQLite + painel
               (tópicos vaxguard_senai_x7k2/...)                              http://localhost:5000
```

O ESP32 publica telemetria/eventos e recebe comandos pelo broker; a ponte repassa para a API do
servidor, que guarda no SQLite, roda a IA (anomalias, previsão de excursão, KPIs) e mostra o painel.

> ⚠️ O broker público não tem autenticação nem TLS — qualquer um pode ler e publicar.
> Serve **só para demonstração**; em produção use broker próprio com usuário/senha e TLS.

## Estrutura

```
firmware/vaxguard/   firmware Arduino (ESP32 / UNO R4 WiFi)
servidor/            Flask, SQLite, IA, painel, ponte MQTT, simulador, testes
pericia/             relatório da perícia de rede + prints do Wireshark
docs/                esquema de ligação
captura_biofrio_2026.pcap   captura analisada na perícia
```

## Compilar o firmware

1. Arduino IDE com o core da placa (esp32 da Espressif ou Arduino UNO R4).
2. Bibliotecas: **DHT sensor library** + **Adafruit Unified Sensor**, **ArduinoJson 7**, **PubSubClient**.
3. Copie `firmware/vaxguard/secrets.example.h` para `secrets.h` e preencha o Wi-Fi
   (o `secrets.h` fica fora do git).
4. Abra `firmware/vaxguard/vaxguard.ino`, escolha a placa e envie.

## Rodar servidor e ponte

Veja [servidor/README.md](servidor/README.md) (instalação, `python app.py`, `python ponte_mqtt.py`, usuários e testes).

## Perícia

Relatório em [pericia/relatorio_pericia.md](pericia/relatorio_pericia.md) (e PDF), prints em `pericia/prints/`.

// rede.h — Wi-Fi com reconexão, MQTT e envio da fila offline.
//
// ===================== CONTRATO MQTT =====================
// Broker MQTT_HOST:MQTT_PORTA (secrets.h), QoS 0, sem retain.
// Tópicos: MQTT_BASE/DEVICE_ID/<sufixo>, ex.: vaxguard_senai_x7k2/VG-CAM01/telemetria
// Atenção: broker público é inseguro (qualquer um lê/publica); serve só para a demonstração.
//
// ESP publica .../telemetria
//   {"device_id":"VG-CAM01","placa":"ESP32","seq":12,"ts":1761000000,
//    "temp":4.5,"umid":60,"porta":false,"estado":"NORMAL","luz_pct":3,
//    "temp_ntc":4.8,"ventilacao":false}
//   (temp/umid/temp_ntc podem ser null; ts = 0 se ainda sem hora NTP)
//
// ESP publica .../eventos
//   {"device_id":"VG-CAM01","placa":"ESP32","ts":1761000000,
//    "de":"NORMAL","para":"ATENCAO","motivo":"PORTA_ABERTA"}
//   motivos: TEMP_FORA_FAIXA, PORTA_ABERTA, PERTO_LIMITE, DIVERGENCIA_TEMP,
//            SENSOR_FALHA, BOTAO, OK
//
// ESP assina .../cmd — cada mensagem é UM comando:
//   {"id":1,"tipo":"SET_LIMITES","min":2.0,"max":8.0}
//   {"id":2,"tipo":"SET_INTERVALO","segundos":10}
//   {"id":3,"tipo":"VENTILACAO_ON"} / VENTILACAO_OFF / REINICIAR
//   id repetido (ack perdido) não executa de novo; só reenvia o ack.
//
// ESP publica .../ack   {"device_id":"VG-CAM01","id":1,"ok":true}
//   ok=false quando o comando foi rejeitado (valor inválido).
// =========================================================
#pragma once
#include <PubSubClient.h>
#include "secrets.h"
#include "estados.h"
#include "alarmes.h"

#define TOPICO(sufixo) MQTT_BASE "/" DEVICE_ID "/" sufixo

bool     wifiOk          = false;
uint32_t esperaWifi      = WIFI_ESPERA_MIN_MS; // dobra a cada tentativa até 30 s
uint32_t ultimaTentativa = 0;
uint32_t proximoSeq      = 1;

WiFiClient   wifiCliente;
PubSubClient mqtt(wifiCliente);
bool     mqttOk              = false;
uint32_t esperaMqtt          = MQTT_ESPERA_MIN_MS; // 1, 2, 4.. até 30 s
uint32_t ultimaTentativaMqtt = 0;

void comandos_aoReceber(char* topico, byte* payload, unsigned int tamanho); // em comandos.h

void rede_iniciar() {
  hal_prepararCliente(wifiCliente);
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setBufferSize(512);                // maior JSON (telemetria) tem ~250 bytes + tópico
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(MQTT_TIMEOUT_S);  // curto para não segurar os alarmes
  mqtt.setCallback(comandos_aoReceber);
}

// ---------- Wi-Fi ----------
void rede_atualizarWifi() {
  static uint32_t ultimaChecagem = 0;
  if (millis() - ultimaChecagem < 500) return; // no R4 cada status() conversa com o modem
  ultimaChecagem = millis();

  bool conectado = WiFi.status() == WL_CONNECTED;
  if (conectado && !wifiOk) {
    Serial.print("[REDE] Wi-Fi conectado, IP ");
    Serial.print(WiFi.localIP());
    Serial.print(", RSSI ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm"); // abaixo de -80 dBm o sinal é fraco
    esperaWifi = WIFI_ESPERA_MIN_MS;
  }
  if (!conectado && wifiOk) {
    Serial.println("[REDE] Wi-Fi caiu");
    ultimaTentativa = millis();
  }
  wifiOk = conectado;

  if (wifiOk) {
    hal_sincronizarHora();
  } else if (millis() - ultimaTentativa >= esperaWifi) {
    Serial.print("[REDE] conectando em ");
    Serial.print(WIFI_SSID);
    Serial.print(" (proxima espera ");
    Serial.print(min(esperaWifi * 2, WIFI_ESPERA_MAX_MS) / 1000);
    Serial.println(" s)");
    hal_wifiConectar(WIFI_SSID, WIFI_SENHA);
    ultimaTentativa = millis();
    esperaWifi = min(esperaWifi * 2, WIFI_ESPERA_MAX_MS);
  }
}

// ---------- MQTT ----------
// Texto do mqtt.state() do PubSubClient.
const char* textoEstadoMqtt(int s) {
  switch (s) {
    case -4: return "sem resposta do broker (timeout) - rede pode estar bloqueando MQTT";
    case -3: return "conexao perdida";
    case -2: return "falha TCP - porta bloqueada ou sem internet";
    case -1: return "desconectado";
    case 1:  return "broker recusou a versao do protocolo";
    case 2:  return "broker recusou o client id";
    case 3:  return "broker indisponivel";
    case 4:  return "usuario/senha recusados";
    case 5:  return "nao autorizado";
    default: return "desconhecido";
  }
}

// Conecta ao broker só com Wi-Fi, com espera progressiva (não bloqueia entre tentativas).
void rede_atualizarMqtt() {
  if (!wifiOk) { mqttOk = false; return; }
  if (mqtt.loop()) { mqttOk = true; return; } // loop() devolve false se desconectado
  if (mqttOk) {
    Serial.println("[REDE] broker caiu");
    mqttOk = false;
    ultimaTentativaMqtt = millis();
  }
  if (millis() - ultimaTentativaMqtt < esperaMqtt) return;

  uint8_t mac[6];
  WiFi.macAddress(mac);
  char clientId[40];
  snprintf(clientId, sizeof(clientId), "vaxguard-" DEVICE_ID "-%02X%02X%02X", mac[3], mac[4], mac[5]);

  // DNS separado do connect: cada etapa bloqueante começa com o WDT recém-alimentado.
  hal_alimentarWatchdog();
  IPAddress ip;
  bool dnsOk = WiFi.hostByName(MQTT_HOST, ip) == 1;
  bool ok = false;
  if (dnsOk) {
    mqtt.setServer(ip, MQTT_PORTA);
    hal_alimentarWatchdog();
    ok = mqtt.connect(clientId); // pior caso: TCP + MQTT_TIMEOUT_S (ver board.h)
  }
  hal_alimentarWatchdog();
  ultimaTentativaMqtt = millis();
  if (ok) {
    Serial.print("[REDE] broker conectado como ");
    Serial.println(clientId);
    mqtt.subscribe(TOPICO("cmd"));
    mqttOk = true;
    esperaMqtt = MQTT_ESPERA_MIN_MS;
  } else {
    esperaMqtt = min(esperaMqtt * 2, WIFI_ESPERA_MAX_MS); // antes do log: é esta a espera real
    Serial.print("[REDE] falha no broker, state=");
    Serial.print(dnsOk ? mqtt.state() : 0);
    Serial.print(" (");
    Serial.print(dnsOk ? textoEstadoMqtt(mqtt.state()) : "DNS nao resolveu o broker - sem internet?");
    Serial.print("), nova tentativa em ");
    Serial.print(esperaMqtt / 1000);
    Serial.println(" s");
  }
}

// true só se o broker estava conectado e o pacote foi escrito no socket.
bool rede_publicar(const char* topico, const char* json) {
  return mqtt.connected() && mqtt.publish(topico, json);
}

// Número em JSON: NAN vira null (JSON não tem NaN).
const char* numeroJson(float valor, char* texto) {
  if (isnan(valor)) strcpy(texto, "null");
  else snprintf(texto, 12, "%.1f", valor);
  return texto;
}

// ---------- Telemetria ----------
// Toda leitura entra na fila; o envio acontece depois (rede_enviarPendentes).
void rede_registrarLeitura() {
  Leitura l;
  l.seq        = proximoSeq++;
  l.ts         = hal_epochAgora();
  l.temp       = temperatura;
  l.umid       = umidade;
  l.tempNtc    = tempNtc;
  l.luzPct     = luzPct;
  l.porta      = portaAberta;
  l.ventilacao = ventilacaoLigada;
  l.estado     = estadoAtual;
  buffer_guardarLeitura(l);
}

bool enviarLeitura(const Leitura& l) {
  char json[320], t[12], u[12], ntc[12];
  snprintf(json, sizeof(json),
           "{\"device_id\":\"%s\",\"placa\":\"%s\",\"seq\":%lu,\"ts\":%lu,\"temp\":%s,\"umid\":%s,"
           "\"porta\":%s,\"estado\":\"%s\",\"luz_pct\":%.0f,\"temp_ntc\":%s,\"ventilacao\":%s}",
           DEVICE_ID, NOME_PLACA, (unsigned long)l.seq, (unsigned long)l.ts,
           numeroJson(l.temp, t), numeroJson(l.umid, u),
           l.porta ? "true" : "false", NOME_ESTADO[l.estado], l.luzPct,
           numeroJson(l.tempNtc, ntc), l.ventilacao ? "true" : "false");
  return rede_publicar(TOPICO("telemetria"), json);
}

bool enviarEvento(const Evento& e) {
  char json[200];
  snprintf(json, sizeof(json),
           "{\"device_id\":\"%s\",\"placa\":\"%s\",\"ts\":%lu,\"de\":\"%s\",\"para\":\"%s\",\"motivo\":\"%s\"}",
           DEVICE_ID, NOME_PLACA, (unsigned long)e.ts, NOME_ESTADO[e.de], NOME_ESTADO[e.para], e.motivo);
  return rede_publicar(TOPICO("eventos"), json);
}

// Envia no máximo 2 itens por volta do loop, mais antigo primeiro
// (eventos antes de leituras). Só remove da fila se o publish deu certo;
// se falhar, para e tenta de novo na próxima volta (mesma ordem).
void rede_enviarPendentes() {
  for (int i = 0; i < 2 && mqttOk; i++) {
    if (qtdEventos > 0) {
      if (!enviarEvento(buffer_eventoMaisAntigo())) return;
      buffer_removerEvento();
    } else if (qtdLeituras > 0) {
      const Leitura& l = buffer_leituraMaisAntiga();
      if (!enviarLeitura(l)) return;
      Serial.print("[REDE] leitura seq=");
      Serial.print(l.seq);
      Serial.println(" saiu da fila");
      buffer_removerLeitura();
    } else {
      return; // nada pendente
    }
  }
}

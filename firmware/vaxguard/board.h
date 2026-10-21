// board.h — HAL (camada de abstração da placa).
// TODO o código que muda de uma placa para outra fica SÓ aqui.
// O resto do firmware chama apenas funções hal_* e as constantes PINO_*.
#pragma once
#include <Arduino.h>
#include "config.h"
#include "tipos.h"

// =====================================================================
#if defined(ARDUINO_UNOR4_WIFI)
// =====================================================================
#include <WiFiS3.h>
#include <EEPROM.h>
#include <WDT.h>
#include <ArduinoGraphics.h>     // precisa vir ANTES da matriz para liberar o texto
#include <Arduino_LED_Matrix.h>

#define NOME_PLACA "UNO_R4_WIFI"

const int PINO_DHT      = 2;
const int PINO_PORTA    = 3;
const int PINO_BOTAO    = 4;
const int PINO_BUZZER   = 5;
const int PINO_RELE     = 7;
const int PINO_LED_VERDE    = 9;
const int PINO_LED_AMARELO  = 10;
const int PINO_LED_VERMELHO = 11;
const int PINO_LDR      = A0;
const int PINO_NTC      = A1;
const int ADC_BITS      = 14;

// O WDT do R4 aceita no máximo ~5,5 s. Usamos 5 s.
const uint32_t WATCHDOG_MS = 5000;
// WiFi.begin() do WiFiS3 fica num laço até conectar ou até este tempo.
// O modem continua tentando sozinho depois, então 2 s basta.
const uint32_t WIFI_TIMEOUT_R4_MS = 2000;
const uint32_t WIFI_ESPERA_MIN_MS = 1000; // 1ª espera entre tentativas de Wi-Fi

ArduinoLEDMatrix matriz;
uint32_t epochBase  = 0; // hora recebida do NTP
uint32_t millisBase = 0; // millis() no momento em que recebemos a hora

void hal_iniciarPlaca() {
  analogReadResolution(ADC_BITS);
  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_AMARELO, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  matriz.begin();
}

void hal_iniciarWatchdog() { WDT.begin(WATCHDOG_MS); }
void hal_alimentarWatchdog() { WDT.refresh(); }

void hal_leds(bool verde, bool amarelo, bool vermelho) {
  digitalWrite(PINO_LED_VERDE, verde);
  digitalWrite(PINO_LED_AMARELO, amarelo);
  digitalWrite(PINO_LED_VERMELHO, vermelho);
}

// Indicador nativo: letra do estado na matriz 12x8.
void hal_mostrarEstado(Estado e) {
  matriz.beginDraw();
  matriz.clear();
  matriz.stroke(0xFFFFFFFF);
  matriz.textFont(Font_5x7);
  matriz.beginText(3, 1, 0xFFFFFF);
  matriz.print(LETRA_ESTADO[e]);
  matriz.endText();
  matriz.endDraw();
}

// Memória não volátil: EEPROM (emulada na flash do R4).
void hal_salvarConfig(const Config& c) { EEPROM.put(0, c); }
void hal_carregarConfig(Config& c)     { EEPROM.get(0, c); }

// Bloqueia no máximo WIFI_TIMEOUT_R4_MS (+ resposta do modem).
// Alimentamos o watchdog logo antes para ter os 5 s inteiros.
void hal_wifiConectar(const char* ssid, const char* senha) {
  WiFi.setTimeout(WIFI_TIMEOUT_R4_MS);
  hal_alimentarWatchdog();
  WiFi.begin(ssid, senha);
  hal_alimentarWatchdog();
}

void hal_prepararCliente(WiFiClient& cliente) {
  cliente.setConnectionTimeout(MQTT_TIMEOUT_S * 1000UL); // sem isso o modem espera até 10 s (WDT é 5 s)
}

// R4: o modem pega a hora por NTP sozinho; WiFi.getTime() devolve 0 até conseguir.
void hal_sincronizarHora() {
  if (epochBase != 0 && millis() - millisBase < 86400000UL) return; // ressincroniza 1x/dia (millis estoura em 49 dias)
  uint32_t t = WiFi.getTime();
  if (t > 1600000000UL) { epochBase = t; millisBase = millis(); }
}

uint32_t hal_epochAgora() {
  if (epochBase == 0) return 0;
  return epochBase + (millis() - millisBase) / 1000;
}

void hal_reiniciar() { NVIC_SystemReset(); }

// 0–100 % da alimentação (ADC de 14 bits, referência = VCC).
float hal_lerAnalogPercentual(int pino) {
  return analogRead(pino) * 100.0 / ((1UL << ADC_BITS) - 1);
}

// =====================================================================
#elif defined(ESP32)
// =====================================================================
#include <WiFi.h>
#include <Preferences.h>
#include <esp_task_wdt.h>
#include <esp_arduino_version.h>
#include <time.h>

#define NOME_PLACA "ESP32"

const int PINO_DHT      = 4;
const int PINO_PORTA    = 27;
const int PINO_BOTAO    = 13;
const int PINO_BUZZER   = 25;
const int PINO_RELE     = 23;
const int PINO_LED_VERDE    = 19;
const int PINO_LED_AMARELO  = 21;
const int PINO_LED_VERMELHO = 18;
const int PINO_LDR      = 34;
const int PINO_NTC      = 35;
const int ADC_BITS      = 12;

const uint32_t WATCHDOG_MS = 8000;
// Uma tentativa de Wi-Fi no ESP32 (associação + DHCP) leva alguns segundos;
// tentar antes disso aborta a tentativa em andamento.
const uint32_t WIFI_ESPERA_MIN_MS = 10000;
Preferences prefs;
bool ntpPedido = false;

// LEDs via PWM (ledc). A API mudou do core 2.x para o 3.x.
const int LEDS[3] = { PINO_LED_VERDE, PINO_LED_AMARELO, PINO_LED_VERMELHO };

void hal_iniciarPlaca() {
  analogReadResolution(ADC_BITS);
  analogSetAttenuation(ADC_11db); // faixa ~0–3,1 V (sensores em 3,3 V)
  for (int i = 0; i < 3; i++) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcAttach(LEDS[i], 5000, 8);   // core 3.x: canal escolhido sozinho
#else
    ledcSetup(i, 5000, 8);          // core 2.x: canal i
    ledcAttachPin(LEDS[i], i);
#endif
  }
}

void hal_iniciarWatchdog() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t c = { .timeout_ms = WATCHDOG_MS, .idle_core_mask = 0, .trigger_panic = true };
  if (esp_task_wdt_reconfigure(&c) != ESP_OK) esp_task_wdt_init(&c); // o core 3.x normalmente já iniciou o WDT
#else
  esp_task_wdt_init(WATCHDOG_MS / 1000, true);
#endif
  esp_task_wdt_add(NULL); // vigia a tarefa do loop()
}

void hal_alimentarWatchdog() { esp_task_wdt_reset(); }

void hal_leds(bool verde, bool amarelo, bool vermelho) {
  bool liga[3] = { verde, amarelo, vermelho };
  for (int i = 0; i < 3; i++) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(LEDS[i], liga[i] ? 255 : 0); // 3.x: escreve pelo pino
#else
    ledcWrite(i, liga[i] ? 255 : 0);       // 2.x: escreve pelo canal
#endif
  }
}

// No ESP32 o indicador nativo SÃO os LEDs (hal_leds); não há matriz.
void hal_mostrarEstado(Estado e) { (void)e; }

void hal_salvarConfig(const Config& c) {
  prefs.begin("vaxguard", false);
  prefs.putBytes("cfg", &c, sizeof(c));
  prefs.end();
}

void hal_carregarConfig(Config& c) {
  prefs.begin("vaxguard", true);
  if (prefs.getBytes("cfg", &c, sizeof(c)) != sizeof(c)) c.magico = 0; // vazio
  prefs.end();
}

// No ESP32 WiFi.begin() não bloqueia.
void hal_wifiConectar(const char* ssid, const char* senha) {
  WiFi.disconnect();
  WiFi.begin(ssid, senha);
}

// ESP32: connect() já usa timeout padrão de 3 s (WDT é 8 s).
void hal_prepararCliente(WiFiClient& cliente) { (void)cliente; }

void hal_sincronizarHora() {
  if (ntpPedido) return;
  configTime(0, 0, "pool.ntp.org"); // UTC; roda em segundo plano
  ntpPedido = true;
}

uint32_t hal_epochAgora() {
  time_t t = time(nullptr);
  return t > 1600000000 ? (uint32_t)t : 0; // antes do NTP o relógio começa em 1970
}

void hal_reiniciar() { ESP.restart(); }

// 0–100 % de 3,3 V. analogReadMilliVolts usa a calibração de fábrica do ADC,
// bem mais exata que o valor cru de 12 bits (que não é linear no ESP32).
float hal_lerAnalogPercentual(int pino) {
  return min(analogReadMilliVolts(pino) * 100.0f / 3300.0f, 100.0f);
}

// =====================================================================
#else
#error "Placa nao suportada: use UNO R4 WiFi ou ESP32"
#endif
// =====================================================================

// ----- Partes iguais nas duas placas -----

void hal_iniciar() {
  pinMode(PINO_PORTA, INPUT_PULLUP);
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  pinMode(PINO_BUZZER, OUTPUT);
  pinMode(PINO_RELE, OUTPUT);
  digitalWrite(PINO_RELE, !RELE_LIGADO_NIVEL); // relé desligado já no boot (módulos ativos em LOW)
  hal_iniciarPlaca();
}

void hal_buzzer(bool ligado) { digitalWrite(PINO_BUZZER, ligado ? BUZZER_LIGADO_NIVEL : !BUZZER_LIGADO_NIVEL); }
void hal_rele(bool ligado)   { digitalWrite(PINO_RELE,   ligado ? RELE_LIGADO_NIVEL   : !RELE_LIGADO_NIVEL); }

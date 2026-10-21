// sensores.h — DHT11, porta (reed + LDR), NTC e botão.
#pragma once
#include <DHT.h>
#include <math.h>
#include "board.h"

DHT dht(PINO_DHT, DHT11);

// Últimos valores lidos (o resto do firmware só lê estas variáveis).
float   temperatura  = NAN; // DHT11 (°C), NAN até a 1ª leitura válida
float   umidade      = NAN;
float   tempNtc      = NAN;
float   luzPct       = 0;
bool    portaAberta  = false;
uint8_t falhasDht    = 0;   // leituras NaN seguidas

void sensores_iniciar() {
  dht.begin();
}

// Converte a leitura do KY-013 (%) em °C pela fórmula Beta:
//   1/T = 1/T0 + ln(R/R0)/B   (T em Kelvin)
// R0 = 10 kΩ a T0 = 25 °C e B = 3950 vêm do datasheet do NTC.
float ntcParaCelsius(float pct) {
  float f = pct / 100.0;                 // fração da tensão de alimentação
  if (f <= 0.01 || f >= 0.99) return NAN; // fio solto ou em curto
  float r = NTC_NO_TOPO ? NTC_R_FIXO * (1.0 / f - 1.0)  // NTC entre VCC e S
                        : NTC_R_FIXO * f / (1.0 - f);    // NTC entre S e GND
  float invT = 1.0 / NTC_T0_K + log(r / NTC_R0) / NTC_BETA;
  float c = 1.0 / invT - 273.15;
  return (c < -40 || c > 80) ? NAN : c; // implausível -> null (o JSON nunca leva valor absurdo)
}

// Porta: lida a cada volta do loop para os tempos de 20/60 s serem precisos.
void sensores_lerPorta() {
  luzPct = hal_lerAnalogPercentual(PINO_LDR);
  if (LDR_INVERTER) luzPct = 100.0 - luzPct;
  bool reedAberto = digitalRead(PINO_PORTA) != PORTA_FECHADA_NIVEL;
  bool luzAcesa   = luzPct > LIMIAR_LUZ_PCT; // luz dentro da câmara = porta aberta
  portaAberta = reedAberto || luzAcesa;
}

// DHT11 e NTC: lidos só a cada intervalo (o DHT11 é lento, ~1 leitura/s).
void sensores_lerTemperatura() {
  float t = dht.readTemperature();
  float u = dht.readHumidity();
  if (isnan(t) || isnan(u)) {
    if (falhasDht < 255) falhasDht++;
    Serial.print("[SENSOR] DHT11 falhou (");
    Serial.print(falhasDht);
    Serial.println(" seguidas)");
  } else {
    falhasDht   = 0;
    temperatura = t;
    umidade     = u;
  }
  tempNtc = ntcParaCelsius(hal_lerAnalogPercentual(PINO_NTC));

  Serial.print("[SENSOR] T=");   Serial.print(temperatura, 1);
  Serial.print(" U=");           Serial.print(umidade, 0);
  Serial.print(" NTC=");         Serial.print(tempNtc, 1);
  Serial.print(" luz=");         Serial.print(luzPct, 0);
  Serial.print("% porta=");      Serial.println(portaAberta ? "ABERTA" : "fechada");
}

// Devolve true UMA vez por aperto (borda), com debounce de 50 ms.
bool sensores_botaoApertado() {
  static bool     estavel   = false; // estado aceito
  static bool     anterior  = false; // última leitura crua
  static uint32_t mudouEm   = 0;
  bool agora = digitalRead(PINO_BOTAO) == BOTAO_APERTADO_NIVEL;
  if (agora != anterior) { anterior = agora; mudouEm = millis(); }
  if (millis() - mudouEm > 50 && agora != estavel) {
    estavel = agora;
    return estavel; // só avisa na hora que APERTA
  }
  return false;
}

// config.h — valores padrão e configuração que fica salva na memória.
#pragma once
#include <Arduino.h>

// ---------- Identificação ----------
#define DEVICE_ID "VG-CAM01"

// ---------- Valores padrão (usados se a memória estiver vazia) ----------
const float    TEMP_MIN_PADRAO     = 2.0;   // °C — faixa segura de vacinas
const float    TEMP_MAX_PADRAO     = 8.0;   // °C
const uint32_t INTERVALO_PADRAO_S  = 5;     // segundos entre leituras

// ---------- Tempos da máquina de estados ----------
const uint32_t PORTA_ATENCAO_MS    = 20000; // porta aberta > 20 s -> ATENCAO
const uint32_t PORTA_CRITICO_MS    = 60000; // porta aberta > 60 s -> CRITICO
const uint32_t FORA_FAIXA_CRIT_MS  = 30000; // fora da faixa > 30 s -> CRITICO
const float    MARGEM_LIMITE_C     = 1.0;   // a menos de 1 °C do limite -> ATENCAO
const float    DIVERGENCIA_MAX_C   = 3.0;   // |NTC - DHT| > 3 °C -> ATENCAO
const uint8_t  FALHAS_MAX_DHT      = 3;     // 3 leituras NaN seguidas -> FALHA_SENSOR

// ---------- Sensores extras ----------
const float LIMIAR_LUZ_PCT = 40.0;  // luz acima disso = luz acesa = porta aberta (calibre no local)
// Teste: cubra o LDR; luz_pct no Serial deve CAIR. Se subir, use true.
const bool  LDR_INVERTER   = false; // true se o módulo dá MENOS tensão com MAIS luz

// NTC do KY-013: 10 kΩ a 25 °C, Beta 3950, resistor fixo de 10 kΩ.
const float NTC_R_FIXO   = 10000.0; // resistor fixo do divisor (Ω)
const float NTC_R0       = 10000.0; // resistência do NTC a 25 °C (Ω)
const float NTC_T0_K     = 298.15;  // 25 °C em Kelvin
const float NTC_BETA     = 3950.0;  // constante Beta (datasheet do NTC)
const bool  NTC_NO_TOPO  = true;    // true = NTC ligado no VCC (S cai com o calor); inverta se ler ao contrário

// ---------- Níveis lógicos da fiação (troque aqui se o módulo for invertido) ----------
const int PORTA_FECHADA_NIVEL = LOW;  // reed com ímã encostado fecha o contato -> LOW (INPUT_PULLUP)
const int BOTAO_APERTADO_NIVEL = LOW; // botão com INPUT_PULLUP vai para LOW quando apertado
// Relé: a maioria dos módulos do kit (com optoacoplador) liga com LOW.
// Se o relé ficar ligado com o sistema em NORMAL, troque para HIGH.
const int RELE_LIGADO_NIVEL    = LOW;
const int BUZZER_LIGADO_NIVEL  = HIGH;

// ---------- Rede ----------
const uint32_t WIFI_ESPERA_MAX_MS = 30000; // reconexão (Wi-Fi e broker) dobra até 30 s (início do Wi-Fi em board.h)
const uint32_t MQTT_ESPERA_MIN_MS = 1000;  // reconexão ao broker: 1, 2, 4.. até 30 s
const uint16_t MQTT_TIMEOUT_S     = 2;     // curto para não segurar os alarmes

// ---------- Configuração salva na memória não volátil ----------
const uint16_t CONFIG_MAGICO = 0x5647; // "VG" — se não bater, a memória está vazia
const uint8_t  CONFIG_VERSAO = 1;                       // mude se a struct mudar

struct Config {
  uint16_t magico;
  uint8_t  versao;
  float    tempMin;
  float    tempMax;
  uint32_t intervaloS;
};

Config cfg; // configuração em uso (global, pois quase todo módulo lê)

// Validações dos comandos remotos (também usadas no boot).
bool config_limitesValidos(float minimo, float maximo) {
  return minimo >= -40 && maximo <= 80 && minimo < maximo;
}

bool config_intervaloValido(long segundos) {
  return segundos >= 1 && segundos <= 3600;
}

void config_padrao() {
  cfg.magico     = CONFIG_MAGICO;
  cfg.versao     = CONFIG_VERSAO;
  cfg.tempMin    = TEMP_MIN_PADRAO;
  cfg.tempMax    = TEMP_MAX_PADRAO;
  cfg.intervaloS = INTERVALO_PADRAO_S;
}

// tipos.h — tipos compartilhados entre os módulos.
#pragma once
#include <Arduino.h>

enum Estado : uint8_t { NORMAL, ATENCAO, CRITICO, RECONHECIDO, FALHA_SENSOR };

const char* const NOME_ESTADO[]  = { "NORMAL", "ATENCAO", "CRITICO", "RECONHECIDO", "FALHA_SENSOR" };
const char        LETRA_ESTADO[] = { 'N', 'A', 'C', 'R', 'F' }; // mostrada na matriz de LED

// Uma leitura completa. Guardamos struct (e não String) no buffer offline
// para não fragmentar a memória.
struct Leitura {
  uint32_t seq;        // contador crescente
  uint32_t ts;         // epoch UTC em segundos (0 = sem hora)
  float    temp;       // DHT11 (°C)
  float    umid;       // DHT11 (%)
  float    tempNtc;    // NTC (°C)
  float    luzPct;     // LDR (0-100 %)
  bool     porta;      // true = aberta
  bool     ventilacao; // relé ligado?
  Estado   estado;
};

// Uma mudança de estado.
struct Evento {
  uint32_t ts;
  Estado   de;
  Estado   para;
  char     motivo[24];
};

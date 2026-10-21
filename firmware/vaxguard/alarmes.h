// alarmes.h — LEDs, buzzer e relé conforme o estado.
// Chamado a cada volta do loop. Pisca e bipa usando millis() (sem delay),
// calculando "em que ponto do ciclo estamos" em vez de guardar timers.
#pragma once
#include "board.h"

const uint32_t PISCA_MS        = 500;   // meio período do pisca
const uint32_t BIPE_PERIODO_MS = 10000; // ATENCAO: um bipe a cada 10 s
const uint32_t BIPE_DURACAO_MS = 150;   // duração do bipe

bool ventilacaoManual = false; // comando remoto VENTILACAO_ON/OFF
bool ventilacaoLigada = false; // estado real do relé (vai na telemetria)

void alarmes_atualizar(Estado estado, uint32_t estadoDesde) {
  uint32_t agora   = millis();
  bool     pisca   = (agora / PISCA_MS) % 2;                                  // alterna a cada 500 ms
  bool     bipe    = (agora - estadoDesde) % BIPE_PERIODO_MS < BIPE_DURACAO_MS; // bipa ao entrar e a cada 10 s
  bool     emAlarme = estado == CRITICO || estado == RECONHECIDO;

  switch (estado) {
    case NORMAL:       hal_leds(true, false, false);  hal_buzzer(false); break;
    case ATENCAO:      hal_leds(false, true, false);  hal_buzzer(bipe);  break;
    case CRITICO:      hal_leds(false, false, true);  hal_buzzer(true);  break;
    case RECONHECIDO:  hal_leds(false, false, pisca); hal_buzzer(false); break; // silenciado
    case FALHA_SENSOR: hal_leds(false, pisca, !pisca); hal_buzzer(false); break;
  }

  // CRITICO/RECONHECIDO sempre ventilam; fora disso vale o comando manual.
  ventilacaoLigada = emAlarme || ventilacaoManual;
  hal_rele(ventilacaoLigada);
}

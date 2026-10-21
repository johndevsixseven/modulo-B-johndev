// estados.h — máquina de estados da câmara fria.
// Funciona só com os sensores: não depende da rede.
#pragma once
#include "sensores.h"
#include "buffer_offline.h"

Estado   estadoAtual  = NORMAL;
uint32_t estadoDesde  = 0;     // millis() da última troca (usado pelos bipes)
bool     reconhecido  = false; // operador apertou o botão durante o CRITICO
uint32_t foraDesde    = 0;     // millis() em que a temp saiu da faixa (0 = está na faixa)
uint32_t portaDesde   = 0;     // millis() em que a porta abriu (0 = fechada)

// Registra o início de uma condição (ou zera quando ela some).
// 0 significa "não está acontecendo", por isso nunca guardamos 0 como início.
void marcarInicio(uint32_t& desde, bool acontecendo) {
  if (!acontecendo) { desde = 0; return; }
  if (desde == 0) desde = millis() ? millis() : 1;
}

// Decide o estado a partir dos sensores. "motivo" recebe o porquê.
Estado calcularEstado(const char*& motivo) {
  marcarInicio(portaDesde, portaAberta); // conta o tempo da porta mesmo com o DHT em falha

  if (falhasDht >= FALHAS_MAX_DHT) { motivo = "SENSOR_FALHA"; return FALHA_SENSOR; }

  // Comparações com NAN dão false: antes da 1ª leitura nada dispara.
  bool foraFaixa  = temperatura < cfg.tempMin || temperatura > cfg.tempMax;
  bool perto      = temperatura < cfg.tempMin + MARGEM_LIMITE_C || temperatura > cfg.tempMax - MARGEM_LIMITE_C;
  bool divergente = fabs(tempNtc - temperatura) > DIVERGENCIA_MAX_C; // NAN -> false
  marcarInicio(foraDesde, foraFaixa);
  uint32_t agora = millis(); // lido DEPOIS de marcarInicio: senão agora - desde = -1 -> CRITICO na hora
  uint32_t tempoFora  = foraDesde  ? agora - foraDesde  : 0;
  uint32_t tempoPorta = portaDesde ? agora - portaDesde : 0;

  // CRITICO (o botão transforma em RECONHECIDO, mas a condição é a mesma)
  if (tempoFora > FORA_FAIXA_CRIT_MS) { motivo = "TEMP_FORA_FAIXA"; return reconhecido ? RECONHECIDO : CRITICO; }
  if (tempoPorta > PORTA_CRITICO_MS)  { motivo = "PORTA_ABERTA";    return reconhecido ? RECONHECIDO : CRITICO; }
  reconhecido = false; // condição crítica sumiu: o próximo CRITICO volta a tocar

  // ATENCAO
  if (foraFaixa)                     { motivo = "TEMP_FORA_FAIXA";  return ATENCAO; }
  if (tempoPorta > PORTA_ATENCAO_MS) { motivo = "PORTA_ABERTA";     return ATENCAO; }
  if (perto)                         { motivo = "PERTO_LIMITE";     return ATENCAO; }
  if (divergente)                    { motivo = "DIVERGENCIA_TEMP"; return ATENCAO; }

  motivo = "OK";
  return NORMAL;
}

// Chamado a cada volta do loop.
void estados_atualizar() {
  if (sensores_botaoApertado() && estadoAtual == CRITICO) {
    reconhecido = true;
    Serial.println("[ESTADO] botao: alarme reconhecido");
  }

  const char* motivo = "";
  Estado novo = calcularEstado(motivo);
  if (novo == RECONHECIDO && estadoAtual == CRITICO) motivo = "BOTAO";
  if (novo == estadoAtual) return;

  Serial.print("[ESTADO] ");
  Serial.print(NOME_ESTADO[estadoAtual]);
  Serial.print(" -> ");
  Serial.print(NOME_ESTADO[novo]);
  Serial.print(" (");
  Serial.print(motivo);
  Serial.println(")");

  // Todo evento vai para a fila; a rede envia quando puder.
  Evento e;
  e.ts   = hal_epochAgora();
  e.de   = estadoAtual;
  e.para = novo;
  strncpy(e.motivo, motivo, sizeof(e.motivo) - 1);
  e.motivo[sizeof(e.motivo) - 1] = '\0';
  buffer_guardarEvento(e);

  estadoAtual = novo;
  estadoDesde = millis();
  hal_mostrarEstado(novo);
}

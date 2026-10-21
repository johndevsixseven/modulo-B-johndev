// buffer_offline.h — filas circulares de leituras e eventos ainda não enviados.
// Tudo entra aqui primeiro; só sai depois que o publish MQTT deu certo.
// Assim, se o broker estiver fora, nada se perde. Se encher, descarta o MAIS ANTIGO.
#pragma once
#include "tipos.h"

const uint8_t MAX_LEITURAS = 60; // 60 x 5 s = 5 min sem rede
const uint8_t MAX_EVENTOS  = 16;

Leitura filaLeituras[MAX_LEITURAS];
uint8_t inicioLeituras = 0, qtdLeituras = 0; // inicio = posição da mais antiga

Evento  filaEventos[MAX_EVENTOS];
uint8_t inicioEventos = 0, qtdEventos = 0;

void buffer_guardarLeitura(const Leitura& l) {
  if (qtdLeituras == MAX_LEITURAS) { // cheio: perde a mais antiga
    inicioLeituras = (inicioLeituras + 1) % MAX_LEITURAS;
    qtdLeituras--;
    Serial.println("[BUFFER] cheio, leitura mais antiga descartada");
  }
  filaLeituras[(inicioLeituras + qtdLeituras) % MAX_LEITURAS] = l;
  qtdLeituras++;
}

Leitura& buffer_leituraMaisAntiga() { return filaLeituras[inicioLeituras]; }

void buffer_removerLeitura() {
  inicioLeituras = (inicioLeituras + 1) % MAX_LEITURAS;
  qtdLeituras--;
}

void buffer_guardarEvento(const Evento& e) {
  if (qtdEventos == MAX_EVENTOS) {
    inicioEventos = (inicioEventos + 1) % MAX_EVENTOS;
    qtdEventos--;
    Serial.println("[BUFFER] cheio, evento mais antigo descartado");
  }
  filaEventos[(inicioEventos + qtdEventos) % MAX_EVENTOS] = e;
  qtdEventos++;
}

Evento& buffer_eventoMaisAntigo() { return filaEventos[inicioEventos]; }

void buffer_removerEvento() {
  inicioEventos = (inicioEventos + 1) % MAX_EVENTOS;
  qtdEventos--;
}

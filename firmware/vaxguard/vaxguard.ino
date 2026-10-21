// VaxGuard Connect — monitor de câmara fria de vacinas.
// Placas: Arduino UNO R4 WiFi (principal) e ESP32 DevKit.
// Regra do projeto: nada de delay() no loop; tudo com millis().
//
// Módulos (cada .h tem uma responsabilidade):
//   config.h         valores padrão e configuração salva
//   tipos.h          estados, leitura e evento
//   board.h          tudo que depende da placa (hal_*)
//   sensores.h       DHT11, porta (reed + LDR), NTC, botão
//   estados.h        máquina de estados
//   alarmes.h        LEDs, buzzer, relé
//   buffer_offline.h fila do que ainda não foi enviado
//   rede.h           Wi-Fi, MQTT e contrato dos tópicos
//   comandos.h       comandos remotos
#include "config.h"
#include "tipos.h"
#include "board.h"
#include "sensores.h"
#include "buffer_offline.h"
#include "estados.h"
#include "alarmes.h"
#include "rede.h"
#include "comandos.h"

uint32_t ultimaLeitura = 0;
bool     primeiraVolta = true; // lê os sensores logo na 1ª volta

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("[ESTADO] VaxGuard Connect - " NOME_PLACA " - " DEVICE_ID);

  hal_iniciar();
  sensores_iniciar();
  configuracao_carregar();
  rede_iniciar();
  hal_mostrarEstado(estadoAtual);
  hal_iniciarWatchdog(); // por último: daqui em diante o loop precisa alimentá-lo
}

void loop() {
  hal_alimentarWatchdog();

  // 1) Sensores: porta sempre; temperatura só a cada intervalo.
  sensores_lerPorta();
  bool horaDeLer = primeiraVolta || millis() - ultimaLeitura >= cfg.intervaloS * 1000UL;
  if (horaDeLer) {
    primeiraVolta = false;
    ultimaLeitura = millis();
    sensores_lerTemperatura();
  }

  // 2) Lógica local (funciona sem rede).
  estados_atualizar();
  alarmes_atualizar(estadoAtual, estadoDesde);

  // 3) Rede.
  rede_atualizarWifi();
  rede_atualizarMqtt(); // mqtt.loop(): mantém a conexão e entrega os comandos
  if (horaDeLer) rede_registrarLeitura();
  rede_enviarPendentes();
  comandos_atualizar();
}

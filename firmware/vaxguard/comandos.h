// comandos.h — configuração salva + comandos remotos vindos pelo MQTT (tópico .../cmd).
#pragma once
#include <ArduinoJson.h>
#include "rede.h"

// Lê a configuração da memória. Se estiver vazia, de outra versão
// ou com valores absurdos, usa os padrões do config.h.
void configuracao_carregar() {
  hal_carregarConfig(cfg);
  bool valida = cfg.magico == CONFIG_MAGICO && cfg.versao == CONFIG_VERSAO &&
                config_limitesValidos(cfg.tempMin, cfg.tempMax) && config_intervaloValido(cfg.intervaloS);
  if (!valida) {
    Serial.println("[CMD] memoria vazia ou invalida: usando valores padrao");
    config_padrao();
  }
  Serial.print("[CMD] limites ");
  Serial.print(cfg.tempMin, 1);
  Serial.print(" a ");
  Serial.print(cfg.tempMax, 1);
  Serial.print(" C, intervalo ");
  Serial.print(cfg.intervaloS);
  Serial.println(" s");
}

// Executa um comando. Devolve false se foi rejeitado.
bool executarComando(JsonObject c) {
  const char* tipo = c["tipo"] | "";
  Serial.print("[CMD] recebido ");
  Serial.println(tipo);

  if (strcmp(tipo, "SET_LIMITES") == 0) {
    float minimo = c["min"] | NAN;
    float maximo = c["max"] | NAN;
    if (!config_limitesValidos(minimo, maximo)) { // NAN também cai aqui
      Serial.println("[CMD] SET_LIMITES invalido (precisa -40 <= min < max <= 80)");
      return false;
    }
    cfg.tempMin = minimo;
    cfg.tempMax = maximo;
    hal_salvarConfig(cfg);
    return true;
  }
  if (strcmp(tipo, "SET_INTERVALO") == 0) {
    long segundos = c["segundos"] | -1L;
    if (!config_intervaloValido(segundos)) {
      Serial.println("[CMD] SET_INTERVALO invalido (precisa 1..3600 s)");
      return false;
    }
    cfg.intervaloS = segundos;
    hal_salvarConfig(cfg);
    return true;
  }
  if (strcmp(tipo, "VENTILACAO_ON") == 0)  { ventilacaoManual = true;  return true; }
  if (strcmp(tipo, "VENTILACAO_OFF") == 0) { ventilacaoManual = false; return true; } // CRITICO continua ligando
  if (strcmp(tipo, "REINICIAR") == 0)      return true; // reinicia depois do ack (ver abaixo)

  Serial.println("[CMD] tipo desconhecido");
  return false;
}

long ultimoId = 0;       // último comando executado (a ponte reenvia o mesmo id se o ack se perder)
bool ultimoOk = false;
bool reiniciarPendente = false;

bool confirmarComando(long id, bool ok) {
  char json[80];
  snprintf(json, sizeof(json), "{\"device_id\":\"%s\",\"id\":%ld,\"ok\":%s}", DEVICE_ID, id, ok ? "true" : "false");
  return rede_publicar(TOPICO("ack"), json);
}

// Callback do MQTT: chamado de dentro do mqtt.loop() com UM comando.
void comandos_aoReceber(char* topico, byte* payload, unsigned int tamanho) {
  (void)topico; // só assinamos .../cmd
  JsonDocument doc;
  DeserializationError erro = deserializeJson(doc, payload, tamanho); // copia: o buffer do MQTT é reusado no ack
  if (erro) {
    Serial.print("[CMD] JSON invalido: ");
    Serial.println(erro.c_str());
    return;
  }
  JsonObject c = doc.as<JsonObject>();
  long id = c["id"] | 0L;
  if (id != 0 && id == ultimoId) {
    Serial.println("[CMD] id repetido: so reenvia o ack");
    confirmarComando(id, ultimoOk);
    return;
  }

  bool ok = executarComando(c);
  if (id == 0) return; // sem id não há ack
  ultimoId = id;
  ultimoOk = ok;
  bool confirmado = confirmarComando(id, ok);
  // Reinicia na próxima volta, para o ack sair antes. Sem ack não reinicia (senão a ponte reenvia e reinicia em laço).
  if (ok && confirmado && strcmp(c["tipo"] | "", "REINICIAR") == 0) reiniciarPendente = true;
}

// Chamado a cada volta do loop.
void comandos_atualizar() {
  if (!reiniciarPendente) return;
  mqtt.loop();
  wifiCliente.flush();
  mqtt.disconnect(); // fecha a conexão de forma limpa (o ack já foi escrito)
  Serial.println("[CMD] reiniciando...");
  Serial.flush();
  hal_reiniciar();
}

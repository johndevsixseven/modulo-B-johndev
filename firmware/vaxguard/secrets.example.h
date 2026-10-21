// secrets.example.h — MODELO. Copie para secrets.h e preencha.
// O secrets.h fica fora do git (.gitignore) para a senha não vazar.
#pragma once

#define WIFI_SSID      "TROCAR_AQUI"
#define WIFI_SENHA     "TROCAR_AQUI"

// Broker MQTT público: inseguro (qualquer um lê/publica), serve só para a demonstração.
#define MQTT_HOST      "broker.hivemq.com"
#define MQTT_PORTA     1883
#define MQTT_BASE      "vaxguard_senai_x7k2" // base dos tópicos; igual à da ponte Python

# Esquema de ligação — ESP32 DevKit

## Regras

1. **Sensores em 3V3.** O ESP32 trabalha em 3,3 V; 5 V num GPIO queima o pino.
2. **VIN (5 V) só para o relé.** A bobina do relé precisa de 5 V; o sinal (IN) vem do GPIO 23.
3. **GND comum:** todos os GND (sensores, relé, LEDs, buzzer) no mesmo GND do ESP32.
4. **Analógicos só em ADC1 (GPIO 34 e 35).** O ADC2 não funciona com o Wi-Fi ligado.
   34 e 35 são só entrada, sem pull-up interno — perfeitos para LDR e NTC.
5. **Evite GPIO 0, 2, 12 e 15** (pinos de boot): ligar coisas neles pode impedir o ESP32 de iniciar ou gravar.
6. **LEDs com resistor de 220 Ω:** perna longa (+) no pino via resistor, perna curta no GND.

## Tabela de pinos

| Componente | Pino do componente | Liga em |
|---|---|---|
| DHT11 | VCC / DATA / GND | 3V3 / GPIO 4 / GND |
| Reed switch (porta) | um lado / outro | GPIO 27 / GND (pull-up interno) |
| Botão (silenciar) | um lado / outro | GPIO 13 / GND (pull-up interno) |
| Buzzer ativo | + / − | GPIO 25 / GND |
| Relé (ventilação) | VCC / IN / GND | **VIN 5 V** / GPIO 23 / GND |
| LED verde | perna longa → 220 Ω / curta | GPIO 19 / GND |
| LED amarelo | perna longa → 220 Ω / curta | GPIO 21 / GND |
| LED vermelho | perna longa → 220 Ω / curta | GPIO 18 / GND |
| LDR (módulo) | VCC / AO / GND | 3V3 / GPIO 34 / GND |
| NTC KY-013 | VCC / S / GND | 3V3 / GPIO 35 / GND |

## Passo a passo

1. Com o USB **desligado**, encaixe o ESP32 na protoboard e puxe 3V3 e GND para os trilhos.
2. Ligue o DHT11 (3V3, GPIO 4, GND).
3. Ligue reed switch (GPIO 27) e botão (GPIO 13), cada um com o outro lado no GND.
4. Ligue LDR (GPIO 34) e NTC (GPIO 35) em 3V3/GND.
5. Ligue os três LEDs com resistor de 220 Ω (19, 21, 18) e o buzzer (25).
6. Por último o relé: VCC no **VIN**, IN no GPIO 23, GND no GND.

## Checklist antes de ligar o USB

- [ ] Nenhum fio de 5 V (VIN) chega a sensor ou GPIO — só ao VCC do relé.
- [ ] 3V3 e GND não estão em curto (confira os trilhos).
- [ ] Todo LED tem resistor e está com a perna longa para o pino.
- [ ] LDR e NTC estão em 34/35 (ADC1), nada em 0, 2, 12 ou 15.
- [ ] Todos os GND estão interligados.
- [ ] `secrets.h` criado a partir do `secrets.example.h`.

// ============================================================================
// techtennis_G.ino  -  variante do techtennis.ino com posicionamento ABSOLUTO dos servos
//
// Novos comandos (o resto e identico ao techtennis.ino):
//   G<x>,<y>\n   move servo1 para x e servo2 para y (0-180). SILENCIOSO: nao responde,
//                para o backend poder mandar comandos com frequencia sem lotar a serial.
//                Ex.: "G90,120\n"
//   P            responde "[POS] <servo1>,<servo2>". O backend usa isto para descobrir
//                se o firmware aceita G (o sketch original ignora o P).
//
// Linha malformada em G (ex.: "G\n" ou "Gabc") e IGNORADA: nao move para 0,0.
// Para gravar: feche o Serial Monitor da IDE e qualquer programa que esteja usando a
// porta serial, abra este arquivo na Arduino IDE e clique em Upload.
// ============================================================================
#include <Servo.h>

// Servos
Servo servo1;
Servo servo2;

// Pinos
const int LED1 = 9;
const int LED2 = 8;
const int BUZZER = 10;
const int SERVO1_PIN = 2;
const int SERVO2_PIN = 3;
const int LASER_PIN = 11;

// Variáveis
int angle1 = 90;
int angle2 = 90;
bool laser_on = false;

void setup() {
  // Inicializa pinos
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  pinMode(LASER_PIN, OUTPUT);
  
  // Inicializa servos
  servo1.attach(SERVO1_PIN);
  servo2.attach(SERVO2_PIN);
  
  // Posição inicial (centro)
  servo1.write(90);
  servo2.write(90);
  
  // Laser desligado inicialmente
  digitalWrite(LASER_PIN, LOW);
  
  Serial.begin(9600);
  Serial.setTimeout(30);   // G: le a linha em ate 30 ms (nao trava o loop)
  
  // Menu
  Serial.println("========== SISTEMA PRONTO ==========");
  Serial.println("SERVOS:");
  Serial.println("  A/D = Servo1 esquerda/direita");
  Serial.println("  W/S = Servo2 cima/baixo");
  Serial.println();
  Serial.println("LASER:");
  Serial.println("  L = Laser liga/desliga");
  Serial.println();
  Serial.println("OUTROS:");
  Serial.println("  E = Alterna LED 1 e LED 2");
  Serial.println("  B = Buzzer faz BIP");
  Serial.println("  R = Reset servos (90°)");
  Serial.println("  G<x>,<y> = Servos em posicao absoluta");
  Serial.println("  P = Mostra posicao dos servos");
  Serial.println("  ? = Mostra este menu");
  Serial.println("====================================");
  Serial.println();
}

void loop() {
  if (Serial.available()) {
    char cmd = Serial.read();
    
    // Remove quebras de linha
    if (cmd == '\n' || cmd == '\r') return;
    
    // ========== SERVO 1 ==========
    if (cmd == 'A' || cmd == 'a') {
      angle1 = constrain(angle1 + 5, 0, 180);
      servo1.write(angle1);
      Serial.print("[SERVO1] Ângulo: ");
      Serial.print(angle1);
      Serial.println("°");
    }
    
    if (cmd == 'D' || cmd == 'd') {
      angle1 = constrain(angle1 - 5, 0, 180);
      servo1.write(angle1);
      Serial.print("[SERVO1] Ângulo: ");
      Serial.print(angle1);
      Serial.println("°");
    }
    
    // ========== SERVO 2 ==========
    if (cmd == 'W' || cmd == 'w') {
      angle2 = constrain(angle2 + 5, 0, 180);
      servo2.write(angle2);
      Serial.print("[SERVO2] Ângulo: ");
      Serial.print(angle2);
      Serial.println("°");
    }
    
    if (cmd == 'S' || cmd == 's') {
      angle2 = constrain(angle2 - 5, 0, 180);
      servo2.write(angle2);
      Serial.print("[SERVO2] Ângulo: ");
      Serial.print(angle2);
      Serial.println("°");
    }
    
    // ========== LASER (Pino 11) ==========
    if (cmd == 'L' || cmd == 'l') {
      laser_on = !laser_on;
      digitalWrite(LASER_PIN, laser_on ? HIGH : LOW);
      Serial.print("[LASER] ");
      Serial.println(laser_on ? "LIGADO ✓" : "DESLIGADO ✗");
    }
    
    // ========== LEDs ==========
    if (cmd == 'E' || cmd == 'e') {
      digitalWrite(LED1, !digitalRead(LED1));
      digitalWrite(LED2, !digitalRead(LED2));
      Serial.println("[LEDs] Alternados");
    }
    
    // ========== BUZZER ==========
    if (cmd == 'B' || cmd == 'b') {
      tone(BUZZER, 1000);  // Frequência 1000Hz
      delay(200);
      noTone(BUZZER);
      Serial.println("[BUZZER] BIP!");
    }
    
    // ========== RESET ==========
    if (cmd == 'R' || cmd == 'r') {
      angle1 = 90;
      angle2 = 90;
      servo1.write(90);
      servo2.write(90);
      Serial.println("[RESET] Servos em 90°");
    }
    
    // ========== POSICAO ABSOLUTA (novo) ==========
    if (cmd == 'G' || cmd == 'g') {
      String linha = Serial.readStringUntil('\n');
      int x, y;
      if (sscanf(linha.c_str(), "%d,%d", &x, &y) == 2) {
        angle1 = constrain(x, 0, 180);
        angle2 = constrain(y, 0, 180);
        servo1.write(angle1);
        servo2.write(angle2);
      }
    }

    if (cmd == 'P' || cmd == 'p') {
      Serial.print("[POS] ");
      Serial.print(angle1);
      Serial.print(",");
      Serial.println(angle2);
    }

    // ========== MENU ==========
    if (cmd == '?') {
      Serial.println();
      Serial.println("COMANDOS:");
      Serial.println("  A/D = Servo1   |  W/S = Servo2");
      Serial.println("  L = Laser      |  E = LEDs");
      Serial.println("  B = Buzzer     |  R = Reset");
      Serial.println("  ? = Menu");
      Serial.println();
    }
  }
}
// SLARC – ESP32-Firmware (Waveshare General Driver for Robots)
// Stand: V0.1 (02.11.2026) – Inbetriebnahme-Werkzeug über USB-Seriell (115200 Bd).
// Noch keine Regelung und kein Pi-Protokoll. Befehle: `help`.
#include <Arduino.h>
#include <Wire.h>
#include "config.h"
#include "st3215.h"

static sts::Bus bus;
static bool armed = false;  // Freigabe für Bewegungsbefehle (goto)

// ------------------------------------------------------------ Hilfsfunktionen
static void relaysOff() {
  digitalWrite(PIN_RELAY_LEG, HIGH);
  digitalWrite(PIN_RELAY_PI, HIGH);  // Open-Drain: HIGH = losgelassen
}

static bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

static bool i2cWrite8(uint8_t addr, uint8_t reg, uint8_t v) {
  Wire.beginTransmission(addr);
  Wire.write(reg); Wire.write(v);
  return Wire.endTransmission() == 0;
}

static bool i2cRead(uint8_t addr, uint8_t reg, uint8_t* buf, uint8_t n) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(addr, n) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}

static const char* jointLabel(uint8_t id) {
  static char s[24];
  int leg, joint;
  if (idToJoint(id, leg, joint)) snprintf(s, sizeof(s), "%s-%s", LEG_NAMES[leg], JOINT_NAMES[joint]);
  else snprintf(s, sizeof(s), "(kein Gelenk)");
  return s;
}

static void printBusError() {
  Serial.printf("  Fehler: %s\n", sts::resultName(bus.lastResult()));
}

// Sucht IDs 0…253 bei der aktuellen Baudrate. Gibt die Anzahl zurück, found[] optional.
static int scanIds(uint8_t* found, int maxFound, bool verbose) {
  int n = 0;
  bus.setTimeoutUs(1500);
  for (int id = 0; id <= 253; id++) {
    if (bus.ping(id)) {
      if (found && n < maxFound) found[n] = id;
      n++;
      if (verbose) Serial.printf("  ID %3d  %s\n", id, jointLabel(id));
    }
  }
  bus.setTimeoutUs(SERVO_TIMEOUT_US);
  return n;
}

// ------------------------------------------------------------ Befehle
static void cmdHelp() {
  Serial.println(
    "SLARC ESP32 V0.1 – Inbetriebnahme\n"
    "  i2c                    I2C-Bus scannen\n"
    "  scan [baud|all]        Servo-Bus scannen (Standard: aktuelle Baudrate)\n"
    "  bus <baud>             Baudrate des ESP32 am Servo-Bus setzen\n"
    "  ping <id>              einzelnen Servo anpingen\n"
    "  info <id>              Register eines Servos auslesen\n"
    "  setid <alt> <neu>      ID vergeben (nur EIN Servo am Bus!)\n"
    "  torque <id> <0|1>      Drehmoment aus/an\n"
    "  watch <id> [id…]       Positionen laufend anzeigen (Taste = Ende)\n"
    "  calib <id>             Gelenk in q=0 halten -> Offset fuer config.h\n"
    "  arm <0|1>              Bewegungsfreigabe fuer goto\n"
    "  goto <id> <grad> [v]   Gelenk auf Winkel fahren (v in Ticks/s, Std. 300)\n"
    "  feet                   Fusskontakte (MCP23017 Port A)\n"
    "  vbat                   Spannung ueber INA219\n"
    "  btn                    Ein/Aus-Taster IO35\n"
    "  relay <pi|legs> <on|off>  Relais K1 bzw. K2…K7\n"
    "  off                    alle Relais aus, arm 0");
}

static void cmdI2c() {
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    if (!i2cPresent(a)) continue;
    const char* name = "";
    if (a == MCP23017_ADDR) name = "MCP23017 (Hub)";
    else if (a == QMI8658_ADDR || a == 0x6A) name = "QMI8658C?";
    else if (a == AK09918_ADDR) name = "AK09918C?";
    else if (a >= INA219_ADDR_MIN && a <= INA219_ADDR_MAX) name = "INA219?";
    Serial.printf("  0x%02X  %s\n", a, name);
    n++;
  }
  Serial.printf("%d Geraet(e). SDA=%d SCL=%d\n", n, PIN_I2C_SDA, PIN_I2C_SCL);
}

static void cmdScan(const char* arg) {
  if (arg && strcmp(arg, "all") == 0) {
    uint32_t old = bus.baud();
    for (int c = 0; c < 8; c++) {
      bus.setBaud(sts::codeToBaud(c));
      Serial.printf("Baud %lu:\n", (unsigned long)bus.baud());
      int n = scanIds(nullptr, 0, true);
      if (n) Serial.printf("  -> %d Servo(s)\n", n);
    }
    bus.setBaud(old);
    return;
  }
  if (arg) bus.setBaud(strtoul(arg, nullptr, 10));
  Serial.printf("Scan bei %lu Bd …\n", (unsigned long)bus.baud());
  int n = scanIds(nullptr, 0, true);
  Serial.printf("%d Servo(s). Echos erkannt: %lu\n", n, (unsigned long)bus.echoCount());
}

static void cmdInfo(uint8_t id) {
  uint8_t r[71];
  // in zwei Blöcken lesen (EEPROM-Bereich, RAM-Bereich)
  if (!bus.read(id, 0, r, 40)) { printBusError(); return; }
  if (!bus.read(id, 40, r + 40, 31)) { printBusError(); return; }
  auto u16 = [&](int a) { return (uint16_t)(r[a] | (r[a + 1] << 8)); };
  Serial.printf("ID %d %s\n", id, jointLabel(id));
  Serial.printf("  Modell %u, Baud-Code %u (%lu Bd), Modus %u\n", u16(sts::MODEL), r[sts::BAUD],
                (unsigned long)sts::codeToBaud(r[sts::BAUD]), r[sts::MODE]);
  Serial.printf("  Winkelgrenzen %u…%u, Ofs %d\n", u16(sts::MIN_ANGLE), u16(sts::MAX_ANGLE),
                sts::stsSigned(u16(sts::OFS), 11));
  Serial.printf("  Drehmoment %s, Limit %.1f %%, Lock %u\n", r[sts::TORQUE_EN] ? "an" : "aus",
                u16(sts::TORQUE_LIMIT) / 10.0f, r[sts::LOCK]);
  int pos = sts::stsSigned(u16(sts::PRESENT_POS), 15);
  Serial.printf("  Position %d (%.1f Grad roh)", pos, (pos - SERVO_CENTER) * 360.0f / SERVO_TICKS_PER_REV);
  int leg, joint;
  if (idToJoint(id, leg, joint)) Serial.printf(", q = %.1f Grad", ticksToDeg(leg, joint, pos));
  Serial.println();
  Serial.printf("  Last %.1f %%, Spannung %.1f V, Temp %u C, Strom %d, bewegt %u, Status 0x%02X\n",
                sts::stsSigned(u16(sts::PRESENT_LOAD), 10) / 10.0f, r[sts::VOLTAGE] / 10.0f,
                r[sts::TEMPERATURE], sts::stsSigned(u16(sts::CURRENT), 15), r[sts::MOVING],
                bus.lastStatus());
}

static void cmdSetId(uint8_t oldId, uint8_t newId) {
  if (newId == 0 || newId > 253) { Serial.println("Neue ID muss 1…253 sein."); return; }
  uint8_t found[4];
  int n = scanIds(found, 4, false);
  if (n != 1) {
    Serial.printf("Abbruch: %d Servos am Bus. Fuer setid genau einen anschliessen.\n", n);
    return;
  }
  if (found[0] != oldId) { Serial.printf("Abbruch: gefundener Servo hat ID %d.\n", found[0]); return; }
  if (!bus.write8(oldId, sts::LOCK, 0)) { Serial.println("EEPROM entsperren fehlgeschlagen"); printBusError(); return; }
  uint8_t v = newId;
  bus.write(oldId, sts::ID, &v, 1, false);  // Antwort kommt evtl. schon mit neuer ID
  delay(20);
  if (!bus.write8(newId, sts::LOCK, 1)) { Serial.println("Sperren mit neuer ID fehlgeschlagen"); printBusError(); return; }
  delay(20);
  if (bus.ping(newId)) Serial.printf("OK: ID %d -> %d %s\n", oldId, newId, jointLabel(newId));
  else Serial.println("Neue ID antwortet nicht – mit `scan` pruefen.");
}

static void cmdWatch(uint8_t* ids, int n) {
  Serial.println("Taste druecken zum Beenden.");
  while (Serial.available()) Serial.read();
  while (!Serial.available()) {
    for (int i = 0; i < n; i++) {
      uint8_t b[6];
      if (!bus.read(ids[i], sts::PRESENT_POS, b, 6)) { Serial.printf("[%d: %s] ", ids[i], sts::resultName(bus.lastResult())); continue; }
      int pos = sts::stsSigned(b[0] | (b[1] << 8), 15);
      float load = sts::stsSigned(b[4] | (b[5] << 8), 10) / 10.0f;
      int leg, joint;
      if (idToJoint(ids[i], leg, joint))
        Serial.printf("[%d: %4d  q %6.1f  L %5.1f%%] ", ids[i], pos, ticksToDeg(leg, joint, pos), load);
      else
        Serial.printf("[%d: %4d  L %5.1f%%] ", ids[i], pos, load);
    }
    Serial.println();
    delay(100);
  }
  while (Serial.available()) Serial.read();
}

static void cmdCalib(uint8_t id) {
  int leg, joint;
  if (!idToJoint(id, leg, joint)) { Serial.println("ID gehoert zu keinem Gelenk."); return; }
  uint16_t raw;
  // Mittelwert aus 10 Messungen
  long sum = 0; int n = 0;
  for (int i = 0; i < 10; i++) { if (bus.read16(id, sts::PRESENT_POS, raw)) { sum += sts::stsSigned(raw, 15); n++; } delay(10); }
  if (!n) { printBusError(); return; }
  int pos = (int)lround((double)sum / n);
  Serial.printf("%s: Position bei q=0 = %d -> JOINT_OFFSET[%s][%s] = %d\n", jointLabel(id), pos,
                LEG_NAMES[leg], JOINT_NAMES[joint], pos - SERVO_CENTER);
  Serial.println("Drehrichtung pruefen: mit `watch` Gelenk von Hand nach unten bewegen (Femur/Tibia) bzw. gegen den Uhrzeigersinn von oben (Coxa) -> q muss steigen.");
}

static void cmdGoto(uint8_t id, float q, int speed) {
  if (!armed) { Serial.println("Nicht freigegeben – erst `arm 1`."); return; }
  int leg, joint;
  if (!idToJoint(id, leg, joint)) { Serial.println("ID gehoert zu keinem Gelenk."); return; }
  float lim = Q_LIMIT_DEG[joint];
  if (q < -lim || q > lim) { Serial.printf("Ausserhalb der Grenze +-%.0f Grad.\n", lim); return; }
  int ticks = degToTicks(leg, joint, q);
  if (ticks < 0 || ticks > SERVO_TICKS_PER_REV - 1) { Serial.println("Ziel ausserhalb 0…4095 – Offset pruefen."); return; }
  if (speed <= 0 || speed > 3000) speed = 300;
  if (bus.writePos(id, ticks, speed, 20)) Serial.printf("%s -> q %.1f Grad (%d Ticks, %d Ticks/s)\n", jointLabel(id), q, ticks, speed);
  else printBusError();
}

static void cmdFeet() {
  // Port A als Eingang, externe 10-kΩ-Pull-ups auf dem Hub
  if (!i2cWrite8(MCP23017_ADDR, 0x00, 0xFF) || !i2cWrite8(MCP23017_ADDR, 0x0C, 0x00)) {
    Serial.println("MCP23017 antwortet nicht."); return;
  }
  uint8_t a;
  if (!i2cRead(MCP23017_ADDR, 0x12, &a, 1)) { Serial.println("Lesen fehlgeschlagen."); return; }
  Serial.printf("GPIOA 0x%02X  ", a);
  for (int l = 0; l < NUM_LEGS; l++)
    Serial.printf("%s:%s ", LEG_NAMES[l], (a & (1 << FOOT_BIT[l])) ? "-" : "KONTAKT");
  Serial.printf(" INTA(IO34)=%d\n", digitalRead(PIN_MCP_INTA));
}

static void cmdVbat() {
  for (uint8_t a = INA219_ADDR_MIN; a <= INA219_ADDR_MAX; a++) {
    if (!i2cPresent(a)) continue;
    uint8_t b[2];
    if (!i2cRead(a, 0x02, b, 2)) continue;
    uint16_t raw = (b[0] << 8) | b[1];
    int mv = (raw >> 3) * 4;
    Serial.printf("INA219 0x%02X: %d mV%s\n", a, mv,
                  mv < VBAT_STOP_MV ? "  (unter Abschaltgrenze!)" : mv < VBAT_WARN_MV ? "  (Warnung)" : "");
    return;
  }
  Serial.println("Kein INA219 gefunden.");
}

static void cmdRelay(const char* which, const char* state) {
  if (!which || !state) { Serial.println("relay <pi|legs> <on|off>"); return; }
  bool on = strcmp(state, "on") == 0;
  if (strcmp(which, "pi") == 0) {
    digitalWrite(PIN_RELAY_PI, on ? LOW : HIGH);
    Serial.printf("K1 (Pi) %s\n", on ? "an" : "aus (faellt nur, wenn der Pi GPIO26 nicht haelt)");
  } else if (strcmp(which, "legs") == 0) {
    // Bein-Relais nur ohne Drehmoment schalten. Nach dem Einschalten starten die
    // Servos ohne Drehmoment; vor dem Ausschalten Drehmoment per Broadcast aus.
    if (!on) { bus.write8(sts::BROADCAST, sts::TORQUE_EN, 0); armed = false; }
    digitalWrite(PIN_RELAY_LEG, on ? LOW : HIGH);
    Serial.printf("K2…K7 (Beine) %s\n", on ? "an" : "aus, Drehmoment aus, arm 0");
  } else {
    Serial.println("relay <pi|legs> <on|off>");
  }
}

// ------------------------------------------------------------ Kommandozeile
static void handleLine(char* line) {
  char* argv[8];
  int argc = 0;
  for (char* t = strtok(line, " \t"); t && argc < 8; t = strtok(nullptr, " \t")) argv[argc++] = t;
  if (!argc) return;
  const char* c = argv[0];
  auto num = [&](int i) { return (i < argc) ? atoi(argv[i]) : -1; };

  if (!strcmp(c, "help") || !strcmp(c, "?")) cmdHelp();
  else if (!strcmp(c, "i2c")) cmdI2c();
  else if (!strcmp(c, "scan")) cmdScan(argc > 1 ? argv[1] : nullptr);
  else if (!strcmp(c, "bus") && argc > 1) { bus.setBaud(strtoul(argv[1], nullptr, 10)); Serial.printf("Bus %lu Bd\n", (unsigned long)bus.baud()); }
  else if (!strcmp(c, "ping") && argc > 1) Serial.println(bus.ping(num(1)) ? "OK" : sts::resultName(bus.lastResult()));
  else if (!strcmp(c, "info") && argc > 1) cmdInfo(num(1));
  else if (!strcmp(c, "setid") && argc > 2) cmdSetId(num(1), num(2));
  else if (!strcmp(c, "torque") && argc > 2) { if (bus.write8(num(1), sts::TORQUE_EN, num(2) ? 1 : 0)) Serial.println("OK"); else printBusError(); }
  else if (!strcmp(c, "watch") && argc > 1) { uint8_t ids[7]; int n = 0; for (int i = 1; i < argc && n < 7; i++) ids[n++] = atoi(argv[i]); cmdWatch(ids, n); }
  else if (!strcmp(c, "calib") && argc > 1) cmdCalib(num(1));
  else if (!strcmp(c, "arm") && argc > 1) { armed = num(1) == 1; Serial.printf("arm %d\n", armed); }
  else if (!strcmp(c, "goto") && argc > 2) cmdGoto(num(1), atof(argv[2]), num(3));
  else if (!strcmp(c, "feet")) cmdFeet();
  else if (!strcmp(c, "vbat")) cmdVbat();
  else if (!strcmp(c, "btn")) Serial.printf("IO35 = %d (%s)\n", digitalRead(PIN_BUTTON), digitalRead(PIN_BUTTON) ? "offen" : "gedrueckt");
  else if (!strcmp(c, "relay")) cmdRelay(argc > 1 ? argv[1] : nullptr, argc > 2 ? argv[2] : nullptr);
  else if (!strcmp(c, "off")) { armed = false; bus.write8(sts::BROADCAST, sts::TORQUE_EN, 0); relaysOff(); Serial.println("Relais aus, arm 0"); }
  else Serial.println("Unbekannt oder Argumente fehlen – `help`.");
}

void setup() {
  // Zuerst sicherer Zustand: alle Relais offen
  digitalWrite(PIN_RELAY_LEG, HIGH);
  pinMode(PIN_RELAY_LEG, OUTPUT);
  digitalWrite(PIN_RELAY_PI, HIGH);
  pinMode(PIN_RELAY_PI, OUTPUT_OPEN_DRAIN);
  relaysOff();
  pinMode(PIN_BUTTON, INPUT);    // externer Pull-up, IO35 hat keinen internen
  pinMode(PIN_MCP_INTA, INPUT);  // IO34 ebenso

  Serial.begin(115200);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ);
  bus.begin(Serial1, PIN_SERVO_RX, PIN_SERVO_TX, SERVO_BAUD);
  bus.setTimeoutUs(SERVO_TIMEOUT_US);

  delay(300);
  Serial.println("\nSLARC ESP32 V0.1 – Inbetriebnahme. `help` fuer Befehle.");
}

void loop() {
  static char line[96];
  static uint8_t len = 0;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      line[len] = 0;
      Serial.printf("> %s\n", line);
      handleLine(line);
      len = 0;
    } else if (len < sizeof(line) - 1) {
      line[len++] = ch;
    }
  }
}

// SLARC – Hardware-Konfiguration ESP32 (Waveshare General Driver for Robots)
// Stand: V0.1 (02.11.2026)
// Quelle: Documentation/Hardware_Interfaces.md, Documentation/Wiring/README.md.
// Werte mit (Annahme) sind bei der Inbetriebnahme zu messen und dann hier
// UND in Hardware_Interfaces.md nachzutragen.
#pragma once
#include <stdint.h>
#include <math.h>

// ---------------------------------------------------------------- Pins
// Servo-Bus: UART1, halbduplex über SN74LVC1G125/126 auf dem Treiber, DATA an H5/H6
constexpr int PIN_SERVO_RX = 18;
constexpr int PIN_SERVO_TX = 19;

// I²C: QMI8658C, AK09918C, INA219 (auf dem Treiber), MCP23017 (Hub)
constexpr int PIN_I2C_SDA = 32;   // (Annahme) laut Waveshare-Belegung, per I²C-Scan bestätigen
constexpr int PIN_I2C_SCL = 33;
constexpr uint32_t I2C_FREQ = 400000;

constexpr int PIN_MCP_INTA  = 34; // nur Eingang, kein interner Pull-up; INTA push-pull aktiv low
constexpr int PIN_RELAY_PI  = 16; // K1, low = an, IMMER Open-Drain (Pi hält IN1 parallel über BC547)
constexpr int PIN_RELAY_LEG = 27; // K2…K7 gemeinsam, low = an
constexpr int PIN_LED_WS2812 = 4; // optional
constexpr int PIN_BUTTON    = 35; // Ein/Aus-Taster, low = gedrückt, 10 kΩ Pull-up auf dem Hub
// IO5: frei, Strapping-Pin – nicht verwenden ohne Prüfung

// ---------------------------------------------------------------- Servo-Bus
constexpr uint32_t SERVO_BAUD = 1000000;   // (Annahme) Werkseinstellung ST3215
constexpr uint32_t SERVO_TIMEOUT_US = 3000; // Antwort-Timeout je Paket

// ST3215: 4096 Ticks = 360°, 2048 = Mitte
constexpr int   SERVO_TICKS_PER_REV = 4096;
constexpr int   SERVO_CENTER = 2048;
constexpr float SERVO_STALL_NM = 2.94f;
constexpr float SERVO_VMAX_RAD_S = 4.7f;   // 45 U/min

// ---------------------------------------------------------------- Beine
// Reihenfolge wie im Protokoll: FR MR HR FL ML HL (Index 0–5).
// Im CAD/in der Verkabelung heißen HR/HL dort RR/RL.
constexpr int NUM_LEGS = 6;
constexpr int NUM_JOINTS = 3;   // 0 Coxa, 1 Femur, 2 Tibia
enum Leg : uint8_t { FR = 0, MR, HR, FL, ML, HL };
static const char* const LEG_NAMES[NUM_LEGS] = {"FR", "MR", "HR", "FL", "ML", "HL"};
static const char* const JOINT_NAMES[NUM_JOINTS] = {"coxa", "femur", "tibia"};

// Servo-ID = 10*(Bein+1) + (Gelenk+1), z. B. FR-Coxa 11, HL-Tibia 63 (fest)
constexpr uint8_t servoId(int leg, int joint) { return 10 * (leg + 1) + (joint + 1); }
// Rückwärts: false, wenn die ID keinem Gelenk gehört
inline bool idToJoint(uint8_t id, int& leg, int& joint) {
  leg = id / 10 - 1; joint = id % 10 - 1;
  return leg >= 0 && leg < NUM_LEGS && joint >= 0 && joint < NUM_JOINTS;
}

// Drehrichtung je Gelenk (offen, Kalibrierung): erwartet −1 für Femur/Tibia
// der linken (gespiegelten) Beine. Coxa ergibt sich aus der Montage.
static const int8_t JOINT_DIR[NUM_LEGS][NUM_JOINTS] = {
  // coxa femur tibia
  { +1, +1, +1 },  // FR
  { +1, +1, +1 },  // MR
  { +1, +1, +1 },  // HR
  { +1, -1, -1 },  // FL
  { +1, -1, -1 },  // ML
  { +1, -1, -1 },  // HL
};

// Nullpunkt-Offset in Ticks (Ist-Position bei q = 0 minus 2048), aus `calib`
static const int16_t JOINT_OFFSET[NUM_LEGS][NUM_JOINTS] = {
  { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 },
  { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 },
};

// Software-Gelenkgrenzen in Grad (mechanischer Anschlag: Coxa ±95, Femur/Tibia ±117)
constexpr float Q_LIMIT_DEG[NUM_JOINTS] = { 90.0f, 112.0f, 112.0f };

// Umrechnung Gelenkwinkel <-> Servo-Ticks
inline float ticksToDeg(int leg, int joint, int ticks) {
  return JOINT_DIR[leg][joint] * (ticks - SERVO_CENTER - JOINT_OFFSET[leg][joint])
         * 360.0f / SERVO_TICKS_PER_REV;
}
inline int degToTicks(int leg, int joint, float q) {
  return SERVO_CENTER + JOINT_OFFSET[leg][joint]
         + (int)lroundf(JOINT_DIR[leg][joint] * q * SERVO_TICKS_PER_REV / 360.0f);
}

// ---------------------------------------------------------------- Fußkontakte
// MCP23017 Port A, 10 kΩ Pull-up nach 3,3 V, Schalter nach GND: 0 = Kontakt
constexpr uint8_t MCP23017_ADDR = 0x20;
// Bit von Port A je Bein (Index FR MR HR FL ML HL)
static const uint8_t FOOT_BIT[NUM_LEGS] = { 4, 2, 0, 5, 3, 1 };  // PA4 FR, PA2 MR, PA0 HR, PA5 FL, PA3 ML, PA1 HL

// ---------------------------------------------------------------- I²C-Adressen (Annahme, Scan)
constexpr uint8_t QMI8658_ADDR  = 0x6B;
constexpr uint8_t AK09918_ADDR  = 0x0C;
constexpr uint8_t INA219_ADDR_MIN = 0x40;  // Waveshare oft 0x42
constexpr uint8_t INA219_ADDR_MAX = 0x45;

// ---------------------------------------------------------------- Akku (3S)
constexpr int VBAT_WARN_MV = 10500;  // 3,5 V/Zelle unter Last
constexpr int VBAT_STOP_MV = 9900;   // 3,3 V/Zelle

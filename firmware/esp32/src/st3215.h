// SLARC – Treiber für den Feetech-STS-Bus (ST3215)
// Stand: V0.1 (02.11.2026)
// Paket: FF FF ID LEN INSTR PARAM… CHK, LEN = Anzahl PARAM + 2,
// CHK = ~(ID + LEN + INSTR + PARAM…) & 0xFF. Antwort: FF FF ID LEN ERR PARAM… CHK.
// Mehrbyte-Register little endian.
#pragma once
#include <Arduino.h>

namespace sts {

// Register (STS/SMS-Reihe, Speicher-Tabelle der ST3215)
enum Reg : uint8_t {
  MODEL        = 3,   // 2 Byte
  ID           = 5,
  BAUD         = 6,   // 0=1M 1=500k 2=250k 3=128k 4=115200 5=76800 6=57600 7=38400
  MIN_ANGLE    = 9,   // 2 Byte
  MAX_ANGLE    = 11,  // 2 Byte
  OFS          = 31,  // 2 Byte, Positionskorrektur (EEPROM)
  MODE         = 33,  // 0 = Position
  TORQUE_EN    = 40,
  ACC          = 41,
  GOAL_POS     = 42,  // 2 Byte
  GOAL_TIME    = 44,
  GOAL_SPEED   = 46,
  TORQUE_LIMIT = 48,  // 2 Byte, 0…1000 = 0…100 %
  LOCK         = 55,  // 0 = EEPROM offen, 1 = gesperrt
  PRESENT_POS  = 56,  // 2 Byte
  PRESENT_SPEED= 58,
  PRESENT_LOAD = 60,  // 2 Byte, Bit 10 Vorzeichen, 0…1000 = 0,1 %
  VOLTAGE      = 62,  // 0,1 V
  TEMPERATURE  = 63,  // °C
  MOVING       = 66,
  CURRENT      = 69,  // 2 Byte
};

enum Instr : uint8_t { PING = 0x01, READ = 0x02, WRITE = 0x03, REG_WRITE = 0x04,
                       ACTION = 0x05, SYNC_READ = 0x82, SYNC_WRITE = 0x83 };

constexpr uint8_t BROADCAST = 0xFE;

// Ergebnis des letzten Transfers
enum class Result : uint8_t { OK, TIMEOUT, BAD_CHECKSUM, BAD_ID, BAD_LENGTH };
const char* resultName(Result r);

// Baudrate zu Registercode (−1 = keine gültige STS-Baudrate)
int baudToCode(uint32_t baud);
uint32_t codeToBaud(int code);

class Bus {
 public:
  void begin(HardwareSerial& port, int rxPin, int txPin, uint32_t baud);
  void setBaud(uint32_t baud);
  uint32_t baud() const { return baud_; }

  bool ping(uint8_t id);
  bool read(uint8_t id, uint8_t addr, uint8_t* data, uint8_t len);
  // expectReply = false: nicht auf Statuspaket warten (Broadcast, ID-Wechsel)
  bool write(uint8_t id, uint8_t addr, const uint8_t* data, uint8_t len, bool expectReply = true);

  bool read8(uint8_t id, uint8_t addr, uint8_t& v);
  bool read16(uint8_t id, uint8_t addr, uint16_t& v);
  bool write8(uint8_t id, uint8_t addr, uint8_t v);
  bool write16(uint8_t id, uint8_t addr, uint16_t v);

  // Zielposition mit Beschleunigung (0…254) und Geschwindigkeit (Ticks/s, 0 = max)
  bool writePos(uint8_t id, uint16_t pos, uint16_t speed, uint8_t acc);

  Result lastResult() const { return lastResult_; }
  uint8_t lastStatus() const { return lastStatus_; }   // Fehlerbits aus dem Statuspaket
  uint32_t echoCount() const { return echoCount_; }    // erkannte Eigen-Echos

  void setTimeoutUs(uint32_t us) { timeoutUs_ = us; }

 private:
  void send(uint8_t id, uint8_t instr, const uint8_t* params, uint8_t n);
  bool receive(uint8_t id, uint8_t* params, uint8_t n);

  HardwareSerial* port_ = nullptr;
  int rx_ = -1, tx_ = -1;
  uint32_t baud_ = 0;
  uint32_t timeoutUs_ = 3000;
  uint8_t txBuf_[64];
  uint8_t txLen_ = 0;
  Result lastResult_ = Result::OK;
  uint8_t lastStatus_ = 0;
  uint32_t echoCount_ = 0;
};

// Vorzeichenbehaftete STS-Werte (Vorzeichen in einem hohen Bit, kein Zweierkomplement)
inline int stsSigned(uint16_t v, int signBit) {
  return (v & (1u << signBit)) ? -(int)(v & ((1u << signBit) - 1)) : (int)v;
}

}  // namespace sts

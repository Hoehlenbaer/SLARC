// SLARC – Treiber für den Feetech-STS-Bus (ST3215), Stand V0.1 (02.11.2026)
#include "st3215.h"

namespace sts {

const char* resultName(Result r) {
  switch (r) {
    case Result::OK: return "OK";
    case Result::TIMEOUT: return "TIMEOUT";
    case Result::BAD_CHECKSUM: return "CHECKSUM";
    case Result::BAD_ID: return "FALSCHE_ID";
    case Result::BAD_LENGTH: return "LAENGE";
  }
  return "?";
}

static const uint32_t BAUDS[8] = {1000000, 500000, 250000, 128000, 115200, 76800, 57600, 38400};

int baudToCode(uint32_t baud) {
  for (int i = 0; i < 8; i++) if (BAUDS[i] == baud) return i;
  return -1;
}
uint32_t codeToBaud(int code) { return (code >= 0 && code < 8) ? BAUDS[code] : 0; }

void Bus::begin(HardwareSerial& port, int rxPin, int txPin, uint32_t baud) {
  port_ = &port; rx_ = rxPin; tx_ = txPin; baud_ = baud;
  port_->begin(baud_, SERIAL_8N1, rx_, tx_);
}

void Bus::setBaud(uint32_t baud) {
  if (baud == baud_) return;
  port_->flush();
  port_->end();
  baud_ = baud;
  port_->begin(baud_, SERIAL_8N1, rx_, tx_);
}

void Bus::send(uint8_t id, uint8_t instr, const uint8_t* params, uint8_t n) {
  while (port_->available()) port_->read();  // Reste verwerfen
  uint8_t len = n + 2;
  uint8_t sum = id + len + instr;
  txLen_ = 0;
  txBuf_[txLen_++] = 0xFF; txBuf_[txLen_++] = 0xFF;
  txBuf_[txLen_++] = id; txBuf_[txLen_++] = len; txBuf_[txLen_++] = instr;
  for (uint8_t i = 0; i < n; i++) { txBuf_[txLen_++] = params[i]; sum += params[i]; }
  txBuf_[txLen_++] = ~sum;
  port_->write(txBuf_, txLen_);
  port_->flush();  // wartet, bis das letzte Bit draußen ist
}

// Liest ein Statuspaket. Ein Echo des eigenen Pakets (je nach Bustreiber-Beschaltung
// möglich) wird erkannt und übersprungen.
bool Bus::receive(uint8_t id, uint8_t* params, uint8_t n) {
  uint8_t frame[64];
  uint8_t pos = 0, need = 4;
  uint32_t t0 = micros();
  while (micros() - t0 < timeoutUs_) {
    if (!port_->available()) continue;
    uint8_t b = port_->read();
    // Kopf FF FF synchronisieren
    if (pos < 2) { if (b == 0xFF) frame[pos++] = b; else pos = 0; continue; }
    if (pos == 2 && b == 0xFF) continue;  // zusätzliches FF
    frame[pos++] = b;
    if (pos == 4) {
      need = 4 + frame[3];
      if (frame[3] < 2 || need > sizeof(frame)) { lastResult_ = Result::BAD_LENGTH; return false; }
    }
    if (pos < need || pos < 4) continue;

    // vollständiges Paket
    if (pos == txLen_ && memcmp(frame, txBuf_, pos) == 0) {  // Eigen-Echo
      echoCount_++; pos = 0; need = 4; continue;
    }
    uint8_t sum = 0;
    for (uint8_t i = 2; i < pos - 1; i++) sum += frame[i];
    if ((uint8_t)~sum != frame[pos - 1]) { lastResult_ = Result::BAD_CHECKSUM; return false; }
    if (frame[2] != id) { lastResult_ = Result::BAD_ID; return false; }
    if (frame[3] != n + 2) { lastResult_ = Result::BAD_LENGTH; return false; }
    lastStatus_ = frame[4];
    for (uint8_t i = 0; i < n; i++) params[i] = frame[5 + i];
    lastResult_ = Result::OK;
    return true;
  }
  lastResult_ = Result::TIMEOUT;
  return false;
}

bool Bus::ping(uint8_t id) {
  send(id, PING, nullptr, 0);
  return receive(id, nullptr, 0);
}

bool Bus::read(uint8_t id, uint8_t addr, uint8_t* data, uint8_t len) {
  uint8_t p[2] = {addr, len};
  send(id, READ, p, 2);
  return receive(id, data, len);
}

bool Bus::write(uint8_t id, uint8_t addr, const uint8_t* data, uint8_t len, bool expectReply) {
  uint8_t p[32];
  if (len > sizeof(p) - 1) return false;
  p[0] = addr;
  memcpy(p + 1, data, len);
  send(id, WRITE, p, len + 1);
  if (!expectReply || id == BROADCAST) {
    // ggf. Echo/Antwort abwarten und verwerfen, damit der nächste Transfer sauber startet
    delayMicroseconds(timeoutUs_ / 2);
    while (port_->available()) port_->read();
    lastResult_ = Result::OK;
    return true;
  }
  return receive(id, nullptr, 0);
}

bool Bus::read8(uint8_t id, uint8_t addr, uint8_t& v) { return read(id, addr, &v, 1); }
bool Bus::read16(uint8_t id, uint8_t addr, uint16_t& v) {
  uint8_t b[2];
  if (!read(id, addr, b, 2)) return false;
  v = b[0] | (b[1] << 8);
  return true;
}
bool Bus::write8(uint8_t id, uint8_t addr, uint8_t v) { return write(id, addr, &v, 1); }
bool Bus::write16(uint8_t id, uint8_t addr, uint16_t v) {
  uint8_t b[2] = {(uint8_t)(v & 0xFF), (uint8_t)(v >> 8)};
  return write(id, addr, b, 2);
}

bool Bus::writePos(uint8_t id, uint16_t pos, uint16_t speed, uint8_t acc) {
  // ACC, GOAL_POS (2), GOAL_TIME (2), GOAL_SPEED (2) ab Register 41
  uint8_t b[7] = {acc, (uint8_t)(pos & 0xFF), (uint8_t)(pos >> 8), 0, 0,
                  (uint8_t)(speed & 0xFF), (uint8_t)(speed >> 8)};
  return write(id, ACC, b, 7);
}

}  // namespace sts

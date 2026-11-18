// SLARC – Testaufbau Fußschalter (Arduino Uno)
// Stand V1.1 (18.11.2026)
//
// Schaltung:
//   Mikroschalter COM -> GND, NO (mittlerer Pin) -> D2 (interner Pull-up). 0 = Kontakt.
//   V1.1 (18.11.2026): NO ist bei den verwendeten Schaltern der mittlere Pin.
//   LED: D8 -> 330 Ohm -> LED-Anode, LED-Kathode -> GND. Zusätzlich Board-LED D13.
//
// Entprellen in Software: Ein neuer Zustand gilt erst, wenn der Pin
// DEBOUNCE_MS lang stabil war. Die Rohflanken im Prellen werden mitgezählt
// und mit der Prelldauer auf dem seriellen Monitor (115200 Bd) ausgegeben.

const uint8_t PIN_SWITCH = 2;
const uint8_t PIN_LED    = 8;
const uint8_t PIN_LED_BOARD = LED_BUILTIN;   // D13
const uint16_t DEBOUNCE_MS = 8;              // 5–10 ms laut Hardware-Schnittstellen

bool stableState;            // entprellter Zustand, true = Kontakt
bool lastRaw;                // letzter Rohwert, true = Kontakt
uint32_t lastChangeMs;       // Zeitpunkt der letzten Rohflanke
uint32_t bounceStartUs;      // erste Rohflanke des aktuellen Wechsels
uint32_t lastBounceUs;       // letzte Rohflanke des aktuellen Wechsels
uint16_t rawEdges = 0;       // Rohflanken seit dem letzten gültigen Wechsel
uint32_t contacts = 0;       // Zahl der erkannten Kontakte

bool readContact() {
  return digitalRead(PIN_SWITCH) == LOW;      // 0 = Kontakt
}

void showState(bool contact) {
  digitalWrite(PIN_LED, contact ? HIGH : LOW);
  digitalWrite(PIN_LED_BOARD, contact ? HIGH : LOW);
}

void setup() {
  pinMode(PIN_SWITCH, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_LED_BOARD, OUTPUT);
  Serial.begin(115200);

  stableState = lastRaw = readContact();
  lastChangeMs = millis();
  showState(stableState);

  Serial.println(F("SLARC Fussschalter-Test V1.1"));
  Serial.print(F("Entprellzeit ")); Serial.print(DEBOUNCE_MS); Serial.println(F(" ms"));
  Serial.println(stableState ? F("Start: KONTAKT") : F("Start: offen"));
}

void loop() {
  bool raw = readContact();

  // Jede Rohflanke merken; der Entprell-Timer startet neu
  if (raw != lastRaw) {
    uint32_t nowUs = micros();
    if (rawEdges == 0) bounceStartUs = nowUs;
    lastBounceUs = nowUs;
    rawEdges++;
    lastRaw = raw;
    lastChangeMs = millis();
  }

  // Zustand übernehmen, wenn der Rohwert DEBOUNCE_MS stabil ist und sich unterscheidet
  if (raw != stableState && (millis() - lastChangeMs) >= DEBOUNCE_MS) {
    stableState = raw;
    showState(stableState);
    if (stableState) contacts++;

    Serial.print(millis());
    Serial.print(F(" ms  "));
    Serial.print(stableState ? F("KONTAKT ") : F("offen   "));
    Serial.print(F(" Nr. ")); Serial.print(contacts);
    Serial.print(F("  Rohflanken ")); Serial.print(rawEdges);
    Serial.print(F("  Prellen ")); Serial.print(lastBounceUs - bounceStartUs);
    Serial.println(F(" us"));
    rawEdges = 0;
  }

  // Kurzer Störimpuls, der vor Ablauf der Entprellzeit wieder verschwindet
  if (raw == stableState && rawEdges > 0 && (millis() - lastChangeMs) >= DEBOUNCE_MS) {
    Serial.print(millis());
    Serial.print(F(" ms  Stoerung verworfen, Rohflanken "));
    Serial.println(rawEdges);
    rawEdges = 0;
  }
}

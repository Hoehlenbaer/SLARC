# Fußschalter-Test (Arduino Uno)

Stand 18.11.2026. Prüft einen Fußschalter vor dem Einbau, unabhängig vom ESP32 und vom MCP23017.

- Aufbau: `fuss_test_breadboard.svg` (Breadboard und Schaltplan). Schalter COM → GND, NO (mittlerer Pin) → D2 (`INPUT_PULLUP`, 0 = Kontakt). LED an D8 über 330 Ω, die Board-LED D13 zeigt dasselbe.
- Programm: `fuss_test.ino`. Entprellung in Software, 8 ms. Der serielle Monitor (115200 Bd) zeigt je Wechsel die Zahl der Rohflanken und die Prelldauer. Damit lässt sich prüfen, ob 5–10 ms für den echten Schalter reichen. Kurze Störimpulse werden verworfen und gemeldet.
- Die SVG erzeugt `gen_breadboard_svg.py`.

Hinweis: Der interne Pull-up des Uno hat ~35 kΩ, auf dem Hub sitzen 10 kΩ. Das Prellbild kann sich deshalb leicht unterscheiden.

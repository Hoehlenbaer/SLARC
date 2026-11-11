# brain/safety.py
# Version 0.1 (07.11.2026) – Harte Sicherheitsgrenzen mit Vetorecht.
#
# Das LLM entscheidet nie über Sicherheit (Konzept Abschnitt 2 und 4.4).
# Hier wird festgelegt, was gar nicht erst ins Menü kommt bzw. was einen
# sofortigen Stopp auslöst. Unabhängig davon hat der ESP32 eigene
# Grenzen (SAFE_STOP bei fehlendem Heartbeat, Notaus über IO27).

from __future__ import annotations

from dataclasses import dataclass, field

from .datatypes import Observation

V_WARN = 10.5            # Warnung unter Last (Hardware_Interfaces.md)
V_STOP = 9.9             # Bewegung beenden
TILT_STOP_DEG = 25.0     # Annahme: darüber erst stabilisieren
SERVO_TEMP_STOP_C = 65.0 # Annahme, ST3215 Datenblatt prüfen
PERSON_MIN_M = 0.3       # keine Annäherung näher als das

# Verhalten, die den Roboter fortbewegen
MOVING = {
    "explore_frontier", "inspect_object", "approach_avoid", "search_item",
    "greet", "follow", "push_out", "fetch", "return_home", "retreat", "identify",
}
# Verhalten, die auf ein Objekt/eine Person zugehen
APPROACHING = {"inspect_object", "approach_avoid", "greet", "push_out", "fetch", "identify"}


@dataclass
class SafetyState:
    stop: bool = False                 # sofort anhalten, nichts Neues starten
    reasons: list[str] = field(default_factory=list)
    forbidden: set[str] = field(default_factory=set)   # Verhalten, die nicht ins Menü dürfen
    warn_battery: bool = False

    def allows(self, behavior: str) -> bool:
        return not self.stop and behavior not in self.forbidden


def check(obs: Observation) -> SafetyState:
    s = SafetyState()
    if obs.lifted:
        s.stop = True
        s.reasons.append("hochgehoben")
    if obs.tilt_deg > TILT_STOP_DEG:
        s.stop = True
        s.reasons.append(f"Neigung {obs.tilt_deg:.0f}°")
    if obs.battery_v < V_STOP:
        s.stop = True
        s.reasons.append(f"Akku {obs.battery_v:.1f} V")
    elif obs.battery_v < V_WARN:
        s.warn_battery = True
        # nur noch heim oder ruhen
        s.forbidden |= MOVING - {"return_home"}
        s.reasons.append("Akku-Warnung")
    if obs.servo_temp_max_c > SERVO_TEMP_STOP_C:
        s.forbidden |= MOVING
        s.reasons.append("Servos heiß")
    if obs.stair_edge_near and not obs.climb_allowed:
        # an der Kante nur weg davon oder stehen bleiben
        s.forbidden |= MOVING - {"retreat", "return_home"}
        s.reasons.append("Treppenkante")
    if any(p.dist_m < PERSON_MIN_M for p in obs.persons):
        s.forbidden |= APPROACHING | {"follow"}
        s.reasons.append("Mensch sehr nah")
    return s

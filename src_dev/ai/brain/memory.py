# brain/memory.py
# Version 0.1 (07.11.2026) – Gedächtnis des Brain: Gewöhnung, Gewichte
# der Dienste (Lernen durch Lob), Kontakte, Meldungen, Tagebuch.
# Persistenz als JSON (Annahme, später ggf. SQLite).
# V0.3: doze_log für die Sättigung beim Dösen.
# V0.2: Orte gewöhnen schneller ab (1 h) als Objekte; last_seen merkt sich, wo eine
#       Klasse zuletzt gesehen wurde (Suche beginnt dort); Meldungen je Objekt und Ort.

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

# Annahmen, im Betrieb einstellen
HABIT_HALF_LIFE_S = 6 * 3600.0     # Gewöhnung an ein Objekt klingt in 6 h auf die Hälfte ab
AREA_HALF_LIFE_S = 3600.0          # an einen Raum in 1 h (dort ändert sich öfter etwas)
HABIT_GAIN_INSPECT = 0.6           # Zuwachs nach gründlichem Untersuchen
HABIT_GAIN_SEEN = 0.005            # Zuwachs je Takt (1 Hz), in dem es nur gesehen wird: halb gewohnt nach ~2,5 min
WEIGHT_PRAISE = 0.15               # Lob erhöht das Gewicht eines Dienstes
WEIGHT_SCOLD = 0.15                # Tadel senkt es
WEIGHT_MIN, WEIGHT_MAX = 0.3, 2.0
DIARY_MAX = 500


@dataclass
class _Habit:
    value: float
    t: float


@dataclass
class Memory:
    habits: dict[str, _Habit] = field(default_factory=dict)
    service_weights: dict[str, float] = field(default_factory=dict)
    last_contact: dict[str, float] = field(default_factory=dict)   # Person-ID -> Zeit
    last_greet: dict[str, float] = field(default_factory=dict)
    reported: dict[str, float] = field(default_factory=dict)       # "oid@ort" -> Zeit der Meldung
    last_seen: dict[str, list] = field(default_factory=dict)       # Klasse -> [ort, zeit]
    doze_log: list[list] = field(default_factory=list)             # [[start, ende], …] der letzten Stunden
    seek_checked: dict[str, float] = field(default_factory=dict)   # Raum -> Zeit, zu der dort niemand war

    def dozed_s(self, now: float, window_s: float = 3600.0) -> float:
        """Wie lange in den letzten window_s Sekunden gedöst wurde."""
        return sum(max(0.0, min(e, now) - max(s, now - window_s)) for s, e in self.doze_log)
    known_objects: set[str] = field(default_factory=set)
    known_persons: set[str] = field(default_factory=set)
    diary: list[dict] = field(default_factory=list)

    # ---------------- Gewöhnung ----------------
    def habituation(self, key: str, now: float) -> float:
        """0 = völlig neu, 1 = völlig gewohnt. Klingt exponentiell ab."""
        h = self.habits.get(key)
        if h is None:
            return 0.0
        half = AREA_HALF_LIFE_S if key.startswith("area:") else HABIT_HALF_LIFE_S
        decay = 0.5 ** ((now - h.t) / half)
        return h.value * decay

    def habituate(self, key: str, now: float, gain: float) -> None:
        v = self.habituation(key, now)
        self.habits[key] = _Habit(min(1.0, v + gain * (1.0 - v)), now)

    # ---------------- Lernen durch Lob ----------------
    def weight(self, service: Optional[str]) -> float:
        if not service:
            return 1.0
        return self.service_weights.get(service, 1.0)

    def praise(self, service: Optional[str], positive: bool = True) -> None:
        if not service:
            return
        w = self.weight(service)
        w = w + WEIGHT_PRAISE if positive else w - WEIGHT_SCOLD
        self.service_weights[service] = max(WEIGHT_MIN, min(WEIGHT_MAX, w))

    # ---------------- Tagebuch ----------------
    def log(self, now: float, kind: str, text: str, **extra) -> None:
        self.diary.append({"t": now, "kind": kind, "text": text, **extra})
        if len(self.diary) > DIARY_MAX:
            del self.diary[: len(self.diary) - DIARY_MAX]

    # ---------------- Persistenz ----------------
    def to_dict(self) -> dict:
        return {
            "habits": {k: [h.value, h.t] for k, h in self.habits.items()},
            "service_weights": self.service_weights,
            "last_contact": self.last_contact,
            "last_greet": self.last_greet,
            "reported": self.reported,
            "known_objects": sorted(self.known_objects),
            "known_persons": sorted(self.known_persons),
            "last_seen": self.last_seen,
            "doze_log": self.doze_log,
            "seek_checked": self.seek_checked,
            "diary": self.diary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        m = cls()
        m.habits = {k: _Habit(v[0], v[1]) for k, v in d.get("habits", {}).items()}
        m.service_weights = dict(d.get("service_weights", {}))
        m.last_contact = dict(d.get("last_contact", {}))
        m.last_greet = dict(d.get("last_greet", {}))
        m.reported = dict(d.get("reported", {}))
        m.known_objects = set(d.get("known_objects", []))
        m.known_persons = set(d.get("known_persons", []))
        m.last_seen = dict(d.get("last_seen", {}))
        m.doze_log = list(d.get("doze_log", []))
        m.seek_checked = dict(d.get("seek_checked", {}))
        m.diary = list(d.get("diary", []))
        return m

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)    # atomar, damit ein Stromausfall die Datei nicht zerstört

    @classmethod
    def load(cls, path: str) -> "Memory":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

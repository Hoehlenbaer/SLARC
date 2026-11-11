# brain/nav/tracker.py
# Version 0.1 (11.11.2026) – Objekte über die Zeit verfolgen und wiedererkennen.  # PORTABLE
#
# Stufe 1 aus Brain_Konzept Abschnitt 13, Punkt 13: gleiche Klasse an ungefähr gleicher
# Stelle = dasselbe Objekt. Die Kennungen der Perzeption gelten nur, solange etwas im
# Bild bleibt; die dauerhafte Kennung (track_id) vergibt dieser Tracker.
#
# Zustände: "da" (zuletzt gesehen, wo erwartet), "fehlt" (Stelle war im Blick, Objekt
# mehrmals nicht erkannt). Taucht dieselbe Klasse woanders auf, während ein Track „fehlt“,
# gilt sie als verschoben (moved=True) und behält die Kennung – so bemerkt SLARC, dass
# die Katze umgezogen ist. Embeddings (Stufe 2) kommen später hinzu.

from __future__ import annotations

import math
from typing import Callable, Optional

from ..blackboard import Detection, TrackedObject

GATE_M = 0.6           # Zuordnung zu einem Track gleicher Klasse bis zu diesem Abstand
MISS_FRAMES = 4        # so oft im Blick und nicht erkannt -> „fehlt“
MOVED_M = 1.0          # erst ab diesem Abstand zur alten Stelle gilt ein wiedergefundenes Objekt als verschoben
                       # (sonst war es nur verdeckt, z. B. durch einen Tisch, den die Karte noch nicht kannte)
EMA = 0.3              # Glättung der Position


class ObjectTracker:
    def __init__(self):
        self.n = 0

    def _new_id(self, cls: str) -> str:
        self.n += 1
        return f"{cls}-{self.n}"

    def update(self, tracks: dict[str, TrackedObject], dets: list[Detection], t: float,
               expect_visible: Callable[[float, float], bool], area_at: Callable[[float, float], Optional[str]]
               ) -> list[tuple[str, str]]:
        """Detektionen eines Bildes zuordnen. Gibt Ereignisse (art, track_id) zurück:
        neu, verschoben, fehlt."""
        events = []
        used = set()
        for d in dets:
            best, bd = None, GATE_M
            for tr in tracks.values():
                if tr.cls != d.cls or tr.track_id in used or tr.state != "da":
                    continue
                dist = math.hypot(tr.x - d.x, tr.y - d.y)
                if dist < bd:
                    best, bd = tr, dist
            if best is None:                                  # vermisstes Objekt gleicher Klasse?
                missing = [tr for tr in tracks.values()
                           if tr.cls == d.cls and tr.state == "fehlt" and tr.track_id not in used]
                if missing:
                    best = min(missing, key=lambda tr: math.hypot(tr.x - d.x, tr.y - d.y))
                    moved = math.hypot(best.x - d.x, best.y - d.y) > MOVED_M
                    best.x, best.y, best.state = d.x, d.y, "da"
                    best.moved = best.moved or moved
                    best.area = area_at(d.x, d.y)
                    events.append(("verschoben" if moved else "wieder_da", best.track_id))
            if best is None:
                tid = self._new_id(d.cls)
                best = TrackedObject(tid, d.cls, d.x, d.y, d.conf, t, t, 0, "da", False, area_at(d.x, d.y))
                tracks[tid] = best
                events.append(("neu", tid))
            else:
                best.x += EMA * (d.x - best.x)
                best.y += EMA * (d.y - best.y)
                best.conf = max(best.conf * 0.9, d.conf)
                if best.area is None:
                    best.area = area_at(best.x, best.y)
            best.last_seen, best.misses = t, 0
            best.n_seen += 1
            used.add(best.track_id)
        for tr in tracks.values():
            if tr.track_id in used or tr.state != "da":
                continue
            if expect_visible(tr.x, tr.y):
                tr.misses += 1
                if tr.misses >= MISS_FRAMES:
                    tr.state = "fehlt"
                    events.append(("fehlt", tr.track_id))
        return events

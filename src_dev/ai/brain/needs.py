# brain/needs.py
# Version 0.1 (07.11.2026) – Bedürfnismodell.
#
# Fünf Bedürfnisse, je ein Wert 0…1, im 1-Hz-Takt aus Messwerten und Zeit
# berechnet (Konzept Abschnitt 4):
#   energie, neugier, nuetzlichkeit, gesellschaft, unbehagen
# Für das LLM werden sie in Stufen übersetzt. Stufenwechsel mit Hysterese,
# damit ein Wert an der Grenze nicht flackert (Lehre aus dem climbing-Flag:
# flackernde Zustände treiben nachgelagerte Logik zwischen Zweigen hin und her).
#
# Alle Konstanten sind Annahmen und werden im Betrieb eingestellt.

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .datatypes import Observation
from .memory import HABIT_GAIN_SEEN, Memory

NEEDS = ("energie", "neugier", "nuetzlichkeit", "gesellschaft", "unbehagen")
LEVELS = ("ruhig", "leicht", "mittel", "hoch", "dringend")
LEVEL_EDGES = (0.2, 0.4, 0.6, 0.8)     # Grenzen zwischen den Stufen
HYST = 0.05                            # Hysterese um jede Grenze

# --- Energie ---
# Ladezustand aus Zellspannung unter Last, stückweise linear (Annahme für 3S LiPo,
# mit echter Entladekurve ersetzen). 3,5 V/Zelle = Warnschwelle, 3,3 V = Bewegung beenden.
SOC_CURVE = ((3.30, 0.00), (3.50, 0.10), (3.60, 0.20), (3.70, 0.40),
             (3.80, 0.60), (3.90, 0.75), (4.00, 0.88), (4.10, 1.00))
CELLS = 3
BATTERY_WH = 99.9        # ZEEE 3S 9000 mAh
WH_PER_M = 0.2           # Verbrauch beim Gehen je Meter (Annahme, messen)
HOME_SAFETY = 1.5        # Faktor auf den Rückwegbedarf (Umwege, Unsicherheit)
RESERVE_COMFORT = 4.0    # ab dieser Reserve (Vielfaches des Rückwegs) kein Energiebedarf
SOC_LOW = 0.40           # unterhalb wächst der Bedarf auch zu Hause …
SOC_MIN = 0.10           # … bis "dringend" an der Warnschwelle

# --- Neugier ---
TAU_BORED_S = 300.0      # Langeweile steigt ohne neue Information auf ~63 % in 5 min
NOVELTY_RANGE_M = 4.0    # Objekte weiter weg ziehen weniger an

# --- Nützlichkeit ---
TAU_USEFUL_S = 1800.0    # ohne nützliche Tat steigt der Wunsch langsam
REQUEST_AGE_S = 1800.0   # offene Bitte wird mit dem Alter dringender

# --- Gesellschaft ---
TAU_SOCIAL_S = 1200.0    # Alleinsein: auf ~63 % in 20 min
SOCIAL_SATIATE_S = 60.0  # Person in der Nähe sättigt schnell
SOCIAL_NEAR_M = 2.0

# --- Unbehagen ---
TAU_CALM_S = 30.0        # Unbehagen klingt in ~30 s ab, wenn die Ursache weg ist
TILT_UNEASY_DEG = 10.0
TILT_BAD_DEG = 20.0


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def soc_from_voltage(v: float) -> float:
    """Grober Ladezustand aus der Spannung unter Last (Kurve SOC_CURVE)."""
    vc = v / CELLS
    pts = SOC_CURVE
    if vc <= pts[0][0]:
        return 0.0
    for (v0, s0), (v1, s1) in zip(pts, pts[1:]):
        if vc <= v1:
            return s0 + (s1 - s0) * (vc - v0) / (v1 - v0)
    return 1.0


def level_index(value: float, prev: int | None = None) -> int:
    """Stufe 0…4 mit Hysterese gegenüber der vorigen Stufe."""
    raw = sum(value >= e for e in LEVEL_EDGES)
    if prev is None or raw == prev:
        return raw
    lvl = prev
    if raw > prev:
        # nach oben: jede Grenze muss um HYST überschritten sein
        while lvl < raw and value >= LEVEL_EDGES[lvl] + HYST:
            lvl += 1
    else:
        # nach unten: jede Grenze muss um HYST unterschritten sein
        while lvl > raw and value < LEVEL_EDGES[lvl - 1] - HYST:
            lvl -= 1
    return lvl


@dataclass
class NeedsState:
    values: dict[str, float] = field(default_factory=lambda: {n: 0.0 for n in NEEDS})
    levels: dict[str, int] = field(default_factory=lambda: {n: 0 for n in NEEDS})
    # interne Zeitmarken
    t_last: float | None = None
    t_new_info: float | None = None      # letzte neue Information (Neugier)
    t_useful: float | None = None        # letzte nützliche Tat
    t_contact: float | None = None       # letzter Kontakt zu einem Menschen
    discomfort_mem: float = 0.0
    home_reserve: float | None = None    # Energie-Reserve als Vielfaches des Rückwegbedarfs (Diagnose)

    def level_name(self, need: str) -> str:
        return LEVELS[self.levels[need]]


class NeedsModel:
    def __init__(self, memory: Memory):
        self.mem = memory
        self.s = NeedsState()

    # ---------------- Ereignisse aus dem Verhaltens-Layer ----------------
    def note_new_info(self, now: float) -> None:
        self.s.t_new_info = now

    def note_useful(self, now: float) -> None:
        self.s.t_useful = now

    def note_contact(self, now: float) -> None:
        self.s.t_contact = now

    # ---------------- Takt ----------------
    def update(self, obs: Observation) -> tuple[NeedsState, list[str]]:
        """Bedürfnisse aktualisieren. Rückgabe: Zustand und Liste der
        Bedürfnisse, deren Stufe gestiegen ist (Auslöser fürs LLM)."""
        now = obs.t
        s = self.s
        if s.t_last is None:
            # Start: Zeitmarken auf jetzt, damit nicht alles sofort "dringend" ist
            s.t_new_info = s.t_useful = s.t_contact = now
        dt = 0.0 if s.t_last is None else max(0.0, now - s.t_last)
        s.t_last = now

        v = s.values
        v["energie"] = self._energy(obs)
        v["neugier"] = self._curiosity(obs, now)
        v["nuetzlichkeit"] = self._usefulness(obs, now)
        v["gesellschaft"] = self._social(obs, now, dt)
        v["unbehagen"] = self._discomfort(obs, dt)

        risen = []
        for n in NEEDS:
            new = level_index(v[n], s.levels[n])
            if new > s.levels[n]:
                risen.append(n)
            s.levels[n] = new
        return s, risen

    # ---------------- einzelne Bedürfnisse ----------------
    def _energy(self, obs: Observation) -> float:
        soc = soc_from_voltage(obs.battery_v)
        usable_wh = soc * BATTERY_WH
        # Bedarf aus dem Ladezustand allein (gilt auch zu Hause)
        e_soc = clamp((SOC_LOW - soc) / (SOC_LOW - SOC_MIN))
        if obs.at_home or obs.home_dist_m is None:
            self.s.home_reserve = None
            # Rückweg unbekannt: vorsichtiger, Ladezustand stärker gewichten
            return e_soc if obs.at_home else clamp(e_soc + 0.2 * (1 - soc))
        need_wh = max(0.5, obs.home_dist_m * WH_PER_M * HOME_SAFETY)
        reserve = usable_wh / need_wh
        self.s.home_reserve = reserve
        # Reserve 1 -> 1.0 (dringend), Reserve >= RESERVE_COMFORT -> 0
        e_home = clamp((RESERVE_COMFORT - reserve) / (RESERVE_COMFORT - 1.0))
        return max(e_soc, e_home)

    def _curiosity(self, obs: Observation, now: float) -> float:
        bored = 1.0 - math.exp(-(now - self.s.t_new_info) / TAU_BORED_S)
        novelty = 0.0
        for o in obs.objects:
            key = f"obj:{o.oid}"
            h = self.mem.habituation(key, now)
            prox = clamp(1.0 - o.dist_m / NOVELTY_RANGE_M, 0.2, 1.0)
            moved = 0.3 if o.moved else 0.0
            novelty = max(novelty, clamp((1.0 - h) * prox + moved))
            # bloßes Sehen gewöhnt langsam (je Takt)
            self.mem.habituate(key, now, HABIT_GAIN_SEEN)
        area = obs.unknown_frac if obs.frontier else 0.0
        return clamp(0.45 * bored + 0.55 * max(novelty, area))

    def _usefulness(self, obs: Observation, now: float) -> float:
        if obs.requests:
            age = max(now - r.t_created for r in obs.requests)
            return clamp(0.7 + 0.3 * age / REQUEST_AGE_S)
        idle = 1.0 - math.exp(-(now - self.s.t_useful) / TAU_USEFUL_S)
        best_w = max([1.0] + list(self.mem.service_weights.values()))
        return clamp(0.6 * idle * best_w)

    def _social(self, obs: Observation, now: float, dt: float) -> float:
        near = [p for p in obs.persons if p.dist_m <= SOCIAL_NEAR_M]
        if near:
            # Nähe sättigt: Kontaktzeit nachziehen, aber nur so schnell wie SOCIAL_SATIATE_S
            gap = now - self.s.t_contact
            self.s.t_contact = now - gap * math.exp(-dt / SOCIAL_SATIATE_S)
            for p in near:
                self.mem.last_contact[p.pid] = now
        alone = now - self.s.t_contact
        return clamp(1.0 - math.exp(-alone / TAU_SOCIAL_S))

    def _discomfort(self, obs: Observation, dt: float) -> float:
        inst = 0.0
        inst = max(inst, clamp((0.5 - obs.light) / 0.5) * 0.7)       # Dunkelheit
        if not obs.floor_known:
            inst = max(inst, 0.4)
        if obs.slipped:
            inst = max(inst, 0.7)
        if obs.lifted:
            inst = max(inst, 0.9)
        if obs.tilt_deg > TILT_UNEASY_DEG:
            inst = max(inst, clamp((obs.tilt_deg - TILT_UNEASY_DEG) / (TILT_BAD_DEG - TILT_UNEASY_DEG)) * 0.9)
        if obs.stair_edge_near and not obs.climb_allowed:
            inst = max(inst, 0.5)
        if any(p.dist_m < 0.5 for p in obs.persons):
            inst = max(inst, 0.4)
        # Leaky Peak: springt sofort hoch, klingt langsam ab
        decayed = self.s.discomfort_mem * math.exp(-dt / TAU_CALM_S) if dt > 0 else self.s.discomfort_mem
        self.s.discomfort_mem = max(inst, decayed)
        return self.s.discomfort_mem

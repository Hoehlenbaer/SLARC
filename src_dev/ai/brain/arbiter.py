# brain/arbiter.py
# Version 0.2 (07.11.2026) – Entscheidungszyklus im 1-Hz-Takt (Konzept 8).
# V0.7 (11.11.2026): Meldung unter dem Ort des Objekts merken, nicht dem des Roboters
#       (2D-Sim: Handy in der Küche vom Flur aus gesehen -> jede Sekunde neu gemeldet).
# V0.6: Personen in last_seen merken (für seek_company); Dösezeiten ins doze_log.
# V0.5: Auslöser unterbrechen ein laufendes Verhalten nur bei Chat oder deutlich besserem
#       Ziel (INTERRUPT_MARGIN); dasselbe Ziel wird nie neu gestartet; last_seen pflegen;
#       Umsehen gewöhnt an den Raum, bringt aber keine neue Information.
# V0.4: Regeln starten ein laufendes Verhalten nicht neu (Heimweg wurde jede Sekunde
#       neu gestartet); jede Entscheidung kommt ins Tagebuch, nicht nur die des LLM.
# V0.3: Gefahr im Bild -> sofort melden (Regel, vor Energie und LLM).
# V0.2: Energie ab "hoch" per Regel (vorher erst "dringend"); das LLM bekommt nur
#       knappe Fälle (close_options), sonst entscheidet der Code.
#
# Reihenfolge je Takt:
#   1. Bedürfnisse aktualisieren
#   2. Sicherheits-Veto -> Stopp
#   3. Energie ab "hoch" -> return_home bzw. rest (Regel, ohne LLM)
#   4. Auslöser und knapper Fall -> LLM als Schiedsrichter (Denk-Zustand), oder
#   5. laufendes Verhalten weiter, sonst Code-Auswahl
#
# Der Arbiter ruft das LLM nicht selbst auf. Er liefert eine Decision mit
# action="ask_llm" samt Menü; der Aufrufer (Brain-Prozess) schaltet in den
# Denk-Zustand, fragt das LLM und meldet das Ergebnis mit apply_llm() zurück.

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from .behaviors import build_options, close_options, select_fallback
from .datatypes import Observation, Option
from .memory import HABIT_GAIN_INSPECT, Memory
from .needs import NeedsModel, NeedsState
from .safety import SafetyState, check

LLM_MIN_INTERVAL_S = 120.0     # höchstens alle 2 min nachdenken (Ausnahme: Chat)
ENERGY_RULE_LEVEL = 3          # ab "hoch": heim/ruhen per Regel
LEVEL_TRIGGER_MIN = 2          # Stufenanstieg löst erst ab "mittel" aus
INTERRUPT_MARGIN = 0.2         # so viel besser muss ein neues Ziel sein, um zu unterbrechen
PERSON_REVISIT_S = 600.0       # Person gilt nach 10 min ohne Sicht als wiedergesehen


@dataclass
class Decision:
    action: str                          # "stop" | "start" | "continue" | "ask_llm"
    option: Optional[Option] = None
    menu: list[Option] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    reason: str = ""


class Arbiter:
    def __init__(self, memory: Memory, rng: Optional[random.Random] = None):
        self.mem = memory
        self.needs = NeedsModel(memory)
        self.rng = rng or random.Random()
        self.current: Optional[Option] = None
        self.t_llm: float = -1e9
        self.last_safety = SafetyState()
        self.last_needs: Optional[NeedsState] = None
        self._seen: dict[str, float] = {}
        self.t_current: float = 0.0

    # ------------------------------------------------------------------
    def step(self, obs: Observation) -> Decision:
        now = obs.t
        needs, risen = self.needs.update(obs)
        self.last_needs = needs
        safety = check(obs)
        self.last_safety = safety

        self._process_feedback(obs)
        for o in obs.objects:
            self.mem.last_seen[o.cls] = [o.place, now]
        if obs.persons:
            self.mem.last_seen["person"] = [obs.place, now]

        # 2. Sicherheit
        if safety.stop:
            self.current = None
            return Decision("stop", reason=", ".join(safety.reasons))
        if self.current and not safety.allows(self.current.behavior):
            self.current = None     # laufendes Verhalten abbrechen, neu wählen

        menu = build_options(obs, needs, self.mem, safety)

        # 2b. Gefahr -> sofort melden, ohne LLM
        hazard = next((o for o in menu if o.service == "hazard"), None)
        if hazard is not None and (self.current is None or self.current.service != "hazard"):
            return self._start(hazard, now, "Gefahr")

        # 3. Energie hoch/dringend -> heim, ohne LLM
        if needs.levels["energie"] >= ENERGY_RULE_LEVEL:
            if not obs.at_home:
                opt = next((o for o in menu if o.behavior == "return_home"), None)
                if opt:
                    if self.current is not None and self.current.behavior == "return_home":
                        return Decision("continue", option=self.current)
                    return self._start(opt, now, "Energie hoch")
            else:
                opt = next((o for o in menu if o.behavior == "rest"), None)
                if opt:
                    if self.current is not None and self.current.behavior == "rest":
                        return Decision("continue", option=self.current)
                    return self._start(opt, now, "Energie hoch, zu Hause")

        # 4. Auslöser
        triggers = self._triggers(obs, risen)
        cooldown_ok = now - self.t_llm >= LLM_MIN_INTERVAL_S
        if triggers and menu and (cooldown_ok or "chat" in triggers):
            close = close_options(menu)
            if self.current is not None and "chat" not in triggers:
                best = close[0]
                if best.key == self.current.key or best.utility < self.current.utility + INTERRUPT_MARGIN:
                    return Decision("continue", option=self.current, triggers=triggers)
            if len(close) >= 2:
                self.t_llm = now
                return Decision("ask_llm", menu=close, triggers=triggers)
            # eindeutiger Fall: der Code entscheidet sofort, kein Denk-Zustand nötig
            if self.current is not None and close[0].key == self.current.key:
                return Decision("continue", option=self.current)
            return self._start(close[0], now, "eindeutig: " + ", ".join(triggers))

        # 5. weiter oder Code-Auswahl
        if self.current is not None:
            return Decision("continue", option=self.current)
        opt = select_fallback(menu, self.rng)
        if opt is None:
            return Decision("stop", reason="kein machbares Ziel")
        return self._start(opt, now, "Code-Auswahl")

    def apply_llm(self, menu: list[Option], choice: Optional[int], now: float,
                  reason: str = "", mood: str = "") -> Decision:
        """Ergebnis des LLM übernehmen. choice ist 1-basiert; None = Zeitüberschreitung
        oder ungültig -> Code-Auswahl."""
        if choice is None or not 1 <= choice <= len(menu):
            opt = select_fallback(menu, self.rng)
            return self._start(opt, now, "LLM ohne gültige Antwort, Code-Auswahl") if opt else Decision("stop")
        opt = menu[choice - 1]
        if not self.last_safety.allows(opt.behavior):     # doppelt hält besser
            return Decision("stop", reason="Veto nach LLM-Wahl")
        if self.current is not None and opt.key == self.current.key:
            return Decision("continue", option=self.current)
        self.mem.log(now, "entscheidung", f"{opt.label} – {reason}", ziel=opt.key, stimmung=mood)
        return self._start(opt, now, reason, log=False)

    # ------------------------------------------------------------------
    def _start(self, opt: Option, now: float, reason: str, log: bool = True) -> Decision:
        self._close_doze(now)
        self.current = opt
        self.t_current = now
        if log:
            self.mem.log(now, "entscheidung", opt.label, ziel=opt.key)
        if opt.behavior == "greet" and opt.arg:
            self.mem.last_greet[opt.arg] = now
        return Decision("start", option=opt, reason=reason)

    def _triggers(self, obs: Observation, risen: list[str]) -> list[str]:
        t = []
        if obs.chat_new:
            t.append("chat")
        t += [f"stufe:{n}" for n in risen if self.needs.s.levels[n] >= LEVEL_TRIGGER_MIN]
        if obs.last_result:
            t.append(f"ergebnis:{obs.last_result[0]}:{obs.last_result[1]}")
        for o in obs.objects:
            if o.oid not in self.mem.known_objects:
                self.mem.known_objects.add(o.oid)
                t.append(f"neu:{o.cls}")
        for p in obs.persons:
            # neu oder nach mindestens 10 min wiedergesehen
            if p.pid not in self.mem.known_persons or obs.t - self._seen.get(p.pid, -1e9) > PERSON_REVISIT_S:
                self.mem.known_persons.add(p.pid)
                t.append(f"person:{p.name or p.pid}")
            self._seen[p.pid] = obs.t
        return t

    def _close_doze(self, now: float) -> None:
        """Endet ein Dösen (fertig oder unterbrochen), kommt es ins doze_log."""
        if self.current is not None and self.current.behavior == "doze":
            self.mem.doze_log.append([self.t_current, now])
            self.mem.doze_log[:] = [x for x in self.mem.doze_log if x[1] > now - 4 * 3600]

    def _process_feedback(self, obs: Observation) -> None:
        now = obs.t
        # Lob durch Antippen gilt dem laufenden Verhalten
        if obs.tapped and self.current is not None:
            self.mem.praise(self.current.service, True)
            self.mem.log(now, "lob", f"Antippen bei {self.current.key}")
        if obs.last_result and self.current is not None:
            beh, res = obs.last_result
            if res == "ok":
                if beh in ("inspect_object", "approach_avoid") and self.current.arg:
                    self.mem.habituate(f"obj:{self.current.arg}", now, HABIT_GAIN_INSPECT)
                    self.needs.note_new_info(now)
                if beh in ("explore_frontier", "wander"):
                    self.mem.habituate(f"area:{self.current.arg}", now, HABIT_GAIN_INSPECT)
                    self.needs.note_new_info(now)
                if beh == "look_around":
                    # im selben Raum wird Umsehen langweilig; neue Information gibt es nur,
                    # wenn dabei etwas Neues auftaucht (Auslöser "neu:")
                    self.mem.habituate(f"area:{obs.place}", now, HABIT_GAIN_INSPECT)
                if self.current.service:
                    self.needs.note_useful(now)
                if beh == "report" and self.current.arg:
                    place = next((o.place for o in obs.objects if o.oid == self.current.arg), obs.place)
                    self.mem.reported[f"{self.current.arg}@{place}"] = now
                if beh in ("greet", "follow"):
                    self.needs.note_contact(now)
                if beh == "seek_company" and not obs.persons:
                    self.mem.seek_checked[obs.place] = now      # hier ist gerade niemand
            self.mem.log(now, "ergebnis", f"{self.current.key}: {res}")
            self._close_doze(now)
            self.current = None

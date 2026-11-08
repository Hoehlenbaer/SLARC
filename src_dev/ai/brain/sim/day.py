# brain/sim/day.py
# Version 0.1 (07.11.2026) – Ein simulierter Tag: Welt + Arbiter + Behavior Tree (+ LLM).
# V0.2 (08.11.2026): Personennamen an interpret_chat/item_problem (Personensuche statt „kann ich nicht erkennen“).
#
# Aufruf aus src_dev/ai:
#   python -m brain.sim.day                          # ohne LLM: Code entscheidet, Chat per Stichwort
#   python -m brain.sim.day --trees                  # zusätzlich jeden Baum mit Status anzeigen
#   python -m brain.sim.day --model Qwen3.5-4B-Q4_K_M.gguf --gpu-layers -1
#
# Ablauf je Sekunde Simulationszeit: Beobachtung -> Arbiter -> ggf. neuer Teilbaum;
# der Baum wird alle 0,5 s getickt. Knappe Fälle gehen ans LLM (Denk-Zustand:
# SLARC steht still, die Zeit läuft um --think-s weiter). Chat-Nachrichten kommen
# aus einem Drehbuch in world.py.

from __future__ import annotations

import argparse
import random
import re
from collections import Counter

import py_trees
from py_trees.common import Status

from .. import semantic as S
from ..arbiter import Arbiter
from ..memory import Memory
from ..needs import NEEDS, LEVELS
from ..perception_classes import INDOOR, normalize_item
from ..prompt import state_text
from .bt import DT, Ctx, build_tree
from .world import default_flat

PEOPLE_PID = {"Marco": "p-marco", "Laura": "p-laura"}


def hms(t: float) -> str:
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def keyword_chat(text: str) -> S.ChatResult:
    """Ersatz für das LLM: sehr einfache Deutung per Stichwort (nur für Läufe ohne Modell)."""
    t = text.lower()
    item = ""
    for w in re.findall(r"[a-zäöüß]+", t):
        if normalize_item(w):
            item = normalize_item(w)
    if not item:
        m = re.search(r"(?:meinen|meine|mein|die|den|das)\s+([a-zäöüß]+)", t)
        item = m.group(1) if m else ""
    if "gut gemacht" in t or "super" in t:
        return S.ChatResult("praise", reply="Danke!")
    if "lass mich" in t or "stopp" in t:
        return S.ChatResult("stop", reply="Okay, ich bin still.")
    if "komm mit" in t:
        return S.ChatResult("follow", reply="Ich komme mit.")
    if t.startswith("komm"):
        return S.ChatResult("come", reply="Ich komme.")
    if "wo ist" in t or "such" in t:
        return S.ChatResult("search", item, reply="Ich schaue nach.")
    if "schieb" in t:
        return S.ChatResult("push_out", item, reply="Ich versuche es.")
    return S.ChatResult("smalltalk", reply="Hm, schön.")


def main() -> None:
    ap = argparse.ArgumentParser(description="SLARC Brain: simulierter Tag mit Behavior Tree")
    ap.add_argument("--hours", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--soc", type=float, default=0.9, help="Ladezustand am Start, 0…1")
    ap.add_argument("--trees", action="store_true", help="jeden Teilbaum am Anfang und Ende zeigen")
    ap.add_argument("--needs", action="store_true", help="Stufenwechsel der Bedürfnisse zeigen")
    ap.add_argument("--model", default=None, help="GGUF; ohne: Code entscheidet, Chat per Stichwort")
    ap.add_argument("--gpu-layers", type=int, default=0)
    ap.add_argument("--think-s", type=float, default=15.0, help="Denkzeit je LLM-Aufruf in Simulationszeit (Pi-Annahme)")
    a = ap.parse_args()

    world = default_flat(a.seed, a.soc)
    mem = Memory()
    arb = Arbiter(mem, random.Random(a.seed))
    rng = random.Random(a.seed + 1)
    brain = None
    if a.model:
        from ..llm import LlamaBrain
        brain = LlamaBrain(a.model, n_gpu_layers=a.gpu_layers)

    def log(msg: str) -> None:
        print(f"[{hms(world.t)}] {msg}", flush=True)

    ctx = Ctx(world, log)
    places_fn = (lambda item, rooms: S.search_places(brain, item, rooms).places) if brain else None

    tree = None
    cur = None
    t_start = 0.0
    last_result = None
    requests: list = []
    chat_i = 0
    tapped = False
    stats = Counter()
    time_in = Counter()
    llm_calls = 0
    prev_levels = None
    end_reason = "Zeit abgelaufen"

    def stop_tree(reason: str) -> None:
        nonlocal tree, cur
        if tree is not None and tree.status == Status.RUNNING:
            tree.stop(Status.INVALID)
            log(f"   abgebrochen: {cur.key} ({reason})")
        tree, cur = None, None

    def start(opt, why: str) -> None:
        nonlocal tree, cur, t_start
        if tree is not None and tree.status == Status.RUNNING:
            stop_tree("neues Ziel")
        ctx.found = None
        tree, cur, t_start = build_tree(opt, ctx, rng, places_fn, mem.last_seen), opt, world.t
        tree.setup_with_descendants()
        stats[opt.behavior] += 1
        log(f"-> {opt.key}   [{why}]")
        if a.trees:
            print(py_trees.display.unicode_tree(tree))

    while world.t < a.hours * 3600:
        chat_new = False
        # ---------------- Chat aus dem Drehbuch
        while chat_i < len(world.chat) and world.chat[chat_i].t <= world.t:
            ev = world.chat[chat_i]
            chat_i += 1
            res = S.interpret_chat(brain, ev.text, ev.sender, mem.diary, tuple(PEOPLE_PID)) if brain else keyword_chat(ev.text)
            if brain:
                llm_calls += 1 + (1 if res.talk else 0)
            problem = S.item_problem(res, tuple(PEOPLE_PID))
            reply = problem or res.reply
            log(f"CHAT {ev.sender}: „{ev.text}“ -> {res.service}({res.item})  SLARC: „{reply}“")
            if problem:
                continue
            if res.service == "praise" and cur is not None:
                mem.praise(cur.service)
            elif res.service in ("stop", "scold"):
                stop_tree("Mensch sagt stopp")
                arb.current = None
                requests.clear()
            req = S.to_request(res, ev.text, ev.sender, PEOPLE_PID.get(ev.sender), world.t)
            if req is not None and req.service in ("search", "push_out", "follow"):
                requests.append(req)
                chat_new = True

        # ---------------- Arbiter (1 Hz)
        obs = world.observe(requests, chat_new, tapped, last_result)
        tapped = False
        d = arb.step(obs)
        if last_result is not None:
            last_result = None
        levels = dict(arb.needs.s.levels)
        if a.needs and levels != prev_levels:
            log("   Bedürfnisse: " + ", ".join(f"{n} {LEVELS[levels[n]]}" for n in NEEDS))
        prev_levels = levels

        if d.action == "stop":
            if tree is not None:
                stop_tree(d.reason)
        elif d.action == "start":
            start(d.option, d.reason)
        elif d.action == "ask_llm":
            if brain:
                st = state_text(obs, arb.needs.s, d.menu, d.triggers)
                r = brain.decide(st, len(d.menu))
                llm_calls += 1
                world.advance(a.think_s)            # Denk-Zustand: steht, Zeit und Akku laufen
                log(f"   (denkt {a.think_s:.0f} s nach: {', '.join(o.key for o in d.menu)})")
                d2 = arb.apply_llm(d.menu, r.choice, world.t, r.reason, r.mood)
                if d2.action == "start":
                    start(d2.option, f"LLM: {r.reason}" if r.choice else "LLM ungültig, Code")
            else:
                d2 = arb.apply_llm(d.menu, None, world.t)
                if d2.action == "start":
                    start(d2.option, f"knapp, Code wählt aus {', '.join(o.key for o in d.menu)}")

        # ---------------- Baum ticken (2× je Sekunde)
        for _ in range(int(1.0 / DT)):
            if tree is None or tree.status not in (Status.RUNNING, Status.INVALID):
                world.advance(DT)
                continue
            tree.tick_once()
            if tree.status in (Status.SUCCESS, Status.FAILURE):
                ok = tree.status == Status.SUCCESS
                dur = world.t - t_start
                time_in[cur.behavior] += dur
                log(f"<- {cur.key}: {'ok' if ok else 'gescheitert'} nach {dur:.0f} s")
                if a.trees:
                    print(py_trees.display.unicode_tree(tree, show_status=True))
                last_result = (cur.behavior, "ok" if ok else "failed")
                if ok and ctx.found:            # Fund aus einer Suche gilt als gemeldet
                    mem.reported[f"{ctx.found}@{world.room}"] = world.t
                if cur.service in ("search", "push_out", "follow"):
                    for r in list(requests):
                        if r.arg == cur.arg or (cur.behavior == "report" and r.service == "search"):
                            requests.remove(r)
                    if not ok and cur.behavior == "search_item":
                        world.messages.append((world.t, f"{cur.arg} habe ich nicht gefunden."))
                        log(f"   >> Meldung: {cur.arg} habe ich nicht gefunden.")
                if cur.behavior == "greet" and ok and rng.random() < 0.5:
                    tapped = True                   # der Mensch freut sich und tippt SLARC an
                    log("   (wird angetippt)")
                tree = None
                break
        if cur is not None and cur.behavior == "rest" and arb.needs.s.levels["energie"] >= 3:
            end_reason = "zu Hause ausgeruht, Akku muss geladen werden"
            time_in["rest"] += world.t - t_start
            break
        if world.soc() <= 0.02:
            end_reason = "Akku leer"
            break

    # ---------------- Zusammenfassung
    print("\n" + "=" * 60)
    print(f"Ende nach {hms(world.t)}: {end_reason}")
    print(f"Akku {world.soc() * 100:.0f} % ({world.battery_v():.2f} V), gelaufen {world.walked_m:.0f} m, "
          f"erkundet {len(world.explored)}/{len(world.rooms)} Räume, LLM-Aufrufe {llm_calls}")
    print("Verhalten (Starts, Zeit):")
    for b, n in stats.most_common():
        print(f"  {b:18} {n:3}×  {time_in[b] / 60:5.1f} min")
    print("Meldungen an die Menschen:")
    for t, m in world.messages:
        print(f"  [{hms(t)}] {m}")
    print("Lob-Gewichte:", {k: round(v, 2) for k, v in mem.service_weights.items()} or "-")
    if brain:
        text, _, _ = S.narrate(brain, mem.diary)
        print("\nTagebuch:\n" + text)


if __name__ == "__main__":
    main()

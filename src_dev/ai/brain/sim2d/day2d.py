# brain/sim2d/day2d.py
# Version 0.2 (11.11.2026) – Simulierter Tag mit Karte: Welt2D + Blackboard + Arbiter + BT.
# V0.2: „Was ist das?“: nachgebildetes VLM, Rückfrage an den Menschen; wer zu Hause ist, antwortet
#       nach ANSWER_DELAY_S im Chat („Das ist eine Socke.“, SIM ONLY); benannte Dinge sind suchbar.
#
# Wie brain/sim/day.py, aber SLARC kennt die Wohnung anfangs nicht: Er baut mit der
# Kamera eine Belegungskarte auf, verfolgt Objekte, erkundet Grenzen zum Unbekannten
# und navigiert mit A* auf der eigenen Karte. Das Brain liest nur das Blackboard.
# Jeder Lauf wird aufgezeichnet und als HTML-Seite zum Abspielen gespeichert.
#
# Aufruf aus src_dev/ai:
#   python -m brain.sim2d.day2d                    # 3 h, ohne LLM, Viewer in brain/ergebnisse/<Datum>/
#   python -m brain.sim2d.day2d --hours 1 --html ~/slarc_tag.html
#   python -m brain.sim2d.day2d --server http://127.0.0.1:8081 --slots 4   # mit Qwen über llama-server
#   python -m brain.sim2d.day2d --model ~/.models/Qwen3.5-4B-Q4_K_M.gguf --gpu-layers -1

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from collections import Counter

import numpy as np
import py_trees
from py_trees.common import Status

from .. import semantic as S
from ..arbiter import Arbiter
from ..memory import Memory
from ..needs import LEVELS, NEEDS
from ..nav.gridmap import FREE, OCC
from ..prompt import state_text
from ..sim.day import PEOPLE_PID, hms, keyword_chat
from ..sim.world import ChatEvent
from .bt2d import DT, Ctx, build_tree
from .world2d import World2D, default_people

FRAME_S = 2.0
ANSWER_DELAY_S = 90.0          # so lange braucht ein Mensch, bis er auf eine Rückfrage antwortet (Annahme)
ARTIKEL = {"socke": "eine", "dose": "eine", "kabel": "ein", "tüte": "eine", "decke": "eine", "flasche": "eine"}
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------- Aufzeichnung
class Recorder:
    """Frames für den Viewer: Pose, Zustand, Kartendiff, geänderte Tracks, Ereignisse."""

    def __init__(self, world: World2D, meta: dict):
        self.w = world
        bb = world.bb
        self.codes = np.zeros(bb.map.w * bb.map.h, np.int16)
        self.objs: dict = {}
        self.frontiers = None
        self.log_buf: list = []
        self.frames: list = []
        self.last_t = -1e9
        plan = world.plan
        occ = world.occ.reshape(-1).astype(np.int8)
        change = np.flatnonzero(np.diff(np.concatenate([[0], occ]))).tolist()   # Lauflängen: Wechselstellen
        self.data = {
            "meta": {**meta, "blackboard": bb.version, "frame_s": FRAME_S,
                     "map": {"res": bb.map.res, "w": bb.map.w, "h": bb.map.h, "origin": [bb.map.ox, bb.map.oy]}},
            "truth": {"res": 0.05, "w": world.occ.shape[1], "h": world.occ.shape[0], "origin": list(world.origin),
                      "occ_changes": change,
                      "rooms": [{"name": r.name, "rect": r.rect, "light": r.light} for r in plan.rooms],
                      "doors": plan.doors,
                      "things": [{"oid": t.oid, "cls": t.cls, "x": t.x, "y": t.y, "rect": t.rect} for t in plan.things],
                      "home": list(plan.home)},
            "frames": self.frames,
        }

    def log(self, t: float, text: str) -> None:
        self.log_buf.append([round(t, 1), text])

    def frame(self, ctx: Ctx, arb: Arbiter, cur, force: bool = False) -> None:
        w, bb = self.w, self.w.bb
        if not force and bb.t - self.last_t < FRAME_S:
            return
        self.last_t = bb.t
        m = bb.map
        st = m.states().reshape(-1)
        codes = np.where(st == OCC, 1, np.where(st == FREE, 2 + np.maximum(m.area.reshape(-1), -1) + 1, 0)).astype(np.int16)
        idx = np.flatnonzero(codes != self.codes)
        self.codes = codes
        objs = []
        for o in bb.objects.values():
            row = [o.track_id, o.cls, round(o.x, 2), round(o.y, 2), o.state, int(o.moved), o.area or "",
                   o.name_vlm or "", int(o.name_sure), o.ident]
            if self.objs.get(o.track_id) != row:
                self.objs[o.track_id] = row
                objs.append(row)
        fr = [[f.fid, round(f.x, 2), round(f.y, 2), f.size, int(f.reachable)] for f in bb.frontiers]
        frs = fr if fr != self.frontiers else None
        self.frontiers = fr
        s = arb.needs.s
        self.frames.append({
            "t": round(bb.t, 1),
            "p": [round(bb.pose.x, 2), round(bb.pose.y, 2), round(bb.pose.theta, 2)],
            "m": bb.robot.mode, "soc": round(bb.robot.soc, 3), "v": round(bb.robot.battery_v, 2),
            "b": cur.key if cur else "", "lbl": cur.label if cur else "", "n": ctx.node if cur else "",
            "mood": bb.robot.mood,
            "nd": {k: [round(s.values[k], 2), s.levels[k]] for k in NEEDS},
            "path": [[round(x, 2), round(y, 2)] for x, y in bb.nav.path] if bb.nav.status == "unterwegs" else [],
            "goal": [round(bb.nav.goal[0], 2), round(bb.nav.goal[1], 2)] if bb.nav.goal and bb.nav.status == "unterwegs" else None,
            "map": [[int(i), int(codes[i])] for i in idx],
            "obj": objs,
            "fr": frs,
            "per": [[p.pid, p.name, round(p.x, 2), round(p.y, 2)] for p in w.persons.values() if p.room],
            "seen": [p.track_id for p in bb.persons.values() if bb.t - p.last_seen < 3.0],
            "mov": [[t.oid, round(t.x, 2), round(t.y, 2)] for t in w.things.values() if t.movable],
            "home": bb.nav.home_dist_m and round(bb.nav.home_dist_m, 1),
            "log": self.log_buf,
        })
        self.log_buf = []

    def finish(self, summary: dict, messages: list, diary: list) -> dict:
        self.data["summary"] = summary
        self.data["messages"] = [[round(t, 1), m] for t, m in messages]
        self.data["diary"] = [d.get("text", "") for d in diary][-60:]
        self.data["areas"] = list(self.w.bb.map.area_names)
        return self.data


def write_html(data: dict, path: str, standalone: bool = True) -> None:
    """Viewer mit eingebetteten Daten. standalone: eigenes HTML-Gerüst (Datei im Browser öffnen);
    sonst nur der Seiteninhalt (Gerüst kommt vom Anzeigeort)."""
    with open(os.path.join(HERE, "viewer.html"), encoding="utf-8") as f:
        tpl = f.read()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = tpl.replace("/*__SIM_DATA__*/null", payload)
    if standalone:
        page = ('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '</head>\n<body>\n' + page + '\n</body>\n</html>\n')
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def default_out() -> str:
    d = os.path.join(HERE, "..", "ergebnisse", time.strftime("%Y-%m-%d"))
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(os.path.join(d, f"sim2d_{time.strftime('%H%M')}.html"))


# ---------------------------------------------------------------------------- Tagesschleife
def run(hours: float = 3.0, seed: int = 1, soc: float = 0.9, brain=None, think_s: float = 15.0,
        trees: bool = False, needs_log: bool = False, quiet: bool = False, model_name: str = "") -> dict:
    persons, chat = default_people()
    world = World2D(soc0=soc, seed=seed, persons=persons, chat=chat)
    bb = world.bb
    mem = Memory()
    arb = Arbiter(mem, random.Random(seed))
    rng = random.Random(seed + 1)
    rec = Recorder(world, {"seed": seed, "hours": hours, "soc0": soc, "model": model_name or "ohne LLM",
                           "think_s": think_s, "created": time.strftime("%d.%m.%Y %H:%M")})

    def log(msg: str) -> None:
        rec.log(world.t, msg)
        if not quiet:
            print(f"[{hms(world.t)}] {msg}", flush=True)

    ctx = Ctx(world, log)
    ctx.vision = world.vlm_what                      # SIM ONLY; Roboter: vision/identify.py
    asked: set = set()
    places_fn = (lambda item, rooms: S.search_places(brain, item, rooms).places) if brain else None
    world.sync()
    ctx.layers.refresh(force=True)

    tree = cur = None
    t_start = 0.0
    last_result = None
    requests: list = []
    chat_i = 0
    tapped = False
    stats, time_in = Counter(), Counter()
    llm_calls = 0
    prev_levels = None
    end_reason = "Zeit abgelaufen"

    def stop_tree(reason: str) -> None:
        nonlocal tree, cur
        if tree is not None and tree.status == Status.RUNNING:
            tree.stop(Status.INVALID)
            log(f"   abgebrochen: {cur.key} ({reason})")
        tree, cur = None, None
        world.stop()

    def start(opt, why: str) -> None:
        nonlocal tree, cur, t_start
        if tree is not None and tree.status == Status.RUNNING:
            stop_tree("neues Ziel")
        ctx.found = None
        ctx.prev_point = (bb.pose.x, bb.pose.y)
        tree, cur, t_start = build_tree(opt, ctx, rng, places_fn, mem.last_seen), opt, world.t
        tree.setup_with_descendants()
        stats[opt.behavior] += 1
        bb.robot.behavior = opt.key
        log(f"-> {opt.key}   [{why}]")
        if trees:
            print(py_trees.display.unicode_tree(tree))

    def answer_questions() -> None:
        """SIM ONLY: Wer zu Hause ist, beantwortet SLARCs Rückfrage nach ANSWER_DELAY_S."""
        for tid in [q for q in ctx.questions if q not in asked]:
            home = [p for p in world.persons.values() if p.room]
            if not home:
                continue
            asked.add(tid)
            truth = min(world.things.values(), key=lambda t: math.hypot(t.x - bb.objects[tid].x, t.y - bb.objects[tid].y))
            name = truth.true_name or truth.cls
            text = "Das ist nichts, nur ein Fleck." if name == "nichts" else f"Das ist {ARTIKEL.get(name, 'ein')} {name.capitalize()}."
            world.chat.append(ChatEvent(world.t + ANSWER_DELAY_S, home[0].name, text))
            world.chat[chat_i:] = sorted(world.chat[chat_i:], key=lambda e: e.t)

    while world.t < hours * 3600:
        chat_new = False
        answer_questions()
        while chat_i < len(world.chat) and world.chat[chat_i].t <= world.t:
            ev = world.chat[chat_i]
            chat_i += 1
            named = S.naming(ev.text) if ctx.questions else None
            if named:                                     # Antwort auf „Was ist das?“
                tid = ctx.questions.pop(0)
                o = bb.objects.get(tid)
                if o is not None:
                    o.name_vlm, o.name_sure, o.name_source = named, True, "mensch"
                    o.ident = "nichts" if named == "nichts" else "sicher"
                reply = "Danke, dann vergesse ich es." if named == "nichts" else f"Danke! Jetzt weiß ich: {named.capitalize()}."
                log(f"CHAT {ev.sender}: „{ev.text}“ -> benennt {tid} als {named}  SLARC: „{reply}“")
                bb.event("benannt", f"{tid} = {named} (Mensch)")
                continue
            res = (S.interpret_chat(brain, ev.text, ev.sender, mem.diary, tuple(PEOPLE_PID)) if brain
                   else keyword_chat(ev.text))
            if brain:
                llm_calls += 1 + (1 if res.talk else 0)
            problem = S.item_problem(res, tuple(PEOPLE_PID), tuple(bb.known_names()))
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

        # ---------------- Arbiter (1 Hz), sieht nur das Blackboard
        obs = bb.to_observation(requests, chat_new, tapped, last_result)
        tapped = False
        d = arb.step(obs)
        last_result = None
        s = arb.needs.s
        bb.robot.needs = {k: round(s.values[k], 3) for k in NEEDS}
        bb.robot.levels = dict(s.levels)
        if needs_log and s.levels != prev_levels:
            log("   Bedürfnisse: " + ", ".join(f"{n} {LEVELS[s.levels[n]]}" for n in NEEDS))
        prev_levels = dict(s.levels)

        if d.action == "stop":
            if tree is not None:
                stop_tree(d.reason)
        elif d.action == "start":
            start(d.option, d.reason)
        elif d.action == "ask_llm":
            if brain:
                st = state_text(obs, arb.needs.s, d.menu, d.triggers)
                world.stop()
                bb.robot.mode = "denken"
                rec.frame(ctx, arb, cur, force=True)
                r = brain.decide(st, len(d.menu))
                llm_calls += 1
                world.advance(think_s)              # Denk-Zustand: steht, Perzeption pausiert
                world.sync()
                log(f"   (denkt {think_s:.0f} s nach: {', '.join(o.key for o in d.menu)})")
                if r.mood:
                    bb.robot.mood = r.mood
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
                ctx.step()
                continue
            tree.tick_once()
            if tree.status in (Status.SUCCESS, Status.FAILURE):
                ok = tree.status == Status.SUCCESS
                dur = world.t - t_start
                time_in[cur.behavior] += dur
                log(f"<- {cur.key}: {'ok' if ok else 'gescheitert'} nach {dur:.0f} s"
                    + ("" if ok else f" ({bb.nav.status})"))
                if trees:
                    print(py_trees.display.unicode_tree(tree, show_status=True))
                last_result = (cur.behavior, "ok" if ok else "failed")
                if ok and ctx.found and ctx.found in bb.objects:
                    mem.reported[f"{ctx.found}@{bb.objects[ctx.found].area}"] = world.t
                if cur.service in ("search", "push_out", "follow"):
                    for r in list(requests):
                        if r.arg == cur.arg or (cur.behavior == "report" and r.service == "search"):
                            requests.remove(r)
                    if not ok and cur.behavior == "search_item":
                        world.messages.append((world.t, f"{cur.arg} habe ich nicht gefunden."))
                        bb.event("meldung", f"{cur.arg} habe ich nicht gefunden.")
                        log(f"   >> Meldung: {cur.arg} habe ich nicht gefunden.")
                if cur.behavior == "greet" and ok and rng.random() < 0.5:
                    tapped = True
                    log("   (wird angetippt)")
                tree = None
                bb.robot.behavior = ""
                break
        rec.frame(ctx, arb, cur)
        if cur is not None and cur.behavior == "rest" and arb.needs.s.levels["energie"] >= 3:
            end_reason = "zu Hause ausgeruht, Akku muss geladen werden"
            time_in["rest"] += world.t - t_start
            break
        if world.soc() <= 0.02:
            end_reason = "Akku leer"
            break

    rec.frame(ctx, arb, cur, force=True)
    st = bb.map.states()
    known_m2 = float((st == FREE).sum()) * bb.map.res ** 2
    true_free = float((~world.occ).sum() - 0) * 0.05 ** 2
    summary = {
        "ende": hms(world.t), "grund": end_reason, "akku_pct": round(world.soc() * 100), "akku_v": round(bb.robot.battery_v, 2),
        "gelaufen_m": round(world.walked_m), "karte_frei_m2": round(known_m2, 1),
        "bereiche": sorted(a.name for a in bb.areas.values() if a.cells >= 30), "objekte": len(bb.objects),
        "llm": llm_calls,
        "verhalten": [[b, n, round(time_in[b] / 60, 1)] for b, n in stats.most_common()],
    }
    if not quiet:
        print("\n" + "=" * 60)
        print(f"Ende nach {summary['ende']}: {end_reason}")
        print(f"Akku {summary['akku_pct']} % ({summary['akku_v']} V), gelaufen {summary['gelaufen_m']} m, "
              f"Karte {summary['karte_frei_m2']} m² frei, Bereiche {', '.join(summary['bereiche'])}, "
              f"{len(bb.objects)} Objekte, LLM-Aufrufe {llm_calls}")
        print("Verhalten (Starts, Zeit):")
        for b, n, mins in summary["verhalten"]:
            print(f"  {b:18} {n:3}×  {mins:5.1f} min")
        print("Meldungen an die Menschen:")
        for t, m in world.messages:
            print(f"  [{hms(t)}] {m}")
    diary = mem.diary
    if brain:
        text, _, _ = S.narrate(brain, mem.diary)
        diary = mem.diary + [{"text": "Tagebuch: " + text}]
        if not quiet:
            print("\nTagebuch:\n" + text)
    return rec.finish(summary, world.messages, diary)


def main() -> None:
    ap = argparse.ArgumentParser(description="SLARC Brain: simulierter Tag mit Karte, A* und Viewer")
    ap.add_argument("--hours", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--soc", type=float, default=0.9)
    ap.add_argument("--trees", action="store_true")
    ap.add_argument("--needs", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="kein Protokoll in der Konsole")
    ap.add_argument("--model", default=None, help="GGUF direkt laden (llama-cpp-python)")
    ap.add_argument("--gpu-layers", type=int, default=0)
    ap.add_argument("--server", default=None, help="llama-server-URL statt --model")
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--think-s", type=float, default=15.0)
    ap.add_argument("--html", default=None, help="Viewer-Datei (Standard: brain/ergebnisse/<Datum>/sim2d_HHMM.html)")
    ap.add_argument("--json", default=None, help="zusätzlich die Rohdaten als JSON")
    a = ap.parse_args()
    brain, name = None, ""
    if a.server:
        from ..llm import ServerBrain
        brain = ServerBrain(a.server, n_slots=a.slots)
        name = brain.name
    elif a.model:
        from ..llm import LlamaBrain
        brain = LlamaBrain(a.model, n_gpu_layers=a.gpu_layers)
        name = os.path.basename(a.model)
    data = run(a.hours, a.seed, a.soc, brain, a.think_s, a.trees, a.needs, a.quiet, name)
    out = a.html or default_out()
    write_html(data, out)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    print(f"\nViewer: {out}  ({os.path.getsize(out) / 1e6:.1f} MB, {len(data['frames'])} Bilder)")


if __name__ == "__main__":
    main()

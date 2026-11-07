# brain/tests/test_brain.py
# Version 0.1 (07.11.2026) – Unit-Tests für Bedürfnismodell, Sicherheit,
# Menü, Arbiter, Prompt und Grammatik. Ohne Sprachmodell lauffähig.
#
# Aufruf aus src_dev/ai:  python -m pytest brain/tests -q
# Grammatik-Test mit dem echten llama.cpp-Parser: Umgebungsvariable
# SLARC_VOCAB_GGUF auf eine GGUF-Datei setzen (z. B. das Modell selbst oder
# models/ggml-vocab-qwen2.gguf aus dem llama.cpp-Repo), sonst übersprungen.

from __future__ import annotations

import json
import math
import os
import random

import pytest

from brain.arbiter import Arbiter, LLM_MIN_INTERVAL_S
from brain.behaviors import MENU_MAX, MOODS, build_options, close_options, matches, select_fallback
from brain.datatypes import ObjectSeen, Observation, Option, Person, Request
from brain.llm import MockBrain, parse
from brain.memory import Memory
from brain.needs import LEVEL_EDGES, NeedsModel, level_index, soc_from_voltage
from brain.prompt import FEW_SHOT, grammar, messages, state_text
from brain.safety import check
from brain.scenarios import SCENARIOS, prepare

T = 50_000.0


def obs(**kw) -> Observation:
    base = dict(t=T, battery_v=12.0, home_dist_m=5.0, at_home=False, place="flur")
    base.update(kw)
    return Observation(**base)


# ---------------------------------------------------------------- Stufen
def test_level_hysteresis_no_flicker():
    lvl = None
    seq = []
    # Wert zittert um die Grenze 0,4 herum
    for v in [0.30, 0.41, 0.39, 0.42, 0.38, 0.41, 0.46, 0.44, 0.36, 0.34]:
        lvl = level_index(v, lvl)
        seq.append(lvl)
    assert seq == [1, 1, 1, 1, 1, 1, 2, 2, 2, 1]


def test_level_multi_step_jump():
    assert level_index(0.9, 0) == 4
    assert level_index(0.62, 0) == 2      # 0,62 überschreitet 0,6 nicht um HYST
    assert level_index(0.05, 4) == 0
    assert len(LEVEL_EDGES) == 4


# ---------------------------------------------------------------- Energie
def test_soc_curve_monotonic():
    vs = [9.6 + 0.05 * i for i in range(60)]
    socs = [soc_from_voltage(v) for v in vs]
    assert all(b >= a for a, b in zip(socs, socs[1:]))
    assert soc_from_voltage(9.9) < 1e-9 and soc_from_voltage(12.6) == 1.0


def test_energy_depends_on_way_home():
    near = NeedsModel(Memory()).update(obs(battery_v=11.0, home_dist_m=5.0))[0].values["energie"]
    far = NeedsModel(Memory()).update(obs(battery_v=11.0, home_dist_m=60.0))[0].values["energie"]
    assert far > near + 0.3


def test_energy_at_home_full_is_calm():
    s, _ = NeedsModel(Memory()).update(obs(battery_v=12.4, at_home=True, home_dist_m=0.0))
    assert s.level_name("energie") == "ruhig"


def test_energy_urgent_returns_home_without_llm():
    arb = Arbiter(Memory(), random.Random(1))
    d = arb.step(obs(battery_v=10.55, home_dist_m=40.0, chat_new=True))
    assert d.action == "start" and d.option.behavior == "return_home"


# ---------------------------------------------------------------- Neugier
def test_curiosity_habituates_after_inspect():
    mem = Memory()
    nm = NeedsModel(mem)
    o = obs(objects=[ObjectSeen("o1", "tasche", "flur", 1.0)])
    v0 = nm.update(o)[0].values["neugier"]
    mem.habituate("obj:o1", T, 0.6)
    nm.note_new_info(T)
    v1 = nm.update(obs(t=T + 1, objects=o.objects))[0].values["neugier"]
    assert v1 < v0 - 0.2


def test_boredom_grows_without_news():
    nm = NeedsModel(Memory())
    nm.update(obs(t=T))
    v = nm.update(obs(t=T + 1200))[0].values["neugier"]
    assert v > 0.4


# ---------------------------------------------------------------- Gesellschaft
def test_social_rises_alone_and_drops_with_person():
    nm = NeedsModel(Memory())
    nm.update(obs(t=T))
    alone = nm.update(obs(t=T + 3600))[0].values["gesellschaft"]
    assert alone > 0.9
    p = [Person("p1", "Marco", 1.0)]
    for k in range(1, 181):          # 3 min mit Marco
        val = nm.update(obs(t=T + 3600 + k, persons=p))[0].values["gesellschaft"]
    assert val < 0.3


# ---------------------------------------------------------------- Unbehagen
def test_discomfort_jumps_and_decays():
    nm = NeedsModel(Memory())
    hi = nm.update(obs(t=T, slipped=True))[0].values["unbehagen"]
    lo = nm.update(obs(t=T + 120))[0].values["unbehagen"]
    assert hi >= 0.7 and lo < 0.05


# ---------------------------------------------------------------- Sicherheit
def test_safety_lifted_stops():
    arb = Arbiter(Memory())
    d = arb.step(obs(lifted=True))
    assert d.action == "stop"


def test_safety_battery_warn_only_home():
    o = obs(battery_v=10.4, objects=[ObjectSeen("o1", "ball", "flur", 1.0)], frontier=["küche"])
    mem = Memory()
    s, _ = NeedsModel(mem).update(o)
    menu = build_options(o, s, mem, check(o))
    moving = {"explore_frontier", "inspect_object", "search_item", "greet", "follow", "push_out"}
    assert not moving & {m.behavior for m in menu}
    assert "return_home" in {m.behavior for m in menu}


def test_safety_stair_edge_blocks_exploring():
    o = obs(stair_edge_near=True, frontier=["keller"])
    mem = Memory()
    s, _ = NeedsModel(mem).update(o)
    assert "explore_frontier" not in {m.behavior for m in build_options(o, s, mem, check(o))}


# ---------------------------------------------------------------- Menü und Auswahl
def test_menu_size_and_request_present():
    o = obs(objects=[ObjectSeen(f"o{i}", "ding", "flur", 1.0 + i) for i in range(6)],
            frontier=["a", "b", "c"], persons=[Person("p1", "Marco", 1.5)],
            requests=[Request("r1", "such den Schlüssel", "search", "schlüssel", "Marco", T - 60)])
    mem = Memory()
    s, _ = NeedsModel(mem).update(o)
    menu = build_options(o, s, mem, check(o))
    assert len(menu) <= MENU_MAX
    assert "search_item" in {m.behavior for m in menu}


def test_fallback_varies_between_equal_options():
    menu = [Option("a", None, "A", 0.5), Option("b", None, "B", 0.5), Option("c", None, "C", 0.1)]
    rng = random.Random(3)
    picks = [select_fallback(menu, rng).behavior for _ in range(1000)]
    # gleichwertige Optionen beide oft, die klar schlechtere nur selten (~1 %)
    assert picks.count("a") > 400 and picks.count("b") > 400 and picks.count("c") < 40


def test_praise_raises_weight():
    mem = Memory()
    arb = Arbiter(mem, random.Random(0))
    arb.current = Option("greet", "p1", "Marco begrüßen", 0.5, "greet")
    arb.step(obs(tapped=True))
    assert mem.weight("greet") > 1.0


def _close_obs(t, oid):
    # zwei fast gleich interessante neue Objekte -> knapper Fall
    return obs(t=t, objects=[ObjectSeen(oid + "a", "tasche", "flur", 1.0),
                             ObjectSeen(oid + "b", "karton", "flur", 1.0)])


def test_llm_only_for_close_cases_and_cooldown():
    arb = Arbiter(Memory(), random.Random(0))
    d1 = arb.step(_close_obs(T, "o1"))
    assert d1.action == "ask_llm" and 2 <= len(d1.menu) <= 3
    d2 = arb.step(_close_obs(T + 10, "o2"))
    assert d2.action != "ask_llm"                     # Abkühlzeit
    d3 = arb.step(_close_obs(T + 10 + LLM_MIN_INTERVAL_S, "o3"))
    assert d3.action == "ask_llm"


def test_clear_chat_request_decided_by_code():
    arb = Arbiter(Memory(), random.Random(0))
    arb.step(_close_obs(T, "o1"))                     # LLM gerade benutzt
    d = arb.step(obs(t=T + 20, chat_new=True, persons=[Person("p1", "Marco", 1.5)],
                     requests=[Request("r", "komm her", "follow", "p1", "Marco", T + 19)]))
    assert d.action == "start" and d.option.behavior == "follow"


def test_energy_high_is_rule():
    arb = Arbiter(Memory(), random.Random(0))
    d = arb.step(obs(battery_v=11.0, home_dist_m=60.0, chat_new=True,
                     requests=[Request("r", "such die Fernbedienung", "search", "fernbedienung", "Marco", T - 60)]))
    assert d.action == "start" and d.option.behavior == "return_home"


def test_request_matches_object_in_view():
    o = obs(objects=[ObjectSeen("o6", "handy", "wohnzimmer", 1.0)],
            requests=[Request("r", "hast du mein Smartphone gesehen?", "search", "smartphone", "Marco", T - 300)])
    mem = Memory()
    s, _ = NeedsModel(mem).update(o)
    menu = build_options(o, s, mem, check(o))
    assert menu[0].behavior == "report" and menu[0].arg == "o6" and "Bitte" in menu[0].label


def test_matches():
    assert matches("handy", "Smartphone") and matches("fernbedienung", "die Fernbedienung")
    assert matches("teddy", "Kuscheltier") and not matches("tasse", "handy")
    assert not matches("ei", "eimer")


def test_close_options():
    menu = [Option("a", None, "A", 0.8), Option("b", None, "B", 0.7), Option("c", None, "C", 0.4)]
    assert [o.behavior for o in close_options(menu)] == ["a", "b"]


def test_apply_llm_invalid_falls_back():
    arb = Arbiter(Memory(), random.Random(0))
    menu = [Option("look_around", None, "Sich umsehen", 0.4)]
    arb.step(obs())
    d = arb.apply_llm(menu, None, T)
    assert d.action == "start" and d.option.behavior == "look_around"


# ---------------------------------------------------------------- Gedächtnis
def test_memory_roundtrip(tmp_path):
    mem = Memory()
    mem.habituate("obj:x", T, 0.5)
    mem.praise("search")
    mem.log(T, "test", "Hallo")
    p = tmp_path / "mem.json"
    mem.save(str(p))
    m2 = Memory.load(str(p))
    assert math.isclose(m2.habituation("obj:x", T), mem.habituation("obj:x", T))
    assert m2.weight("search") == mem.weight("search") and m2.diary[0]["text"] == "Hallo"


# ---------------------------------------------------------------- Prompt und Antwort
def test_few_shot_answers_are_valid():
    for user, answer in FEW_SHOT:
        n = sum(1 for line in user.split("MÖGLICHE ZIELE\n")[1].splitlines() if line.strip())
        z, reason, mood, err = parse(answer, n)
        assert err == "" and z is not None and mood in MOODS and reason


def test_parse_rejects_bad_answers():
    assert parse('{"ziel": 9, "begruendung": "x", "stimmung": "ruhig"}', 3)[3]
    assert parse("kein json", 3)[3]
    assert parse('{"ziel": "1"}', 3)[3]


def test_state_text_lists_menu():
    sc = SCENARIOS[0]
    mem, nm, s = prepare(sc)
    menu = build_options(sc.obs, s, mem, check(sc.obs))
    txt = state_text(sc.obs, s, menu, sc.triggers)
    assert txt.splitlines()[-len(menu):] == [f"{i} {o.label}" for i, o in enumerate(menu, 1)]
    assert "Wunsch nach Gesellschaft" in txt
    assert messages(txt)[0]["role"] == "system" and len(messages(txt)) == 2 + 2 * len(FEW_SHOT)


# ---------------------------------------------------------------- Szenarien
@pytest.mark.parametrize("sc", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_scenario_expected_is_in_menu(sc):
    mem, nm, s = prepare(sc)
    menu = build_options(sc.obs, s, mem, check(sc.obs))
    assert sc.expected & {o.behavior for o in menu}, [o.key for o in menu]


def test_mock_chain_runs():
    b = MockBrain()
    for sc in SCENARIOS:
        mem, nm, s = prepare(sc)
        menu = build_options(sc.obs, s, mem, check(sc.obs))
        r = b.decide(state_text(sc.obs, s, menu, sc.triggers), len(menu))
        assert r.choice is not None and 1 <= r.choice <= len(menu)


# ---------------------------------------------------------------- Grammatik (llama.cpp)
def _vocab():
    path = os.environ.get("SLARC_VOCAB_GGUF")
    if not path or not os.path.exists(path):
        pytest.skip("SLARC_VOCAB_GGUF nicht gesetzt")
    L = pytest.importorskip("llama_cpp")
    p = L.llama_model_default_params()
    p.vocab_only = True
    m = L.llama_model_load_from_file(path.encode(), p)
    assert m
    return L, m, L.llama_model_get_vocab(m)


def _accepts(L, vocab, gbnf: str, text: str) -> bool:
    """Prüft Token für Token, ob die Grammatik den Text zulässt."""
    smpl = L.llama_sampler_init_grammar(vocab, gbnf.encode(), b"root")
    assert smpl, "Grammatik lässt sich nicht parsen"
    buf = (L.llama_token * 512)()
    n = L.llama_tokenize(vocab, text.encode(), len(text.encode()), buf, 512, False, True)
    assert n > 0
    for i in range(n):
        data = (L.llama_token_data * 1)(L.llama_token_data(buf[i], 0.0, 0.0))
        arr = L.llama_token_data_array(data, 1, -1, False)
        L.llama_sampler_apply(smpl, L.ctypes.byref(arr))
        if data[0].logit == -math.inf:
            L.llama_sampler_free(smpl)
            return False
        L.llama_sampler_accept(smpl, buf[i])
    L.llama_sampler_free(smpl)
    return True


def test_grammar_parses_and_accepts_examples():
    L, m, vocab = _vocab()
    for user, answer in FEW_SHOT:
        n = sum(1 for line in user.split("MÖGLICHE ZIELE\n")[1].splitlines() if line.strip())
        assert _accepts(L, vocab, grammar(n), answer), answer
    # ungültige Nummer und erfundene Stimmung werden abgelehnt
    assert not _accepts(L, vocab, grammar(3), '{"begruendung": "x", "ziel": 5')
    assert not _accepts(L, vocab, grammar(3), '{"begruendung": "x", "ziel": 1, "stimmung": "wütend"')
    assert json.loads(FEW_SHOT[0][1])


def test_hazard_reported_by_rule_even_when_tired(monkeypatch):
    # Die Detektion V5.0 kennt keine Gefahren; Mechanismus mit einer Testklasse prüfen
    import brain.behaviors as B
    monkeypatch.setattr(B, "HAZARDS", {"herd_an"})
    arb = Arbiter(Memory(), random.Random(0))
    d = arb.step(obs(battery_v=11.0, home_dist_m=60.0,
                     objects=[ObjectSeen("h1", "herd_an", "küche", 3.0)]))
    assert d.action == "start" and d.option.service == "hazard" and d.option.arg == "h1"


def _opts(o, mem, ago_contact=3600):
    nm = NeedsModel(mem)
    nm.s.t_last, nm.s.t_new_info, nm.s.t_useful, nm.s.t_contact = o.t - 1, o.t - 60, o.t - 60, o.t - ago_contact
    s, _ = nm.update(o)
    return {x.behavior: x for x in build_options(o, s, mem, check(o))}


def test_seek_company_when_alone_and_not_twice():
    mem = Memory()
    o = obs(place="flur", known_places=["flur", "wohnzimmer", "küche"])
    opts = _opts(o, mem)
    assert opts["seek_company"].arg == "wohnzimmer"           # meist Menschen dort
    mem.seek_checked["wohnzimmer"] = T - 60                     # eben niemand gewesen
    assert _opts(o, Memory.from_dict(mem.to_dict()))["seek_company"].arg == "küche"
    mem.last_seen["person"] = ["küche", T - 30]
    mem.seek_checked["küche"] = T - 10
    assert "seek_company" not in _opts(o, mem)


def test_doze_saturates():
    mem = Memory()
    o = obs(place="flur")
    fresh = _opts(o, mem, ago_contact=60)["doze"].utility
    mem.doze_log.append([T - 40 * 60, T - 5 * 60])              # 35 min gedöst
    assert _opts(o, mem, ago_contact=60)["doze"].utility < 0.3 * fresh

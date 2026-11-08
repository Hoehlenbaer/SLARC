# brain/tests/test_semantic.py
# Version 0.2 (08.11.2026) – Tests für semantic.py ohne Sprachmodell.
# V0.2: ehrliche Bestätigungen (Vorlagen), claims_result, check/Personen in item_problem.
# Grammatik-Prüfung wie in test_brain.py über SLARC_VOCAB_GGUF.

from __future__ import annotations

import json

import pytest

from brain import semantic as S
from brain.llm import MockBrain
from brain.open_scenarios import CHAT_CASES, OBJECT_CASES, SEARCH_CASES
from brain.run_open_suite import mock_responder
from brain.tests.test_brain import _accepts, _vocab

PLACES = ["flur", "küche", "bad"]


def fixed(raw):
    return MockBrain(responder=lambda m, g: raw)


def test_chat_parses_and_maps_to_request():
    b = fixed('{"dienst": "search", "gegenstand": "Handy", "antwort": "Ich schaue nach."}')
    r = S.interpret_chat(b, "Wo ist mein Handy?")
    assert r.service == "search" and r.item == "handy" and r.reply
    req = S.to_request(r, "Wo ist mein Handy?", "Marco", "p-marco", 100.0)
    assert req.service == "search" and req.arg == "handy" and req.from_person == "Marco"


def test_chat_follow_targets_sender():
    r = S.interpret_chat(fixed('{"dienst": "come", "gegenstand": "", "antwort": "Komme!"}'), "Komm her")
    req = S.to_request(r, "Komm her", "Marco", "p-marco", 1.0)
    assert req.service == "follow" and req.arg == "p-marco"


def test_chat_praise_is_no_request():
    r = S.interpret_chat(fixed('{"dienst": "praise", "gegenstand": "", "antwort": "Danke!"}'), "Toll")
    assert S.to_request(r, "Toll", "Marco", None, 1.0) is None


def test_chat_invalid_service_flagged():
    r = S.interpret_chat(fixed('{"dienst": "tanzen", "gegenstand": "", "antwort": "x"}'), "Tanz!")
    assert r.service is None and r.error


def test_object_and_search_parse():
    a = S.assess_object(fixed('{"grund": "x", "interesse": "hoch", "melden": "ja"}'), "herd_an", "küche")
    assert a.interest == "hoch" and a.report is True
    p = S.search_places(fixed('{"grund": "x", "orte": ["küche", "küche", "bad"]}'), "dose", PLACES)
    assert p.places == ["küche", "bad"]


def test_mock_chain_all_cases():
    b = MockBrain(responder=mock_responder)
    assert all(S.interpret_chat(b, c.text).service for c in CHAT_CASES)
    assert all(S.assess_object(b, c.cls, c.place).interest for c in OBJECT_CASES)
    assert all(S.search_places(b, c.item, c.places).places for c in SEARCH_CASES)
    assert S.narrate(b, [{"kind": "x", "text": "y"}])[0] == "Mock."


def test_few_shots_are_json():
    for shots in (S.CHAT_SHOTS, S.OBJECT_SHOTS, S.SEARCH_SHOTS):
        for _, a in shots:
            json.loads(a)


def test_semantic_grammars_with_llama_cpp():
    L, m, vocab = _vocab()
    for _, a in S.CHAT_SHOTS:
        assert _accepts(L, vocab, S.CHAT_GBNF, a)
    for _, a in S.OBJECT_SHOTS:
        assert _accepts(L, vocab, S.OBJECT_GBNF, a)
    places = ["flur", "küche", "bad", "wohnzimmer"]
    for _, a in S.SEARCH_SHOTS:
        assert _accepts(L, vocab, S.search_gbnf(places), a)
    assert _accepts(L, vocab, S.NARRATE_GBNF, '{"text": "Heute war ich neugierig."}')
    for _, a in S.TALK_SHOTS:
        assert _accepts(L, vocab, S.TALK_GBNF, a)
    assert not _accepts(L, vocab, S.CHAT_GBNF, '{"dienst": "tanzen"')
    assert not _accepts(L, vocab, S.search_gbnf(places), '{"grund": "x", "orte": ["keller"')


def test_rule_assessment_skips_llm():
    calls = []
    b = MockBrain(responder=lambda m, g: calls.append(1) or '{"grund": "x", "interesse": "niedrig", "melden": "nein"}')
    assert S.assess_object(b, "handy", "flur").report is True       # meldenswert (Regel)
    assert S.assess_object(b, "stuhl", "küche").report is False     # Möbel (Regel)
    assert not calls                                   # beides ohne LLM
    r = S.assess_object(b, "handy", "flur", use_rules=False)
    assert calls and r.source == "llm"


def test_chat_two_stage_diary_only_for_smalltalk():
    calls = []
    def resp(msgs, g):
        task = msgs[0]["content"].split("\n", 1)[0]
        calls.append((task, msgs[-1]["content"]))
        if task == "AUFGABE: chat":
            svc = "smalltalk" if "erlebt" in msgs[-1]["content"] else "search"
            return '{"dienst": "%s", "gegenstand": "", "antwort": "Ok."}' % svc
        return '{"antwort": "Ich habe eine Tasche untersucht."}'
    b = MockBrain(responder=resp)
    diary = [{"kind": "entscheidung", "text": "Tasche untersucht"}]
    r = S.interpret_chat(b, "Suche nach Laura!", diary=diary)
    assert r.service == "search" and not r.talk and len(calls) == 1
    assert "ERLEBT" not in calls[0][1]                      # Stufe 1 ohne Tagebuch
    calls.clear()
    r = S.interpret_chat(b, "Was hast du erlebt?", diary=diary)
    assert r.talk and r.reply.startswith("Ich habe") and len(calls) == 2
    assert calls[1][1].startswith("ERLEBT: Tasche untersucht")
    calls.clear()
    S.interpret_chat(b, "Was hast du erlebt?")
    assert calls[1][1].startswith("ERLEBT: noch nichts")


def test_item_problem_for_undetectable():
    r = S.ChatResult("search", "schlüssel")
    assert "nicht erkennen" in S.item_problem(r)
    assert S.item_problem(S.ChatResult("search", "smartphone")) is None
    req = S.to_request(S.ChatResult("search", "smartphone"), "Wo ist mein Smartphone?", "Marco", None, 1.0)
    assert req.arg == "handy"


def test_outdoor_classes_are_detectable():
    from brain.perception_classes import normalize_item
    assert normalize_item("mein Fahrrad") == "fahrrad"
    assert normalize_item("Parkbank") == "bank" and normalize_item("Baum") == "topfpflanze"
    assert S.item_problem(S.ChatResult("search", "fahrrad")) is None
    assert "fahrrad" in S.CHAT_SYSTEM


def test_confirmation_replaces_claimed_result():
    b = fixed('{"dienst": "check", "gegenstand": "staubsauger", "antwort": "Ja, der Staubsauger steht im Wohnzimmer."}')
    r = S.interpret_chat(b, "Steht der Staubsauger im Wohnzimmer?")
    assert S.claims_result(r.llm_reply) and not S.claims_result(r.reply)
    assert "nicht erkennen" in r.reply
    b = fixed('{"dienst": "search", "gegenstand": "katze", "antwort": "Ich habe die Katze gefunden."}')
    r = S.interpret_chat(b, "Such die Katze")
    assert r.reply == "Ich suche nach der Katze und sage dir Bescheid."
    b = fixed('{"dienst": "smalltalk", "gegenstand": "", "antwort": "Gut, danke!"}')
    assert S.interpret_chat(MockBrain(responder=lambda m, g: '{"antwort": "Gut, danke!"}'
                                      if "plaudern" in m[0]["content"] else
                                      '{"dienst": "smalltalk", "gegenstand": "", "antwort": "x"}'),
                            "Wie geht's?").reply == "Gut, danke!"


def test_check_rooms_and_persons():
    assert S.item_problem(S.ChatResult("check", "zimmer")) is None
    assert S.item_problem(S.ChatResult("check", "licht"))
    assert S.item_problem(S.ChatResult("search", "laura"))
    assert S.item_problem(S.ChatResult("search", "laura"), ("Marco", "Laura")) is None
    assert S.confirmation(S.ChatResult("search", "laura")) == "Ich suche nach Laura und sage dir Bescheid."
    assert S.confirmation(S.ChatResult("push_out", "bett")) == "Ich schaue nach, was unter dem Bett liegt."
    assert S.confirmation(S.ChatResult("fetch", "flasche")) == "Ich versuche, die Flasche zu holen."


def test_claims_result_heuristic():
    for t in ("Ja, das Licht im Schlafzimmer ist an.", "Nein, nicht zu sehen.", "Ich habe es gefunden."):
        assert S.claims_result(t), t
    for t in ("Ich schaue, ob das Licht an ist.", "Ich suche jetzt nach deiner Tasse.",
              "Ich werde das Wohnzimmer im Auge behalten.", ""):
        assert not S.claims_result(t), t


def test_every_template_is_honest():
    from brain.perception_classes import DETECTABLE
    for svc in ("search", "check", "fetch", "push_out", "follow", "come"):
        for item in DETECTABLE + ["", "laura"]:
            assert not S.claims_result(S.confirmation(S.ChatResult(svc, item))), (svc, item)
    assert set(S.GENUS) == set(DETECTABLE)

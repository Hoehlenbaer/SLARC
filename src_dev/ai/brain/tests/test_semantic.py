# brain/tests/test_semantic.py
# Version 0.1 (07.11.2026) – Tests für semantic.py ohne Sprachmodell.
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
    assert not _accepts(L, vocab, S.CHAT_GBNF, '{"dienst": "tanzen"')
    assert not _accepts(L, vocab, S.search_gbnf(places), '{"grund": "x", "orte": ["keller"')
